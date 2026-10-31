"""National squads are private observations, never club IDs or gameplay authority."""
import asyncio
import pytest
from fastapi.testclient import TestClient

from server.classic import ClassicClient, ClassicError
from server.main import create_app
from server.storage import pack
from server.national import prepare_selection


def login(client, username='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def connected_app(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    store = app.state.store
    store.set('classic_account', {'id': '123', 'username': 'Manager', 'team_ids': ['9'], 'imported_at': '2026-01-01T00:00:00Z'})
    store.set('api_manager', store.cipher.encrypt(pack({'m': '123', 'mk': 'PRIVATE-MEMBER-KEY'}).encode()).decode())
    store.save_secrets('9', {'d': '1', 'dk': 'PRIVATE-DEV-KEY', 'm': '123', 'mk': 'PRIVATE-MEMBER-KEY'})
    with store.db() as db:
        db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?)', ('9', 'Club Nine', 'BE'))
    store.save_snapshot('9', False, [{'id': '42', 'name': 'Club player', 'strength': 4}], 'Club source')
    return app


def classic_fixture(monkeypatch, *, manager='123', authenticated=True, fail=None, malformed=False, invalid_players=False, game_date=None):
    calls = []

    async def request(self, resource, **params):
        calls.append((resource, params))
        if resource == 'm':
            member = {'id': '123', 'username': 'Manager', 'teams': ['9']}
            if authenticated:
                member['email'] = 'PRIVATE@example.com'
            return {'members': {'123': member}}
        kind = 'u20' if params.get('u20') == '1' else 'nt' if params.get('nat') == '1' else 'club'
        assert not (params.get('u20') and params.get('nat'))
        if kind != 'club':
            assert 'youth' not in params
        if fail == (resource, kind):
            raise ClassicError('Lecture de sélection indisponible.')
        if resource == 't':
            if kind == 'club':
                return {'teams': {'9': {'id': '9', 'owner': '123', 'name': 'Club refreshed', 'country_iso': 'BE'}}}
            team = {'id': '9', 'name': 'Belgium', 'country_iso': 'BE', 'manager': manager, 'stadium': 'Belgium Stadium'}
            if malformed:
                team.pop('manager')
                team['owner'] = manager
            return {'teams': {'9': team}}
        if resource == 'p':
            if invalid_players:
                return {'players': {'not-a-player-id': {'name': 'Bad response'}}}
            return {'players': {'42': {'id': '42', 'name': kind + ' player', 'strength': '12', 'energy': '91'}},
                    'gameDate': game_date if game_date is not None else {'season': 62, 'round': 9, 'day': 6}}
        raise AssertionError(resource)

    monkeypatch.setattr(ClassicClient, 'request', request)
    return calls


def attach(client, headers, kind='u20'):
    return client.post('/api/classic/selections', headers=headers, json={'kind': kind, 'country': 'BE'})


