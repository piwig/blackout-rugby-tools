"""Private observations and manual scenarios; no Classic requests or predictions."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from itertools import groupby
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Path, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import ATTACKS, SKILLS, ZONES, attack_summary, number
from .storage import now, pack

Identifier = Annotated[str, Field(pattern=r'^[0-9]{1,15}$')]
LocalId = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')]
SkillName = Literal['stamina', 'handling', 'attack', 'defense', 'technique', 'strength', 'jumping', 'speed', 'agility', 'kicking']
Money = Annotated[float, Field(ge=0, le=1_000_000_000_000, allow_inf_nan=False, strict=True)]
Capacity = Annotated[int, Field(ge=0, le=1_000_000, strict=True)]
CATEGORIES = ('standing', 'uncovered', 'covered', 'members', 'corporate')


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Goal(Model):
    player_id: Identifier
    text: str = Field(min_length=1, max_length=1000)
    skill: SkillName | None = None
    target: Annotated[float, Field(ge=0, le=21, allow_inf_nan=False, strict=True)] | None = None
    due_season: Annotated[int, Field(ge=1, le=999, strict=True)] | None = None

    @model_validator(mode='after')
    def target_needs_skill(self):
        if not self.text.strip() or (self.target is not None and not self.skill):
            raise ValueError('Objectif et compétence cible à renseigner.')
        return self


class Session(Model):
    id: LocalId
    season: int = Field(ge=1, le=999, strict=True)
    week: int = Field(ge=1, le=16, strict=True)
    slot: int = Field(ge=1, le=4, strict=True)
    skill: SkillName
    performed_at: AwareDatetime
    note: str = Field(default='', max_length=1000)

    @field_validator('performed_at')
    @classmethod
    def past_observation(cls, value):
        if value > datetime.now(timezone.utc):
            raise ValueError('Une séance réalisée doit être datée dans le passé.')
        return value


class MatchLink(Model):
    match_id: Identifier
    match_type: Literal[0, 1, 2]
    club_side: Literal['home', 'away']
    opponent: str = Field(min_length=1, max_length=150)
    season: int | None = Field(default=None, ge=1, le=999, strict=True)

    @field_validator('match_type', mode='before')
    @classmethod
    def competition_integer(cls, value):
        if type(value) is not int:
            raise ValueError('Type de rencontre entier requis.')
        return value

    @field_validator('opponent')
    @classmethod
    def opponent_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Nom d’adversaire requis.')
        return value


class Seats(Model):
    standing: Capacity | None = None
    uncovered: Capacity | None = None
    covered: Capacity | None = None
    members: Capacity | None = None
    corporate: Capacity | None = None


class Costs(Model):
    standing: Money | None = None
    uncovered: Money | None = None
    covered: Money | None = None
    members: Money | None = None
    corporate: Money | None = None


class StadiumScenario(Model):
    id: LocalId
    name: str = Field(min_length=1, max_length=100)
    current: Seats
    target: Seats
    unit_costs: Costs
    treasury: Money | None = None
    reserve: Money | None = None
    note: str = Field(default='', max_length=1000)

    @field_validator('name')
    @classmethod
    def scenario_name(cls, value):
        if not value.strip():
            raise ValueError('Nom du scénario requis.')
        return value.strip()


class Document(Model):
    version: Literal[1] = 1
    goals: list[Goal] = Field(default_factory=list, max_length=300)
    sessions: list[Session] = Field(default_factory=list, max_length=1000)
    match_links: list[MatchLink] = Field(default_factory=list, max_length=500)
    stadium_scenarios: list[StadiumScenario] = Field(default_factory=list, max_length=40)

    @model_validator(mode='after')
    def unique_references(self):
        groups = ([g.player_id for g in self.goals], [s.id for s in self.sessions],
                  [(s.season, s.week, s.slot) for s in self.sessions],
                  [(m.match_type, m.match_id) for m in self.match_links],
                  [s.id for s in self.stadium_scenarios])
        if any(len(values) != len(set(values)) for values in groups):
            raise ValueError('Références en double dans le document.')
        return self


class Save(Model):
    expected_revision: int = Field(ge=0, le=2_147_483_647, strict=True)
    document: Document


def read_document(store, team_id):
    return store.get('insights:' + team_id, {**Document().model_dump(), 'revision': 0, 'updated_at': None})


def export_insights(store):
    """Only the module's validated, public-to-manager documents; never other kv."""
    with store.db() as db:
        return {r['key'].split(':', 1)[1]: json.loads(r['value'])
                for r in db.execute("SELECT key,value FROM kv WHERE key LIKE 'insights:%' ORDER BY key")}


