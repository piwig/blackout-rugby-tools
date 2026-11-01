"""Synthetic API tests exercise real authentication, storage and atomic preview confirmation."""
import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from server.main import create_app
from tests.test_coach_engine import player


@pytest.fixture
def app(tmp_path):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    if not any(getattr(r,'path','')=='/api/coach-lab' for r in app.routes):
        from server.coach_lab import register_coach_lab
        route=next(r for r in app.routes if getattr(r,'path','')=='/api/state')
        context=inspect.getclosurevars(route.endpoint).nonlocals
        register_coach_lab(app,context['store'],route.dependant.dependencies[0].call,context['require_team'],route.endpoint)
        app.router.routes.sort(key=lambda r:getattr(r,'path','')=='/{path:path}')
    return app


def setup(client,app):
    response=client.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'})
    assert response.status_code==200
    app.state.store.save_snapshot('72450',False,[player(str(i)) for i in range(1,24)],'Synthetic source','2026-10-31')
    return {'X-CSRF-Token':response.json()['csrf']}


def preview(client,h,cohort='club',**changes):
    doc=client.get('/api/coach-lab',params={'team_id':'72450','cohort':cohort}).json()
    return client.post('/api/coach-lab/preview',headers=h,json={'team_id':'72450','cohort':cohort,'expected_revision':doc['revision'],'config':doc['config'],**changes})


def confirm(client,h,p,cohort='club',apply=True):
    assert p.status_code==200,p.text
    return client.post('/api/coach-lab/confirm',headers=h,json={'team_id':'72450','cohort':cohort,'preview_id':p.json()['preview_id'],'apply_local':apply})


def test_auth_csrf_ownership_and_finite_bounded_config(app):
    with TestClient(app) as c:
        assert c.get('/api/coach-lab?team_id=72450&cohort=club').status_code==401
        h=setup(c,app);doc=c.get('/api/coach-lab?team_id=72450&cohort=club').json()
        assert c.get('/api/coach-lab?team_id=999&cohort=club').status_code==404
        body={'team_id':'72450','cohort':'club','expected_revision':0,'config':doc['config']}
        assert c.post('/api/coach-lab/preview',json=body).status_code==403
        body['config']['weights']['1']['strength']=-1
        assert c.post('/api/coach-lab/preview',headers=h,json=body).status_code==422
        body['config']=doc['config'];body['cohort']='nt'
        assert c.post('/api/coach-lab/preview',headers=h,json=body).status_code==422


def test_saved_evidence_and_local_lineup_are_atomic_and_replay_is_rejected(app):
    with TestClient(app) as c:
        h=setup(c,app);p=preview(c,h)
        assert confirm(c,h,p).status_code==200
        doc=c.get('/api/coach-lab?team_id=72450&cohort=club').json()
        assert doc['revision']==1
        assert doc['sheet']['source']['source']=='Synthetic source'
        assert app.state.store.get('lineup:72450')==doc['sheet']['slots']
        assert confirm(c,h,p).status_code==409


@pytest.mark.parametrize('change',['roster','lineup','performance','document','ttl'])
def test_any_relevant_revision_change_invalidates_preview(app,change):
    with TestClient(app) as c:
        h=setup(c,app);p=preview(c,h);assert p.status_code==200,p.text
        if change=='roster':app.state.store.save_snapshot('72450',False,[player('98')],'New synthetic source')
        if change=='lineup':app.state.store.set('lineup:72450',{'1':'23'})
        if change=='performance':app.state.store.set('player_performance:observations',{'revision':1,'observations':[]})
        if change=='document':assert confirm(c,h,preview(c,h),apply=False).status_code==200
        if change=='ttl':
            key='coach_preview:'+p.json()['preview_id'];stored=app.state.store.get(key);stored['expires']=time.time()-1;app.state.store.set(key,stored)
        assert confirm(c,h,p).status_code==409
        assert app.state.store.get('lineup:72450',{})==({'1':'23'} if change=='lineup' else {})


def test_youth_is_independent_and_hidden_skills_stay_unknown(app):
    with TestClient(app) as c:
        h=setup(c,app);app.state.store.save_snapshot('72450',True,[player('1',strength=None,technique=None)],'Synthetic youth')
        p=preview(c,h,'youth',manual_slots={'1':'1'})
        assert confirm(c,h,p,'youth').status_code==200
        assert app.state.store.get('coach_lineup:72450:youth')=={'1':'1'}
        assert app.state.store.get('lineup:72450',{})=={}
        doc=c.get('/api/coach-lab?team_id=72450&cohort=youth').json()
        assert doc['sheet']['players'][0]['score'] is None
        assert c.get('/api/coach-lab?team_id=72450&cohort=club').json()['revision']==0


def test_concurrent_confirm_only_one_writes(app):
    with TestClient(app) as c:
        h=setup(c,app);a,b=preview(c,h),preview(c,h)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda p:confirm(c,h,p),[a,b]))
        assert sorted(r.status_code for r in responses)==[200,409]


def test_other_manager_cannot_read_or_consume_private_preview(app):
    with TestClient(app) as c, TestClient(app) as other:
        h=setup(c,app);p=preview(c,h)
        assert c.post('/api/admin/users',headers=h,json={'username':'alice','password':'Another-password-5678'}).status_code==200
        response=other.post('/api/login',json={'username':'alice','password':'Another-password-5678'})
        oh={'X-CSRF-Token':response.json()['csrf']}
        assert other.post('/api/teams',headers=oh,json={'team_id':'72450','name':'Synthetic other','country':'FR'}).status_code==200
        assert other.get('/api/coach-lab?team_id=72450&cohort=club').json()['revision']==0
        assert confirm(other,oh,p).status_code==409
        assert confirm(c,h,p).status_code==200


def test_numeric_tactics_totals_and_missing_dates_are_validated(app):
    with TestClient(app) as c:
        h=setup(c,app);p=preview(c,h);plan=p.json()['sheet']['tactics']
        tactics={k:plan[k] for k in ('attacks','kick_frequency','kick_types','defense','intensity','discipline')}
        tactics['attacks']['driving']+=1
        assert preview(c,h,tactics=tactics).status_code==422
        tactics['attacks']['driving']-=1
        assert preview(c,h,tactics=tactics).status_code==200
        config=c.get('/api/coach-lab?team_id=72450&cohort=club').json()['config']
        config['opponent']={'name':'Synthetic','source':'Notebook','observed_at':'2026-02-30','exposure':'driving'}
        assert preview(c,h,config=config).status_code==422
