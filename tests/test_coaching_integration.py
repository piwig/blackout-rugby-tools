"""Exercise coaching with the application's real auth, CSRF and export boundary."""
from fastapi.testclient import TestClient

from server.classic import ClassicClient
from server.main import create_app
from server.storage import pack


def test_coaching_auth_preview_confirm_and_private_export(tmp_path, monkeypatch):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    store = app.state.store
    store.save_secrets('', {'d': '1', 'dk': 'synthetic-developer'})
    store.set('api_manager', store.cipher.encrypt(pack({'m': '50', 'mk': 'synthetic-member'}).encode()).decode())
    store.set('classic_account', {'id': '50', 'team_ids': ['72450']})
    calls = []

    async def remote(self, resource, **params):
        calls.append(resource)
        if resource == 'm':
            return {'status': 'Ok', 'members': {'50': {'id': '50', 'email': 'synthetic@example.invalid'}}}
        if resource == 't':
            return {'status': 'Ok', 'teams': {'72450': {'id': '72450', 'owner': '50'}}}
        assert resource == 'ti'
        return {'status': 'Ok', 'team training': {'teamid': '72450', 's1': 'stamina', 's2': 'none'}}

    monkeypatch.setattr(ClassicClient, 'request', remote)
    base = '/api/clubs/72450/coaching'
    with TestClient(app) as manager, TestClient(app) as other:
        assert manager.get(base).status_code == 401
        assert manager.post(base+'/preview', json={'kind': 'instructions'}).status_code == 401
        assert manager.post(base+'/confirm', json={}).status_code == 401
        login = manager.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
        headers = {'X-CSRF-Token': login.json()['csrf']}
        assert manager.post(base+'/preview', json={'kind': 'instructions'}).status_code == 403
        assert manager.post(base+'/preview', headers={**headers, 'Origin': 'https://example.invalid'}, json={'kind': 'instructions'}).status_code == 403
        assert manager.get(base).json()['revision'] == 0
        assert calls == []
        preview = manager.post(base+'/preview', headers=headers, json={'kind': 'instructions'})
        assert preview.status_code == 200, preview.text
        assert calls == ['m', 't', 'ti']
        assert manager.get(base).json()['instructions'] is None
        body = {key: preview.json()[key] for key in ('preview_id', 'expected_revision')}
        assert manager.post(base+'/confirm', json=body).status_code == 403
        saved = manager.post(base+'/confirm', headers=headers, json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()['bundle']['instructions']['team_skills'] == ['stamina', None, 'unreported', 'unreported']
        assert calls == ['m', 't', 'ti']
        exported = manager.get('/api/export')
        assert any(key.startswith('coaching:') for key in exported.json()['manager_documents'])
        assert 'synthetic-member' not in exported.text and 'synthetic-developer' not in exported.text
        assert manager.post('/api/admin/users', headers=headers, json={'username': 'secondcoach', 'password': 'Another-password-5678'}).status_code == 200
        other.post('/api/login', json={'username': 'secondcoach', 'password': 'Another-password-5678'})
        assert other.get(base).status_code == 404
        assert not any(key.startswith('coaching:') for key in other.get('/api/export').json()['manager_documents'])
