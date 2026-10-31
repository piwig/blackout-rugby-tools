"""Private, read-only Classic coaching observations with explicit import previews.

Classic's current JSON documentation uses lowercase skill codes, exactly the
ten codes in SKILLS. Only the literal `none` in current instruction slots means
no scheduled skill (normalized to null). An omitted slot is `unreported`.
Unknown codes/casing are rejected;
localized labels and legacy XML `old/new` changes are never guessed. Reports
use JSON `was/is`. `balltime` is documented as ball carries, never minutes.

Source: https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329
Current sections: Training Instructions 360, Training Reports 361, Player
Statistics 356. Live club evidence confirmed ti/ps; tr success remains unverified.
"""
import asyncio
import hashlib
import json
import math
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .classic import ClassicClient, ClassicError, _utc
from .national import authenticated_member
from .storage import now, pack
from .team_identity import TeamId, require_club_id


SKILLS = frozenset(('stamina', 'handling', 'attack', 'defense', 'technique', 'strength', 'jumping', 'speed', 'agility', 'kicking'))
MAX_PLAYERS = 200
STATISTICS_BATCH = 50
HISTORY_LIMIT = 20
READ_TIMEOUT = 120
PREVIEW_TTL = 600
MAX_PREVIEW_BYTES = 16_000_000
MAX_DOCUMENT_BYTES = 512_000
_UNAVAILABLE = 'Lecture Classic indisponible. Les données enregistrées sont conservées.'
_INVALID = 'Données de suivi Classic incohérentes ou non reconnues.'
_CONFLICT = 'Le compte ou les données ont changé. Relisez un nouvel aperçu avant de confirmer.'
_EXPIRED = 'Cet aperçu a expiré ou a déjà été utilisé. Relisez les données Classic.'
_TOO_LARGE = 'Ce relevé dépasse la limite de taille. Les données enregistrées sont conservées.'

# Explicit aliases from the documented JSON names, without inferred quantities.
COUNTERS = {
    'tackles': 'tackles', 'missedtackles': 'missed_tackles', 'tries': 'tries',
    'totalpoints': 'total_points', 'metresgained': 'metres_gained', 'balltime': 'carries',
    'linebreaks': 'line_breaks', 'tryassists': 'try_assists', 'turnoverswon': 'turnovers_won',
    'penaltiesconceded': 'penalties_conceded', 'handlingerrors': 'handling_errors',
    'yellowcards': 'yellow_cards', 'redcards': 'red_cards', 'kicks': 'kicks',
    'leaguecaps': 'league_caps', 'friendlycaps': 'friendly_caps', 'cupcaps': 'cup_caps',
    'conversions': 'conversions', 'dropgoals': 'drop_goals', 'penalties': 'penalties',
    'intercepts': 'intercepts', 'knockons': 'knock_ons', 'forwardpasses': 'forward_passes',
    'beatendefenders': 'beaten_defenders', 'injuries': 'injuries', 'fights': 'fights',
    'kickingmetres': 'kicking_metres', 'undertwentycaps': 'u20_caps', 'nationalcaps': 'national_caps',
    'othercaps': 'other_caps', 'avkickingmetres': 'average_kicking_metres',
    'kicksoutonthefull': 'kicks_out_on_the_full', 'penaltytime': 'penalty_time',
    'missedconversions': 'missed_conversions', 'misseddropgoals': 'missed_drop_goals',
    'missedpenalties': 'missed_penalties', 'goodupandunders': 'good_up_and_unders',
    'badupandunders': 'bad_up_and_unders', 'upandunders': 'up_and_unders',
    'goodkicks': 'good_kicks', 'badkicks': 'bad_kicks', 'lineoutssecured': 'lineouts_secured',
    'lineoutsconceded': 'lineouts_conceded', 'lineoutsstolen': 'lineouts_stolen',
    'successfullineoutthrows': 'successful_lineout_throws', 'unsuccessfullineoutthrows': 'unsuccessful_lineout_throws',
    'worldcupcaps': 'world_cup_caps', 'undertwentyworldcupcaps': 'u20_world_cup_caps',
}


