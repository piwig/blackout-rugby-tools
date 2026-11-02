import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED','0')
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as c:
        login=c.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'})
        c.headers['X-CSRF-Token']=login.json()['csrf']
        assert c.post('/api/teams',json={'team_id':'9','name':'Synthetic club'}).status_code==200
        yield c


@pytest.mark.parametrize('path,extra',[('fixtures',{}),('read',{'reference':'90'}),('recent',{'reference':'90'})])
def test_sheet_routes_auth_csrf_and_workspace(client,monkeypatch,path,extra):
    calls=[]
    async def fake(*args,**kwargs): calls.append(args); return {'team_id':'9','match_type':3}
    monkeypatch.setattr('server.main.list_sheet_fixtures',fake)
    monkeypatch.setattr('server.main.fetch_match_sheet',fake)
    monkeypatch.setattr('server.main.compare_recent_matches',fake,raising=False)
    body={'team_id':'9','match_type':3,**extra}
    url='/api/match-sheet/'+path
    csrf=client.headers.pop('X-CSRF-Token')
    assert client.post(url,json=body).status_code==403
    client.headers['X-CSRF-Token']=csrf
    assert client.post(url,json={**body,'team_id':'8'}).status_code==404
    assert not calls
    assert client.post(url,json=body).status_code==200
    assert len(calls)==1
    assert client.post('/api/admin/users',json={'username':'tester','password':'Another-password-1234'}).status_code==200
    login=client.post('/api/login',json={'username':'tester','password':'Another-password-1234'})
    client.headers['X-CSRF-Token']=login.json()['csrf']
    assert client.post(url,json=body).status_code==404
    client.cookies.clear()
    assert client.post(url,json=body).status_code==401
    assert len(calls)==1
