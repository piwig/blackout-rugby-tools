import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.mark.parametrize('language',['fr','en','es','it'])
def test_registration_keeps_selected_language_in_private_profile(tmp_path,language):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as client:
        response=client.post('/api/register',json={'username':'newmanager','password':'New-manager-password-1234','email':'manager@example.test','language':language})
        assert response.status_code==200
        assert client.get('/api/profile').json()['profile']['language']==language
        assert client.get('/api/state').json()['profile']['profile']['language']==language
        assert client.get('/api/profile').json()['revision']==1


@pytest.mark.parametrize('language',['de','EN','',None,4])
def test_registration_rejects_unknown_language_without_creating_account(tmp_path,language):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as client:
        response=client.post('/api/register',json={'username':'newmanager','password':'New-manager-password-1234','email':'manager@example.test','language':language})
        assert response.status_code==422
        assert not app.state.accounts.user('newmanager')
