from fastapi.testclient import TestClient
from server.main import create_app


def test_private_advice_requires_current_session_and_owned_team(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with app.state.store.db() as db:
        db.execute("INSERT INTO teams(id,name,country) VALUES('9','Private club','BE')")
    with TestClient(app) as client:
        assert client.get('/api/coach-advice?team_id=9').status_code == 401
        token = client.post('/api/login', json={'username':'piwig','password':'Testing-password-1234'}).json()['csrf']
        assert client.get('/api/coach-advice?team_id=9').status_code == 403
        headers = {'X-CSRF-Token':token}
        report = client.get('/api/coach-advice?team_id=9', headers=headers)
        assert report.status_code == 200
        assert report.json()['team']['id'] == '9'
        assert client.get('/api/coach-advice?team_id=999', headers=headers).status_code == 404
        assert client.post('/api/admin/users', headers=headers, json={'username':'tester','password':'Different-password-1234'}).status_code == 200
        other = client.post('/api/login', json={'username':'tester','password':'Different-password-1234'}).json()['csrf']
        assert client.get('/api/coach-advice?team_id=9',headers=headers).status_code == 403
        assert client.get('/api/insights/9',headers=headers).status_code == 403
        assert client.get('/api/coach-advice?team_id=9',headers={'X-CSRF-Token':other}).status_code == 404
