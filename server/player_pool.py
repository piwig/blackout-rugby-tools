"""Manager-private cross-context observations. No game calls or roster writes."""
import json
import re
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .domain import SKILLS, number, player_metrics
from .imports import PLAYER_FIELDS
from .optimization import injury_status
from .storage import now, pack
from .team_identity import is_selection, team_identity


PREFIX = 'player_pool:'
MAX_CONTEXTS = 256
MAX_OBSERVATIONS = 16_000
MAX_PAYLOAD_BYTES = 4_000_000
MAX_TOTAL_BYTES = 32_000_000
CONFLICT_FIELDS = tuple(sorted(PLAYER_FIELDS - {'id', 'pops', 'reveals'}))
ROLES = ('Pilier', 'Talonneur', 'Deuxième ligne', 'Troisième ligne', 'Demi de mêlée',
         'Demi d’ouverture', 'Centre', 'Ailier', 'Arrière')


class PoolSave(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: int = Field(ge=0, le=2**31-1)
    watch: bool
    text: str = Field(max_length=3000)


def _document(db, player_id):
    row = db.execute('SELECT value FROM kv WHERE key=?', (PREFIX + player_id,)).fetchone()
    return json.loads(row['value']) if row else {'revision': 0, 'watch': False, 'text': '', 'updated_at': None}


def _limit():
    raise HTTPException(413, 'Le vivier dépasse les plafonds de lecture. Réduisez les données locales avant de réessayer.')


def _identifier(value):
    return type(value) in (str, int) and re.fullmatch(r'[0-9]{1,15}', str(value))


def _observations(db):
    # A single read transaction keeps latest contexts, notes and paused flags coherent.
    rows = db.execute('SELECT s.id,s.team_id,s.youth,length(CAST(s.payload AS BLOB)) AS size '
                      'FROM snapshots s JOIN teams t ON t.id=s.team_id '
                      'WHERE s.id=(SELECT MAX(x.id) FROM snapshots x WHERE x.team_id=s.team_id AND x.youth=s.youth) '
                      'ORDER BY s.team_id,s.youth LIMIT ?', (MAX_CONTEXTS+1,)).fetchall()
    if len(rows) > MAX_CONTEXTS or any(r['size'] > MAX_PAYLOAD_BYTES for r in rows) or sum(r['size'] for r in rows) > MAX_TOTAL_BYTES:
        _limit()
    account_row = db.execute("SELECT value FROM kv WHERE key='classic_account'").fetchone()
    account = json.loads(account_row['value']) if account_row else {}
    active = (account or {}).get('selection_ids', [])
    grouped, count = {}, 0
    for row in rows:
        snap = db.execute('SELECT s.*,t.name AS team_name FROM snapshots s JOIN teams t ON t.id=s.team_id WHERE s.id=?', (row['id'],)).fetchone()
        players = json.loads(snap['payload'])
        if not isinstance(players, list):
            raise HTTPException(422, 'Un effectif local est illisible. Réimportez sa source.')
        count += len(players)
        if count > MAX_OBSERVATIONS:
            _limit()
        for raw in players:
            if not isinstance(raw, dict) or not _identifier(raw.get('id')):
                continue
            # Existing normalized roster fields only; never expose account metadata.
            player = {k: v for k, v in raw.items() if k in PLAYER_FIELDS and (v is None or isinstance(v, (str, int, float, bool)))}
            for field in ('pops', 'reveals'):
                if isinstance(raw.get(field), list):
                    player[field] = [skill for skill in raw[field][:100] if isinstance(skill, str) and skill in SKILLS]
            player['id'] = str(raw['id'])
            # Invalid or masked skills remain absent; no missing value becomes zero.
            for skill in SKILLS:
                value = number(player.get(skill))
                if value is None or not 0 <= value <= 21:
                    player.pop(skill, None)
                else:
                    player[skill] = value
            player['metrics'] = player_metrics(player)
            player['changes'] = {}
            observed = snap['last_observed_at'] or snap['observed_at']
            injured = injury_status(player.get('injured'), observed)
            availability = 'unknown' if injured is None else 'injured' if injured else 'healthy'
            quality = 'complete' if player['metrics']['known_skills'] == 10 and number(player.get('age')) is not None and player.get('nationality') else 'partial'
            game_date = snap['last_game_date'] or snap['game_date']
            observation = {'snapshot_id': snap['id'], 'team_id': snap['team_id'], 'team_name': snap['team_name'],
                           'kind': team_identity(snap['team_id'])['kind'], 'cohort': 'academy' if snap['youth'] else 'squad',
                           'archive': is_selection(snap['team_id']) and snap['team_id'] not in active,
                           'source': snap['last_source'] or snap['source'], 'observed_at': observed,
                           'first_source': snap['source'], 'first_observed_at': snap['observed_at'],
                           'imported_at': snap['imported_at'], 'game_date': json.loads(game_date) if game_date else None,
                           'availability': availability, 'quality': quality, 'player': player}
            grouped.setdefault(player['id'], []).append(observation)
    return grouped


def _summary(player_id, observations, document):
    def values(field):
        known = [o['player'].get(field) for o in observations]
        return sorted(set(v for v in known if v is not None and v != ''), key=lambda v: (str(type(v)), v))
    conflicts = {field: values(field) for field in CONFLICT_FIELDS if len(values(field)) > 1}
    return {'player_id': player_id, 'names': values('name'), 'nationalities': values('nationality'),
            'ages': sorted({number(o['player'].get('age')) for o in observations if number(o['player'].get('age')) is not None}),
            'observation_count': len(observations), 'archive_count': sum(o['archive'] for o in observations),
            'conflicts': conflicts, 'positions': sorted({r['name'] for o in observations for r in o['player']['metrics']['roles'][:3]}),
            'document': document}


def register_player_pool(app, store, auth, require_team):
    @app.get('/api/player-pool')
    def pool(q: str = Query(default='', max_length=120), nationality: str = Query(default='', max_length=100),
             age_min: float | None = Query(default=None, ge=0, le=100), age_max: float | None = Query(default=None, ge=0, le=100),
             position: str = Query(default='', max_length=80),
             availability: Literal['', 'healthy', 'injured', 'unknown'] = '',
             quality: Literal['', 'partial', 'complete', 'conflicting'] = '', watch: bool = False,
             offset: int = Query(default=0, ge=0, le=MAX_OBSERVATIONS), limit: int = Query(default=25, ge=1, le=100), session=Depends(auth)):
        if age_min is not None and age_max is not None and age_min > age_max or position and position not in ROLES:
            raise HTTPException(422, 'Vérifiez les filtres du vivier.')
        with store.db() as db:
            db.execute('BEGIN')
            grouped = _observations(db)
            result = []
            for player_id in sorted(grouped, key=lambda value: (int(value), value)):
                observations = grouped[player_id]
                summary = _summary(player_id, observations, _document(db, player_id))
                if watch and not summary['document']['watch'] or quality == 'conflicting' and not summary['conflicts']:
                    continue
                if q.strip().casefold() not in (' '.join([player_id, *summary['names']])).casefold():
                    continue
                def matches(o):
                    p = o['player']
                    age = number(p.get('age'))
                    return (not nationality or nationality.casefold() in [str(p.get(k, '')).casefold() for k in ('nationality', 'dualnationality')]) and (age_min is None or age is not None and age >= age_min) and (age_max is None or age is not None and age <= age_max) and (not position or position in [r['name'] for r in p['metrics']['roles'][:3]]) and (not availability or o['availability'] == availability) and (quality not in ('partial', 'complete') or o['quality'] == quality)
                if any(matches(o) for o in observations):
                    result.append(summary)
        return {'players': result[offset:offset+limit], 'total': len(result), 'offset': offset, 'limit': limit,
                'limits': {'contexts': MAX_CONTEXTS, 'observations': MAX_OBSERVATIONS, 'page_size': 100,
                           'payload_bytes': MAX_PAYLOAD_BYTES, 'total_bytes': MAX_TOTAL_BYTES}, 'position_options': list(ROLES)}

    @app.get('/api/player-pool/{player_id}')
    def detail(player_id: str, session=Depends(auth)):
        if not _identifier(player_id):
            raise HTTPException(422, 'Identifiant de joueur invalide.')
        with store.db() as db:
            db.execute('BEGIN')
            observations = _observations(db).get(player_id)
            if not observations:
                raise HTTPException(404, 'Joueur absent du vivier.')
            return {**_summary(player_id, observations, _document(db, player_id)), 'observations': observations}

    @app.post('/api/player-pool/{player_id}')
    def save(player_id: str, body: PoolSave, session=Depends(auth)):
        if not _identifier(player_id):
            raise HTTPException(422, 'Identifiant de joueur invalide.')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if player_id not in _observations(db):
                raise HTTPException(404, 'Joueur absent du vivier.')
            previous = _document(db, player_id)
            if previous['revision'] != body.expected_revision:
                raise HTTPException(409, 'La note du vivier a changé dans un autre onglet. Votre brouillon est conservé ; relisez la note enregistrée.')
            document = {'revision': body.expected_revision+1, 'watch': body.watch, 'text': body.text, 'updated_at': now()}
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', (PREFIX + player_id, pack(document)))
        return document
