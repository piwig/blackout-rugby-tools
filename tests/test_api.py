import pytest,json
from fastapi.testclient import TestClient
from server import main

@pytest.fixture
def client(tmp_path):
    with TestClient(main.create_app(tmp_path,'Testing-password-1234',secure=False)) as c:yield c

def login(c):
    r=c.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'})
    assert r.status_code==200
    return {'X-CSRF-Token':r.json()['csrf']}

def test_authentication_and_csrf_are_enforced(client):
    assert client.get('/api/state').status_code==401
    assert client.get('/api/export').status_code==401
    assert client.post('/api/login',json={'username':'piwig','password':'no'}).status_code==401
    headers=login(client)
    assert client.get('/api/state').status_code==200
    assert client.post('/api/notes',json={'team_id':'72450','player_id':'42','text':'ok','watch':True}).status_code==403
    assert client.post('/api/notes',headers={**headers,'Origin':'https://evil.example'},json={'team_id':'72450','player_id':'42','text':'ok','watch':True}).status_code==403
    assert client.post('/api/logout',headers=headers).status_code==200
    assert client.get('/api/state').status_code==401

def test_import_is_persistent_idempotent_and_invalid_import_is_atomic(client):
    h=login(client);csv=b'player_id,player_name,age,strength\n42,A,16,Unknown'
    for _ in range(2):
        r=client.post('/api/import',headers=h,data={'team_id':'72450','youth':'true'},files={'file':('academy.csv',csv,'text/csv')})
        assert r.status_code==200,r.text
    s=client.get('/api/state?team_id=72450').json()
    assert s['academy'][0]['strength']=='Unknown'
    assert len(s['snapshots'])==1
    assert client.post('/api/import',headers=h,data={'team_id':'72450'},files={'file':('bad.json',b'broken','application/json')}).status_code==422
    assert len(client.get('/api/state?team_id=72450').json()['academy'])==1

def test_secrets_are_write_only_and_encrypted(client):
    h=login(client)
    r=client.post('/api/settings',headers=h,json={'team_id':'72450','developer_id':'123','developer_key':'SECRET-DEV','manager_id':'42','manager_key':'SECRET-MEMBER'})
    assert r.status_code==200
    assert 'SECRET' not in client.get('/api/state').text
    assert 'SECRET' not in client.get('/api/export').text
    for p in client.app.state.store.path.parent.glob('*.sqlite*'):
        assert b'SECRET-DEV' not in p.read_bytes()

def test_match_type_is_part_of_identity_and_stats_are_available(client):
    h=login(client)
    for t in [0,1,2]:
        r=client.post('/api/matches/import',headers=h,json={'id':'99','type':t,'home':'A','away':'B','events':[{'field':1,'possession':t%2,'att':'percu'}]})
        assert r.status_code==200,r.text
    matches=client.get('/api/state').json()['matches']
    assert len(matches)==3
    assert all(m['summary']['classified']==1 for m in matches)

def test_plans_notes_and_lineup_survive_reload(client):
    h=login(client)
    grid=[['stamina']*16 for _ in range(4)]
    assert client.post('/api/plans',headers=h,json={'team_id':'72450','season':62,'grid':grid}).status_code==200
    assert client.post('/api/notes',headers=h,json={'team_id':'72450','player_id':'42','text':'à suivre','watch':True}).status_code==200
    assert client.post('/api/lineup',headers=h,json={'team_id':'72450','slots':{'1':'42','2':'42'}}).status_code==422
    assert client.post('/api/lineup',headers=h,json={'team_id':'72450','slots':{'1':'42'}}).status_code==200
    s=client.get('/api/state').json()
    assert s['plans']['62'][0][0]=='stamina'
    assert s['notes']['42']['watch'] is True
    assert s['lineup']['1']=='42'

def test_failed_sync_preserves_snapshot(client):
    h=login(client)
    client.post('/api/import',headers=h,data={'team_id':'72450','youth':'true'},files={'file':('a.csv',b'player_id,player_name\n42,A')})
    r=client.post('/api/sync',headers=h,json={'team_id':'72450','kind':'academy'})
    assert r.status_code==422
    assert len(client.get('/api/state').json()['academy'])==1

def test_return_to_earlier_values_creates_a_new_observation(client):
    h=login(client)
    for value in [10,11,10]:
        r=client.post('/api/import',headers=h,data={'team_id':'72450','youth':'true'},files={'file':('a.csv',f'player_id,player_name,strength\n42,A,{value}'.encode())})
        assert r.status_code==200
    s=client.get('/api/state').json()
    assert s['academy'][0]['strength']==10
    assert len(s['snapshots'])==3

def test_full_export_includes_saved_lineup_without_credentials(client):
    h=login(client)
    client.post('/api/lineup',headers=h,json={'team_id':'72450','slots':{'1':'42'}})
    assert client.get('/api/export').json()['lineups']['72450']=={'1':'42'}

@pytest.mark.parametrize('bad',['NaN','Infinity','1e100','-1','22','true','{}','"garbage"'])
def test_invalid_skill_import_preserves_readable_snapshot(client,bad):
    h=login(client)
    client.post('/api/import',headers=h,data={'team_id':'72450'},files={'file':('a.csv',b'player_id,player_name,strength\n42,A,10')})
    raw=('{"players":[{"id":"42","name":"A","strength":'+bad+'}]}').encode()
    r=client.post('/api/import',headers=h,data={'team_id':'72450'},files={'file':('a.json',raw)})
    assert r.status_code==422
    s=client.get('/api/state')
    assert s.status_code==200
    assert s.json()['academy'][0]['strength']==10
    assert len(s.json()['snapshots'])==1

def test_match_csv_import_keeps_quoted_comments_and_orientation(client):
    h=login(client)
    raw='field;possession;att;text\n1;0;percu;"Une action; avec virgule"\n1;1;large;Visiteurs'.encode()
    r=client.post('/api/matches/file',headers=h,data={'id':'42','type':'1','home':'A','away':'B'},files={'file':('match.csv',raw)})
    assert r.status_code==200,r.text
    m=client.get('/api/matches/1/42').json()
    assert m['events'][0]['text']=='Une action; avec virgule'
    assert m['summary']['home']['zones']['22']['Percussion']==1
    assert m['summary']['away']['zones']['22A']['Large']==1
