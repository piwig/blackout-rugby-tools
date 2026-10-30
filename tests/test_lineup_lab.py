"""Constraints and private, revisioned preparation scenarios; no game calls."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import importlib
import inspect
import json

import pytest
from fastapi.testclient import TestClient

from server.domain import SKILLS
from server.main import create_app
from server.optimization import make_lineup


NOW = '2026-10-30T12:00:00+00:00'
PASSWORD = 'Testing-password-1234'


def player(identifier, value=10, **fields):
    return {'id': str(identifier), 'name': 'Joueur '+str(identifier),
            **dict.fromkeys(SKILLS, value), 'energy': 90, 'injured': False, **fields}


def lineup(squad, **options):
    return make_lineup(squad, {}, 'balanced', 60, 'percent', NOW, **options)[0]


def test_locked_position_and_required_starter_survive_optimization_without_duplicates():
    squad = [player(i, 20) for i in range(1, 24)] + [player(24, 1)]
    original = deepcopy(squad)
    result = lineup(squad, locks={'9': '23'}, starter_ids=['24'], excluded_ids=['1'])
    assert result['slots']['9'] == '23'
    assert '24' in [ident for slot, ident in result['slots'].items() if int(slot) <= 15]
    assert '1' not in result['slots'].values()
    assert len(result['slots']) == len(set(result['slots'].values())) == 23
    assert squad == original


@pytest.mark.parametrize('options', [
    {'locks': {'1': '1', '2': '1'}}, {'locks': {'16': '1'}},
    {'locks': {'1': '99'}}, {'locks': {'1': '1'}, 'excluded_ids': ['1']},
    {'starter_ids': ['99']}, {'starter_ids': ['1'], 'excluded_ids': ['1']},
])
def test_inconsistent_constraints_are_rejected(options):
    with pytest.raises(ValueError):
        lineup([player(1), player(2)], **options)


def test_lock_does_not_override_injury_or_missing_role_skills():
    with pytest.raises(ValueError):
        lineup([player(1, injured=True)], locks={'1': '1'})
    with pytest.raises(ValueError):
        lineup([player(1, handling=None)], locks={'2': '1'})


def test_bench_adds_role_coverage_before_another_stronger_duplicate_specialist():
    starters = [player(i, 21) for i in range(1, 16)]
    # Eight stronger forwards cannot cover the backs. One lower-scored reserve can.
    forwards = [{'id': str(i), 'name': 'Avant '+str(i), 'strength': 18,
                 'technique': 18, 'stamina': 18, 'energy': 90, 'injured': False}
                for i in range(16, 24)]
    result = lineup(starters+forwards+[player(24, 10)], locks={str(i): str(i) for i in range(1, 16)})
    assert '24' in [p['id'] for p in result['players'] if p['slot'] > 15]
    assert result['bench_coverage']['gaps'] == []
    without_backs = lineup(starters+forwards, locks={str(i): str(i) for i in range(1, 16)})
    assert 'Arrière' in without_backs['bench_coverage']['gaps']
    assert 'Talonneur' in without_backs['bench_coverage']['gaps']
    assert next(r for r in without_backs['bench_coverage']['roles'] if r['role'] == 'Pilier')['missing'] == 0


def app_with_lab(tmp_path):
    app = create_app(tmp_path, PASSWORD, secure=False)
    if not any(getattr(route, 'path', '') == '/api/lineup-lab/scenarios' for route in app.routes):
        try:
            module = importlib.import_module('server.lineup_lab')
        except ModuleNotFoundError:
            pytest.fail('Le module de scénarios de composition est absent.')
        state_route = next(route for route in app.routes if getattr(route, 'path', '') == '/api/state')
        closure = inspect.getclosurevars(state_route.endpoint).nonlocals
        before = len(app.routes)
        module.register_lineup_lab(app, closure['store'], state_route.dependant.dependencies[0].call,
                                  closure['require_team'], state_route.endpoint)
        app.router.routes[:] = app.routes[before:]+app.routes[:before]
    return app


def login(client, username='piwig', password=PASSWORD):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def save_body(**fields):
    return {'team_id': '72450', 'name': 'Premier XV', 'expected_revision': 0,
            'options': {'locks': {}, 'starter_ids': [], 'excluded_ids': [],
                        'objective': 'balanced', 'energy_floor': 60, 'energy_scale': 'percent'}, **fields}


def test_scenarios_require_auth_csrf_and_do_not_replace_lineup(tmp_path):
    with TestClient(app_with_lab(tmp_path)) as client:
        assert client.get('/api/lineup-lab/scenarios?team_id=72450').status_code == 401
        headers = login(client)
        body = save_body()
        assert client.post('/api/lineup-lab/scenarios', json=body).status_code == 403
        response = client.post('/api/lineup-lab/scenarios', headers=headers, json=body)
        assert response.status_code == 200, response.text
        doc = response.json()
        assert doc['revision'] == 1
        assert doc['scenarios'][0]['name'] == 'Premier XV'
        assert client.get('/api/state?team_id=72450').json()['lineup'] == {}
        assert client.get('/api/lineup-lab/scenarios?team_id=72450').json() == doc


def test_stale_save_and_delete_cannot_erase_newer_scenarios(tmp_path):
    with TestClient(app_with_lab(tmp_path)) as client:
        headers = login(client)
        saved = client.post('/api/lineup-lab/scenarios', headers=headers, json=save_body()).json()
        identifier = saved['scenarios'][0]['id']
        assert client.post('/api/lineup-lab/scenarios', headers=headers,
                           json=save_body(id=identifier, name='Périmé')).status_code == 409
        assert client.post('/api/lineup-lab/delete', headers=headers, json={
            'team_id': '72450', 'id': identifier, 'expected_revision': 0}).status_code == 409
        assert client.get('/api/lineup-lab/scenarios?team_id=72450').json() == saved
        removed = client.post('/api/lineup-lab/delete', headers=headers, json={
            'team_id': '72450', 'id': identifier, 'expected_revision': 1})
        assert removed.json() == {'revision': 2, 'scenarios': []}


def test_scenarios_and_comparison_never_cross_manager_spaces(tmp_path):
    with TestClient(app_with_lab(tmp_path)) as admin, TestClient(admin.app) as other:
        headers = login(admin)
        saved = admin.post('/api/lineup-lab/scenarios', headers=headers, json=save_body()).json()
        ident = saved['scenarios'][0]['id']
        assert admin.post('/api/admin/users', headers=headers, json={
            'username': 'second', 'password': PASSWORD}).status_code == 200
        other_headers = login(other, 'second')
        assert other.get('/api/lineup-lab/scenarios?team_id=72450').status_code == 404
        assert other.post('/api/teams', headers=other_headers, json={
            'team_id': '72450', 'name': 'Autre espace', 'country': 'FR'}).status_code == 200
        assert other.get('/api/lineup-lab/scenarios?team_id=72450').json() == {'revision': 0, 'scenarios': []}
        assert other.get(f'/api/lineup-lab/compare?team_id=72450&left_id={ident}&right_id={ident}').status_code == 404
        assert other.post('/api/lineup-lab/scenarios', headers=other_headers,
                          json=save_body(id=ident)).status_code == 404


@pytest.mark.parametrize('update', [
    {'expected_revision': True}, {'expected_revision': -1}, {'name': ' '}, {'name': 'x'*81},
    {'options': {'energy_floor': 'NaN'}}, {'options': {'energy_floor': 110.1}},
    {'options': {'locks': {'16': '1'}}}, {'options': {'excluded_ids': ['x']}},
    {'options': {'starter_ids': ['1', '1']}}, {'options': {'excluded_ids': ['1']*501}},
    {'tenant_id': 'primary'},
])
def test_scenarios_validate_strictly(tmp_path, update):
    with TestClient(app_with_lab(tmp_path)) as client:
        headers = login(client)
        assert client.post('/api/lineup-lab/scenarios', headers=headers,
                           json=save_body(**update)).status_code == 422
        assert client.get('/api/lineup-lab/scenarios?team_id=72450').json()['revision'] == 0


def test_scenario_comparison_uses_saved_values_and_flags_different_methods(tmp_path):
    with TestClient(app_with_lab(tmp_path)) as client:
        headers = login(client)
        players = [player(i) for i in range(1, 24)]
        assert client.post('/api/import', headers=headers, data={'team_id': '72450', 'youth': 'false'},
                           files={'file': ('squad.json', json.dumps(players))}).status_code == 200
        first = client.post('/api/lineup-lab/scenarios', headers=headers, json=save_body()).json()['scenarios'][0]
        second_doc = client.post('/api/lineup-lab/scenarios', headers=headers, json=save_body(
            name='Développement', expected_revision=1, options={'objective': 'development'})).json()
        second = second_doc['scenarios'][1]
        comparison = client.get('/api/lineup-lab/compare', params={
            'team_id': '72450', 'left_id': first['id'], 'right_id': second['id']}).json()
        assert comparison['left']['score'] == 150
        assert comparison['delta'] is None
        assert comparison['warnings']
        comparable = client.get('/api/lineup-lab/compare', params={
            'team_id': '72450', 'left_id': first['id'], 'right_id': first['id']}).json()
        assert comparable['delta'] == 0


def test_concurrent_writers_preserve_the_first_revision(tmp_path):
    app = app_with_lab(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        first_headers, second_headers = login(first), login(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(client.post, '/api/lineup-lab/scenarios', headers=headers,
                                 json=save_body(name=name)) for client, headers, name in
                     [(first, first_headers, 'A'), (second, second_headers, 'B')]]
        assert sorted(call.result().status_code for call in calls) == [200, 409]
        result = first.get('/api/lineup-lab/scenarios?team_id=72450').json()
        assert result['revision'] == 1 and len(result['scenarios']) == 1


def test_source_change_blocks_scenario_save_and_apply(tmp_path):
    app = app_with_lab(tmp_path)
    with TestClient(app) as client:
        headers = login(client)
        app.state.store.save_snapshot('72450', False, [player(i) for i in range(1, 24)], 'Avant')
        original = client.get('/api/state?team_id=72450').json()
        source_id = original['squad_source']['id']
        app.state.store.save_snapshot('72450', False, [player(i, 11) for i in range(1, 24)], 'Après')
        assert client.post('/api/lineup-lab/scenarios', headers=headers, json=save_body(
            expected_source_id=source_id)).status_code == 409
        assert client.post('/api/lineup-lab/apply', headers=headers, json={
            'team_id': '72450', 'options': {}, 'expected_source_id': source_id,
            'expected_slots': {}}).status_code == 409
        assert client.get('/api/state?team_id=72450').json()['lineup'] == {}


def test_apply_recalculates_valid_players_and_checks_existing_lineup_atomically(tmp_path):
    app = app_with_lab(tmp_path)
    with TestClient(app) as client:
        headers = login(client)
        app.state.store.save_snapshot('72450', False, [player(i) for i in range(1, 24)], 'Test')
        original = client.get('/api/state?team_id=72450').json()
        body = {'team_id': '72450', 'options': {'locks': {'9': '23'}},
                'expected_source_id': original['squad_source']['id'], 'expected_slots': {}}
        assert client.post('/api/lineup-lab/apply', json=body).status_code == 403
        applied = client.post('/api/lineup-lab/apply', headers=headers, json=body)
        assert applied.status_code == 200, applied.text
        saved = client.get('/api/state?team_id=72450').json()['lineup']
        assert saved['9'] == '23'
        assert len(saved) == len(set(saved.values())) == 23
        assert client.post('/api/lineup-lab/apply', headers=headers, json=body).status_code == 409
        body.update(expected_slots=saved, options={'locks': {'9': '999'}})
        assert client.post('/api/lineup-lab/apply', headers=headers, json=body).status_code == 422
        assert client.get('/api/state?team_id=72450').json()['lineup'] == saved
