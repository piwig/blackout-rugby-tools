"""Durable preparation survives export; ephemeral confirmations remain private."""
from fastapi.testclient import TestClient
from server.main import create_app
from server.classic import ClassicClient
import pytest


@pytest.mark.parametrize('path', ['/api/coach-lab?team_id=72450&cohort=club',
                                '/api/stadium-economy?team_id=72450',
                                '/api/transfer-ledger?team_id=72450'])
def test_complete_manager_routes_use_real_auth_and_private_team_boundary(tmp_path, path):
    app = create_app(tmp_path, 'Synthetic-password-2026!', secure=False)
    with TestClient(app) as owner, TestClient(app) as other:
        assert owner.get(path).status_code == 401
        login = owner.post('/api/login', json={'username': 'piwig', 'password': 'Synthetic-password-2026!'})
        assert login.status_code == 200
        assert owner.get(path).status_code == 200
        post_path = '/api/coach-lab/preview' if 'coach-lab' in path else path.split('?')[0]
        assert owner.post(post_path, json={}).status_code == 403
        assert owner.post(post_path, headers={'X-CSRF-Token': login.json()['csrf'], 'Origin': 'https://example.invalid'}, json={}).status_code == 403
        assert owner.post('/api/admin/users', headers={'X-CSRF-Token': login.json()['csrf']}, json={
            'username': 'isolated', 'password': 'Other-password-2026!'}).status_code == 200
        assert other.post('/api/login', json={'username': 'isolated', 'password': 'Other-password-2026!'}).status_code == 200
        assert other.get(path).status_code == 404


def test_complete_manager_export_keeps_work_and_excludes_confirmation_tokens(tmp_path):
    app = create_app(tmp_path, 'Synthetic-password-2026!', secure=False)
    store = app.state.accounts.store('primary')
    durable = ['coach_lab:72450:club', 'coach_lineup:72450:youth',
               'stadium_economy:72450', 'transfer_ledger:72450']
    temporary = ['coach_preview:temporary', 'transfer_preview:temporary']
    for key in durable:
        store.set(key, {'revision': 3, 'label': 'Private synthetic work'})
    for key in temporary:
        store.set(key, {'token': 'single-use-confirmation'})
    with TestClient(app) as owner:
        assert owner.get('/api/export').status_code == 401
        login = owner.post('/api/login', json={'username': 'piwig', 'password': 'Synthetic-password-2026!'})
        assert login.status_code == 200
        response = owner.get('/api/export')
        documents = response.json()['manager_documents']
        for key in durable:
            assert documents[key]['revision'] == 3
        assert all(key not in documents for key in temporary)
        assert 'single-use-confirmation' not in response.text
        assert owner.post('/api/admin/users', headers={'X-CSRF-Token': login.json()['csrf']}, json={
            'username': 'second', 'password': 'Other-password-2026!'}).status_code == 200
    with TestClient(app) as other:
        assert other.post('/api/login', json={'username': 'second', 'password': 'Other-password-2026!'}).status_code == 200
        assert all(key not in other.get('/api/export').json()['manager_documents'] for key in durable)


def test_fresh_club_sync_supplies_dated_stadium_capacity_without_invented_prices(tmp_path, monkeypatch):
    app = create_app(tmp_path, 'Synthetic-password-2026!', secure=False)
    async def remote(self, resource, **params):
        assert resource == 't'
        return {'teams': {'72450': {'stadium_standing': 100, 'stadium_covered': 200}}}
    monkeypatch.setattr(ClassicClient, 'request', remote)
    with TestClient(app) as owner:
        login = owner.post('/api/login', json={'username': 'piwig', 'password': 'Synthetic-password-2026!'})
        response = owner.post('/api/sync', headers={'X-CSRF-Token': login.json()['csrf']}, json={'team_id': '72450', 'kind': 'team'})
        assert response.status_code == 200, response.text
        seed = owner.get('/api/stadium-economy?team_id=72450').json()['initial_current']
        assert seed['source'] == 'API Classic'
        assert seed['observed_on']
        assert seed['seats']['standing']['capacity'] == 100
        assert seed['seats']['covered']['capacity'] == 200
        assert seed['seats']['standing']['price'] is None
        assert seed['seats']['corporate']['capacity'] is None
