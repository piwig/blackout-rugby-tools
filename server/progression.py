"""Read-only history from retained snapshots, never training estimates or forecasts.

Dates are ordered before limiting payload reads. A boundary timestamp is discarded
if the row limit cuts its observation batch, so insertion order cannot choose a
winner. Legacy calendar dates and naive datetimes use UTC for sorting, with their
original precision retained. The ingestion layer may deduplicate unchanged
snapshots: absence of a point says nothing about the player's activity.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from itertools import groupby

from fastapi import Depends, Query
from .team_identity import TEAM_PATTERN

from .domain import SKILLS, number

SNAPSHOT_LIMIT = 240
PLAYER_LIMIT = 300
PLAYER_POINT_LIMIT = 12_000
PAYLOAD_LIMIT = 250_000
METRICS = ['csr', *SKILLS]
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?$')


def _stamp(value):
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _epoch(value):
    stamp = _stamp(value)
    return (stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() if stamp is not None else None


def _metric(player, metric):
    value = number(player.get(metric))
    maximum = 1_000_000_000_000 if metric == 'csr' else 21
    return value if value is not None and 0 <= value <= maximum else None


def progression_series(store, team_id, youth):
    """Select bounded metadata, then read payloads one at a time.

    Payloads over the byte budget are treated as an unreadable observation; the
    date remains a gap. Neither raw JSON strings nor unrelated legacy fields are
    retained for the complete history.
    """
    with store.db() as db:
        db.create_function('progression_epoch', 1, _epoch, deterministic=True)
        total, invalid_dates = db.execute(
            'SELECT COUNT(*),COALESCE(SUM(progression_epoch(substr(observed_at,1,80)) IS NULL),0) FROM snapshots WHERE team_id=? AND youth=?',
            (team_id, int(youth))).fetchone()
        rows = [dict(row) for row in db.execute(
            '''SELECT id,substr(observed_at,1,80) AS observed_at,substr(source,1,500) AS source,
                      CASE WHEN json_valid(payload) THEN COALESCE(json_array_length(payload),0) ELSE ? END AS player_count
               FROM snapshots WHERE team_id=? AND youth=? AND progression_epoch(substr(observed_at,1,80)) IS NOT NULL
               ORDER BY progression_epoch(substr(observed_at,1,80)) DESC,id DESC LIMIT ?''',
            (PLAYER_LIMIT, team_id, int(youth), SNAPSHOT_LIMIT + 1))]
    selected, boundary_excluded = rows[:SNAPSHOT_LIMIT], 0
    if len(rows) > SNAPSHOT_LIMIT:
        cutoff = _stamp(rows[-1]['observed_at'])
        # Drop the whole partial batch, including UTC-equivalent date strings.
        complete = [row for row in selected if _stamp(row['observed_at']) != cutoff]
        boundary_excluded = len(selected) - len(complete)
        selected = complete
    # A separate bound on the normalized response prevents huge histories of
    # many players from exhausting memory during FastAPI's JSON serialization.
    # Use an upper bound on distinct players and retain whole timestamp batches.
    budgeted, player_points = [], 0
    for _, batch in groupby(selected, key=lambda row: _stamp(row['observed_at'])):
        batch = list(batch)
        cost = min(PLAYER_LIMIT, sum(row['player_count'] for row in batch))
        if player_points + cost > PLAYER_POINT_LIMIT:
            break
        budgeted.extend(batch)
        player_points += cost
    budget_excluded = len(selected) - len(budgeted)
    selected = sorted(budgeted, key=lambda row: _stamp(row['observed_at']))
    points, catalog, previous, previous_roster_signature = [], {}, None, None
    invalid_payloads, invalid_players, omitted_players, usable_snapshots = 0, 0, 0, 0
    for stamp, batch in groupby(selected, key=lambda row: _stamp(row['observed_at'])):
        observations, roster_signatures, sources = {}, set(), set()
        malformed_batch, truncated_players = False, False
        batch_rows, largest_id, maximum_roster_count = 0, None, 0
        for row in batch:
            original = row['observed_at']
            precision = 'day' if len(original) == 10 else 'naive' if datetime.fromisoformat(original.replace('Z', '+00:00')).tzinfo is None else 'instant'
            sources.add((original, str(row['source'])[:500], precision))
            try:
                with store.db() as db:
                    stored = db.execute('SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END FROM snapshots WHERE id=? AND team_id=? AND youth=?',
                                        (PAYLOAD_LIMIT, row['id'], team_id, int(youth))).fetchone()
                    payload = json.loads(stored[0] if stored else None)
                del stored
                if not isinstance(payload, list):
                    raise ValueError('Player list required')
            except (ValueError, TypeError):
                invalid_payloads += 1
                malformed_batch = True
                continue
            usable_snapshots += 1
            batch_rows += 1
            roster = set()
            for player in payload:
                if not isinstance(player, dict) or not re.fullmatch(r'[0-9]{1,15}', str(player.get('id', ''))):
                    invalid_players += 1
                    malformed_batch = True
                    continue
                pid = str(player['id'])
                roster.add(pid)
                # Keep the lexicographically smallest IDs. Once an ID has been
                # discarded it cannot re-enter as this threshold only decreases;
                # consequently retained IDs never lose an earlier observation.
                if pid not in observations:
                    if len(observations) == PLAYER_LIMIT:
                        truncated_players = True
                        if pid > largest_id:
                            continue
                        del observations[largest_id]
                    observations[pid] = {'name': str(player.get('name') or pid)[:120],
                                         'values': {metric: _metric(player, metric) for metric in METRICS},
                                         'conflicts': set(), 'seen_rows': 1, 'last_row': row['id']}
                    largest_id = max(observations)
                    continue
                merged = observations[pid]
                merged['name'] = min(merged['name'], str(player.get('name') or pid)[:120])
                if merged['last_row'] != row['id']:
                    merged['seen_rows'] += 1
                    merged['last_row'] = row['id']
                for metric in METRICS:
                    if metric not in merged['conflicts'] and merged['values'][metric] != _metric(player, metric):
                        merged['conflicts'].add(metric)
                        merged['values'][metric] = None
            maximum_roster_count = max(maximum_roster_count, len(roster))
            # One bounded digest replaces each complete per-snapshot roster set.
            roster_signatures.add(hashlib.sha256('\0'.join(sorted(roster)).encode()).hexdigest())
        ids = sorted(observations)
        roster_count = max(maximum_roster_count, PLAYER_LIMIT + 1) if truncated_players else len(ids)
        roster_count_exact = not truncated_players or len(roster_signatures) == 1
        omitted_players += max(0, roster_count - PLAYER_LIMIT)
        roster_conflict = malformed_batch or len(roster_signatures) > 1
        roster_signature = tuple(sorted(roster_signatures))
        date_precision = bool(previous and previous['at'][:10] == stamp.date().isoformat()
                              and (any(item[2] == 'day' for item in sources)
                                   or any(item['precision'] == 'day' for item in previous['sources'])))
        players = {}
        for pid in ids:
            merged = observations[pid]
            catalog[pid] = merged['name']
            values, conflicts, revealed, deltas = {}, [], [], {}
            presence_conflict = malformed_batch or merged['seen_rows'] != batch_rows
            old = previous['players'].get(pid) if previous else None
            for metric in METRICS:
                conflict = metric in merged['conflicts']
                value = merged['values'][metric]
                values[metric] = value
                if conflict:
                    conflicts.append(metric)
                elif old and value is not None and metric not in old['conflicts'] and not presence_conflict and not old['presence_conflict'] and not date_precision:
                    before = old['values'][metric]
                    if before is None:
                        revealed.append(metric)
                    else:
                        deltas[metric] = round(value - before, 4)
            players[pid] = {'values': values, 'conflicts': conflicts, 'revealed': revealed,
                            'deltas': deltas, 'presence_conflict': presence_conflict}
        all_ids = set(observations)
        prior_ids = set(previous['roster_ids']) if previous else set()
        point = {'at': stamp.isoformat(),
                 'sources': [{'observed_at': at, 'source': source, 'precision': precision} for at, source, precision in sorted(sources)],
                 'roster_ids': ids, 'roster_count': roster_count, 'roster_count_exact': roster_count_exact,
                 'roster_conflict': roster_conflict,
                 'roster_changed': previous is not None and roster_signature != previous_roster_signature,
                 'entered': sorted(all_ids - prior_ids) if previous and not truncated_players and not previous['players_truncated'] else [],
                 'left': sorted(prior_ids - all_ids) if previous and not truncated_players and not previous['players_truncated'] else [],
                 'date_precision': date_precision,
                 'players_truncated': truncated_players, 'players': players, 'metrics': {}}
        for metric in METRICS:
            known_ids = {pid for pid, player in players.items() if player['values'][metric] is not None}
            conflict_count = sum(metric in player['conflicts'] for player in players.values())
            # Divide before summing: finite bounded values cannot overflow a mean.
            value = round(sum(players[pid]['values'][metric] / len(known_ids) for pid in known_ids), 4) if known_ids and not truncated_players else None
            old_metric = previous['metrics'][metric] if previous else None
            old_known = {pid for pid, player in previous['players'].items() if player['values'][metric] is not None} if previous else set()
            if not previous:
                comparison = 'first_observation'
            elif roster_conflict or previous['roster_conflict'] or conflict_count or old_metric['conflict_count']:
                comparison = 'conflicting_observation'
            elif truncated_players or previous['players_truncated']:
                comparison = 'truncated_roster'
            elif date_precision:
                comparison = 'date_precision'
            elif point['roster_changed']:
                comparison = 'roster_changed'
            elif known_ids != old_known:
                comparison = 'coverage_changed'
            elif value is None:
                comparison = 'unknown'
            else:
                comparison = 'comparable'
            point['metrics'][metric] = {'value': value, 'known_count': len(known_ids),
                                        'unknown_count': roster_count - len(known_ids), 'conflict_count': conflict_count,
                                        'delta': round(value - old_metric['value'], 4) if comparison == 'comparable' else None,
                                        'comparison': comparison}
        points.append(point)
        previous = point
        previous_roster_signature = roster_signature
    return {'points': points, 'players': [{'id': pid, 'name': name} for pid, name in sorted(catalog.items())],
            'total_snapshots': total, 'snapshot_count': usable_snapshots, 'snapshot_limit': SNAPSHOT_LIMIT,
            'invalid_dates': invalid_dates, 'invalid_payloads': invalid_payloads, 'invalid_players': invalid_players,
            'history_truncated': total - invalid_dates > SNAPSHOT_LIMIT or budget_excluded > 0,
            'excluded_boundary_snapshots': boundary_excluded, 'player_limit': PLAYER_LIMIT,
            'player_point_limit': PLAYER_POINT_LIMIT, 'budget_truncated_snapshots': budget_excluded,
            'omitted_player_observations': omitted_players,
            'from': points[0]['at'] if points else None, 'to': points[-1]['at'] if points else None}


def register_progression(app, store, auth, require_team):
    @app.get('/api/progression')
    def get_progression(team_id: str = Query(pattern=TEAM_PATTERN), session=Depends(auth)):
        require_team(team_id)
        return {'team_id': team_id, 'metrics': METRICS,
                'seniors': progression_series(store, team_id, False),
                'academy': progression_series(store, team_id, True)}
