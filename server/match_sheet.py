"""Public match-sheet comparison. Bounded reads only; never fall back to Default."""
import math
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .classic import ClassicError
from .match_direct import _check_flags, _flags, _identifier, _kind, parse_fixture_reference
from .match_prep import _date, _fixture, _now, _rows
from .team_identity import TeamId, team_identity

INVALID = 'Feuille Classic incohérente ou non reconnue. Aucune donnée du jeu modifiée.'
EnergyScale = Literal['auto', 'percent', 'level']
SLOTS = tuple([f'p{i}' for i in range(1, 16)] + [f'b{i}' for i in range(1, 9)])
GROUPS = (
    ('pack', tuple(range(1, 9))), ('first_row', (1, 2, 3)), ('second_row', (4, 5)),
    ('back_row', (6, 7, 8)), ('halves', (9, 10)), ('centres', (12, 13)),
    ('back_three', (11, 14, 15)), ('xv', tuple(range(1, 16))),
    ('bench', tuple(range(16, 24))), ('all', tuple(range(1, 24))),
)
# Explicit numerical contracts: Unknown/Low/etc., bools and non-finite values
# are never converted to zero. Experience uses Classic's 1–21 scale.
BOUNDS = {'csr': (0, 1_000_000_000), 'weight': (1, 500), 'height': (1, 300),
          'form': (1, 11), 'experience': (1, 21), 'aggression': (1, 5), 'discipline': (1, 5)}


class SheetCalendarRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: TeamId
    match_type: int = Field(strict=True, ge=0, le=3)


class SheetRequest(SheetCalendarRequest):
    reference: str = Field(strict=True, min_length=1, max_length=2000)
    home_energy_scale: EnergyScale = 'auto'
    guest_energy_scale: EnergyScale = 'auto'


def _context(team_id, kind):
    identity = team_identity(team_id)
    expected = {'club': 0, 'u20': 1, 'nt': 2}[identity['kind']]
    kind = _kind(kind)
    if kind != expected and not (expected == 0 and kind == 3):
        raise ClassicError('Le type de rencontre ne correspond pas à l’équipe choisie.')
    return _identifier(identity['classic_id']), kind


async def _read(client, resource, **params):
    try:
        doc = await client.request(resource, **params)
    except (ClassicError, TimeoutError):
        # Never propagate upstream URLs/credentials, including adapter errors.
        raise ClassicError('Lecture Classic impossible. Réessayez ; aucune donnée du jeu modifiée.') from None
    if not isinstance(doc, dict) or doc.get('status') not in (None, 'Ok') or doc.get('error') or doc.get('errors'):
        raise ClassicError(INVALID)
    return doc


def _fixture_row(raw, team_id, kind):
    _check_flags(raw, kind)
    fixture = _fixture(raw, team_id)
    if fixture is None:
        raise ClassicError('Cette rencontre ne concerne pas l’équipe choisie.')
    fixture['type'] = kind
    return fixture


async def list_sheet_fixtures(client, team_id, match_type, *, now=None):
    team, kind = _context(team_id, match_type)
    current = _now(now)
    document = await _read(client, 'f', future=team, **_flags(kind))
    _check_flags(document, kind)
    rows = _rows(document, 200)
    fixtures = []
    for raw in rows.values():
        item = _fixture_row(raw, team, kind)
        start = _date(raw.get('matchstart'))
        if start and start > current and raw.get('matchfinish') in (None, '', 0, '0'):
            fixtures.append(item)
    fixtures.sort(key=lambda f: (f['start_at'], int(f['id'])))
    return {'team_id': team_id, 'match_type': kind, 'retrieved_at': current.isoformat(timespec='seconds'),
            'fixtures': fixtures, 'excluded_count': len(rows) - len(fixtures)}


def _lineup(doc, team, fixture, kind):
    _check_flags(doc, kind)
    rows = doc.get('lineups', [])
    if isinstance(rows, dict): rows = list(rows.values())
    if not isinstance(rows, list) or len(rows) > 1:
        raise ClassicError(INVALID)
    if not rows: return None
    row = rows[0]
    if not isinstance(row, dict): raise ClassicError(INVALID)
    # Both identities are mandatory: fixture 0 is a Default, not this match.
    if _identifier(row.get('teamid')) != team or _identifier(row.get('fixtureid')) != fixture:
        raise ClassicError(INVALID)
    _check_flags(row, kind)
    ids = []
    for slot in SLOTS:
        value = row.get(slot)
        if value not in (None, '', 0, '0') or isinstance(value, bool):
            ids.append(_identifier(value))
    if len(set(ids)) != len(ids): raise ClassicError(INVALID)
    return row


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)): return None
    try:
        number = float(value)
    except (ValueError, OverflowError): return None
    return number if math.isfinite(number) and low <= number <= high else None


def _energy(raw, scale):
    value = _number(raw, 0, 110)
    if value is None: return None, None, 'unknown'
    if scale == 'percent' or scale == 'auto' and value > 11: return value, value, 'percent'
    if scale == 'level' and 1 <= value <= 11: return value, value * 10, 'level'
    return value, None, 'unknown'


