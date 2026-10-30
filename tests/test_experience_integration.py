"""Profile integration must stay private in state and explicit exports."""
from fastapi.testclient import TestClient
from server.main import create_app


def login(client,name='piwig',password='Testing-password-1234'):
    response=client.post('/api/login',json={'username':name,'password':password})
    assert response.status_code==200
    return {'X-CSRF-Token':response.json()['csrf']}


def test_profile_state_export_are_scoped_to_logged_manager(tmp_path):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as first,TestClient(app) as second:
        headers=login(first)
        assert first.get('/api/state').json()['profile']['revision']==0
        document=first.get('/api/profile').json()
        document['profile']['display_name']='Le coach privé'
        saved=first.post('/api/profile',headers=headers,json={'expected_revision':0,'profile':document['profile']})
        assert saved.status_code==200
        assert first.get('/api/state').json()['profile']==saved.json()
        export=first.get('/api/export').json()
        assert export['manager_documents']['profile:preferences']['profile']['display_name']=='Le coach privé'
        assert all(key.startswith(('workbench:','insights:','lineup_lab:')) or key=='profile:preferences' for key in export['manager_documents'])
        assert first.post('/api/admin/users',headers=headers,json={'username':'newmanager','password':'Another-password-5678'}).status_code==200
        login(second,'newmanager','Another-password-5678')
        state=second.get('/api/state').json()
        assert state['setup_required'] is True
        assert state['profile']['profile']['display_name']==''
        assert 'profile:preferences' not in second.get('/api/export').json()['manager_documents']


def test_new_manager_can_start_with_manual_club_before_import(tmp_path):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as admin,TestClient(app) as new:
        ah=login(admin)
        admin.post('/api/admin/users',headers=ah,json={'username':'newmanager','password':'Another-password-5678'})
        nh=login(new,'newmanager','Another-password-5678')
        assert new.post('/api/teams',headers=nh,json={'team_id':'888','name':'Mon premier club','country':'FR'}).status_code==200
        state=new.get('/api/state').json()
        assert state['setup_required'] is False
        assert state['current_team']['id']=='888'
        assert state['squad']==[] and state['academy']==[]
        assert new.get('/api/progression?team_id=888').json()['seniors']['points']==[]


def test_registration_contact_export_stays_private(tmp_path,monkeypatch):
    monkeypatch.setattr('server.contact._notify',lambda *args:'sent')
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as first,TestClient(app) as second:
        result=first.post('/api/register',json={'username':'private_manager','password':'Secret password 123456','email':'private@example.org','avatar_style':'rugby'})
        assert result.status_code==200
        csrf={'X-CSRF-Token':result.json()['csrf']}
        assert result.json()['user']['admin']==0
        assert first.get('/api/state').json()['profile']['profile']['avatar_style']=='rugby'
        first.post('/api/contact',headers=csrf,json={'kind':'feature','subject':'Mon idée','message':'Une idée privée','email':'private@example.org'})
        export=first.get('/api/export').json()
        assert export['account_contact']['email']=='private@example.org'
        assert export['contact_messages'][0]['message']=='Une idée privée'
        assert 'notification_status' not in export['contact_messages'][0]
        login(second)
        assert second.get('/api/export').json()['contact_messages']==[]
        assert first.get('/api/contact/admin').status_code==403
        assert len(second.get('/api/contact/admin').json()['items'])==1


def test_stream_export_can_advance_on_different_worker_threads(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from server.exports import export_chunks
    import json
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    accounts=app.state.accounts
    chunks=export_chunks(accounts.store('primary'),accounts,'primary')
    pools=[ThreadPoolExecutor(max_workers=1) for _ in range(3)]
    values=[]
    try:
        while True:
            try:values.append(pools[len(values)%3].submit(next,chunks).result())
            except StopIteration:break
        doc=json.loads(''.join(values))
        assert len(doc['teams'])==7 and doc['contact_messages']==[]
    finally:
        chunks.close()
        for pool in pools:pool.shutdown()


def test_legacy_metadata_and_duplicate_history_are_bounded(tmp_path):
    import json
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    store=app.state.store
    players=[{'id':'42','name':'Joueur','speed':12},{'id':'42','name':'Doublon','speed':13}]
    store.save_snapshot('72450',True,players,'x'*2000,'2026-10-30')
    with store.db() as db:
        assert len(db.execute('SELECT source FROM snapshots').fetchone()[0])==500
        db.execute('UPDATE snapshots SET source=?',('x'*100000,))
    with TestClient(app) as client:
        login(client)
        state=client.get('/api/state?team_id=72450').json()
        assert len(state['academy_source']['source'])==500
        assert len(state['snapshots'][0]['source'])==500
        history=client.get('/api/history/72450/42').json()
        assert len(history)==1 and len(history[0]['source'])==500
        series=client.get('/api/progression?team_id=72450').json()
        assert len(json.dumps(series))<30000


def test_duplicate_players_are_rejected_before_storage():
    import json,pytest
    from server.imports import parse_import
    body=json.dumps([{'id':'42','name':'A'},{'id':'42','name':'B'}]).encode()
    with pytest.raises(ValueError,match='même identifiant'):
        parse_import(body,'players.json')
