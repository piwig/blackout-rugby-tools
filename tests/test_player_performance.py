"""Synthetic observation contracts: wrong averages, identity collisions and unsafe writes must fail."""
import importlib.util
import inspect
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    if not any(getattr(r, 'path', '') == '/api/player-performance' for r in app.routes):
        from server.player_performance import register_player_performance
        endpoint = next(r for r in app.routes if getattr(r, 'path', '') == '/api/state')
        context = inspect.getclosurevars(endpoint.endpoint).nonlocals
        register_player_performance(app, context['store'], endpoint.dependant.dependencies[0].call, context['require_team'])
        app.router.routes.sort(key=lambda r: getattr(r, 'path', '') == '/{path:path}')
    return app


def login(client, name='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': name, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def row(**changes):
    return {'team_id':'72450', 'context':'club', 'match_id':'17', 'match_date':'2026-10-01',
            'competition':'League', 'opponent':'Synthetic XV', 'venue':'home', 'player_id':'42',
            'player_name':'Synthetic player', 'position':'Centre', 'rating':6, 'rating_scale':'observer-10',
            'scale_min':0, 'scale_max':10, 'minutes':None, 'source':'Manual observer notebook', **changes}


def preview(client, headers, rows, revision=0, mode='append'):
    return client.post('/api/player-performance/preview',headers=headers,json={
        'format':'json','content':json.dumps(rows),'mode':mode,'expected_revision':revision})


def confirm(client, headers, p):
    assert p.status_code == 200, p.text
    return client.post('/api/player-performance/confirm',headers=headers,json={
        'preview_id':p.json()['preview_id'],'expected_revision':p.json()['revision']})


def test_calculates_hand_checked_samples_without_inventing_missing_notes_or_minutes(app):
    with TestClient(app) as c:
        h=login(c)
        p=preview(c,h,[row(minutes=60),row(match_id='18',rating=8),row(match_id='19',rating=None,minutes=20),
                       row(match_id='20',rating=3,rating_scale='observer-5',scale_max=5),row(position='Ailier',rating=None)])
        assert c.get('/api/player-performance').json()['total'] == 0
        assert confirm(c,h,p).status_code == 200
        report=c.get('/api/player-performance?position=Centre&rating_scale=observer-10').json()
        assert report['total'] == 3
        g=report['groups'][0]
        assert (g['mean'],g['min'],g['max'],g['matches'],g['rated'],g['missing_ratings']) == (7,6,8,3,2,1)
        assert (g['known_minutes'],g['minutes_observations'],g['missing_minutes'],g['small_sample']) == (80,2,1,True)
        assert c.get('/api/player-performance?position=Ailier').json()['groups'][0]['mean'] is None
        assert c.get('/api/player-performance?start=2026-10-02').json()['total'] == 0
        assert len(c.get('/api/player-performance?position=Centre').json()['groups']) == 2


def test_duplicates_skip_but_corrections_require_explicit_replace_and_revisions(app):
    with TestClient(app) as c:
        h=login(c)
        assert confirm(c,h,preview(c,h,[row(),row()])).json()['revision'] == 1
        p=preview(c,h,[row()],1)
        assert p.json()['duplicates'] == 1
        assert confirm(c,h,p).json()['revision'] == 1
        assert preview(c,h,[row(rating=9)],1).status_code == 409
        p=preview(c,h,[row(rating=9)],1,'replace')
        assert p.json()['replaced'] == 1
        assert confirm(c,h,p).json()['revision'] == 2
        assert confirm(c,h,p).status_code == 409
        assert c.get('/api/player-performance').json()['groups'][0]['mean'] == 9
        observation_id=c.get('/api/player-performance').json()['observations'][0]['id']
        assert c.post('/api/player-performance/delete',headers=h,json={'ids':[observation_id],'expected_revision':1}).status_code == 409
        assert c.post('/api/player-performance/delete',headers=h,json={'ids':[observation_id],'expected_revision':2}).json()['revision'] == 3
        assert c.get('/api/player-performance').json()['total'] == 0


def test_conflicting_match_context_and_scale_definitions_are_rejected_atomically(app):
    with TestClient(app) as c:
        h=login(c)
        assert preview(c,h,[row(),row(player_id='43',opponent='Other')]).status_code == 422
        assert preview(c,h,[row(),row(match_id='18',scale_max=20)]).status_code == 422
        assert c.get('/api/player-performance').json()['total'] == 0
        p=preview(c,h,[row()]);assert confirm(c,h,p).status_code == 200
        assert preview(c,h,[row(player_id='43',match_date='2026-10-02')],1).status_code == 422


def test_club_youth_u20_nt_match_identifiers_remain_distinct(app):
    with TestClient(app) as c:
        h=login(c)
        with app.state.store.db() as db:
            for tid in ('u20:72450','nt:72450'):
                db.execute('INSERT INTO teams VALUES(?,?,?,?)',(tid,tid,'FR','{}'))
        p=preview(c,h,[row(),row(context='youth'),row(team_id='u20:72450',context='u20'),row(team_id='nt:72450',context='nt')])
        assert confirm(c,h,p).status_code == 200
        assert c.get('/api/player-performance').json()['total'] == 4
        assert len(c.get('/api/player-performance').json()['groups']) == 4
        assert preview(c,h,[row(team_id='u20:72450')],1).status_code == 422


@pytest.mark.parametrize('change',[{'minutes':True},{'minutes':-1},{'rating':True},{'rating':11},{'match_date':'2026-02-30'},
    {'position':''},{'source':''},{'scale_max':0},{'player_id':'nope'},{'team_id':'999999'}, {'rating':float('inf')}])
def test_invalid_observations_never_enter_ledger(app,change):
    with TestClient(app) as c:
        h=login(c)
        assert preview(c,h,[row(),row(match_id='18',**change)]).status_code in (404,422)
        assert c.get('/api/player-performance').json()['total'] == 0


def test_preview_is_private_csrf_protected_and_rechecks_team_access(app):
    with TestClient(app) as c, TestClient(app) as other:
        assert c.get('/api/player-performance').status_code == 401
        h=login(c)
        assert preview(c,{},[row()]).status_code == 403
        p=preview(c,h,[row()])
        c.post('/api/admin/users',headers=h,json={'username':'alice','password':'Another-password-5678'})
        oh=login(other,'alice','Another-password-5678')
        other.post('/api/teams',headers=oh,json={'team_id':'72450','name':'Other private team','country':'FR'})
        assert confirm(other,oh,p).status_code == 404
        assert other.get('/api/player-performance/export').json()['observations'] == []
        with app.state.store.db() as db:db.execute('DELETE FROM teams WHERE id=?',('72450',))
        assert confirm(c,h,p).status_code == 404
        assert c.get('/api/player-performance').json()['total'] == 0


def test_stale_confirmation_cannot_commit_any_rows_and_parallel_confirmation_is_single_use(app):
    with TestClient(app) as c:
        h=login(c);a=preview(c,h,[row()]);b=preview(c,h,[row(match_id='18')])
        assert confirm(c,h,a).status_code == 200
        assert confirm(c,h,b).status_code == 409
        assert c.get('/api/player-performance').json()['total'] == 1
        p=preview(c,h,[row(match_id='19')],1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(lambda _:confirm(c,h,p).status_code,range(2)))
        assert sorted(codes) == [200,409]
        assert c.get('/api/player-performance').json()['total'] == 2


def test_csv_template_roundtrip_export_and_bounded_input(app):
    with TestClient(app) as c:
        h=login(c)
        template=c.get('/api/player-performance/template?team_id=72450').json()
        p=c.post('/api/player-performance/preview',headers=h,json={'format':'csv','content':template['content'],'mode':'append','expected_revision':0})
        assert confirm(c,h,p).status_code == 200
        exported=c.get('/api/player-performance/export').json()
        assert exported['observations'][0]['rating'] is None
        assert exported['observations'][0]['minutes'] is None
        assert preview(c,h,exported['observations'],1).json()['duplicates'] == 1
        assert preview(c,h,[row(match_id=str(i)) for i in range(501)],1).status_code == 422
        assert c.post('/api/player-performance/preview',headers=h,json={'format':'json','content':' '*1_000_001,'expected_revision':1}).status_code == 422
        assert c.get('/api/player-performance?start=2026-12-01&end=2026-01-01').status_code == 422

def test_zero_rating_and_zero_minutes_are_known_and_expired_previews_cannot_write(app):
    with TestClient(app) as c:
        h=login(c)
        assert confirm(c,h,preview(c,h,[row(rating=0,minutes=0)])).status_code == 200
        g=c.get('/api/player-performance').json()['groups'][0]
        assert (g['mean'],g['min'],g['max'],g['known_minutes'],g['missing_minutes']) == (0,0,0,0,0)
        p=preview(c,h,[row(match_id='18')],1)
        key='player_performance:preview:'+p.json()['preview_id']
        doc=app.state.store.get(key);doc['expires_at']=0;app.state.store.set(key,doc)
        assert confirm(c,h,p).status_code == 409
        assert c.get('/api/player-performance').json()['total'] == 1


def test_invalid_deep_json_is_bounded_validation_error(app):
    with TestClient(app) as c:
        h=login(c)
        response=c.post('/api/player-performance/preview',headers=h,json={
            'format':'json','content':'['*2000+']'*2000,'expected_revision':0})
        assert response.status_code == 422

def test_declared_scale_bounds_can_be_unknown_together_but_are_not_invented(app):
    with TestClient(app) as c:
        h=login(c)
        p=preview(c,h,[row(rating=12,rating_scale='Classic-rs-current',scale_min=None,scale_max=None)])
        assert confirm(c,h,p).status_code == 200
        g=c.get('/api/player-performance').json()['groups'][0]
        assert (g['mean'],g['scale_min'],g['scale_max']) == (12,None,None)
        assert preview(c,h,[row(match_id='18',scale_min=None)],1).status_code == 422

def test_utf8_payload_limit_counts_bytes_not_only_characters(app):
    with TestClient(app) as c:
        h=login(c)
        rows=[row(match_id=str(i+1),source='測'*500,player_name='測'*160,competition='測'*160,opponent='測'*160,position='測'*80) for i in range(400)]
        content=json.dumps(rows,ensure_ascii=False)
        assert len(content)<1_000_000 and len(content.encode('utf-8'))>1_000_000
        response=c.post('/api/player-performance/preview',headers=h,json={
            'format':'json','content':content,'expected_revision':0})
        assert response.status_code==422
        assert c.get('/api/player-performance').json()['total']==0
