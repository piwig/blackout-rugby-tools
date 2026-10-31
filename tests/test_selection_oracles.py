"""Synthetic independent oracles for selection and cumulative player statistics.

Expected results come from hand calculations and exhaustive permutations, not
the Hungarian solver or role-weight implementation under test. No game calls.
"""
from copy import deepcopy
from itertools import permutations, product
import random

import pytest

from server.domain import player_metrics
from server.optimization import make_lineup, maximum_assignment
from test_coaching import env, preview, confirm, bundle


NOW = '2026-10-31T12:00:00+00:00'
SKILLS = ('stamina', 'handling', 'attack', 'defense', 'technique',
          'strength', 'jumping', 'speed', 'agility', 'kicking')
ROLES = ('Pilier', 'Talonneur', 'Deuxième ligne', 'Troisième ligne',
         'Demi de mêlée', 'Demi d’ouverture', 'Centre', 'Ailier', 'Arrière')


def player(identifier, value=10, **fields):
    return {'id': str(identifier), 'name': f'Synthetic {identifier}',
            **dict.fromkeys(SKILLS, value), 'energy': 90, 'injured': False, **fields}


def test_hand_calculated_roles_and_local_csr_estimate_remain_separate_from_observed_csr():
    source = player(1, **dict(zip(SKILLS, range(0, 20, 2))), csr=123456)
    before = deepcopy(source)
    result = player_metrics(source)
    assert {role['name']: role['score'] for role in result['roles']} == {
        'Pilier': 7.67, 'Talonneur': 6.67, 'Deuxième ligne': 10.67,
        'Troisième ligne': 6.33, 'Demi de mêlée': 9.33,
        'Demi d’ouverture': 8, 'Centre': 7.33, 'Ailier': 13, 'Arrière': 11.33,
    }
    assert result['known_skills'] == 10 and result['skill_total'] == 90
    # 0.42 * (0^4 + 2^4 + ... + 18^4) = 0.42 * 245328 = 103037.76.
    assert result['estimated_csr'] == 103038
    assert source == before and source['csr'] == 123456


def test_single_positive_weight_requires_only_that_skill_and_keeps_zero_observed():
    weights = {role: {skill: int(skill == 'speed') for skill in SKILLS} for role in ROLES}
    result = player_metrics({'speed': 0}, role_weights=weights)
    assert result['known_skills'] == 1 and result['estimated_csr'] is None
    assert len(result['roles']) == 9 and all(role['score'] == 0 for role in result['roles'])
    for unknown in (None, 'Unknown', 'Low', 'Medium', 'High', True, '', 'NaN', 'Infinity'):
        assert player_metrics({'speed': unknown}, role_weights=weights)['roles'] == []


def exhaustive_assignment_value(matrix):
    """Enumerate every assignment, including vacancies; prioritize cardinality."""
    width = len(matrix[0]) if matrix else 0
    best = (0, 0)
    for assignment in product(range(-1, width), repeat=len(matrix)):
        used = [column for column in assignment if column >= 0]
        if len(used) != len(set(used)):
            continue
        if any(column >= 0 and matrix[row][column] is None for row, column in enumerate(assignment)):
            continue
        value = (len(used), sum(matrix[row][column] for row, column in enumerate(assignment) if column >= 0))
        if value > best:
            best = value
    return best


def test_exact_assignment_matches_exhaustive_small_matrices():
    rng = random.Random(20261031)
    matrices = [[], [[]], [[0]], [[None]], [[10, 9], [9, 0]], [[21, 0], [0, None]]]
    for _ in range(240):
        height, width = rng.randrange(1, 5), rng.randrange(0, 5)
        matrices.append([[rng.choice((None, 0, -1, 2.25, 6.67, 10, 21))
                          for _ in range(width)] for _ in range(height)])
    for matrix in matrices:
        assignment = maximum_assignment(matrix)
        used = [column for column in assignment if column is not None]
        assert len(assignment) == len(matrix) and len(set(used)) == len(used)
        actual = (len(used), sum(matrix[row][column] for row, column in enumerate(assignment)
                                 if column is not None))
        expected = exhaustive_assignment_value(matrix)
        assert actual[0] == expected[0], matrix
        assert actual[1] == pytest.approx(expected[1], abs=1e-8), matrix


