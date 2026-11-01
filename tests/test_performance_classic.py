"""Synthetic copies of documented JSON shapes; never contact Classic."""
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from server.classic import ClassicClient, ClassicError

NOW=datetime(2026,11,1,tzinfo=timezone.utc)


def documents():
    fixture={'status':'Ok','fixtures':{'17':{'id':'17','hometeamid':'72450','guestteamid':'99',
        'matchstart':'2026-10-01T12:00:00+00:00','matchfinish':'2026-10-01T14:00:00+00:00','competition':'League','stadium':'0'}}}
    summary={'status':'Ok','home':{'teamid':'72450','players':{
        '1':{'playerid':42,'position':12,'rating':12,'potential':'reached','performance':'normal'},
        '2':{'playerid':'43','position':18,'rating':7,'performance':'over'},
        '3':{'playerid':'44','position':3},
        '4':{'playerid':'45','position':5,'rating_old':4}}},'guest':{'teamid':'99','players':{}}}
    statistics={'status':'Ok','fixtures':{'17':{'home player 1':{'id':'43','minutes played':20,'ball time':500},
        'home player 2':{'id':'42','minutes played':65,'played':1},'home player 3':{'id':'44','ball time':80}}}}
    return {'f':fixture,'rs':summary,'fs':statistics}


def run_read(monkeypatch,docs=None,context='club',team_id='72450'):
    from server.performance_classic import read_match_observations
    docs=docs or documents();sent=[]
    async def send(self,method,query,data=None,before_send=None):
        sent.append((method,query,data));return json.dumps(docs[query['r']]).encode()
    monkeypatch.setattr(ClassicClient,'_send',send)
    client=ClassicClient({'d':'1','dk':'synthetic','m':'2','mk':'synthetic-manager'})
    return asyncio.run(read_match_observations(client,team_id,context,'17',names={'42':'Synthetic player'},current=NOW)),sent


def test_reporter_json_reads_use_exact_id_and_one_context_flag_only(monkeypatch):
    sent=[]
    async def send(self,method,query,data=None,before_send=None):
        sent.append((method,query,data));return b'{"status":"Ok"}'
    monkeypatch.setattr(ClassicClient,'_send',send)
    client=ClassicClient({'d':'1','dk':'synthetic'})
    for context,flag in [('club',None),('youth','youth'),('u20','u20'),('nt','nat')]:
        asyncio.run(client.read_reporter_summary('17',context))
        assert sent[-1][0]=='GET' and sent[-1][2] is None
        assert sent[-1][1]['r']=='rs' and sent[-1][1]['fixtureid']=='17'
        assert {key for key in sent[-1][1] if key in ('youth','u20','nat')} == ({flag} if flag else set())
    with pytest.raises(ClassicError):asyncio.run(client.request('rs',fixtureid='17',fixtureids='18'))
    with pytest.raises(ClassicError):asyncio.run(client.request('rs',fixtureid='17',nat='1',u20='1'))
    with pytest.raises(ClassicError):asyncio.run(client.read_reporter_summary(True,'club'))
    with pytest.raises(ClassicError):asyncio.run(client.read_reporter_summary('17','unknown'))
    assert len(sent)==4


def test_current_legacy_and_bench_ratings_stay_distinct_and_minutes_join_by_id_not_slot(monkeypatch):
    result,sent=run_read(monkeypatch)
    rows={r['player_id']:r for r in result['observations']}
    assert len(rows)==4
    assert (rows['42']['player_name'],rows['42']['rating'],rows['42']['minutes'],rows['42']['position'],rows['42']['position_basis']) == ('Synthetic player',12,65,'Centre','report_start')
    assert (rows['42']['scale_min'],rows['42']['scale_max']) == (None,None)
    assert rows['43']['position_basis']=='report_bench_unknown'
    assert rows['43']['position']=='Poste inconnu' and rows['43']['minutes']==20
    assert rows['44']['rating'] is None and rows['44']['minutes'] is None
    assert rows['45']['rating_scale'] != rows['42']['rating_scale']
    assert rows['45']['rating']==4
    assert [s[1]['r'] for s in sent] == ['f','rs','fs']
    assert sent[-1][1]['playersonly']=='1'
    assert 'slot=18' in rows['43']['source']
    assert result['warnings']


@pytest.mark.parametrize('context,team_id,flag',[('youth','72450','youth'),('u20','u20:72450','u20'),('nt','nt:72450','nat')])
def test_context_flags_keep_same_numeric_fixture_and_team_spaces_distinct(monkeypatch,context,team_id,flag):
    result,sent=run_read(monkeypatch,context=context,team_id=team_id)
    assert all(r['team_id']==team_id and r['context']==context for r in result['observations'])
    assert all(s[1][flag]=='1' for s in sent)
    assert all(r['minutes'] is None for r in result['observations'])


@pytest.mark.parametrize('change',[
    lambda d:d['rs']['home'].update(teamid='404'),
    lambda d:d['f']['fixtures']['17'].update(hometeamid='404'),
    lambda d:d['f']['fixtures']['17'].update(matchfinish='2027-01-01T12:00:00+00:00'),
    lambda d:d['f']['fixtures']['17'].update(matchfinish='2026-10-01T14:00:00'),
    lambda d:d['rs']['home']['players']['1'].update(rating=True),
    lambda d:d['rs']['home']['players']['1'].update(position=24),
    lambda d:d['rs']['home']['players']['2'].update(playerid=42),
    lambda d:d['fs']['fixtures']['17']['home player 1'].update(id='42'),
    lambda d:d['fs']['fixtures']['17']['home player 1'].update(**{'minutes played':True}),
    lambda d:d['rs'].update(fixtureid='18'),
    lambda d:d['fs'].update(fixtures={'18':{}}),
    lambda d:d['f']['fixtures']['17'].update(youth='1'),
])
def test_incoherent_match_observations_fail_closed(monkeypatch,change):
    docs=documents();change(docs)
    with pytest.raises(ClassicError):run_read(monkeypatch,docs)