def _summaries(players):
    groups = []
    for key, slots in GROUPS:
        selected = [players[i-1] for i in slots]
        metrics = {}
        for field in ('csr', 'adjusted_csr', 'height', 'form', 'experience', 'energy_percent', 'aggression', 'discipline', 'weight'):
            values = [p[field] for p in selected if p[field] is not None]
            value = None
            if values:
                if field == 'weight':
                    if len(values) == len(selected): value = round(sum(values), 2)
                elif field == 'adjusted_csr': value = sum(values) // len(values)
                else: value = round(sum(values) / len(values), 2)
            name = 'weight_total' if field == 'weight' else field + '_average'
            metrics[name] = {'value': value, 'known': len(values), 'expected': len(selected)}
        groups.append({'key': key, 'slots': slots, 'size': len(slots), 'metrics': metrics})
    return groups


def build_side(team, name, lineup, players, scale):
    slots = []
    for index, key in enumerate(SLOTS, 1):
        pid = lineup.get(key) if lineup else None
        pid = None if pid in (None, '', 0, '0') else _identifier(pid)
        raw = players.get(pid) if pid else None
        slot = {'slot': index, 'player_id': pid,
                'status': 'available' if raw is not None else 'missing_player' if pid else 'not_provided',
                'captain': bool(pid and str(lineup.get('captain')) == pid),
                'kicker': bool(pid and str(lineup.get('kicker')) == pid),
                'name': str(raw['name']).strip()[:150] if raw and isinstance(raw.get('name'), str) and raw['name'].strip() else None,
                **{field: _number(raw.get(field), *bounds) if raw else None for field, bounds in BOUNDS.items()}}
        energy, percent, energy_scale = _energy(raw.get('energy') if raw else None, scale)
        slot.update(energy_raw=energy, energy_percent=percent, energy_scale=energy_scale, adjusted_csr=None)
        if all(slot[f] is not None for f in ('csr', 'form', 'experience')) and percent is not None:
            csr, form, xp, energy = (Decimal(str(v)) for v in (slot['csr'],slot['form'],slot['experience'],percent))
            slot['adjusted_csr'] = int(csr * (1 + Decimal('.07') * (form-7)) * (1 + Decimal('.02') * (xp-7)) * energy / 100)
        slots.append(slot)
    return {'team_id': team, 'name': name, 'lineup_state': 'available' if lineup else 'not_provided',
            'energy_scale': scale,
            'deadline_at': d.isoformat(timespec='seconds') if lineup and (d := _date(lineup.get('deadline'))) else None,
            'tactics_deadline_at': d.isoformat(timespec='seconds') if lineup and (d := _date(lineup.get('tacticsdeadline'))) else None,
            'players': slots, 'groups': _summaries(slots)}


async def fetch_match_sheet(client, request, *, now=None):
    team, kind = _context(request.team_id, request.match_type)
    fixture_id = parse_fixture_reference(request.reference, kind)
    current, flags = _now(now), _flags(kind)
    document = await _read(client, 'f', fixtureid=fixture_id, **flags)
    _check_flags(document, kind)
    rows = _rows(document, 1)
    if fixture_id not in rows: raise ClassicError(INVALID)
    fixture = _fixture_row(rows[fixture_id], team, kind)
    teams = [fixture['home_id'], fixture['guest_id']]
    # Resource matrix: f/lu/p use the population; junior names use club t.
    names_doc = await _read(client, 't', teamids=','.join(teams), **_flags(0 if kind == 3 else kind))
    _check_flags(names_doc, 0 if kind == 3 else kind)
    names = names_doc.get('teams')
    if not isinstance(names, dict) or len(names) > 2: raise ClassicError(INVALID)
    for key, row in names.items():
        if key not in teams or not isinstance(row, dict) or 'id' in row and _identifier(row['id']) != key:
            raise ClassicError(INVALID)
        _check_flags(row, 0 if kind == 3 else kind)
    lineups = [await _read(client, 'lu', teamid=t, fixtureid=fixture_id, **flags) for t in teams]
    lineups = [_lineup(doc, t, fixture_id, kind) for doc, t in zip(lineups, teams)]
    all_players = []
    for row in lineups:
        ids = [_identifier(row[k]) for k in SLOTS if row and row.get(k) not in (None, '', 0, '0')]
        players = {}
        if ids:
            doc = await _read(client, 'p', playerids=','.join(ids), **flags)
            _check_flags(doc, kind)
            players = doc.get('players', {})
            if not isinstance(players, dict) or len(players) > len(ids): raise ClassicError(INVALID)
            for key, player in players.items():
                if key not in ids or not isinstance(player, dict) or 'id' in player and _identifier(player['id']) != key:
                    raise ClassicError(INVALID)
                _check_flags(player, kind)
        all_players.append(players)
    sides = [build_side(t, names.get(t, {}).get('name') if isinstance(names.get(t, {}).get('name'), str) else None,
                        row, players, scale) for t, row, players, scale in zip(teams, lineups, all_players,
                         (request.home_energy_scale, request.guest_energy_scale))]
    start = _date(fixture['start_at'])
    guidance = {key: (start - timedelta(minutes=minutes)).isoformat(timespec='seconds') if start else None
                for key, minutes in (('lineup_at', 185), ('publication_at', 180), ('tactics_at', 125))}
    return {'team_id': request.team_id, 'match_type': kind, 'fixture': fixture,
            'retrieved_at': current.isoformat(timespec='seconds'), 'home': sides[0], 'guest': sides[1],
            'timing': {'indicative': guidance}}
