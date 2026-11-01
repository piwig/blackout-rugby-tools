"""Chronology shared by explicit previews and the compatible legacy import."""
import json
import re
from datetime import datetime, timezone


def _game_order(value):
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    result = []
    for key, maximum in (('season', 999), ('round', 16), ('day', 7)):
        number = value.get(key)
        if (isinstance(number, bool) or not isinstance(number, (str, int))
                or not re.fullmatch(r'[0-9]{1,3}', str(number)) or not 1 <= int(number) <= maximum):
            return None
        result.append(int(number))
    return tuple(result)


def older_observation(observed_at, game_date, current, *, clock=None):
    """Compare changed content only; a date without time cannot order its day."""
    try:
        previous = datetime.fromisoformat((current['last_observed_at'] or current['observed_at']).replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        return False
    clock = datetime.fromisoformat(clock.replace('Z', '+00:00')) if clock else datetime.now(timezone.utc)
    previous_instant = previous.replace(tzinfo=timezone.utc) if previous.tzinfo is None else previous
    # A corrupt legacy timestamp cannot make its associated game date an
    # authoritative lower bound that blocks a valid current observation.
    if previous_instant > clock:
        return False
    try:
        incoming = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
        if previous.tzinfo is not None and incoming.tzinfo is not None:
            if incoming < previous:
                return True
        elif incoming.date() < previous.date():
            return True
    except (ValueError, TypeError, AttributeError):
        pass
    previous_game = _game_order(current['last_game_date'] or current['game_date'])
    incoming_game = _game_order(game_date)
    return bool(previous_game and incoming_game and incoming_game < previous_game)
