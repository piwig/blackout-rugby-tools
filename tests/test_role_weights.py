"""Private selection criteria: strict inputs, stable snapshots and tenant isolation."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from server.domain import player_metrics
from server.lineup_lab import Options, calculate, compare_scenarios
from server.role_weights import default_weights, validate_weights
from test_lineup_lab import app_with_lab, login, player, lineup, save_body, PASSWORD


def only(skill):
    return {role: {key: int(key == skill) for key in weights} for role, weights in default_weights().items()}


@pytest.mark.parametrize('mutation', [
    lambda w: w.pop('Pilier'), lambda w: w.update({'unknown': w['Pilier']}),
    lambda w: w['Pilier'].pop('speed'), lambda w: w['Pilier'].update({'unknown': 1}),
    *[lambda w, value=value: w['Pilier'].update(speed=value) for value in (True, -1, 11, 1.5, '2', float('nan'))],
    lambda w: w.update(Pilier=dict.fromkeys(w['Pilier'], 0)),
])
def test_weights_reject_invalid_partial_and_zero_roles(mutation):
    weights = default_weights()
    mutation(weights)
    with pytest.raises(ValueError):
        validate_weights(weights)
    with pytest.raises(ValueError):
        Options(role_weights=weights)


def test_default_is_exactly_compatible_and_zero_weights_ignore_missing_skills():
    p = player(1, speed=None)
    assert player_metrics(p) == player_metrics(p, role_weights=default_weights())
    custom = only('handling')
    assert len(player_metrics(p, role_weights=custom)['roles']) == 9
    assert player_metrics(player(1, handling=None), role_weights=custom)['roles'] == []
    assert len(default_weights()) == 9 and all(len(w) == 10 for w in default_weights().values())
    # Independent historical formula, including its operation order.
    p = player(2, strength=1.025, technique=11.125, stamina=8.575)
    expected = round((p['strength']*3+p['technique']*2+p['stamina'])/6, 2)
    assert next(r['score'] for r in player_metrics(p)['roles'] if r['name']=='Pilier') == expected


def test_invalid_weights_never_reach_optimizer_and_profile_metadata_is_strict():
    with pytest.raises(ValueError):
        lineup([player(1)], role_weights={})
    for update in ({'weight_method':'official'}, {'weight_profile_name':'\n'}, {'role_weights':None}):
        with pytest.raises(ValueError):
            Options(**update)


@pytest.mark.parametrize('update', [
    {'expected_revision':True}, {'expected_revision':-1}, {'name':' '}, {'name':'\n'},
    {'name':'x'*81}, {'role_weights':{}}, {'tenant_id':'primary'},
])
def test_profile_api_rejects_invalid_inputs_without_writing(tmp_path, update):
    with TestClient(app_with_lab(tmp_path)) as client:
        headers=login(client)
        assert client.post('/api/lineup-lab/weights',headers=headers,json=weights_body(**update)).status_code==422
        assert client.get('/api/lineup-lab/weights?team_id=72450').json()['revision']==0


def test_custom_criteria_change_assignment_and_bench_without_mutating_inputs():
    squad = [player(1, strength=20, speed=1), player(2, strength=1, speed=20)]
    weights = only('speed')
    before = deepcopy(weights)
    assert lineup(squad)['slots']['1'] == '1'
    result = lineup(squad, role_weights=weights)
    assert result['slots']['1'] == '2'
    assert 'moyenne pondérée' in result['players'][0]['reason']
    assert weights == before
    starters = [player(i) for i in range(3, 18)]
    bench = lineup(starters+[player(18, handling=None), player(19, handling=None)], role_weights=only('speed'),
                   locks={str(i): str(i+2) for i in range(1,16)})
    assert bench['bench_coverage']['gaps'] == []


def weights_body(**changes):
    return {'team_id': '72450', 'expected_revision': 0, 'name': 'Rapidité', 'role_weights': only('speed'), **changes}


def test_profiles_auth_csrf_club_scope_revision_and_limit(tmp_path):
    with TestClient(app_with_lab(tmp_path)) as client:
        assert client.get('/api/lineup-lab/weights?team_id=72450').status_code == 401
        headers = login(client)
        assert client.post('/api/lineup-lab/weights', json=weights_body()).status_code == 403
        saved = client.post('/api/lineup-lab/weights', headers=headers, json=weights_body())
        assert saved.status_code == 200, saved.text
        doc = saved.json()
        assert doc['revision'] == 1 and len(doc['profiles']) == 1
        assert doc['default']['role_weights'] == default_weights()
        assert client.get('/api/lineup-lab/weights?team_id=72444').json()['profiles'] == []
        assert client.post('/api/lineup-lab/weights', headers=headers, json=weights_body()).status_code == 409
        for revision in range(1,10):
            assert client.post('/api/lineup-lab/weights', headers=headers,
                               json=weights_body(expected_revision=revision, name=f'Profil {revision}')).status_code == 200
        assert client.post('/api/lineup-lab/weights', headers=headers,
                           json=weights_body(expected_revision=10)).status_code == 422
        assert client.post('/api/lineup-lab/weights/delete', headers=headers,
                           json={'team_id':'72450','expected_revision':10,'id':doc['profiles'][0]['id']}).status_code == 200


def test_profiles_atomic_concurrent_writes_and_manager_isolation(tmp_path):
    app = app_with_lab(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        h1, h2 = login(first), login(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(c.post, '/api/lineup-lab/weights', headers=h, json=weights_body()) for c,h in ((first,h1),(second,h2))]
        assert sorted(c.result().status_code for c in calls) == [200,409]
        first.post('/api/admin/users', headers=h1, json={'username':'second','password':PASSWORD})
        h2 = login(second,'second')
        assert second.get('/api/lineup-lab/weights?team_id=72450').status_code == 404
        second.post('/api/teams', headers=h2,json={'team_id':'72450','name':'Other','country':'FR'})
        assert second.get('/api/lineup-lab/weights?team_id=72450').json()['profiles'] == []


def test_scenarios_snapshot_criteria_and_compare_historical_defaults(tmp_path):
    app = app_with_lab(tmp_path)
    with TestClient(app) as client:
        headers = login(client)
        app.state.store.save_snapshot('72450', False, [player(i) for i in range(1,24)], 'Test')
        first = client.post('/api/lineup-lab/scenarios', headers=headers,json=save_body()).json()['scenarios'][0]
        assert first['options']['role_weights'] == default_weights()
        assert first['preview']['criteria']['method'] == 'weighted-average-v1'
        second = client.post('/api/lineup-lab/scenarios', headers=headers,json=save_body(expected_revision=1,
            options={'energy_scale':'percent','role_weights':only('speed'),'weight_profile_name':'Rapidité'})).json()['scenarios'][1]
        assert compare_scenarios(first,second)['delta'] is None
        old = deepcopy(first)
        old['options'].pop('role_weights'); old['options'].pop('weight_profile_name'); old['options'].pop('weight_method')
        assert compare_scenarios(old,first)['delta'] == 0
        profile = client.post('/api/lineup-lab/weights',headers=headers,json=weights_body()).json()['profiles'][0]
        updated = client.post('/api/lineup-lab/weights',headers=headers,json=weights_body(
            id=profile['id'],expected_revision=1,role_weights=only('handling')))
        assert updated.status_code == 200 and len(updated.json()['profiles']) == 1
        assert updated.json()['profiles'][0]['role_weights'] == only('handling')
        assert client.post('/api/lineup-lab/weights/delete',headers=headers,json={
            'team_id':'72450','expected_revision':1,'id':profile['id']}).status_code == 409
        assert client.get('/api/lineup-lab/scenarios?team_id=72450').json()['scenarios'][1] == second