def test_club_u20_and_nt_same_id_keep_independent_observations_and_notes(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    calls = classic_fixture(monkeypatch)
    with TestClient(app) as client:
        headers = login(client)
        for kind in ('u20', 'nt'):
            response = attach(client, headers, kind)
            assert response.status_code == 200, response.text
            assert response.json()['team']['id'] == kind + ':9'
        for tid, name in [('9', 'Club player'), ('u20:9', 'u20 player'), ('nt:9', 'nt player')]:
            assert client.post('/api/notes', headers=headers, json={'team_id': tid, 'player_id': '42', 'text': tid}).status_code == 200
            state = client.get('/api/state', params={'team_id': tid}).json()
            assert state['current_team']['id'] == tid
            assert state['current_team']['classic_id'] == '9'
            assert state['squad'][0]['name'] == name
            assert state['notes']['42']['text'] == tid
            if tid != '9':
                assert state['academy_source'] is None
                assert state['current_team']['kind'] == tid.split(':')[0]
                assert client.get('/api/progression', params={'team_id': tid}).status_code == 200
                assert client.get('/api/lineup-lab/scenarios', params={'team_id': tid}).status_code == 200
        account = client.get('/api/state').json()['classic_account']
        assert account['team_ids'] == ['9']
        assert account['selection_ids'] == ['u20:9', 'nt:9']
        assert ('t', {'country_iso': 'BE', 'u20': '1'}) in calls
        assert ('p', {'teamid': '9', 'u20': '1'}) in calls
        exported = client.get('/api/export').text
        assert all(secret not in exported for secret in ('PRIVATE@example.com', 'PRIVATE-MEMBER-KEY', 'PRIVATE-DEV-KEY'))
    assert app.state.store.get('api_member:u20:9') is None
    assert app.state.store.get('api_member:nt:9') is None


@pytest.mark.parametrize('options', [{'manager': '456'}, {'authenticated': False}, {'malformed': True}])
def test_unproven_selection_rights_refuse_before_private_players_or_mutation(tmp_path, monkeypatch, options):
    app = connected_app(tmp_path)
    before = app.state.store.get('classic_account')
    calls = classic_fixture(monkeypatch, **options)
    with TestClient(app) as client:
        response = attach(client, login(client))
        assert response.status_code == 422, response.text
        assert not any(resource == 'p' for resource, _ in calls)
        assert app.state.store.get('classic_account') == before
        assert not any(team['id'] == 'u20:9' for team in client.get('/api/state').json()['teams'])


def test_failed_selection_collection_keeps_previous_snapshot_and_global_import_atomic(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch)
    with TestClient(app) as client:
        headers = login(client)
        assert attach(client, headers).status_code == 200
        before = client.get('/api/export').json()
        old_account = app.state.store.get('classic_account')
        classic_fixture(monkeypatch, fail=('p', 'u20'))
        response = client.post('/api/classic/sync', headers=headers, json={})
        assert response.status_code == 422, response.text
        after = client.get('/api/export').json()
        assert after['teams'] == before['teams']
        assert after['snapshots'] == before['snapshots']
        assert app.state.store.get('classic_account') == old_account


def test_global_sync_preserves_selection_and_read_flags(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    calls = classic_fixture(monkeypatch)
    with TestClient(app) as client:
        headers = login(client)
        assert attach(client, headers).status_code == 200
        calls.clear()
        response = client.post('/api/classic/sync', headers=headers, json={})
        assert response.status_code == 200, response.text
        assert response.json()['account']['selection_ids'] == ['u20:9']
        assert ('t', {'teamid': '9', 'u20': '1'}) in calls
        assert ('p', {'teamid': '9', 'u20': '1'}) in calls
        assert client.get('/api/state?team_id=9').json()['current_team']['name'] == 'Club refreshed'


def test_selection_is_private_and_club_only_routes_never_send_game_requests(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    calls = classic_fixture(monkeypatch)
    with TestClient(app) as owner, TestClient(app) as other:
        headers = login(owner)
        assert attach(owner, headers).status_code == 200
        assert owner.post('/api/admin/users', headers=headers, json={'username': 'franck', 'password': 'Other-password-5678'}).status_code == 200
        other_headers = login(other, 'franck', 'Other-password-5678')
        assert not other.get('/api/state').json()['teams']
        assert other.get('/api/progression?team_id=u20:9').status_code == 404
        assert other.post('/api/classic/selections/sync', headers=other_headers, json={'team_id': 'u20:9'}).status_code in (404, 422)
        calls.clear()
        for path, body in [
            ('/api/vacation/preview', {'team_id': 'u20:9'}),
            ('/api/settings', {'team_id': 'u20:9', 'manager_id': '123', 'manager_key': 'KEY'}),
            ('/api/teams', {'team_id': 'u20:9', 'name': 'Bogus'}),
            ('/api/plans', {'team_id': 'u20:9', 'season': 62, 'grid': [[''] * 16 for _ in range(4)]}),
            ('/api/workbench/starter/u20:9', {'expected_revision': 0, 'completed': [], 'collapsed': False}),
            ('/api/sync', {'team_id': 'u20:9', 'kind': 'academy'}),
        ]:
            response = owner.post(path, headers=headers, json=body)
            assert response.status_code == 422, (path, response.text)
            assert 'sélection' in response.json()['detail'].lower(), (path, response.text)
        assert owner.get('/api/vacation/fixtures?team_id=u20:9').status_code == 422
        assert not calls
        invalid_player = owner.post('/api/notes', headers=headers, json={'team_id': 'u20:9', 'player_id': 'u20:42', 'text': 'invalid'})
        assert invalid_player.status_code == 422


def test_targeted_selection_sync_and_local_calendar_use_namespace(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch)
    with TestClient(app) as client:
        headers = login(client)
        assert attach(client, headers).status_code == 200
        response = client.post('/api/classic/selections/sync', headers=headers, json={'team_id': 'u20:9'})
        assert response.status_code == 200, response.text
        response = client.post('/api/workbench/calendar', headers=headers, json={'team_id': 'u20:9', 'expected_revision': 0, 'events': []})
        assert response.status_code == 200, response.text
        assert client.get('/api/workbench/calendar?team_id=u20:9').status_code == 200
        assert client.post('/api/lineup', headers=headers, json={'team_id': 'u20:9', 'slots': {'1': '42'}}).status_code == 200
        assert client.get('/api/state?team_id=u20:9').json()['lineup'] == {'1': '42'}
        assert client.get('/api/state?team_id=9').json()['lineup'] == {}


def test_malformed_players_return_safe_error_without_saving_selection(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch, invalid_players=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = attach(client, login(client))
        assert response.status_code == 422, response.text
        assert 'not-a-player-id' not in response.text
        assert not any(team['id'] == 'u20:9' for team in client.get('/api/state').json()['teams'])


def test_fresh_selection_does_not_raise_missing_club_academy_alert(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch)
    with TestClient(app) as client:
        assert attach(client, login(client)).status_code == 200
        daily = client.get('/api/workbench/daily').json()
        selection = next(team for team in daily['clubs'] if team['team_id'] == 'u20:9')
        assert [source['kind'] for source in selection['sources']] == ['squad']
        assert not any(action['team_id'] == 'u20:9' and action['kind'] == 'freshness' for action in daily['actions'])


def test_selection_insights_namespace_is_private_and_club_scenarios_are_refused(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch)
    with TestClient(app) as owner, TestClient(app) as other:
        headers = login(owner)
        assert attach(owner, headers).status_code == 200
        owner.post('/api/admin/users', headers=headers, json={'username': 'franck', 'password': 'Other-password-5678'})
        other_headers = login(other, 'franck', 'Other-password-5678')
        for route in ['/api/insights/u20:9', '/api/insights/u20:9/opponents', '/api/history/u20:9/42', '/api/workbench/calendar?team_id=u20:9']:
            assert other.get(route).status_code == 404, route
        assert other.post('/api/insights/u20:9', headers=other_headers, json={'expected_revision': 0, 'document': {}}).status_code == 404
        assert owner.post('/api/matches/import', headers=headers, json={'id': '90', 'type': 1, 'home': 'Belgium', 'away': 'Opponent', 'events': []}).status_code == 200
        document = {'match_links': [{'match_id': '90', 'match_type': 1, 'club_side': 'home', 'opponent': 'Opponent'}]}
        assert owner.post('/api/insights/u20:9', headers=headers, json={'expected_revision': 0, 'document': document}).status_code == 200
        assert owner.get('/api/insights/u20:9').json()['document']['match_links'][0]['match_id'] == '90'
        assert owner.get('/api/insights/9').json()['document']['match_links'] == []
        document['sessions'] = [{'id': 'session1', 'season': 62, 'week': 9, 'slot': 1, 'skill': 'strength', 'performed_at': '2026-01-01T12:00:00Z'}]
        refused = owner.post('/api/insights/u20:9', headers=headers, json={'expected_revision': 1, 'document': document})
        assert refused.status_code == 422
        assert 'sélection' in refused.json()['detail']
        assert owner.get('/api/insights/u20:9').json()['document']['revision'] == 1


def test_pause_selection_preserves_history_and_allows_club_sync_after_mandate_ends(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch)
    with TestClient(app) as client:
        headers = login(client)
        assert attach(client, headers).status_code == 200
        client.post('/api/notes', headers=headers, json={'team_id': 'u20:9', 'player_id': '42', 'text': 'Private national note'})
        state = client.get('/api/state?team_id=u20:9').json()
        revision = state['classic_account'].get('selection_revision', 0)
        before_source = state['squad_source']
        calls = classic_fixture(monkeypatch, manager='456')
        response = client.post('/api/classic/selections/pause', headers=headers,
                               json={'team_id': 'u20:9', 'expected_revision': revision})
        assert response.status_code == 200, response.text
        assert not calls
        assert response.json()['account']['selection_ids'] == []
        assert client.get('/api/state?team_id=u20:9').json()['notes']['42']['text'] == 'Private national note'
        assert client.get('/api/state?team_id=u20:9').json()['squad_source'] == before_source
        assert client.post('/api/classic/sync', headers=headers, json={}).status_code == 200
        assert all('u20' not in params and 'nat' not in params for _, params in calls)
        assert client.post('/api/classic/selections/sync', headers=headers, json={'team_id': 'u20:9'}).status_code == 422


def test_pause_requires_csrf_private_reference_and_current_revision(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    classic_fixture(monkeypatch)
    with TestClient(app) as owner, TestClient(app) as other:
        headers = login(owner)
        assert attach(owner, headers).status_code == 200
        revision = app.state.store.get('classic_account').get('selection_revision', 0)
        payload = {'team_id': 'u20:9', 'expected_revision': revision}
        assert owner.post('/api/classic/selections/pause', json=payload).status_code == 403
        owner.post('/api/admin/users', headers=headers, json={'username': 'franck', 'password': 'Other-password-5678'})
        other_headers = login(other, 'franck', 'Other-password-5678')
        assert other.post('/api/classic/selections/pause', headers=other_headers, json=payload).status_code == 404
        assert owner.post('/api/classic/selections/pause', headers=headers, json={**payload, 'expected_revision': revision + 1}).status_code == 409
        assert owner.post('/api/classic/selections/pause', headers=headers, json=payload).status_code == 200
        assert owner.post('/api/classic/selections/pause', headers=headers, json=payload).status_code == 409
        assert app.state.store.get('classic_account')['selection_ids'] == []


def test_selection_state_uses_latest_valid_selection_date_even_when_players_unchanged(tmp_path, monkeypatch):
    app = connected_app(tmp_path)
    old_club_date = {'season': 60, 'round': 1, 'day': 1}
    app.state.store.set('game_date', old_club_date)
    classic_fixture(monkeypatch)
    with TestClient(app) as client:
        headers = login(client)
        assert attach(client, headers).status_code == 200
        first = client.get('/api/state?team_id=u20:9').json()
        assert first['game_date'] == {'season': 62, 'round': 9, 'day': 6}
        latest = {'season': 63, 'round': 2, 'day': 3}
        classic_fixture(monkeypatch, game_date=latest)
        assert client.post('/api/classic/selections/sync', headers=headers, json={'team_id': 'u20:9'}).status_code == 200
        refreshed = client.get('/api/state?team_id=u20:9').json()
        assert refreshed['squad_source']['id'] == first['squad_source']['id']
        assert refreshed['game_date'] == latest
        assert client.get('/api/state?team_id=9').json()['game_date'] == old_club_date


@pytest.mark.parametrize('invalid', [{'season': 62, 'round': 99, 'day': 6}, {'season': 'oops'}, {'season': 62, 'round': 9.5, 'day': 6}])
def test_selection_date_never_reuses_unrelated_club_date_or_invalid_source(tmp_path, monkeypatch, invalid):
    app = connected_app(tmp_path)
    app.state.store.set('game_date', {'season': 60, 'round': 1, 'day': 1})
    classic_fixture(monkeypatch, game_date=invalid)
    with TestClient(app) as client:
        assert attach(client, login(client)).status_code == 200
        assert client.get('/api/state?team_id=u20:9').json()['game_date'] is None


def observed_u20_client(monkeypatch, team):
    calls = []

    async def request(self, resource, **params):
        calls.append((resource, params))
        if resource == 't':
            return {'teams': {'22': team}}
        if resource == 'p':
            return {'players': {'42': {'name': 'Synthetic player', 'strength': '12'}}}
        raise AssertionError(resource)

    monkeypatch.setattr(ClassicClient, 'request', request)
    return ClassicClient({}), calls


def test_live_u20_json_owner_is_accepted_with_explicit_u20_marker(monkeypatch):
    # Public identity fields observed through an authorized Classic GET on 2026-10-31.
    team = {'id': '22', 'name': 'Belgium U20', 'country_iso': 'BE', 'owner': '169377', 'u20': 1}
    client, calls = observed_u20_client(monkeypatch, team)
    result = asyncio.run(prepare_selection(client, '169377', 'u20', country='BE'))
    assert result['id'] == 'u20:22'
    assert result['classic_id'] == '22'
    assert result['country'] == 'BE'
    assert result['players'][0]['id'] == '42'
    assert calls == [('t', {'country_iso': 'BE', 'u20': '1'}), ('p', {'teamid': '22', 'u20': '1'})]


@pytest.mark.parametrize('flag', [None, 0, 2, True, '1', 'true'])
def test_json_owner_without_verified_u20_marker_refuses_private_players(monkeypatch, flag):
    team = {'id': '22', 'name': 'Belgium U20', 'country_iso': 'BE', 'owner': '169377', 'u20': flag}
    client, calls = observed_u20_client(monkeypatch, team)
    with pytest.raises(ClassicError):
        asyncio.run(prepare_selection(client, '169377', 'u20', country='BE'))
    assert [resource for resource, _ in calls] == ['t']


@pytest.mark.parametrize('manager,owner', [('169377', '123'), ('123', '169377')])
def test_conflicting_documented_manager_and_live_owner_refuse_private_players(monkeypatch, manager, owner):
    team = {'id': '22', 'name': 'Belgium U20', 'country_iso': 'BE', 'manager': manager, 'owner': owner, 'u20': 1}
    client, calls = observed_u20_client(monkeypatch, team)
    with pytest.raises(ClassicError):
        asyncio.run(prepare_selection(client, '169377', 'u20', country='BE'))
    assert [resource for resource, _ in calls] == ['t']


def test_nt_owner_fallback_remains_unproven_and_is_refused(monkeypatch):
    team = {'id': '22', 'name': 'Belgium', 'country_iso': 'BE', 'owner': '169377', 'nat': 1, 'u20': 1}
    client, calls = observed_u20_client(monkeypatch, team)
    with pytest.raises(ClassicError):
        asyncio.run(prepare_selection(client, '169377', 'nt', country='BE'))
    assert [resource for resource, _ in calls] == ['t']