def academy_report(store, team_id, state, document):
    with store.db() as db:
        total = db.execute('SELECT COUNT(*) FROM snapshots WHERE team_id=? AND youth=1', (team_id,)).fetchone()[0]
        rows = [dict(r) for r in db.execute('SELECT id,observed_at,source,payload FROM snapshots WHERE team_id=? AND youth=1 ORDER BY id DESC LIMIT 240', (team_id,))]
    dated, undated = [], 0
    for row in rows:
        try:
            stamp = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
            # Legacy imports may provide only a date; keep that original precision in output.
            row['_stamp'] = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
            dated.append(row)
        except (ValueError, TypeError, AttributeError):
            undated += 1
    dated.sort(key=lambda row: (row['_stamp'], row['id']))
    previous, timeline = {}, []
    for _, same_time in groupby(dated, key=lambda row: row['_stamp']):
        observations, current = {}, {}
        for row in same_time:
            for player in json.loads(row['payload']):
                observations.setdefault(str(player.get('id', '')), []).append((player, row))
        for pid, entries in sorted(observations.items()):
            name = min(str(player.get('name') or pid) for player, _ in entries)
            observed_at = min(row['observed_at'] for _, row in entries)
            source = ' · '.join(sorted({row['source'] for _, row in entries}))
            for skill in SKILLS:
                values = sorted({number(player.get(skill)) for player, _ in entries},
                                key=lambda value: (value is not None, value or 0))
                conflicting = len(values) > 1
                after = values[-1]
                # A timestamp is one observation batch. Never emit a change before
                # all values for this player/skill at this instant are reconciled.
                current[(pid, skill)] = (after, conflicting)
                old = previous.get((pid, skill))
                if conflicting:
                    before, delta, kind = values[0], None, 'conflicting_observation'
                else:
                    if old is None or old[1] or after is None or old[0] == after:
                        continue
                    before = old[0]
                    delta = None if before is None else round(after - before, 4)
                    kind = 'revealed' if before is None else 'numeric_change'
                timeline.append({'player_id': pid, 'name': name, 'skill': skill,
                                 'before': before, 'after': after, 'delta': delta, 'kind': kind,
                                 'observed_at': observed_at, 'source': source,
                                 **({'values': values} if conflicting else {})})
        previous = current
    generations = {}
    goals = {goal['player_id']: goal for goal in document['goals']}
    for player in state.get('academy', []):
        projection = player.get('wc_projection')
        key = str(projection) if projection else 'unknown'
        goal = goals.get(str(player['id']))
        current_value = number(player.get(goal['skill'])) if goal and goal.get('skill') else None
        generations.setdefault(key, []).append({'id': str(player['id']), 'name': player.get('name', ''),
                                               'age': player.get('age'), 'goal': goal,
                                               'current_value': current_value,
                                               'target_gap': round(goal['target'] - current_value, 4) if goal and goal.get('target') is not None and current_value is not None else None})
    planned = {}
    for season, grid in state.get('plans', {}).items():
        for slot, row in enumerate(grid, 1):
            for week, skill in enumerate(row, 1):
                if skill:
                    planned[(int(season), week, slot)] = skill
    sessions, recorded = [], set()
    for session in document['sessions']:
        key = (session['season'], session['week'], session['slot'])
        recorded.add(key)
        planned_skill = planned.get(key)
        sessions.append({**session, 'provenance': 'manual', 'planned_skill': planned_skill,
                         'comparison': 'unplanned' if not planned_skill else 'matches_plan' if planned_skill == session['skill'] else 'differs_from_plan'})
    return {'generations': generations, 'timeline': timeline[-500:], 'snapshot_count': len(dated),
            'history_truncated': total > 240 or len(timeline) > 500, 'undated_snapshots': undated,
            'sessions': sessions, 'planned_count': len(planned), 'unrecorded_count': len(set(planned) - recorded),
            'latest_training_observation': state.get('training', []),
            'stale_goal_ids': [pid for pid in goals if pid not in {str(p['id']) for p in state.get('academy', [])}]}


