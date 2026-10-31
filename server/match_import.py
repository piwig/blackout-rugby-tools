"""Bounded, offline match imports; never infer team identity or a final score."""
import csv
import json
import math
import re

from .classic import classify_attack
from .imports import read_csv, reject_constant


MAX_MATCH_BYTES = 8_000_000
MAX_MATCH_EVENTS = 20_000
EVENT_FIELDS = frozenset({
    'id', 'index', 'att', 'field', 'possession', 'text', 'commentary', 'comment',
    'time', 'minute', 'att_origin', 'possession_reported', 'gametime', 'half',
    'rule_version', 'actualtime', 'losttime', 'homescore', 'guestscore',
})
MATCH_FIELDS = frozenset({
    'id', 'type', 'home', 'away', 'home_score', 'away_score', 'events', 'season',
    'round', 'source_game_date', 'source_observed_at',
})
CLASSIC_FIELDS = frozenset({'status', 'fixtureid', 'brt', 'gameDate', 'game_date',
                           'u20', 'nat', 'homescore', 'guestscore'})


def read_match_document(raw, filename):
    if len(raw) > MAX_MATCH_BYTES:
        raise ValueError('Fichier limité à 8 Mo.')
    name = filename.lower()
    if name.endswith('.json'):
        try:
            return json.loads(raw.decode('utf-8-sig'), parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise ValueError('JSON invalide. Collez le document complet ou choisissez son fichier JSON.') from None
    if name.endswith('.csv'):
        try:
            rows = read_csv(raw, max_rows=MAX_MATCH_EVENTS)
        except csv.Error:
            raise ValueError('CSV invalide : un champ dépasse la taille autorisée ou une ligne est mal formée.') from None
        if not rows or not {'field', 'possession'}.issubset(rows[0]):
            raise ValueError('CSV : colonnes field et possession requises ; att et text conseillées.')
        return {'events': rows}
    raise ValueError('Format CSV ou JSON attendu.')


def _identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'[0-9]{1,15}', str(value).strip()):
        raise ValueError('Indiquez un identifiant de match numérique de 1 à 15 chiffres.')
    return str(value).strip()


def _flag(value):
    if value in (0, 1, '0', '1', False, True) and not isinstance(value, (list, dict, float)):
        return str(value).lower() in ('1', 'true')
    raise ValueError('Indicateur U20 ou national invalide.')


def _events(source):
    if not isinstance(source, (list, dict)) or len(source) > MAX_MATCH_EVENTS:
        raise ValueError('Les événements doivent former une liste ou un objet de 20 000 éléments maximum.')
    if any(not isinstance(event, dict) for event in (source.values() if isinstance(source, dict) else source)):
        raise ValueError('Chaque événement doit être un objet JSON.')
    ordered = isinstance(source, list)
    if isinstance(source, dict):
        rows = [{**event, **({'id': key} if 'id' not in event and re.fullmatch(r'[0-9]{1,15}', key) else {})}
                for key, event in source.items()]
        indexes = [str(event.get('index', '')) for event in rows]
        if indexes and all(re.fullmatch(r'[0-9]{1,18}', index) for index in indexes) and len({int(index) for index in indexes}) == len(indexes):
            rows.sort(key=lambda event: int(event['index']))
            ordered = True
    else:
        rows = source
    events = []
    previous = None
    for row in rows:
        event = {}
        for key, value in row.items():
            if key not in EVENT_FIELDS:
                continue
            if isinstance(value, (list, dict)) or isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Les champs d’un événement doivent contenir du texte ou des nombres finis.')
            event[key] = None if value is None else str(value)[:2000]
        reported = event.get('possession_reported', event.get('possession'))
        # Imported BRT classifications retain their provenance and orientation.
        if not event.get('att') and not event.get('att_origin'):
            raw = event.get('commentary', event.get('text', event.get('comment', ''))) or ''
            if 'text' not in event:
                event['text'] = re.sub(r'\[[^\]]+\]', '', raw)
            attack = classify_attack(raw)
            if attack:
                event.update(att=attack, att_origin='commentary-rule', rule_version='1')
                if ordered and previous in ('0', '1') and reported in ('0', '1') and previous != reported:
                    event['possession_reported'] = reported
                    event['possession'] = previous
        clock = event.get('gametime') or ''
        if 'time' not in event and clock.isdigit():
            seconds = int(clock)
            event['time'] = f'{seconds // 60}:{seconds % 60:02d}'
        if reported is not None:
            previous = reported
        events.append(event)
    return events


def normalize_match_document(source, *, match_id=None, match_type=None, home=None, away=None):
    if not isinstance(source, dict) or set(source) - MATCH_FIELDS - CLASSIC_FIELDS:
        raise ValueError('Objet match BRT ou réponse JSON Classic attendu.')
    if source.get('status') not in (None, 'Ok'):
        raise ValueError('Classic signale une erreur : ce document ne contient pas un match importable.')
    if 'fixtureid' in source and 'events' not in source:
        raise ValueError('Le document Classic ne contient pas de collection d’événements.')
    identifiers = [_identifier(value) for value in (source.get('id'), source.get('fixtureid'), match_id) if value not in (None, '')]
    if not identifiers:
        raise ValueError('Indiquez l’identifiant du match : il manque dans le document.')
    if len(set(identifiers)) != 1:
        raise ValueError('L’identifiant saisi ne correspond pas à celui du document.')
    kinds = [value for value in (source.get('type'), match_type) if value is not None]
    if not kinds or any(type(value) is not int or value not in (0, 1, 2) for value in kinds):
        raise ValueError('Choisissez explicitement le type du match : Club, U20 ou Sélection nationale.')
    if len(set(kinds)) != 1:
        raise ValueError('Le type choisi ne correspond pas à celui du document.')
    kind = kinds[0]
    for flag, expected_kind in (('u20', 1), ('nat', 2)):
        if flag in source and _flag(source[flag]) != (kind == expected_kind):
            raise ValueError('Le type choisi contredit les indicateurs U20 ou national du document.')
    result = {key: value for key, value in source.items() if key in MATCH_FIELDS}
    result.update(id=identifiers[0], type=kind, events=_events(source.get('events', [])))
    for key, selected, fallback in (('home', home, 'Domicile (nom non fourni)'),
                                    ('away', away, 'Extérieur (nom non fourni)')):
        value = selected if selected not in (None, '') else source.get(key)
        result[key] = value if value not in (None, '') else fallback
    # These are observations supplied by the API, not the match's date or final score.
    if 'source_game_date' not in result:
        result['source_game_date'] = source.get('gameDate', source.get('game_date'))
    if 'source_observed_at' not in result:
        result['source_observed_at'] = source.get('brt')
    for target, alias in (('home_score', 'homescore'), ('away_score', 'guestscore')):
        if target not in result and alias in source:
            result[target] = source[alias]
    return result
