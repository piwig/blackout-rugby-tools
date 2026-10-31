"""Bounded, read-only fixture and opponent preparation."""
import math
import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .classic import ClassicError
from .team_identity import TeamId


HISTORY_LIMIT = 20
MATCH_LIMIT = 5
CALENDAR_LIMIT = 200
METRICS = (
    ('points_for', 'Points marqués', 'points'),
    ('points_against', 'Points encaissés', 'points'),
    ('tries', 'Essais', 'essais'),
    ('possession_pct', 'Possession', '%'),
    ('territory_pct', 'Territoire adverse', '%'),
    ('metres_gained', 'Mètres gagnés', 'm'),
    ('missed_tackles', 'Plaquages manqués', 'plaquages'),
    ('handling_errors', 'Fautes de main', 'fautes'),
    ('penalties_conceded', 'Pénalités concédées', 'pénalités'),
    ('lineouts_pct', 'Touches gagnées', '%'),
    ('scrums_pct', 'Mêlées gagnées', '%'),
)


class FixturesRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: TeamId


class ScoutRequest(FixturesRequest):
    fixture_id: str = Field(strict=True, pattern=r'^[0-9]{1,15}$')


def _id(value):
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) and re.fullmatch(r'[0-9]{1,15}', str(value)) and int(value) > 0 else None


def _club(team_id):
    if not _id(team_id):
        raise ClassicError('Cette préparation est disponible pour les clubs uniquement. Les statistiques U20 et nationales ne sont pas encore prises en charge.')
    return str(team_id)


def _date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _now(value):
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ClassicError('La date de référence doit préciser son fuseau horaire.')
    return current.astimezone(timezone.utc)


def _rows(document, limit):
    raw = document.get('fixtures') if isinstance(document, dict) else None
    if not isinstance(raw, (list, dict)) or len(raw) > limit:
        raise ClassicError('Liste de rencontres Classic non reconnue ou trop volumineuse. Aucune donnée n’a été modifiée.')
    rows = raw.items() if isinstance(raw, dict) else ((None, value) for value in raw)
    result = {}
    for key, value in rows:
        if not isinstance(value, dict):
            raise ClassicError('Rencontre Classic non reconnue.')
        identifier = _id(value.get('id', key))
        if not identifier or key is not None and str(key) != identifier or identifier in result:
            raise ClassicError('Identifiant de rencontre Classic incohérent.')
        result[identifier] = {**value, 'id': identifier}
    return result


def _fixture(raw, team_id):
    home, guest = _id(raw.get('hometeamid')), _id(raw.get('guestteamid'))
    if not home or not guest or home == guest or team_id not in (home, guest):
        return None
    start, finish = _date(raw.get('matchstart')), _date(raw.get('matchfinish'))
    side = 'home' if home == team_id else 'guest'
    return {'id': raw['id'], 'home_id': home, 'guest_id': guest, 'side': side,
            'opponent_id': guest if side == 'home' else home,
            'start_at': start.isoformat(timespec='seconds') if start else None,
            'finish_at': finish.isoformat(timespec='seconds') if finish else None,
            'competition': str(raw.get('competition') or 'Non renseignée')[:80]}


def _future(raw, team_id, current):
    fixture = _fixture(raw, team_id)
    if not fixture or raw.get('matchfinish') not in (None, '', 0, '0'):
        return None
    start = _date(raw.get('matchstart'))
    return fixture if start is not None and start > current else None


async def list_upcoming_fixtures(client, team_id, *, now=None):
    """One documented future-fixtures read; no club state or game action is saved."""
    team_id, current = _club(team_id), _now(now)
    rows = _rows(await client.request('f', future=team_id), CALENDAR_LIMIT)
    fixtures = [fixture for row in rows.values() if (fixture := _future(row, team_id, current))]
    fixtures.sort(key=lambda item: (item['start_at'], int(item['id'])))
    return {'team_id': team_id, 'retrieved_at': current.isoformat(timespec='seconds'),
            'fixtures': fixtures, 'excluded_count': len(rows)-len(fixtures)}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)) or isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 1_000_000_000 else None
    except (ValueError, OverflowError):
        return None


def _percentage(first, second):
    if first is None or second is None or first + second <= 0:
        return None
    # Keep each ratio precise until the average across matches is rounded.
    return 100 * first / (first + second)