def test_locked_and_required_lineup_matches_every_feasible_three_player_permutation():
    # Leave Pilier, Talonneur and Demi de mêlée free; all other slots are fixed.
    free_slots = (1, 2, 9)
    locks = {str(slot): str(100 + slot) for slot in range(1, 16) if slot not in free_slots}
    fixed = [player(identifier) for identifier in locks.values()]
    rng = random.Random(20261031)
    for iteration in range(36):
        pool = [player(i, **{skill: rng.randrange(0, 22) for skill in SKILLS}) for i in range(1, 6)]
        required = ['1'] if iteration % 2 == 0 else []
        excluded = ['5'] if iteration % 3 == 0 else []
        eligible = [p for p in pool if p['id'] not in excluded]
        best = max(
            round((prop['strength'] * 3 + prop['technique'] * 2 + prop['stamina']) / 6, 2)
            + round((hooker['handling'] * 2 + hooker['strength'] * 2 + hooker['technique'] * 2) / 6, 2)
            + round((half['handling'] * 3 + half['agility'] * 2 + half['kicking']) / 6, 2)
            for prop, hooker, half in permutations(eligible, 3)
            if set(required) <= {prop['id'], hooker['id'], half['id']}
        )
        result, _, _ = make_lineup(fixed + pool, {}, 'balanced', 60, 'percent', NOW,
                                   locks=locks, starter_ids=required, excluded_ids=excluded)
        actual = [p for p in result['players'] if p['slot'] in free_slots]
        assert len(actual) == 3 and sum(p['score'] for p in actual) == pytest.approx(best, abs=1e-8)
        assert all(result['slots'][slot] == identifier for slot, identifier in locks.items())
        assert set(required) <= {result['slots'][str(slot)] for slot in range(1, 16)}
        assert not set(excluded) & set(result['slots'].values())
        assert len(set(result['slots'].values())) == len(result['slots'])


def test_statistics_denominator_cases_are_manual_and_missing_is_not_zero(env):
    env.responses['p'] = {'status': 'Ok', 'players': {
        str(i): {'id': str(i), 'teamid': '123', 'name': f'Synthetic {i}'} for i in range(1, 8)}}
    env.responses['ps'] = {'status': 'Ok', 'player statistics': {
        '1': {'tackles': '3', 'missedtackles': '1', 'balltime': '7'},
        '2': {'tackles': '0', 'missedtackles': '0'},
        '3': {'tackles': '0', 'missedtackles': '2'},
        '4': {'tackles': '2', 'missedtackles': '0'},
        '5': {'tackles': '7'},
        '6': {'tackles': '2', 'missedtackles': '1', 'avkickingmetres': '12.3456'},
    }}
    response = preview(env, 'statistics', scope='league', season=61)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert [p['tackle_success_rate'] for p in data['players']] == [75, None, 0, 100, None, 66.67]
    assert data['players'][0]['counters']['carries'] == 7
    assert data['players'][0]['counters']['tries'] is None
    assert data['players'][5]['counters']['average_kicking_metres'] == 12.3456
    assert data['requested_count'] == 7 and data['missing_player_ids'] == ['7']
    assert data['scope'] == 'league' and data['season'] == 61


def test_statistics_a_b_a_and_idempotence_are_independent_for_each_period(env):
    # Interleave career, season 61 and season 62; an import in another period
    # must not change the latest digest against which a period is compared.
    periods = ({'scope': 'career'}, {'scope': 'league', 'season': 61}, {'scope': 'league', 'season': 62})
    for value in (1, 2, 1):
        for period in periods:
            env.responses['ps']['player statistics']['101']['tries'] = str(value)
            pending = preview(env, 'statistics', **period)
            assert pending.status_code == 200, pending.text
            saved = confirm(env, pending.json())
            assert saved.status_code == 200 and saved.json()['imported']
    for period in periods:
        repeated = preview(env, 'statistics', **period).json()
        assert repeated['already_imported']
        assert confirm(env, repeated).json()['unchanged']
    history = bundle(env).json()['statistics']
    assert len(history) == 9 and len({row['key'] for row in history}) == 9
    for period in periods:
        values = [row['players'][0]['counters']['tries'] for row in history
                  if row['scope'] == period['scope'] and row['season'] == period.get('season')]
        assert values == [1, 2, 1]
