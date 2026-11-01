"""Manager workbench exports must include durable work and exclude preview tokens."""
from fastapi.testclient import TestClient

from server.main import create_app


def login(client, username='piwig'):
    response = client.post('/api/login', json={'username': username, 'password': 'Workbench-testing-2026!'})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def test_workbench_export_preserves_private_work_without_preview_payloads(tmp_path):
    app = create_app(tmp_path, 'Workbench-testing-2026!', secure=False)
    store = app.state.accounts.store('primary')
    store.set('player_pool:123', {'revision': 1, 'watch': True, 'text': 'Private pool note'})
    store.set('player_performance:observations', {'revision': 2, 'observations': [{'player_id': '123'}]})
    store.set('player_performance:preview:temporary', {'token': 'must-not-export'})
    store.set('import_preview:temporary', {'token': 'must-not-export'})
    with TestClient(app) as owner, TestClient(app) as other:
        headers = login(owner)
        exported = owner.get('/api/export').json()['manager_documents']
        assert exported.get('player_pool:123', {}).get('text') == 'Private pool note'
        assert exported.get('player_performance:observations', {}).get('revision') == 2
        assert 'player_performance:preview:temporary' not in exported
        assert 'import_preview:temporary' not in exported
        assert owner.post('/api/admin/users', headers=headers, json={
            'username': 'another_manager', 'password': 'Workbench-testing-2026!'}).status_code == 200
        login(other, 'another_manager')
        assert not any(key.startswith(('player_pool:', 'player_performance:'))
                       for key in other.get('/api/export').json()['manager_documents'])
