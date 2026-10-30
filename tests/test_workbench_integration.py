"""Full backups include new manager work without exposing credential KV records."""
from fastapi.testclient import TestClient
from server.main import create_app


def test_export_includes_new_private_documents_but_never_credentials(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    store = app.state.store
    store.set('lineup_lab:72450', {'revision': 2, 'scenarios': [{'name': 'Rotation'}]})
    store.set('insights:72450', {'revision': 1, 'objectives': [{'label': 'U20'}]})
    store.set('workbench:calendar:72450', {'revision': 3, 'events': [{'title': 'Match'}]})
    store.set('api_developer', 'TOP-SECRET')
    with TestClient(app) as client:
        assert client.get('/api/export').status_code == 401
        login = client.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
        headers = {'X-CSRF-Token': login.json()['csrf']}
        response = client.get('/api/export')
        assert response.status_code == 200
        data = response.json()
        assert data['manager_documents']['lineup_lab:72450']['scenarios'][0]['name'] == 'Rotation'
        assert data['manager_documents']['insights:72450']['revision'] == 1
        assert data['manager_documents']['workbench:calendar:72450']['revision'] == 3
        assert 'TOP-SECRET' not in response.text
        assert 'api_developer' not in response.text
        client.post('/api/admin/users', headers=headers, json={'username': 'friend', 'password': 'Another-password-5678'})
        client.post('/api/login', json={'username': 'friend', 'password': 'Another-password-5678'})
        assert client.get('/api/export').json()['manager_documents'] == {}
