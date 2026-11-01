"""Bounded Classic match reads. Supplied URLs are parsed, never requested."""
import re
from urllib.parse import parse_qs, urlsplit

from .classic import ClassicError
from .match_import import normalize_match_document
from .match_prep import _date, _now, _rows
from .team_identity import team_identity


HISTORY_LIMIT = 20
_INVALID_REFERENCE = 'Indiquez un identifiant de match ou un lien officiel Classic, avec le bon type de rencontre.'
_INVALID_RESPONSE = 'Données de match Classic incohérentes ou non reconnues. Aucune rencontre enregistrée.'


def _kind(value):
    if type(value) is not int or value not in (0, 1, 2, 3):
        raise ClassicError(_INVALID_REFERENCE)
    return value


def _identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'[1-9][0-9]{0,14}', str(value)):
        raise ClassicError(_INVALID_REFERENCE)
    return str(value)


def _flags(kind):
    # Type 3 is BRT's local context. Classic accepts youth=1, never type=3.
    return {1: {'u20': '1'}, 2: {'nat': '1'}, 3: {'youth': '1'}}.get(_kind(kind), {})


def _check_flags(values, kind):
    for flag, expected in (('u20', kind == 1), ('nat', kind == 2), ('youth', kind == 3)):
        if flag not in values:
            continue
        value = values[flag]
        if type(value) not in (int, str) or str(value) not in ('0', '1') or (str(value) == '1') != expected:
            raise ClassicError(_INVALID_REFERENCE)


def parse_fixture_reference(value, kind):
    """Accept an ID or official match URL; discard all URL credentials and extras."""
    _kind(kind)
    if not isinstance(value, str) or len(value) > 2000:
        raise ClassicError(_INVALID_REFERENCE)
    value = value.strip()
    if re.fullmatch(r'[1-9][0-9]{0,14}', value):
        return value
    try:
        url = urlsplit(value.replace('&amp;', '&'))
        if (url.scheme not in ('https', 'http') or url.username is not None or url.password is not None
                or url.port not in (None, 443 if url.scheme == 'https' else 80)):
            raise ValueError
        if url.hostname == 'classic-api.blackoutrugby.com':
            if url.path not in ('', '/') or url.fragment:
                raise ValueError
        elif url.hostname in ('www.blackoutrugby.com', 'blackoutrugby.com'):
            if url.path != '/game/tools.live.scoring.php':
                raise ValueError
        else:
            raise ValueError
        query = parse_qs(url.query, keep_blank_values=True, max_num_fields=40)
        fragment = parse_qs(url.fragment, keep_blank_values=True, max_num_fields=4)
        if set(fragment) - {'fixture', 'u20', 'nat', 'youth'} or set(fragment) & set(query):
            raise ValueError
        query.update(fragment)
        for key in ('id', 'fixtureid', 'fixture', 'u20', 'nat', 'youth', 'r'):
            if key in query and len(query[key]) != 1:
                raise ValueError
        if 'r' in query and query['r'][0] not in ('f', 'me', 'ls', 'fs', 'ms'):
            raise ValueError
        ids = [_identifier(query[key][0]) for key in ('fixtureid', 'id', 'fixture') if key in query]
        if not ids or len(set(ids)) != 1:
            raise ValueError
        _check_flags({key: values[0] for key, values in query.items()}, kind)
        return ids[0]
    except (ValueError, TypeError):
        raise ClassicError(_INVALID_REFERENCE) from None


async def _read(client, resource, **params):
    try:
        document = await client.request(resource, **params)
    except TimeoutError:
        raise ClassicError('Lecture Classic trop longue. Réessayez ; aucune rencontre enregistrée.') from None
    if (not isinstance(document, dict) or document.get('status') not in (None, 'Ok')
            or document.get('error') or document.get('errors')):
        raise ClassicError(_INVALID_RESPONSE)
    return document


def _optional_number(value, maximum):
    if value in (None, ''):
        return None
    if type(value) not in (int, str) or not re.fullmatch(r'[0-9]{1,7}', str(value)) or not 0 <= int(value) <= maximum:
        raise ClassicError(_INVALID_RESPONSE)
    return int(value)


def _fixture(raw, kind, current, team_id=None):
    home, away = _identifier(raw.get('hometeamid')), _identifier(raw.get('guestteamid'))
    if home == away or team_id is not None and team_id not in (home, away):
        return None
    _check_flags(raw, kind)
    start, finish = _date(raw.get('matchstart')), _date(raw.get('matchfinish'))
    if finish is None or finish > current or start is not None and start > finish:
        return None
    # Classic omits these optional fields on some national/U20 fixtures.
    # An absent flag leaves availability unknown until the commentary is read.
    for flag in ('botmatch', 'data_removed'):
        if flag not in raw:
            continue
        value = raw[flag]
        if type(value) not in (int, str) or str(value) not in ('0', '1'):
            raise ClassicError(_INVALID_RESPONSE)
        if str(value) == '1':
            return None
    competition = raw.get('competition')
    if competition is not None and not isinstance(competition, str):
        raise ClassicError(_INVALID_RESPONSE)
    return {'id': _identifier(raw['id']), 'type': kind, 'home_id': home, 'away_id': away,
            'start_at': start.isoformat(timespec='seconds') if start else None,
            'finish_at': finish.isoformat(timespec='seconds'), 'competition': competition[:80] if competition else None,
            'season': _optional_number(raw.get('season'), 1_000_000),
            'round': _optional_number(raw.get('round'), 1_000_000), 'home_score': None, 'away_score': None}


