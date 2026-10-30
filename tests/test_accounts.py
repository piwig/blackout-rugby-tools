from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from server.main import create_app

def sign_in(client,username='piwig',password='Testing-password-1234'):
    r=client.post('/api/login',json={'username':username,'password':password})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def test_private_accounts_cannot_read_each_others_data(tmp_path):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as admin,TestClient(app) as other:
        h=sign_in(admin)
        r=admin.post('/api/admin/users',headers=h,json={'username':'franck','password':'Another-password-5678'})
        assert r.status_code==200,r.text
        oh=sign_in(other,'franck','Another-password-5678')
        assert other.get('/api/state').json()['setup_required'] is True
        assert other.get('/api/admin/users').status_code==403
        assert other.get('/api/history/72450/42').status_code==404
        assert other.get('/api/export').json()['teams']==[]
        assert other.post('/api/teams',headers=oh,json={'team_id':'72450','name':'Mon club','country':'BE'}).status_code==200
        for c,headers,label in [(admin,h,'private-admin'),(other,oh,'private-franck')]:
            assert c.post('/api/notes',headers=headers,json={'team_id':'72450','player_id':'42','text':label}).status_code==200
            assert c.post('/api/matches/import',headers=headers,json={'id':'9','type':0,'home':label,'away':'B','events':[]}).status_code==200
        def state(c):return c.get('/api/state?team_id=72450').json()
        with ThreadPoolExecutor(2) as pool:
            a,b=list(pool.map(state,[admin,other]))
        assert a['notes']['42']['text']=='private-admin'
        assert b['notes']['42']['text']=='private-franck'
        assert a['matches'][0]['home']=='private-admin'
        assert b['matches'][0]['home']=='private-franck'
        assert 'private-admin' not in other.get('/api/export').text
        assert other.post('/api/admin/users',headers=oh,json={'username':'evil','password':'Another-password-5678'}).status_code==403

def test_password_change_requires_old_password_and_revokes_sessions(tmp_path):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as a,TestClient(app) as b:
        h=sign_in(a);sign_in(b)
        assert a.post('/api/account/password',headers=h,json={'current_password':'wrong','new_password':'Changed-password-5678'}).status_code==403
        assert a.post('/api/account/password',headers=h,json={'current_password':'Testing-password-1234','new_password':'Changed-password-5678'}).status_code==200
        assert b.get('/api/state').status_code==401
        assert a.get('/api/state').status_code==401
        assert a.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'}).status_code==401
        sign_in(a,password='Changed-password-5678')

def test_bad_manager_key_never_changes_saved_account(tmp_path,monkeypatch):
    from server.classic import ClassicClient,ClassicError
    async def fail(*args,**kwargs):raise ClassicError('Accès refusé')
    monkeypatch.setattr(ClassicClient,'request',fail)
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as c:
        h=sign_in(c)
        r=c.post('/api/classic/import',headers=h,json={'access_key':'m=123&mk=INVALID','developer_id':'1','developer_key':'DEV'})
        assert r.status_code==422
        assert not c.get('/api/state').json()['settings']['manager_ready']

def test_classic_import_discovers_and_saves_owned_teams(tmp_path,monkeypatch):
    from server.classic import ClassicClient
    async def fake(self,resource,**params):
        if resource=='m':return {'members':{'123':{'id':'123','username':'Manager','email':'PRIVATE@example.com','teams':['101','102']}},'gameDate':{'season':62,'round':9,'day':6}}
        if resource=='t':
            tid=params['teamid'];return {'teams':{tid:{'id':tid,'owner':'123','name':'Club '+tid,'country_iso':'BE','members':'500'}}}
        if resource=='p':return {'players':{'42':{'name':'Player','strength':'10'}},'gameDate':{'season':62,'round':9,'day':6}}
        raise AssertionError(resource)
    monkeypatch.setattr(ClassicClient,'request',fake)
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as c:
        h=sign_in(c)
        r=c.post('/api/classic/import',headers=h,json={'access_key':'m=123&mk=KEY','developer_id':'1','developer_key':'DEV'})
        assert r.status_code==200,r.text
        assert len(r.json()['teams'])==2
        for tid in ('101','102'):
            s=c.get('/api/state?team_id='+tid).json()
            assert len(s['academy'])==len(s['squad'])==1
            assert s['settings']['manager_ready'] is True
            assert 'PRIVATE@example.com' not in str(s)
        assert 'KEY' not in c.get('/api/export').text