def test_minute_transport_failure_keeps_ratings_with_explicit_missingness(monkeypatch):
    docs=documents();docs['fs']={'status':'Failed','error':'synthetic secret must not escape'}
    result,_=run_read(monkeypatch,docs)
    assert len(result['observations'])==4
    assert all(r['minutes'] is None for r in result['observations'])
    assert any('minutes' in warning.lower() for warning in result['warnings'])
    assert 'secret' not in json.dumps(result)

@pytest.fixture
def classic_app(tmp_path):
    """Real auth/store plus injected credential provider; transport alone is doubled."""
    import inspect
    from server.main import create_app
    from server.player_performance import register_player_performance
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    app.router.routes[:]=[r for r in app.router.routes if not getattr(r,'path','').startswith('/api/player-performance')]
    endpoint=next(r for r in app.routes if getattr(r,'path','')=='/api/state')
    context=inspect.getclosurevars(endpoint.endpoint).nonlocals
    keys={'d':'1','dk':'synthetic','m':'2','mk':'synthetic-manager'}
    register_player_performance(app,context['store'],endpoint.dependant.dependencies[0].call,context['require_team'],lambda tid:keys,lambda key:None)
    app.router.routes.sort(key=lambda r:getattr(r,'path','')=='/{path:path}')
    return app,keys


def test_classic_preview_never_commits_before_confirmation_and_key_change_invalidates_it(classic_app,monkeypatch):
    from fastapi.testclient import TestClient
    app,keys=classic_app;docs=documents();sent=[]
    async def send(self,method,query,data=None,before_send=None):
        sent.append(query['r']);return json.dumps(docs[query['r']]).encode()
    monkeypatch.setattr(ClassicClient,'_send',send)
    with TestClient(app) as c:
        assert c.post('/api/player-performance/classic-preview',json={}).status_code==401
        login=c.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'})
        h={'X-CSRF-Token':login.json()['csrf']}
        body={'team_id':'72450','context':'club','fixture_id':'17','expected_revision':0}
        assert c.post('/api/player-performance/classic-preview',json=body).status_code==403
        p=c.post('/api/player-performance/classic-preview',json=body,headers=h)
        assert p.status_code==200,p.text
        assert len(p.json()['observations'])==4 and p.json()['warnings']
        assert c.get('/api/player-performance').json()['total']==0
        keys['mk']='changed synthetic key'
        confirmation={'preview_id':p.json()['preview_id'],'expected_revision':0}
        assert c.post('/api/player-performance/confirm',json=confirmation,headers=h).status_code==409
        assert c.get('/api/player-performance').json()['total']==0
        p=c.post('/api/player-performance/classic-preview',json=body,headers=h)
        assert p.status_code==200,p.text
        confirmation['preview_id']=p.json()['preview_id']
        assert c.post('/api/player-performance/confirm',json=confirmation,headers=h).status_code==200
        result=c.get('/api/player-performance').json()
        assert result['total']==4
        assert {g['position_basis'] for g in result['groups']}=={'report_start','report_bench_unknown'}
        assert sent==['f','rs','fs','f','rs','fs']


def test_account_binding_changes_during_classic_read_leave_no_preview_or_observations(classic_app,monkeypatch):
    from fastapi.testclient import TestClient
    app,keys=classic_app;docs=documents()
    async def send(self,method,query,data=None,before_send=None):
        if query['r']=='rs':keys['m']='3'
        return json.dumps(docs[query['r']]).encode()
    monkeypatch.setattr(ClassicClient,'_send',send)
    with TestClient(app) as c:
        login=c.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'})
        response=c.post('/api/player-performance/classic-preview',headers={'X-CSRF-Token':login.json()['csrf']},json={
            'team_id':'72450','context':'club','fixture_id':'17','expected_revision':0})
        assert response.status_code==409
        assert c.get('/api/player-performance').json()['total']==0
        with app.state.store.db() as db:
            assert db.execute("SELECT count(*) FROM kv WHERE key GLOB 'player_performance:preview:*'").fetchone()[0]==0

def test_invalid_write_iv_cannot_block_read_only_https_match_preview(classic_app,monkeypatch):
    from fastapi.testclient import TestClient
    app,keys=classic_app;keys['iv']='write-only-invalid-iv';docs=documents();sent=[]
    async def send(self,method,query,data=None,before_send=None):
        sent.append(query);return json.dumps(docs[query['r']]).encode()
    monkeypatch.setattr(ClassicClient,'_send',send)
    with TestClient(app) as c:
        login=c.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'})
        response=c.post('/api/player-performance/classic-preview',headers={'X-CSRF-Token':login.json()['csrf']},json={
            'team_id':'72450','context':'club','fixture_id':'17','expected_revision':0})
        assert response.status_code==200,response.text
        assert len(sent)==3
        assert all('iv' not in query and 'er' not in query for query in sent)

def test_documented_empty_fixture_statistics_preserve_ratings_with_unknown_minutes(monkeypatch):
    docs=documents();docs['fs']={'status':'Ok','fixtures':{}}
    result,_=run_read(monkeypatch,docs)
    assert len(result['observations'])==4
    assert result['observations'][0]['rating']==12
    assert all(r['minutes'] is None for r in result['observations'])
    assert any('minutes' in warning.lower() for warning in result['warnings'])