def _stats(raw, fixture, opponent_id):
    def side_stats(side, expected_id):
        values = raw.get(side + ' team stats', raw.get(side + '_team_stats'))
        if not isinstance(values, dict) or 'id' in values and str(values['id']) != expected_id:
            return {}
        return {str(key).replace(' ', '_'): _number(value) for key, value in values.items()}

    own = side_stats(fixture['side'], opponent_id)
    other = side_stats('guest' if fixture['side'] == 'home' else 'home', fixture['opponent_id'])
    if not any(own.get(key) is not None for key in ('total_points', 'tries', 'possession', 'territory', 'metres_gained', 'missed_tackles', 'handling_errors', 'penalties_conceded', 'lineouts_won', 'scrums_won')):
        return None
    values = {'points_for': own.get('total_points'), 'points_against': other.get('total_points'),
              **{key: own.get(key) for key in ('tries', 'metres_gained', 'missed_tackles', 'handling_errors', 'penalties_conceded')},
              'possession_pct': _percentage(own.get('possession'), other.get('possession')),
              'territory_pct': _percentage(own.get('territory'), other.get('territory')),
              'lineouts_pct': _percentage(own.get('lineouts_won'), own.get('lineouts_lost')),
              'scrums_pct': _percentage(own.get('scrums_won'), own.get('scrums_lost'))}
    return values


async def scout_opponent(client, team_id, fixture_id, *, now=None):
    """Revalidate the chosen match, then inspect at most 20 opponents' fixtures.

    Statistics use the documented fixtureids-only query (both teams, no players).
    Up to four batches of five reads yield at most five matches with useful stats.
    """
    team_id, current = _club(team_id), _now(now)
    fixture_id = _id(fixture_id)
    if not fixture_id:
        raise ClassicError('Choisissez une rencontre valide dans le calendrier actualisé.')
    selected_rows = _rows(await client.request('f', fixtureid=fixture_id), 1)
    raw = selected_rows.get(fixture_id)
    selected = _future(raw, team_id, current) if raw else None
    if selected is None:
        raise ClassicError('Cette rencontre n’est plus à venir ou ne concerne pas ce club. Actualisez le calendrier.')
    opponent_id = selected['opponent_id']
    history = _rows(await client.request('f', teamid=opponent_id, last=str(HISTORY_LIMIT)), HISTORY_LIMIT)
    candidates = []
    for row in history.values():
        fixture, finish, start = _fixture(row, opponent_id), _date(row.get('matchfinish')), _date(row.get('matchstart'))
        # An absent bot flag is not proof that a full match was played.
        if fixture and row.get('botmatch') in (0, '0') and finish is not None and finish <= current and (start is None or start <= finish):
            candidates.append(fixture)
    candidates.sort(key=lambda item: (item['finish_at'], int(item['id'])), reverse=True)
    matches, missing = [], []
    for offset in range(0, len(candidates), MATCH_LIMIT):
        batch = candidates[offset:offset+MATCH_LIMIT]
        statistics = _rows(await client.request('fs', fixtureids=','.join(item['id'] for item in batch)), MATCH_LIMIT)
        for fixture in batch:
            values = _stats(statistics.get(fixture['id'], {}), fixture, opponent_id)
            if values is None:
                missing.append({'id': fixture['id'], 'finish_at': fixture['finish_at'], 'reason': 'Statistiques de cette équipe indisponibles.'})
            else:
                matches.append({**fixture, 'metrics': values})
                if len(matches) == MATCH_LIMIT:
                    break
        if len(matches) == MATCH_LIMIT:
            break
    summary = []
    for key, label, unit in METRICS:
        values = [row['metrics'][key] for row in matches if row['metrics'][key] is not None]
        summary.append({'key': key, 'label': label, 'unit': unit, 'average': round(sum(values)/len(values), 2) if values else None,
                        'sample_count': len(values)})
    return {'team_id': team_id, 'retrieved_at': current.isoformat(timespec='seconds'), 'fixture': selected,
            'opponent_id': opponent_id, 'matches': matches, 'missing_stats': missing, 'summary': summary,
            'history_count': len(history), 'eligible_count': len(candidates), 'excluded_count': len(history)-len(candidates),
            'history_limit': HISTORY_LIMIT, 'match_limit': MATCH_LIMIT,
            'methodology': [
                'Les 20 dernières rencontres retournées par Classic sont examinées ; au plus 5 matchs terminés, hors botmatch et avec statistiques utilisables sont retenus.',
                'Le filtre botmatch de Classic signale un match entre deux bots ; il ne prouve pas l’absence d’un seul adversaire bot.',
                'Le tri utilise la fin réelle du match en UTC. Les dates sans fuseau, matchs non terminés, bots et appartenances incohérentes sont exclus.',
                'Chaque moyenne utilise uniquement les valeurs connues ; sa couverture est indiquée séparément. Les données manquantes ne valent jamais zéro.',
                'Possession et territoire : part des secondes de cette équipe dans le total connu des deux équipes. Touches et mêlées : gagnées / (gagnées + perdues). Les pourcentages affichés sont ensuite moyennés par match.',
                'Ces observations ne constituent pas une tactique recommandée ni un pronostic. Aucun ordre ou changement de composition n’est envoyé dans Classic.',
            ]}