class CoachingPreview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['instructions', 'report', 'statistics']
    scope: Literal['career', 'league'] | None = None
    season: int | None = Field(default=None, ge=1, le=999)
    round: int | None = Field(default=None, ge=1, le=16)

    @model_validator(mode='after')
    def explicit_scope(self):
        if self.kind == 'instructions' and any(value is not None for value in (self.scope, self.season, self.round)):
            raise ValueError('Les instructions décrivent le réglage actuel.')
        if self.kind == 'report' and (self.scope is not None or (self.season is None) != (self.round is None)):
            raise ValueError('Indiquez la saison et la semaine ensemble.')
        if self.kind == 'statistics':
            self.scope = self.scope or 'career'
            if self.round is not None or (self.scope == 'league') != (self.season is not None):
                raise ValueError('Le championnat exige une saison explicite ; la carrière n’en accepte pas.')
        return self


class CoachingConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    preview_id: str = Field(min_length=20, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    expected_revision: int = Field(ge=0, le=2**31-1)


def _bad():
    raise ClassicError(_INVALID)


def _identifier(value):
    if type(value) not in (str, int) or not re.fullmatch(r'[1-9][0-9]{0,14}', str(value)):
        _bad()
    return str(value)


def _integer(value, maximum=10**12, *, minimum=0, optional=False):
    if optional and value is None:
        return None
    if (type(value) not in (str, int) or not re.fullmatch(r'[0-9]{1,15}', str(value))
            or not minimum <= int(value) <= maximum):
        _bad()
    return int(value)


def _decimal(value):
    if value is None:
        return None
    if type(value) not in (str, int, float) or not re.fullmatch(r'[0-9]{1,13}(?:\.[0-9]{1,6})?', str(value)):
        _bad()
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 10**12:
        _bad()
    return number


def _name(value):
    if value is None:
        return None
    if not isinstance(value, str):
        _bad()
    return value.strip()[:120] or None


def _skill(value, *, slot=False):
    if slot and value == 'none':
        return None
    if not isinstance(value, str) or value not in SKILLS:
        _bad()
    return value


def _game_date(value):
    if value is None:
        return None
    if not isinstance(value, dict) or not {'season', 'round', 'day'}.issubset(value):
        _bad()
    return {key: _integer(value[key], maximum, minimum=1) for key, maximum in (('season', 999), ('round', 16), ('day', 7))}


def _provenance(doc, resource, **params):
    return {'source': 'Classic API', 'source_resource': resource, **params,
            'source_game_date': _game_date(doc.get('gameDate')),
            'source_observed_at': _utc(doc.get('brt'))}


def _rows(value, *, id_field='id', limit=MAX_PLAYERS):
    if not isinstance(value, (list, dict)) or len(value) > limit:
        _bad()
    result, seen = [], set()
    for key, row in value.items() if isinstance(value, dict) else ((None, row) for row in value):
        if not isinstance(row, dict):
            _bad()
        identity = _identifier(row.get(id_field, key))
        if key is not None and _identifier(key) != identity or identity in seen:
            _bad()
        seen.add(identity)
        result.append((identity, row))
    return sorted(result, key=lambda pair: int(pair[0]))


async def _read(client, resource, **params):
    doc = await client.request(resource, **params)
    if not isinstance(doc, dict) or doc.get('status') != 'Ok' or doc.get('error') or doc.get('errors'):
        _bad()
    return doc


def _slots(value, team_id):
    if not isinstance(value, dict) or _identifier(value.get('teamid')) != team_id:
        _bad()
    # Missing slots are unknown; literal `none` is the documented empty setting.
    return [_skill(value[f's{number}'], slot=True) if f's{number}' in value else 'unreported' for number in range(1, 5)]


def _instructions(doc, team_id):
    result = {'team_skills': _slots(doc.get('team training'), team_id), 'youth_skills': None, 'individual': None,
              'observed_at': now(), 'provenance': _provenance(doc, 'ti')}
    if 'youth training' in doc:
        result['youth_skills'] = _slots(doc['youth training'], team_id)
    if 'individual training' in doc:
        entries = doc['individual training']
        if not isinstance(entries, (list, dict)) or len(entries) > 1000:
            _bad()
        normalized = []
        for entry in entries.values() if isinstance(entries, dict) else entries:
            if not isinstance(entry, dict) or _identifier(entry.get('teamid')) != team_id:
                _bad()
            normalized.append({'player_id': _identifier(entry.get('playerid')), 'player_name': _name(entry.get('player name')),
                               'skill': _skill(entry.get('skill')), 'sessions': _integer(entry.get('sessions'), 1000, minimum=1)})
        result['individual'] = sorted(normalized, key=lambda row: (int(row['player_id']), row['skill'], row['sessions'], row['player_name'] or ''))
    return result


def _changes(value, direction=1):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > len(SKILLS):
        _bad()
    result, seen = [], set()
    for change in value:
        if not isinstance(change, dict):
            _bad()
        skill = _skill(change.get('skill'))
        before, after = _integer(change.get('was'), 1000, optional=True), _integer(change.get('is'), 1000, optional=True)
        if skill in seen or before is not None and after is not None and direction * (after - before) <= 0:
            _bad()
        seen.add(skill)
        result.append({'skill': skill, 'before': before, 'after': after})
    return result


def _before_after(row, field):
    if field not in row or row[field] is None:
        return {field + '_before': None, field + '_after': None}
    value = row[field]
    if not isinstance(value, dict) or set(value) - {'was', 'is'}:
        _bad()
    return {field + '_before': _integer(value.get('was'), optional=True), field + '_after': _integer(value.get('is'), optional=True)}


def _phase(value, individual=False):
    if value is None:
        return None
    if not isinstance(value, dict):
        _bad()
    result = {'players': None}
    if not individual:
        skills = value.get('skills')
        if skills is not None and (not isinstance(skills, list) or len(skills) > 4):
            _bad()
        result['skills'] = [_skill(skill) for skill in skills] if skills is not None else None
    if 'players' not in value:
        return result
    result['players'] = []
    for player_id, raw in _rows(value['players']):
        player = {'player_id': player_id, 'player_name': _name(raw.get('name', raw.get('player name'))),
                  **_before_after(raw, 'csr'), **_before_after(raw, 'energy')}
        if individual:
            skills = raw.get('skills')
            if skills is not None and (not isinstance(skills, list) or len(skills) > len(SKILLS)):
                _bad()
            player['skills'] = None
            if skills is not None:
                player['skills'] = []
                seen = set()
                for skill in skills:
                    if not isinstance(skill, dict):
                        _bad()
                    code = _skill(skill.get('skill'))
                    if code in seen:
                        _bad()
                    seen.add(code)
                    player['skills'].append({'skill': code,
                                             'sessions': _integer(skill.get('sessions'), 1000, minimum=1),
                                             'pops': _changes(skill.get('pops'))})
        else:
            player.update(pops=_changes(raw.get('pops')), drops=_changes(raw.get('drops'), -1))
        result['players'].append(player)
    return result


def _report(doc, team_id, request):
    raw = doc.get('report')
    if not isinstance(raw, dict) or _identifier(raw.get('teamid')) != team_id or not isinstance(raw.get('report'), dict):
        _bad()
    season, round_number = _integer(raw.get('season'), 999, minimum=1), _integer(raw.get('round'), 16, minimum=1)
    if request.season is not None and (season, round_number) != (request.season, request.round):
        _bad()
    source_date = _game_date(doc.get('gameDate'))
    if source_date is not None and (season, round_number) > (source_date['season'], source_date['round']):
        _bad()
    return {'report_id': _identifier(raw.get('id')), 'season': season, 'round': round_number,
            'team': _phase(raw['report'].get('team')), 'individual': _phase(raw['report'].get('individual'), True),
            'observed_at': now(), 'provenance': _provenance(doc, 'tr', requested_period=(
                {'season': request.season, 'round': request.round} if request.season is not None else None))}


async def _statistics(client, team_id, request):
    roster_doc = await _read(client, 'p', teamid=team_id)
    roster = {}
    for player_id, raw in _rows(roster_doc.get('players')):
        if _identifier(raw.get('teamid')) != team_id:
            _bad()
        roster[player_id] = _name(raw.get('name'))
    requested, players, metadata = list(roster), [], None
    for start in range(0, len(requested), STATISTICS_BATCH):
        batch = requested[start:start + STATISTICS_BATCH]
        params = {'playerids': ','.join(batch)}
        if request.scope == 'league':
            params.update(league='1', season=str(request.season))
        doc = await _read(client, 'ps', **params)
        current_metadata = _provenance(doc, 'ps', requested_scope=request.scope, requested_period=(
            {'season': request.season} if request.scope == 'league' else None))
        if metadata is not None and metadata['source_game_date'] != current_metadata['source_game_date']:
            _bad()
        metadata = current_metadata
        for player_id, raw in _rows(doc.get('player statistics'), id_field='playerid', limit=len(batch)):
            if player_id not in batch:
                _bad()
            counters = {name: (_decimal(raw.get(source)) if source == 'avkickingmetres' else _integer(raw.get(source), optional=True))
                        for source, name in COUNTERS.items()}
            tackles, missed = counters['tackles'], counters['missed_tackles']
            ratio = round(100 * tackles / (tackles + missed), 2) if tackles is not None and missed is not None and tackles + missed > 0 else None
            players.append({'player_id': player_id, 'player_name': roster[player_id], 'counters': counters, 'tackle_success_rate': ratio})
    received = {row['player_id'] for row in players}
    if metadata is None:
        metadata = _provenance(roster_doc, 'ps', requested_scope=request.scope,
                               requested_period={'season': request.season} if request.scope == 'league' else None)
    return {'scope': request.scope, 'season': request.season, 'observed_at': now(), 'requested_count': len(requested),
            'missing_player_ids': [player_id for player_id in requested if player_id not in received],
            'players': sorted(players, key=lambda row: int(row['player_id'])), 'provenance': metadata}


def _digest(document):
    # Observation clocks are provenance, not a new semantic revision.
    content = {key: value for key, value in document.items() if key not in ('key', 'observed_at', 'provenance')}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _safe_values(db, suffix, parameters=()):
    # SQLite tests the byte length before transmitting a value to Python. An
    # oversized legacy row never reaches json.loads or a list of raw documents.
    return db.execute('SELECT length(CAST(value AS BLOB)) AS bytes, '
                      'CASE WHEN length(CAST(value AS BLOB))<=? THEN value ELSE NULL END AS value FROM kv ' + suffix,
                      (MAX_DOCUMENT_BYTES, *parameters))


def _decoded(row):
    if row['bytes'] > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, _TOO_LARGE)
    try:
        return json.loads(row['value'])
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(409, 'Un relevé enregistré est incompatible. Les données sont conservées.') from None


