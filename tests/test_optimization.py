"""Behavioral checks for private, read-only preparation advice."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import importlib
import json

import pytest
from fastapi.testclient import TestClient

from server.domain import SKILLS, attack_summary
from server.main import create_app


NOW = '2026-10-30T12:00:00+00:00'


def engine():
    # Keep collection usable before the module exists: the first run is a real failure.
    try:
        return importlib.import_module('server.optimization')
    except ModuleNotFoundError:
        pytest.fail('The optimization engine has not been implemented yet.')


def player(ident, value=10, **fields):
    return {'id': str(ident), 'name': 'Player '+str(ident),
            **dict.fromkeys(SKILLS, value), 'energy': 80, 'age': 25, **fields}


def state(squad=None, academy=None, **fields):
    return {'current_team': {'id': '72450', 'name': 'Club', 'country': 'BE', 'meta': {}},
            'squad': squad or [], 'academy': academy or [], 'lineup': {}, 'plans': {},
            'matches': [], 'game_date': {'season': 62, 'round': 9, 'day': 6},
            'squad_source': {'observed_at': NOW, 'source': 'Test'},
            'academy_source': {'observed_at': NOW, 'source': 'Test'}, **fields}


def report(data, **options):
    return engine().build_report(data, generated_at=NOW, **options)


def test_global_assignment_beats_greedy_and_preserves_zero_and_missing_edges():
    assert engine().maximum_assignment([[10, 9], [9, 0]]) == [1, 0]
    assert engine().maximum_assignment([[None, 0], [None, None]]) == [1, None]
    # Fill the greatest possible number of positions before maximizing scores.
    assert engine().maximum_assignment([[21, 0], [0, None]]) == [1, 0]


def test_lineup_has_unique_starters_and_eight_distinct_reserves_without_mutation():
    data = state([player(i) for i in range(1, 25)])
    original = deepcopy(data)
    result = report(data)
    assert len(result['lineup']['slots']) == len(set(result['lineup']['slots'].values())) == 23
    assert result['summary']['selected'] == 15
    assert result['lineup']['unfilled'] == []
    assert len([p for p in result['lineup']['players'] if p['slot'] > 15]) == 8
    assert data == original


@pytest.mark.parametrize('marker', ['0', 'False', 'false', False, 0, 'no', ''])
def test_false_injury_markers_do_not_exclude_a_player(marker):
    result = report(state([player(1, injured=marker)]))
    assert result['summary']['eligible'] == 1
    assert result['summary']['selected'] == 1


@pytest.mark.parametrize('marker', ['1', 'True', True, 'yes', 'injured'])
def test_explicit_injury_excludes_a_player(marker):
    result = report(state([player(1, injured=marker)]))
    assert result['summary']['eligible'] == 0
    assert result['lineup']['excluded'][0]['id'] == '1'


def test_zero_energy_is_not_unknown_and_floor_is_inclusive():
    data = state([player(1, energy=0), player(2, energy=None), player(3, energy=60), player(4, energy=59)])
    result = report(data, energy_floor=60)
    assert result['summary']['eligible'] == 2
    assert result['summary']['unknown_energy'] == 1
    assert result['summary']['low_energy'] == 2
    assert set(result['lineup']['slots'].values()) == {'2', '3'}
    assert next(p for p in result['lineup']['players'] if p['id'] == '2')['energy'] is None
    assert report(data, energy_floor=0)['summary']['eligible'] == 4
    assert report(state([player(1, energy=100), player(2, energy=99)]), energy_floor=100)['summary']['eligible'] == 1


def test_unknown_skills_leave_roles_unfilled_instead_of_becoming_zero():
    result = report(state([{'id': '1', 'name': 'Hidden', 'strength': 'Unknown', 'energy': 90}]))
    assert result['summary']['selected'] == 0
    assert result['lineup']['unfilled'] == list(range(1, 16))
    assert result['lineup']['comparison'] == {'saved_score': None, 'proposed_score': None, 'delta': None}


def test_recovery_and_development_use_only_known_bonus_values():
    data = state([player(i) for i in range(1, 17)])
    data['squad'][0].update(energy=110, age=20)
    data['squad'][1].update(energy=None, age=None)
    recovery = report(data, objective='recovery')
    development = report(data, objective='development')
    assert next(p for p in recovery['lineup']['players'] if p['id'] == '1')['score'] == 13
    assert next(p for p in recovery['lineup']['players'] if p['id'] == '2')['score'] == 10
    assert next(p for p in development['lineup']['players'] if p['id'] == '1')['score'] == 13
    assert next(p for p in development['lineup']['players'] if p['id'] == '2')['score'] == 10


def test_percent_energy_supports_110_and_ignores_out_of_range_observations():
    result = report(state([player(1, energy=110), player(2, energy=111)]), energy_floor=110)
    assert result['summary']['unknown_energy'] == 1
    assert next(p for p in result['lineup']['players'] if p['id'] == '1')['energy'] == 110
    assert next(p for p in result['lineup']['players'] if p['id'] == '2')['energy'] is None


def test_ambiguous_auto_energy_never_treats_levels_as_low_percentages():
    data = state([player(1, energy=9), player(2, energy=0)])
    result = report(data, objective='recovery')
    assert result['summary']['low_energy'] == 0
    assert result['summary']['unknown_energy'] == 2
    assert result['summary']['eligible'] == 2
    assert all(p['energy'] is None and p['score'] == 10 for p in result['lineup']['players'])
    assert result['warnings']
    percent = report(data, energy_scale='percent')
    assert percent['summary']['eligible'] == 0
    levels = report(data, energy_scale='level')
    assert next(p for p in levels['lineup']['players'] if p['id'] == '1')['energy'] == 90
    assert next(p for p in levels['lineup']['players'] if p['id'] == '2')['energy'] is None


@pytest.mark.parametrize('injured,eligible', [
    ('-001-11-30T00:00:00+12:00', 1),
    ('2023-04-02T00:00:00+12:00', 1),
    ('2026-10-31T00:00:00+12:00', 1),  # Equal to report time.
    ('2026-10-31T00:01:00+12:00', 0),
    ('2026-12-01T00:00:00+12:00', 0),
])
def test_classic_injury_timestamps_respect_offsets_and_the_empty_sentinel(injured, eligible):
    assert report(state([player(1, injured=injured)]))['summary']['eligible'] == eligible


@pytest.mark.parametrize('injured,eligible', [
    (1700000000, 1), ('1700000000', 1),  # 2023-11-14 UTC.
    (2000000000, 0), ('2000000000', 0),  # 2033-05-18 UTC.
    ('2026-11-10 12:00:00+12:00', 0),
])
def test_numeric_injury_timestamps_are_compared_with_report_time(injured, eligible):
    assert report(state([player(1, injured=injured)]))['summary']['eligible'] == eligible


def test_comparison_requires_complete_valid_eligible_saved_xv():
    data = state([player(i, value=10) for i in range(1, 17)],
                 lineup={str(i): str(i) for i in range(1, 16)})
    assert report(data)['lineup']['comparison'] == {'saved_score': 150, 'proposed_score': 150, 'delta': 0}
    for invalid in [{'1': '1'}, {str(i): '1' for i in range(1, 16)}, {str(i): '999' if i == 1 else str(i) for i in range(1, 16)}]:
        data['lineup'] = invalid
        assert report(data)['lineup']['comparison']['delta'] is None
    data['lineup'] = {str(i): str(i) for i in range(1, 16)}
    data['squad'][0]['energy'] = 0
    assert report(data)['lineup']['comparison']['delta'] is None


def test_training_uses_known_academy_means_preserves_cells_and_never_fills_past():
    grid = [['']*16 for _ in range(4)]
    grid[0][0] = 'speed'
    grid[2][12] = 'kicking'
    data = state(academy=[{'id': '1', 'name': 'A', 'strength': 0, 'handling': 'Unknown'},
                         {'id': '2', 'name': 'B', 'strength': 10, 'handling': 8}], plans={'62': grid})
    original = deepcopy(data)
    training = report(data, season=62)['training']
    assert training['grid'][0][0] == 'speed'
    assert training['grid'][2][12] == 'kicking'
    assert all(training['grid'][row][week] == grid[row][week] for row in range(4) for week in range(8))
    assert training['added'] == 31 and training['preserved'] == 2
    assert training['start_week'] == 9 and training['remaining_weeks'] == 8
    strength = next(p for p in training['priorities'] if p['skill'] == 'strength')
    assert strength['average'] == 5 and strength['count'] == 2
    assert next(p for p in training['priorities'] if p['skill'] == 'handling')['average'] == 8
    assert data == original


def test_old_season_and_unknown_calendar_add_nothing_future_starts_at_one():
    data = state(academy=[player(1)])
    assert report(data, season=61)['training']['added'] == 0
    assert report(data, season=61)['training']['remaining_weeks'] == 0
    assert report(data, season=63)['training']['added'] == 64
    assert report(data, season=63)['training']['start_week'] == 1
    data['game_date'] = None
    assert report(data, season=62)['training']['added'] == 0
    assert report(state(), season=62)['training']['added'] == 0


def test_match_library_has_real_denominators_both_sides_and_no_weak_sample_verdict():
    events = ([{'field': 1, 'possession': 0, 'att': 'percu'}]*3
              + [{'field': 1, 'possession': 1, 'att': 'large', 'att_origin': 'commentary-rule'}]
              + [{'text': 'unclassified'}]*16)
    match = {'id': '9', 'type': 1, 'home': 'Other A', 'away': 'Other B', 'summary': attack_summary(events)}
    result = report(state(matches=[match]))
    actual = result['matches'][0]
    assert (actual['classified'], actual['total'], actual['inferred'], actual['coverage']) == (4, 20, 1, 20)
    assert [s['actions'] for s in actual['sides']] == [3, 1]
    assert all(side['dominant'] is None and side['share'] is None for side in actual['sides'])
    assert all(side['advice'] and side['evidence'] for side in actual['sides'])


def test_match_observation_requires_good_coverage_and_twenty_actions_for_that_side():
    events = ([{'field': 1, 'possession': 0, 'att': 'percu'}]*20
              + [{'field': 1, 'possession': 1, 'att': 'large'}]*2)
    match = {'id': '9', 'type': 0, 'home': 'A', 'away': 'B', 'summary': attack_summary(events)}
    actual = report(state(matches=[match]))['matches'][0]
    assert actual['sides'][0]['dominant'] == 'Percussion'
    assert actual['sides'][0]['share'] == 100
    assert actual['sides'][1]['dominant'] is None


@pytest.mark.parametrize('attack,skills', [
    ('large', ['Vitesse', 'Agilité', 'Défense']),
    ('percu', ['Force', 'Technique', 'Défense']),
    ('png', ['Force', 'Technique', 'Défense']),
    ('crea', ['Dextérité', 'Attaque']),
    ('kick', ['Jeu au pied', 'arrière']),
])
def test_preparation_advice_follows_observed_style_only_with_sufficient_coverage(attack, skills):
    events = [{'field': 1, 'possession': 0, 'att': attack}]*20
    match = {'id': '9', 'type': 0, 'home': 'A', 'away': 'B', 'summary': attack_summary(events)}
    side = report(state(matches=[match]))['matches'][0]['sides'][0]
    assert all(skill in ' '.join(side['advice']) for skill in skills)
    match['summary'] = attack_summary(events + [{'text': 'unclassified'}]*21)
    side = report(state(matches=[match]))['matches'][0]['sides'][0]
    assert side['dominant'] is None
    assert not any(skill in ' '.join(side['advice']) for skill in skills)


def test_stadium_only_gets_numeric_advice_with_complete_capacity_data():
    data = state()
    partial = report(data)
    assert not any(r['category'] == 'stadium' for r in partial['recommendations'])
    data['current_team']['meta'] = {'members': 1000, **{'stadium_'+k: 0 for k in ['standing', 'uncovered', 'covered', 'members', 'corporate']}}
    full = report(data)
    assert any(r['category'] == 'stadium' for r in full['recommendations'])


def sign_in(client, username='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def test_optimization_endpoint_auth_validation_and_read_only(tmp_path):
    with TestClient(create_app(tmp_path, 'Testing-password-1234', secure=False)) as client:
        assert client.get('/api/optimization?team_id=72450').status_code == 401
        headers = sign_in(client)
        assert client.post('/api/import', headers=headers, data={'team_id': '72450', 'youth': 'false'},
                           files={'file': ('squad.json', json.dumps([player(i) for i in range(1, 24)]).encode())}).status_code == 200
        before = client.get('/api/export').json()
        response = client.get('/api/optimization?team_id=72450&season=62')
        assert response.status_code == 200, response.text
        assert response.json()['reports'][0]['team']['id'] == '72450'
        after = client.get('/api/export').json()
        before.pop('exported_at'); after.pop('exported_at')
        assert before == after
        assert client.get('/api/optimization?team_id=999').status_code == 404
        for query in ['objective=bad', 'energy_floor=-1', 'energy_floor=111', 'energy_floor=nan', 'energy_scale=bad', 'season=0', 'season=1000', 'scope=other', 'team_id=abc']:
            prefix = '' if query.startswith('team_id=') else 'team_id=72450&'
            assert client.get('/api/optimization?'+prefix+query).status_code == 422


def test_all_scope_never_leaks_another_managers_teams_or_matches(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with TestClient(app) as admin, TestClient(app) as other:
        headers = sign_in(admin)
        assert admin.post('/api/admin/users', headers=headers, json={'username': 'franck', 'password': 'Another-password-5678'}).status_code == 200
        other_headers = sign_in(other, 'franck', 'Another-password-5678')
        assert other.get('/api/optimization?scope=all').json() == {'reports': []}
        assert admin.post('/api/matches/import', headers=headers, json={'id': '9', 'type': 0, 'home': 'private-admin', 'away': 'B', 'events': []}).status_code == 200
        for ident in ['101', '102']:
            assert other.post('/api/teams', headers=other_headers, json={'team_id': ident, 'name': 'private-'+ident, 'country': 'BE'}).status_code == 200
        response = other.get('/api/optimization?team_id=101&scope=all')
        assert response.status_code == 200, response.text
        assert {r['team']['id'] for r in response.json()['reports']} == {'101', '102'}
        assert 'private-admin' not in response.text
        assert other.get('/api/optimization?team_id=72450').status_code == 404
        assert other.get('/api/optimization?team_id=72450&scope=all').status_code == 404


@pytest.mark.parametrize('resource', ['plans', 'lineup'])
def test_stale_previews_cannot_overwrite_another_session_and_legacy_saves_still_work(tmp_path, resource):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    empty = [['']*16 for _ in range(4)]
    first_grid, second_grid = deepcopy(empty), deepcopy(empty)
    first_grid[0][0], second_grid[0][0] = 'strength', 'speed'
    if resource == 'plans':
        first = {'team_id': '72450', 'season': 62, 'grid': first_grid, 'expected_grid': empty}
        stale = {'team_id': '72450', 'season': 62, 'grid': second_grid, 'expected_grid': empty}
        key, expected_key = 'grid', 'expected_grid'
        def saved(client): return client.get('/api/state?team_id=72450').json()['plans']['62']
    else:
        first = {'team_id': '72450', 'slots': {'1': '42'}, 'expected_slots': {}}
        stale = {'team_id': '72450', 'slots': {'2': '43'}, 'expected_slots': {}}
        key, expected_key = 'slots', 'expected_slots'
        def saved(client): return client.get('/api/state?team_id=72450').json()['lineup']
    with TestClient(app) as a, TestClient(app) as b:
        ah, bh = sign_in(a), sign_in(b)
        assert a.post('/api/'+resource, headers=ah, json=first).status_code == 200
        response = b.post('/api/'+resource, headers=bh, json=stale)
        assert response.status_code == 409, response.text
        assert saved(b) == first[key]
        # Recalculated preview based on the current observation is accepted.
        stale[expected_key] = first[key]
        assert b.post('/api/'+resource, headers=bh, json=stale).status_code == 200
        # Older screens without the optional precondition keep their contract.
        first.pop(expected_key)
        assert a.post('/api/'+resource, headers=ah, json=first).status_code == 200
        assert saved(a) == first[key]


@pytest.mark.parametrize('resource', ['plans', 'lineup'])
def test_competing_previews_have_exactly_one_atomic_winner(tmp_path, resource):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    empty = [['']*16 for _ in range(4)]
    with TestClient(app) as a, TestClient(app) as b:
        ah, bh = sign_in(a), sign_in(b)
        if resource == 'plans':
            bodies = []
            for skill in ('strength', 'speed'):
                grid = deepcopy(empty)
                grid[0][0] = skill
                bodies.append({'team_id': '72450', 'season': 62, 'grid': grid, 'expected_grid': empty})
            def saved(): return a.get('/api/state?team_id=72450').json()['plans']['62']
            key = 'grid'
        else:
            bodies = [{'team_id': '72450', 'slots': {'1': ident}, 'expected_slots': {}} for ident in ('42', '43')]
            def saved(): return a.get('/api/state?team_id=72450').json()['lineup']
            key = 'slots'
        def submit(args):
            client, headers, body = args
            return client.post('/api/'+resource, headers=headers, json=body)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(submit, [(a, ah, bodies[0]), (b, bh, bodies[1])]))
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(i for i, result in enumerate(results) if result.status_code == 200)
        assert saved() == bodies[winner][key]
