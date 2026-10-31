"""Private historical match statistics, computed over every matching record."""
import json

from fastapi import Depends, HTTPException, Query

from .domain import ATTACKS, ZONES
from .match_review import effective_match


_UNKNOWN_NAMES = frozenset(('Domicile', 'Extérieur', 'Domicile (nom non fourni)', 'Extérieur (nom non fourni)'))


def _known_name(value):
    return isinstance(value, str) and bool(value.strip()) and value not in _UNKNOWN_NAMES


def _score(value):
    return value if type(value) is int and 0 <= value <= 999 else None


def _season(value):
    return value if type(value) is int and 0 <= value <= 1_000_000 else None


def _ratio(numerator, denominator):
    return round(100 * numerator / denominator, 2) if denominator else None


def _counts():
    return {'matches': 0, 'scored_matches': 0, 'events': 0, 'classified': 0,
            'unclassified': 0, 'non_attack': 0, 'manual': 0, 'inferred': 0, 'points_total': 0}


def _accumulate(counts, summary, home_score, away_score):
    counts['matches'] += 1
    counts['events'] += summary['total_events']
    for key in ('classified', 'unclassified', 'non_attack', 'manual', 'inferred'):
        counts[key] += summary.get(key, 0)
    if home_score is not None and away_score is not None:
        counts['scored_matches'] += 1
        counts['points_total'] += home_score + away_score


def match_history(store, *, kind=None, season=None, team=None, offset=0, limit=20):
    """Stream stored sources; only one page of compact match summaries is retained."""
    seasons, teams, types, selected_types, named_types = set(), set(), set(), set(), set()
    totals, by_season = _counts(), {}
    attacks, zones = dict.fromkeys(ATTACKS, 0), dict.fromkeys(ZONES, 0)
    record = {'played': 0, 'scored_matches': 0, 'won': 0, 'drawn': 0, 'lost': 0,
              'points_for': 0, 'points_against': 0}
    page, stored = [], 0
    if team is not None and not _known_name(team):
        raise HTTPException(422, 'Choisissez un nom d’équipe renseigné dans votre historique.')
    with store.db() as db:
        db.execute('BEGIN')
        rows = db.execute('SELECT id,type,payload,updated_at FROM matches ORDER BY updated_at DESC,type,id')
        for row in rows:
            stored += 1
            source = json.loads(row['payload'])
            match_type, match_season = row['type'], _season(source.get('season'))
            types.add(match_type)
            if match_season is not None:
                seasons.add(match_season)
            names = (source.get('home'), source.get('away'))
            teams.update(name for name in names if _known_name(name))
            if team is not None and team in names:
                named_types.add(match_type)
            if ((kind is not None and match_type != kind) or (season is not None and match_season != season)
                    or (team is not None and team not in names)):
                continue
            selected_types.add(match_type)
            match = effective_match(store, source)
            summary = match['summary']
            home_score, away_score = _score(match.get('home_score')), _score(match.get('away_score'))
            _accumulate(totals, summary, home_score, away_score)
            seasonal = by_season.setdefault(match_season, _counts())
            _accumulate(seasonal, summary, home_score, away_score)
            for side in ('home', 'away'):
                for attack in ATTACKS:
                    attacks[attack] += summary[side]['attacks'][attack]
                for zone in ZONES:
                    zones[zone] += sum(summary[side]['zones'][zone].values())
            if team is not None:
                record['played'] += 1
                if home_score is not None and away_score is not None and names[0] != names[1]:
                    points_for, points_against = ((home_score, away_score) if names[0] == team else (away_score, home_score))
                    record['scored_matches'] += 1
                    record['points_for'] += points_for
                    record['points_against'] += points_against
                    record['won' if points_for > points_against else 'lost' if points_for < points_against else 'drawn'] += 1
            if offset <= totals['matches'] - 1 < offset + limit:
                page.append({'id': row['id'], 'type': match_type,
                             'home': match.get('home'), 'away': match.get('away'),
                             'home_score': home_score, 'away_score': away_score,
                             'season': match_season, 'round': match.get('round'),
                             'summary': summary, 'event_count': summary['total_events'],
                             'updated_at': row['updated_at']})
    if team is not None and kind is None and len(named_types) > 1:
        raise HTTPException(422, 'Ce nom existe dans plusieurs types de matchs. Choisissez Club, U20 ou Sélection nationale.')
    totals['coverage_pct'] = _ratio(totals['classified'], totals['events'])
    totals['points_per_match'] = (round(totals['points_total'] / totals['scored_matches'], 2)
                                  if totals['scored_matches'] else None)
    if not totals['scored_matches']:
        totals['points_total'] = None
    seasonal_rows = []
    for match_season in sorted(by_season, key=lambda value: (value is None, -(value or 0))):
        values = by_season[match_season]
        seasonal_rows.append({'season': match_season,
            **{key: values[key] for key in ('matches', 'scored_matches', 'classified', 'events')},
            'points_total': values['points_total'] if values['scored_matches'] else None,
            'coverage_pct': _ratio(values['classified'], values['events'])})
    record['win_pct'] = _ratio(record['won'], record['scored_matches'])
    if not record['scored_matches']:
        record['points_for'] = record['points_against'] = None
    return {'filters': {'type': kind, 'season': season, 'team': team},
            'options': {'seasons': sorted(seasons, reverse=True), 'teams': sorted(teams, key=lambda name: (name.casefold(), name)), 'types': sorted(types)},
            'total_stored': stored, 'total_filtered': totals['matches'], 'offset': offset, 'limit': limit,
            'matches': page, 'totals': totals,
            'attacks': [{'name': name, 'count': count, 'percent': _ratio(count, totals['classified'])} for name, count in attacks.items()],
            'zones': [{'name': name, 'count': count, 'percent': _ratio(count, totals['classified'])} for name, count in zones.items()],
            'by_season': seasonal_rows, 'team_record': record if team is not None else None,
            'mixed_types': len(selected_types) > 1,
            'methodology': [
                'Les totaux portent sur tous les matchs conservés correspondant aux filtres, et non sur la seule page affichée.',
                'La liste est triée par date d’import ou de mise à jour ; cette date ne représente pas le coup d’envoi.',
                'Les options proviennent de toute la bibliothèque. Les noms importés sont comparés exactement ; un changement de nom reste distinct.',
                'Les répartitions comptent les attaques classées des deux équipes, dans les zones relatives à chacune. Leur dénominateur est le nombre total d’attaques classées.',
                'La couverture est le nombre d’attaques classées divisé par tous les événements. Les corrections manuelles sont prises en compte.',
                'Les points et résultats utilisent uniquement les matchs dont les deux scores sont connus. Un score nul est connu ; une valeur absente ne vaut pas zéro.',
                'Sans filtre de type, les totaux décrivent toute la bibliothèque, éventuellement Club, U20 et Nationale réunis. Sélectionnez un type pour comparer une équipe.',
                'Les évolutions regroupent uniquement les saisons fournies. Une saison inconnue reste séparée et aucune date de match n’est déduite.',
            ]}


def register_match_history(app, store, auth):
    @app.get('/api/matches/history', dependencies=[Depends(auth)])
    def get_match_history(type: int | None = Query(default=None, ge=0, le=2),
                          season: int | None = Query(default=None, ge=0, le=1_000_000),
                          team: str | None = Query(default=None, min_length=1, max_length=150),
                          offset: int = Query(default=0, ge=0),
                          limit: int = Query(default=20, ge=1, le=100)):
        return match_history(store, kind=type, season=season, team=team, offset=offset, limit=limit)