def _revision(db, team_id):
    row = _safe_values(db, 'WHERE key=?', (f'coaching:{team_id}:revision',)).fetchone()
    value = _decoded(row) if row else 0
    if type(value) is not int or not 0 <= value <= 2**31-1:
        raise HTTPException(409, _CONFLICT)
    return value


def _context(db, values):
    row = db.execute("SELECT value FROM kv WHERE key='classic_account'").fetchone()
    # Never persisted or returned: changes to a key OR account binding invalidate a preview.
    return hashlib.sha256(pack({'account': json.loads(row['value']) if row else None,
                               'credentials': {key: values.get(key) for key in ('d', 'dk', 'iv', 'm', 'mk')}}).encode()).hexdigest()


def _bundle(db, team_id, report_offset=0, statistics_offset=0):
    result = {'team_id': team_id, 'revision': _revision(db, team_id), 'history_limit': HISTORY_LIMIT,
              'report_offset': report_offset, 'statistics_offset': statistics_offset, 'instructions': None}
    latest = _safe_values(db, 'WHERE key LIKE ? ORDER BY key DESC LIMIT 1', (f'coaching:{team_id}:instructions:%',)).fetchone()
    if latest:
        result['instructions'] = _decoded(latest)
    for kind, plural, offset in (('report', 'reports', report_offset), ('statistics', 'statistics', statistics_offset)):
        pattern = f'coaching:{team_id}:{kind}:%'
        result[kind + '_total'] = db.execute('SELECT COUNT(*) FROM kv WHERE key LIKE ?', (pattern,)).fetchone()[0]
        rows = _safe_values(db, 'WHERE key LIKE ? ORDER BY key DESC LIMIT ? OFFSET ?', (pattern, HISTORY_LIMIT, offset))
        result[plural] = [_decoded(row) for row in rows]
    return result


