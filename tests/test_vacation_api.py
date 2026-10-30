"""Private vacation routes never infer authority from a submitted tenant ID."""
from datetime import datetime, timedelta, timezone
import asyncio
from fastapi.testclient import TestClient
from server.main import create_app


def login(client, username='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def rule():
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    return {'team_id': '72450', 'enabled': False, 'mode': 'prepare',
            'start_at': start.isoformat(), 'end_at': (start+timedelta(days=7)).isoformat(),
            'energy_scale': 'percent'}


def test_vacation_routes_require_session_csrf_and_known_private_club(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with TestClient(app) as client:
        assert client.get('/api/vacation/status').status_code == 401
        headers = login(client)
        assert client.get('/api/vacation/status?team_id=9999999').status_code == 404
        assert client.get('/api/vacation/fixtures?team_id=bad').status_code == 422
        assert client.post('/api/vacation/stop', json={}).status_code == 403
        assert client.post('/api/vacation/preview', headers=headers,
                           json={'team_id': '9999999', 'fixture_id': '0'}).status_code == 404
        response = client.get('/api/vacation/status?team_id=72450')
        assert response.status_code == 200, response.text
        status = response.json()
        assert status['rules'][0]['enabled'] is False
        assert status['rules'][0]['revision'] == 0
        assert status['write_ready'] is False
        assert status['worker_enabled'] is False


def test_vacation_configuration_is_private_and_has_revision_conflicts(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with TestClient(app) as owner, TestClient(app) as friend:
        h = login(owner)
        created = owner.post('/api/admin/users', headers=h,
                             json={'username': 'franck', 'password': 'Another-password-5678'}).json()
        fh = login(friend, 'franck', 'Another-password-5678')
        friend.post('/api/teams', headers=fh, json={'team_id': '72450', 'name': 'Autre espace'})
        # An imported ownership claim is required even when merely configuring a rule.
        for storage in [app.state.store, app.state.accounts.store(created['id'])]:
            storage.set('classic_account', {'id': '123', 'team_ids': ['72450']})
        response = owner.post('/api/vacation/rules', headers=h, json={'rule': rule(), 'expected_revision': 0})
        assert response.status_code == 200, response.text
        assert owner.get('/api/vacation/status?team_id=72450').json()['rules'][0]['revision'] == 1
        assert friend.get('/api/vacation/status?team_id=72450').json()['rules'][0]['revision'] == 0
        assert owner.post('/api/vacation/rules', headers=h,
                          json={'rule': rule(), 'expected_revision': 0}).status_code == 409
        assert friend.post('/api/vacation/send', headers=fh,
                           json={'preview_id': '12345678901234567890123456789012'}).status_code == 404
        assert owner.post('/api/vacation/rules', headers=h,
                          json={'rule': {**rule(), 'team_id': '9999999'}, 'expected_revision': 0}).status_code == 404


def test_developer_iv_is_encrypted_write_only_and_validated(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with TestClient(app) as client:
        h = login(client)
        data = {'team_id': '72450', 'developer_id': '12', 'developer_key': 'a'*32,
                'developer_iv': 'SECRET-IV-123456', 'manager_id': '123', 'manager_key': 'TEST-MEMBER'}
        response = client.post('/api/settings', headers=h, json=data)
        assert response.status_code == 200, response.text
        assert app.state.store.secrets('72450')['iv'] == data['developer_iv']
        for url in ['/api/state?team_id=72450', '/api/export', '/api/vacation/status?team_id=72450']:
            response = client.get(url)
            assert response.status_code == 200
            assert data['developer_iv'] not in response.text
        assert client.get('/api/vacation/status?team_id=72450').json()['write_ready'] is True
        invalid=client.post('/api/settings', headers=h, json={**data, 'developer_iv': 'short'})
        assert invalid.status_code == 422
        assert 'short' not in invalid.text
        assert app.state.store.secrets('72450')['iv'] == data['developer_iv']
        assert client.post('/api/settings', headers=h, json={'team_id': '72450'}).status_code == 200
        assert app.state.store.secrets('72450')['iv'] == data['developer_iv']
        for path in tmp_path.glob('*.sqlite*'):
            assert data['developer_iv'].encode() not in path.read_bytes()


def test_worker_explicitly_visits_private_stores_and_does_not_share_errors(tmp_path,monkeypatch):
    from server.vacation import VacationService
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    friend=app.state.accounts.create('franck','Another-password-5678')
    visited=[]
    async def tick(service):
        visited.append(service.store.path)
        if service.store.path==app.state.store.path:raise ValueError('PRIVATE-UPSTREAM-ERROR')
        return []
    monkeypatch.setattr(VacationService,'tick',tick)
    asyncio.run(app.state.vacation_cycle())
    assert set(visited)=={app.state.store.path,app.state.accounts.store(friend['id']).path}
    with TestClient(app) as owner,TestClient(app) as other:
        login(owner);login(other,'franck','Another-password-5678')
        a=owner.get('/api/vacation/status').json()
        b=other.get('/api/vacation/status').json()
        assert a['worker_last_run'] and b['worker_last_run']
        assert a['worker_error'] and b['worker_error'] is None
        assert 'PRIVATE-UPSTREAM-ERROR' not in str(a)


def test_upstream_classic_errors_are_actionable_without_http_500(tmp_path,monkeypatch):
    from server.classic import ClassicClient,ClassicError
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    app.state.store.set('classic_account',{'id':'123','team_ids':['72450']})
    app.state.store.save_secrets('72450',{'d':'12','dk':'test','m':'123','mk':'test'})
    async def fail(*args,**kwargs):raise ClassicError('API Classic indisponible. Réessayez plus tard.')
    monkeypatch.setattr(ClassicClient,'request',fail)
    with TestClient(app,raise_server_exceptions=False) as client:
        login(client)
        response=client.get('/api/vacation/fixtures?team_id=72450')
        assert response.status_code==422
        assert response.json()['detail']=='API Classic indisponible. Réessayez plus tard.'
