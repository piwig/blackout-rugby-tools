import pytest
from fastapi.testclient import TestClient
from server.main import create_app
from server.match_import import normalize_match_document


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED', '0')
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    with TestClient(app) as c:
        login = c.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
        c.headers['X-CSRF-Token'] = login.json()['csrf']
        yield c


def doc():
    return {'id':'123','type':0,'home':'Home','away':'Away','events':[
        {'id':'1','commentary':'A synthetic unknown action.','possession':'0','field':'2'}]}


def test_preview_is_read_only_and_confirmation_is_single_use(client, monkeypatch):
    async def fetch(*args, **kwargs): return doc()
    monkeypatch.setattr('server.match_routes.fetch_match', fetch)
    preview = client.post('/api/matches/direct/preview', json={'reference':'123','type':0})
    assert preview.status_code == 200, preview.text
    assert client.get('/api/matches/0/123').status_code == 404
    p = preview.json()
    body={key:p[key] for key in ('source_token','expected_revision','expected_source_digest')}
    saved = client.post('/api/matches/direct/confirm',json=body)
    assert saved.status_code == 200 and saved.json()['match']['summary']['total_events']==1
    assert client.post('/api/matches/direct/confirm',json=body).status_code == 409


def test_source_changed_since_preview_prevents_overwrite(client, monkeypatch):
    async def fetch(*args, **kwargs): return doc()
    monkeypatch.setattr('server.match_routes.fetch_match', fetch)
    p=client.post('/api/matches/direct/preview',json={'reference':'123','type':0}).json()
    assert client.post('/api/matches/import',json={**doc(),'home':'Newer home'}).status_code==200
    body={key:p[key] for key in ('source_token','expected_revision','expected_source_digest')}
    assert client.post('/api/matches/direct/confirm',json=body).status_code==409
    assert client.get('/api/matches/0/123').json()['home']=='Newer home'


def test_annotation_changed_since_preview_prevents_overwrite(client, monkeypatch):
    client.post('/api/matches/import',json=doc())
    async def fetch(*args, **kwargs): return doc()
    monkeypatch.setattr('server.match_routes.fetch_match', fetch)
    p=client.post('/api/matches/direct/preview',json={'reference':'123','type':0}).json()
    m=client.get('/api/matches/0/123').json()
    change={'event_key':m['events'][0]['event_key'],'classification':'attack','att':'percu','possession':0,'field':2,'learn':False}
    assert client.post('/api/matches/0/123/annotations',json={'expected_revision':m['review']['revision'],'expected_source_digest':m['review']['source_digest'],'changes':[change]}).status_code==200
    body={key:p[key] for key in ('source_token','expected_revision','expected_source_digest')}
    assert client.post('/api/matches/direct/confirm',json=body).status_code==409
    assert client.get('/api/matches/0/123').json()['summary']['classified']==1


def test_preview_token_bound_to_manager(client, monkeypatch):
    async def fetch(*args, **kwargs): return doc()
    monkeypatch.setattr('server.match_routes.fetch_match', fetch)
    p=client.post('/api/matches/direct/preview',json={'reference':'123','type':0}).json()
    client.post('/api/admin/users',json={'username':'tester','password':'Another-password-1234'})
    login=client.post('/api/login',json={'username':'tester','password':'Another-password-1234'})
    client.headers['X-CSRF-Token']=login.json()['csrf']
    body={key:p[key] for key in ('source_token','expected_revision','expected_source_digest')}
    assert client.post('/api/matches/direct/confirm',json=body).status_code==409
    assert client.get('/api/matches/0/123').status_code==404


def test_oversized_preview_does_not_evict_existing_preview(client, monkeypatch):
    current=doc()
    async def fetch(*args, **kwargs): return current
    monkeypatch.setattr('server.match_routes.fetch_match', fetch)
    p=client.post('/api/matches/direct/preview',json={'reference':'123','type':0}).json()
    current={**doc(),'id':'456','events':[{'text':'x'*2000,'commentary':'x'*2000} for _ in range(4100)]}
    refused=client.post('/api/matches/direct/preview',json={'reference':'456','type':0})
    assert refused.status_code==413
    assert 'source_token' not in refused.json()
    assert client.get('/api/matches/0/456').status_code==404
    body={key:p[key] for key in ('source_token','expected_revision','expected_source_digest')}
    assert client.post('/api/matches/direct/confirm',json=body).status_code==200


def test_legacy_sync_retains_top_level_effective_summary(client, monkeypatch):
    client.post('/api/matches/import',json=doc())
    match=client.get('/api/matches/0/123').json()
    change={'event_key':match['events'][0]['event_key'],'classification':'attack','att':'percu','possession':0,'field':2,'learn':False}
    edited=client.post('/api/matches/0/123/annotations',json={'expected_revision':match['review']['revision'],'expected_source_digest':match['review']['source_digest'],'changes':[change]})
    assert edited.status_code==200
    # The real Classic adapter returns normalized events, like file imports.
    async def fetch(*args, **kwargs): return normalize_match_document(doc())
    monkeypatch.setattr('server.match_routes.fetch_match', fetch)
    synced=client.post('/api/matches/sync',json={'id':'123','type':0})
    assert synced.status_code==200
    assert synced.json()['summary']==synced.json()['match']['summary']
    assert synced.json()['summary']['manual']==1