def _stored(db, team_id, kind, document, digest):
    if kind == 'report':
        key = f"coaching:{team_id}:report:{document['season']:03d}:{document['round']:02d}"
        row = _safe_values(db, 'WHERE key=?', (key,)).fetchone()
        if row and _digest(_decoded(row)) != digest:
            raise HTTPException(409, 'Un rapport différent existe déjà pour cette saison et cette semaine. L’observation précédente est conservée.')
        return bool(row)
    if kind == 'instructions':
        row = _safe_values(db, 'WHERE key LIKE ? ORDER BY key DESC LIMIT 1', (f'coaching:{team_id}:instructions:%',)).fetchone()
        return bool(row and _digest(_decoded(row)) == digest)
    row = _safe_values(db, 'WHERE key=?', (_statistics_current_key(team_id, document),)).fetchone()
    return bool(row and _decoded(row) == digest)


def _statistics_current_key(team_id, document):
    return f"coaching:{team_id}:current-statistics:{document['scope']}:{document['season'] or 'all'}"


def register_coaching(app, store, auth, require_team, credentials, throttle):
    """Register private club routes. `store` may be a ContextVar-backed PrivateStore."""
    previews, guard = {}, threading.Lock()

    def club(team_id):
        require_club_id(team_id)
        require_team(team_id)

    @app.get('/api/clubs/{team_id}/coaching', dependencies=[Depends(auth)])
    def get_bundle(team_id: TeamId, report_offset: int = Query(0, ge=0, le=1_000_000),
                   statistics_offset: int = Query(0, ge=0, le=1_000_000)):
        club(team_id)
        with store.db() as db:
            db.execute('BEGIN')
            return _bundle(db, team_id, report_offset, statistics_offset)

    @app.post('/api/clubs/{team_id}/coaching/preview', dependencies=[Depends(auth)])
    async def preview(team_id: TeamId, body: CoachingPreview):
        club(team_id)
        throttle('coaching-preview:' + team_id)
        values = credentials(team_id)
        account = store.get('classic_account')
        if (not isinstance(account, dict) or str(account.get('id')) != str(values.get('m'))
                or not isinstance(account.get('team_ids'), list) or team_id not in account['team_ids'] or not values.get('mk')):
            raise HTTPException(403, 'Rattachez ce club au compte Classic propriétaire avant de le lire.')
        owner = str(store.path)
        with store.db() as db:
            baseline = (_revision(db, team_id), _context(db, values))
        client = ClassicClient(values)

        async def collect():
            await authenticated_member(client, str(values['m']))
            teams = (await _read(client, 't', teamid=team_id)).get('teams')
            team = teams.get(team_id) if isinstance(teams, dict) else None
            if (not isinstance(team, dict) or _identifier(team.get('id')) != team_id
                    or str(team.get('owner')) != str(values['m'])):
                raise HTTPException(403, 'Ce club n’appartient pas au compte Classic connecté.')
            if body.kind == 'instructions':
                return _instructions(await _read(client, 'ti', teamid=team_id), team_id)
            if body.kind == 'report':
                params = {'teamid': team_id}
                if body.season is not None:
                    params.update(season=str(body.season), round=str(body.round))
                return _report(await _read(client, 'tr', **params), team_id, body)
            return await _statistics(client, team_id, body)
        try:
            document = await asyncio.wait_for(collect(), timeout=READ_TIMEOUT)
        except (ClassicError, TimeoutError):
            raise HTTPException(502, _UNAVAILABLE) from None
        digest = _digest(document)
        document['key'] = (f"report:{document['season']}:{document['round']}" if body.kind == 'report' else
                           f"statistics:{document['scope']}:{document['season'] or 'all'}:{digest}" if body.kind == 'statistics' else
                           f'instructions:{digest}')
        with store.db() as db:
            if (_revision(db, team_id), _context(db, credentials(team_id))) != baseline or str(store.path) != owner:
                raise HTTPException(409, _CONFLICT)
            already_imported = _stored(db, team_id, body.kind, document, digest)
        payload = pack(document)
        size = len(payload.encode())
        if size > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, _TOO_LARGE)
        if size > MAX_PREVIEW_BYTES:
            raise HTTPException(413, 'Aperçu trop volumineux. Les aperçus précédents sont conservés.')
        token = secrets.token_urlsafe(32)
        with guard:
            for key in list(previews):
                if previews[key]['expires'] <= time.monotonic():
                    previews.pop(key)
            own = [key for key, entry in previews.items() if entry['owner'] == owner]
            while len(own) >= 3:
                previews.pop(own.pop(0))
            while previews and (len(previews) >= 16 or sum(entry['size'] for entry in previews.values()) + size > MAX_PREVIEW_BYTES):
                previews.pop(next(iter(previews)))
            previews[token] = {'owner': owner, 'team_id': team_id, 'kind': body.kind, 'payload': payload, 'size': size,
                               'digest': digest, 'baseline': baseline, 'expires': time.monotonic() + PREVIEW_TTL}
        warnings = []
        if body.kind == 'statistics':
            warnings.append('Les statistiques concernent les joueurs actuels ; leur carrière peut inclure d’autres clubs. Les minutes et les postes ne sont pas fournis.')
            if document['missing_player_ids']:
                warnings.append('Certains joueurs n’ont pas de statistiques retournées ; leurs valeurs restent inconnues.')
        if body.kind == 'instructions':
            warnings.append('Ces instructions sont les réglages actuels ; elles ne prouvent pas un entraînement réalisé.')
        return {'team_id': team_id, 'kind': body.kind, 'preview_id': token, 'expected_revision': baseline[0],
                'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=PREVIEW_TTL)).isoformat(timespec='seconds'),
                'status': 'empty' if body.kind == 'statistics' and not document['players'] else 'available',
                'data': document, 'already_imported': already_imported, 'warnings': warnings}

    @app.post('/api/clubs/{team_id}/coaching/confirm', dependencies=[Depends(auth)])
    def confirm(team_id: TeamId, body: CoachingConfirm):
        club(team_id)
        with guard:
            entry = previews.get(body.preview_id)
            if (not entry or entry['owner'] != str(store.path) or entry['team_id'] != team_id
                    or entry['expires'] <= time.monotonic()):
                raise HTTPException(409, _EXPIRED)
            if entry['baseline'][0] != body.expected_revision:
                raise HTTPException(409, _CONFLICT)
            previews.pop(body.preview_id)
        if entry['size'] > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, _TOO_LARGE)
        document, kind = json.loads(entry['payload']), entry['kind']
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if (_revision(db, team_id), _context(db, credentials(team_id))) != entry['baseline']:
                raise HTTPException(409, _CONFLICT)
            unchanged = _stored(db, team_id, kind, document, entry['digest'])
            if not unchanged:
                revision = entry['baseline'][0] + 1
                # Content can legitimately return A -> B -> A. Each persisted
                # observation needs a distinct UI key; digest handles deduplication.
                if kind != 'report':
                    document['key'] += ':' + str(revision)
                serialized = pack(document)
                if len(serialized.encode()) > MAX_DOCUMENT_BYTES:
                    raise HTTPException(413, _TOO_LARGE)
                key = (f"coaching:{team_id}:report:{document['season']:03d}:{document['round']:02d}" if kind == 'report'
                       else f"coaching:{team_id}:{kind}:{revision:012d}:{entry['digest']}")
                db.execute('INSERT INTO kv(key,value) VALUES(?,?)', (key, serialized))
                if kind == 'statistics':
                    db.execute('INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)', (_statistics_current_key(team_id, document), pack(entry['digest'])))
                db.execute('INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)', (f'coaching:{team_id}:revision', pack(revision)))
            result = _bundle(db, team_id)
        return {'ok': True, 'imported': not unchanged, 'unchanged': unchanged, 'bundle': result}
