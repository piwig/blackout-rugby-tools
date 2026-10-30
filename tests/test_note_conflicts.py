from fastapi.testclient import TestClient
from server.main import create_app

def test_note_conflict_keeps_existing_content_and_watch(tmp_path):
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as client:
        csrf=client.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'}).json()['csrf']
        headers={'X-CSRF-Token':csrf}
        original={'text':'','watch':False}
        base={'team_id':'72450','player_id':'42','expected_note':original}
        first=client.post('/api/notes',headers=headers,json={**base,'text':'Premier avis','watch':True})
        assert first.status_code==200
        stale=client.post('/api/notes',headers=headers,json={**base,'text':'Avis ancien','watch':False})
        assert stale.status_code==409
        note=client.get('/api/state?team_id=72450').json()['notes']['42']
        assert note=={'text':'Premier avis','watch':True}
        changed=client.post('/api/notes',headers=headers,json={**base,'expected_note':note,'text':'Avis relu','watch':False})
        assert changed.status_code==200
        assert client.get('/api/state?team_id=72450').json()['notes']['42']=={'text':'Avis relu','watch':False}

def test_note_precondition_legacy_and_private_scope(tmp_path):
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as client:
        csrf=client.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'}).json()['csrf']
        headers={'X-CSRF-Token':csrf}
        payload={'team_id':'72450','player_id':'42','text':'Note','watch':False,'expected_note':{'text':'','watch':False}}
        assert client.post('/api/notes',json=payload).status_code==403
        assert client.post('/api/notes',headers=headers,json={**payload,'team_id':'999999'}).status_code==404
        # Legacy clients retain the historical payload contract.
        payload.pop('expected_note')
        assert client.post('/api/notes',headers=headers,json=payload).status_code==200
        bad={**payload,'expected_note':{'text':'Note','watch':False,'extra':'refused'}}
        assert client.post('/api/notes',headers=headers,json=bad).status_code==422

