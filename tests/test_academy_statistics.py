"""Independent examples for academy history: ambiguous data cannot measure gain."""
import json
from itertools import permutations

import pytest

from server.insights import academy_report
from server.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path, 'Synthetic-audit-password', seed=False)


def retain(store, at, players):
    # Retain every observation, including empty/unchanged rosters, to exercise
    # historical input independently of ingestion's deduplication policy.
    with store.db() as db:
        db.execute('INSERT INTO snapshots(team_id,youth,source,observed_at,imported_at,digest,payload) VALUES(?,?,?,?,?,?,?)',
                   ('1', 1, 'Synthetic', at, at, 'fixture', json.dumps(players)))


def timeline(store):
    return academy_report(store, '1', {}, {'goals': [], 'sessions': []})['timeline']


@pytest.mark.parametrize('batch', list(permutations([
    ('2026-01-02T08:00:00Z', [{'id': '42', 'strength': 6}]),
    ('2026-01-02T10:00:00+02:00', []),
])))
def test_presence_conflict_cannot_supply_either_end_of_numeric_comparison(store, batch):
    retain(store, '2026-01-01T08:00:00Z', [{'id': '42', 'strength': 5}])
    for at, players in batch:
        retain(store, at, players)
    retain(store, '2026-01-03T08:00:00Z', [{'id': '42', 'strength': 8}])
    retain(store, '2026-01-04T08:00:00Z', [{'id': '42', 'strength': 9}])
    events = timeline(store)
    # Day two could mean either presence or absence. Neither 5 -> 6 nor 6 -> 8
    # is comparable; the later unambiguous 8 -> 9 remains an observed +1.
    assert [(event['before'], event['after'], event['delta'])
            for event in events if event['kind'] == 'numeric_change'] == [(8, 9, 1)]
    assert any(event['kind'] == 'conflicting_observation' for event in events)


@pytest.mark.parametrize('instant', ['2026-01-01T12:00:00Z', '2026-01-01T14:00:00+02:00', '2026-01-01T12:00:00'])
@pytest.mark.parametrize('reverse', [False, True])
def test_calendar_date_and_same_day_instant_have_no_ordered_change(store, instant, reverse):
    observations = [('2026-01-01', 5), (instant, 6)]
    for at, value in reversed(observations) if reverse else observations:
        retain(store, at, [{'id': '42', 'strength': value}])
    assert timeline(store) == []


@pytest.mark.parametrize('invalid', [-1, 21.01, 1e100, 'Unknown', None, True])
def test_invalid_skill_to_numeric_zero_is_a_revelation_not_a_gain(store, invalid):
    retain(store, '2026-01-01', [{'id': '42', 'strength': invalid}])
    retain(store, '2026-01-02', [{'id': '42', 'strength': 0}])
    retain(store, '2026-01-03', [{'id': '42', 'strength': 1}])
    assert [(event['kind'], event['before'], event['after'], event['delta']) for event in timeline(store)] == [
        ('revealed', None, 0, None), ('numeric_change', 0, 1, 1)]


def test_absence_is_a_gap_and_unknown_is_not_zero(store):
    for day, players in [(1, [{'id': '42', 'strength': 4}]), (2, []),
                         (3, [{'id': '42', 'strength': 7}]),
                         (4, [{'id': '42', 'strength': None}]),
                         (5, [{'id': '42', 'strength': 0}])]:
        retain(store, f'2026-01-0{day}', players)
    assert [(event['kind'], event['before'], event['after'], event['delta']) for event in timeline(store)] == [
        ('revealed', None, 0, None)]


@pytest.mark.parametrize('invalid', [-1, 21.01])
def test_goal_gap_does_not_use_an_invalid_observed_skill(store, invalid):
    result = academy_report(store, '1', {'academy': [{'id': '42', 'strength': invalid}]},
                            {'goals': [{'player_id': '42', 'skill': 'strength', 'target': 10}], 'sessions': []})
    player = result['generations']['unknown'][0]
    assert player['current_value'] is None
    assert player['target_gap'] is None