def opponent_report(store, document, opponent=None, season=None, match_type=None, club_side=None):
    links = document['match_links']
    selected = [m for m in links if (not opponent or m['opponent'].casefold() == opponent.casefold())
                and (season is None or m['season'] == season) and (match_type is None or m['match_type'] == match_type)
                and (club_side is None or m['club_side'] == club_side)]
    result = {'match_count': 0, 'total_events': 0, 'classified': 0, 'inferred': 0, 'opponent_actions': 0,
              'attacks': dict.fromkeys(ATTACKS, 0), 'zones': dict.fromkeys(ZONES, 0), 'matches': [], 'missing_matches': 0}
    with store.db() as db:
        total = db.execute('SELECT COUNT(*) FROM matches').fetchone()[0]
        linked_exists = sum(bool(db.execute('SELECT 1 FROM matches WHERE id=? AND type=?', (m['match_id'], m['match_type'])).fetchone()) for m in links)
        for link in selected:
            row = db.execute('SELECT payload FROM matches WHERE id=? AND type=?', (link['match_id'], link['match_type'])).fetchone()
            if not row:
                result['missing_matches'] += 1
                continue
            match = json.loads(row['payload'])
            summary = attack_summary(match.get('events', []))
            side = summary['away' if link['club_side'] == 'home' else 'home']
            result['match_count'] += 1
            for key in ('total_events', 'classified', 'inferred'):
                result[key] += summary[key]
            result['opponent_actions'] += side['total']
            for attack in ATTACKS:
                result['attacks'][attack] += side['attacks'][attack]
            for zone in ZONES:
                result['zones'][zone] += sum(side['zones'][zone].values())
            result['matches'].append({**link, 'home': match.get('home'), 'away': match.get('away'),
                                      'total_events': summary['total_events'], 'classified': summary['classified'],
                                      'opponent_actions': side['total']})
    result['coverage_pct'] = round(100 * result['classified'] / result['total_events'], 1) if result['total_events'] else None
    result['unlinked_count'] = total - linked_exists
    return result


def stadium_report(scenario):
    costs, missing, reductions = [], [], []
    for key in CATEGORIES:
        current, target, price = scenario['current'][key], scenario['target'][key], scenario['unit_costs'][key]
        if current is None or target is None:
            missing.append(key)
            continue
        if target < current:
            reductions.append(key)
        addition = max(0, target - current)
        if addition and price is None:
            missing.append(key)
        else:
            costs.append(Decimal(addition) * Decimal(str(price or 0)))
    subtotal = sum(costs, Decimal(0))
    cost = None if missing else subtotal
    available = None
    if cost is not None and scenario['treasury'] is not None and scenario['reserve'] is not None:
        available = Decimal(str(scenario['treasury'])) - Decimal(str(scenario['reserve'])) - cost
    return {'id': scenario['id'], 'name': scenario['name'], 'construction_cost': float(cost) if cost is not None else None,
            'known_subtotal': float(subtotal), 'remaining_available': float(available) if available is not None else None,
            'missing_categories': missing, 'reduction_categories': reductions,
            'target_capacity': sum(scenario['target'].values()) if all(v is not None for v in scenario['target'].values()) else None}


def register_insights(app, store, auth, require_team, state):
    def bundle(team_id, session):
        require_team(team_id)
        document = read_document(store, team_id)
        current = state(team_id, session)
        return {'team_id': team_id, 'document': document,
                'academy': academy_report(store, team_id, current, document),
                'opponents': opponent_report(store, document),
                'stadium': [stadium_report(s) for s in document['stadium_scenarios']]}

    @app.get('/api/insights/{team_id}')
    def get_insights(team_id: str = Path(pattern=r'^[0-9]{1,15}$'), session=Depends(auth)):
        return bundle(team_id, session)

    @app.get('/api/insights/{team_id}/opponents')
    def get_opponents(team_id: str = Path(pattern=r'^[0-9]{1,15}$'),
                      opponent: str | None = Query(default=None, max_length=150),
                      season: int | None = Query(default=None, ge=1, le=999),
                      match_type: int | None = Query(default=None, ge=0, le=2),
                      club_side: Literal['home', 'away'] | None = None, session=Depends(auth)):
        require_team(team_id)
        return opponent_report(store, read_document(store, team_id), opponent, season, match_type, club_side)

    @app.post('/api/insights/{team_id}')
    def save_insights(body: Save, team_id: str = Path(pattern=r'^[0-9]{1,15}$'), session=Depends(auth)):
        require_team(team_id)
        current_state = state(team_id, session)
        document = body.document.model_dump(mode='json')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM kv WHERE key=?', ('insights:' + team_id,)).fetchone()
            previous = json.loads(row['value']) if row else {**Document().model_dump(), 'revision': 0}
            if previous['revision'] != body.expected_revision:
                raise HTTPException(409, 'Données modifiées dans un autre onglet. Rechargez les suivis avant de réessayer.')
            known = {str(p['id']) for p in current_state.get('academy', [])}
            old_goals = {g['player_id']: g for g in previous['goals']}
            for goal in document['goals']:
                if goal['player_id'] not in known and old_goals.get(goal['player_id']) != goal:
                    raise HTTPException(422, 'Ce jeune n’est plus présent dans l’académie observée. Actualisez les données.')
            for link in document['match_links']:
                if not db.execute('SELECT 1 FROM matches WHERE id=? AND type=?', (link['match_id'], link['match_type'])).fetchone():
                    raise HTTPException(422, 'Une rencontre rattachée est absente de votre bibliothèque.')
            document.update(revision=previous['revision'] + 1, updated_at=now())
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('insights:' + team_id, pack(document)))
        return {'ok': True, 'team_id': team_id, 'document': document}