async def _names(client, identifiers, kind):
    # Juniors belong to the club namespace; t does not require a youth selector.
    kind = 0 if kind == 3 else kind
    names = {}
    identifiers = list(dict.fromkeys(identifiers))
    for offset in range(0, len(identifiers), 10):
        batch = identifiers[offset:offset + 10]
        document = await _read(client, 't', teamids=','.join(batch), **_flags(kind))
        rows = document.get('teams')
        if not isinstance(rows, dict) or len(rows) > len(batch):
            raise ClassicError(_INVALID_RESPONSE)
        for key, team in rows.items():
            if key not in batch or not isinstance(team, dict) or 'id' in team and _identifier(team['id']) != key:
                raise ClassicError(_INVALID_RESPONSE)
            _check_flags(team, kind)
            name = team.get('name')
            if name is not None and not isinstance(name, str):
                raise ClassicError(_INVALID_RESPONSE)
            if isinstance(name, str) and name.strip():
                names[key] = name.strip()[:150]
    return names


def _with_names(fixture, names):
    return {**fixture, 'home': names.get(fixture['home_id'], 'Domicile (nom non fourni)'),
            'away': names.get(fixture['away_id'], 'Extérieur (nom non fourni)')}


async def recent_matches(client, team_id, *, match_type=None, now=None):
    """Read at most twenty matches and names for their participating teams."""
    try:
        identity = team_identity(team_id)
        classic_id = _identifier(identity['classic_id'])
    except (ValueError, TypeError):
        raise ClassicError('Choisissez un club ou une sélection valide.') from None
    kind = {'club': 0, 'u20': 1, 'nt': 2}[identity['kind']]
    if match_type is not None:
        selected = _kind(match_type)
        if selected != kind and not (kind == 0 and selected == 3):
            raise ClassicError('Le type de rencontre ne correspond pas au club ou à la sélection choisis.')
        kind = selected
    current = _now(now)
    rows = _rows(await _read(client, 'f', teamid=classic_id, last=str(HISTORY_LIMIT), **_flags(kind)), HISTORY_LIMIT)
    fixtures = []
    for raw in rows.values():
        item = _fixture(raw, kind, current, classic_id)
        if item:
            fixtures.append(item)
    fixtures.sort(key=lambda item: (item['finish_at'], int(item['id'])), reverse=True)
    names = await _names(client, [item[key] for item in fixtures for key in ('home_id', 'away_id')], kind)
    return {'team_id': team_id, 'type': kind, 'retrieved_at': current.isoformat(timespec='seconds'),
            'fixtures': [_with_names(item, names) for item in fixtures],
            'excluded_count': len(rows) - len(fixtures), 'history_limit': HISTORY_LIMIT}


async def fetch_match(client, fixture_id, kind, *, now=None):
    """Collect and validate the complete match before the caller saves anything."""
    fixture_id, kind = _identifier(fixture_id), _kind(kind)
    flags, current = _flags(kind), _now(now)
    rows = _rows(await _read(client, 'f', fixtureid=fixture_id, **flags), 1)
    raw = rows.get(fixture_id)
    fixture = _fixture(raw, kind, current) if raw else None
    if fixture is None:
        raise ClassicError('Cette rencontre n’est pas terminée ou ses commentaires ne sont pas disponibles dans Classic.')
    names = await _names(client, [fixture['home_id'], fixture['away_id']], kind)
    fixture = _with_names(fixture, names)
    commentary = await _read(client, 'me', fixtureid=fixture_id, **flags)
    if 'events' not in commentary or 'fixtureid' in commentary and _identifier(commentary['fixtureid']) != fixture_id:
        raise ClassicError(_INVALID_RESPONSE)
    _check_flags(commentary, kind)
    score = await _read(client, 'ls', fixtureid=fixture_id, **flags)
    if 'fixtureid' in score and _identifier(score['fixtureid']) != fixture_id:
        raise ClassicError(_INVALID_RESPONSE)
    _check_flags(score, kind)
    finished = score.get('match_has_finished')
    if finished is not None and (type(finished) not in (int, str) or str(finished) != '1'):
        raise ClassicError(_INVALID_RESPONSE)
    document = {key: value for key, value in commentary.items()
                if key in ('events', 'status', 'fixtureid', 'brt', 'gameDate', 'game_date', 'u20', 'nat', 'youth')}
    document.update(id=fixture_id, type=kind, home=fixture['home'], away=fixture['away'],
                    home_score=_optional_number(score.get('homescore'), 999) if finished is not None else None,
                    away_score=_optional_number(score.get('guestscore'), 999) if finished is not None else None,
                    season=fixture['season'], round=fixture['round'])
    try:
        return normalize_match_document(document, match_id=fixture_id, match_type=kind)
    except (ValueError, TypeError):
        raise ClassicError(_INVALID_RESPONSE) from None
