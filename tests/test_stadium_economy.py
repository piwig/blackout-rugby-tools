"""Synthetic economic examples: money, missing facts, tenancy and stale writes."""
import importlib.util
import inspect
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient


def engine():
    assert importlib.util.find_spec('server.stadium_economy'), 'Stadium economy feature is missing'
    from server import stadium_economy
    return stadium_economy


def side(**changes):
    return {'seats': {key: {'capacity': 100 if key == 'standing' else 0,
                           'price': '10', 'occupancy': '50', 'variable_cost': '2'}
                      for key in ('standing','uncovered','covered','members','corporate')},
            'ancillary_revenue_per_spectator':'0', 'ancillary_cost_per_spectator':'0',
            'ancillary_revenue_fixed':'0', 'ancillary_cost_fixed':'0',
            'match_fixed_cost':'100', 'weekly_upkeep':'20', 'investment':'0',
            'source':'Synthetic manual assumption', 'observed_on':'2026-10-01', **changes}


def scenario(**changes):
    return {'id':'example', 'name':'Synthetic comparison', 'current':side(),
            'project':side(investment='1000'), 'matches':4, 'weeks':3, **changes}


def test_manual_net_and_weekly_cost_once():
    m=engine(); result=m.compare(m.Scenario.model_validate(scenario()))
    current=result['current']['custom']
    assert current['attendance'] == 50
    assert current['ticket_revenue'] == '500.00'
    assert current['match_costs'] == '200.00'
    assert current['net_match'] == '300.00'
    assert current['net_projection'] == '1140.00'  # 4*300 - 3*20
    assert result['incremental']['payback_matches'] is None
    assert len(result['current']['occupancies']) == 6


def test_ancillary_integer_attendance_and_incremental_recovery():
    m=engine(); base=side(); base['seats']['standing']['capacity']=101
    project=side(ancillary_revenue_per_spectator='3',ancillary_cost_per_spectator='1',
                 ancillary_revenue_fixed='10',ancillary_cost_fixed='5',investment='1000')
    result=m.compare(m.Scenario.model_validate(scenario(current=base,project=project)))
    assert result['current']['custom']['attendance'] == 50  # floor, never rounded upward
    assert result['project']['custom']['ancillary_revenue'] == '160.00'
    assert result['project']['custom']['net_match'] == '405.00'
    assert result['incremental']['net_projection'] == '420.00'
    assert result['incremental']['payback_matches'] == '9.5238'
    assert result['incremental']['roi_percent'] == '-58.0000'


def test_unknown_is_not_free_and_nonpositive_gain_has_no_recovery():
    m=engine(); current=side(weekly_upkeep=None); project=side(match_fixed_cost='500',investment='1000')
    result=m.compare(m.Scenario.model_validate(scenario(current=current,project=project)))
    assert result['current']['custom']['net_match'] == '300.00'
    assert result['current']['custom']['net_projection'] is None
    assert result['incremental']['payback_matches'] is None
    assert result['incremental']['roi_percent'] is None
    project['seats']['standing']['price']=None
    result=m.compare(m.Scenario.model_validate(scenario(project=project)))
    assert result['project']['custom']['net_match'] is None
    assert 'standing.price' in result['project']['custom']['missing']


def test_breakeven_is_bounded_and_zero_investment_recovers_immediately():
    m=engine(); project=side(match_fixed_cost='1000')
    result=m.compare(m.Scenario.model_validate(scenario(project=project)))
    assert result['project']['break_even_occupancy'] is None  # full attendance still loses
    assert result['project']['break_even_reason'] == 'unreachable'
    project=side(match_fixed_cost='0')
    result=m.compare(m.Scenario.model_validate(scenario(project=project)))
    assert result['incremental']['payback_matches'] == '0.0000'
    assert result['incremental']['roi_percent'] is None  # no zero denominator


@pytest.mark.parametrize('value',['NaN','Infinity','-1','1000000000001',True])
def test_invalid_money_rejected(value):
    from pydantic import ValidationError
    m=engine()
    with pytest.raises(ValidationError): m.Scenario.model_validate(scenario(project=side(investment=value)))


@pytest.fixture
def app(tmp_path):
    from server.main import create_app
    m=engine(); app=create_app(tmp_path,'Testing-password-1234',secure=False)
    if not any(getattr(r,'path','')=='/api/stadium-economy' for r in app.routes):
        route=next(r for r in app.routes if getattr(r,'path','')=='/api/state')
        context=inspect.getclosurevars(route.endpoint).nonlocals
        m.register_stadium_economy(app,context['store'],route.dependant.dependencies[0].call,context['require_team'])
        app.router.routes.sort(key=lambda r:getattr(r,'path','')=='/{path:path}')
    return app


def login(c,name='piwig',password='Testing-password-1234'):
    r=c.post('/api/login',json={'username':name,'password':password}); assert r.status_code==200
    return {'X-CSRF-Token':r.json()['csrf']}


def test_save_reload_duplicate_export_and_revision_conflict(app):
    with TestClient(app) as c:
        h=login(c); payload={'team_id':'72450','context':'club','expected_revision':0,'scenarios':[scenario()]}
        assert c.post('/api/stadium-economy',headers=h,json=payload).json()['revision']==1
        assert c.post('/api/stadium-economy',headers=h,json=payload).status_code==409
        doc=c.get('/api/stadium-economy?team_id=72450').json()
        doc['scenarios'].append(scenario(id='copy',name='Copy'))
        payload.update(expected_revision=1,scenarios=doc['scenarios'])
        assert c.post('/api/stadium-economy',headers=h,json=payload).json()['revision']==2
        assert len(c.get('/api/stadium-economy/export?team_id=72450').json()['scenarios'])==2
        assert c.get('/api/stadium-economy?team_id=72444').json()['scenarios']==[]
        payload['scenarios'].append(scenario())
        payload['expected_revision']=2
        assert c.post('/api/stadium-economy',headers=h,json=payload).status_code==422


def test_private_authorized_club_only_csrf_and_capacity_provenance(app):
    with TestClient(app) as c, TestClient(app) as other:
        assert c.get('/api/stadium-economy?team_id=72450').status_code==401
        h=login(c)
        payload={'team_id':'72450','context':'club','expected_revision':0,'scenarios':[scenario()]}
        assert c.post('/api/stadium-economy',json=payload).status_code==403
        assert c.post('/api/stadium-economy',headers=h,json={**payload,'context':'youth'}).status_code==422
        with app.state.store.db() as db:
            db.execute('INSERT INTO teams VALUES(?,?,?,?)',('nt:72450','Synthetic NT','FR','{}'))
            db.execute('UPDATE teams SET meta=? WHERE id=?',(json.dumps({'stadium_standing':100,'date_maj':'2026-10-01'}),'72450'))
        assert c.get('/api/stadium-economy?team_id=nt:72450').status_code==422
        assert c.get('/api/stadium-economy?team_id=72450').json()['initial_current'] is None
        c.post('/api/admin/users',headers=h,json={'username':'alice','password':'Another-password-5678'})
        oh=login(other,'alice','Another-password-5678')
        assert other.get('/api/stadium-economy?team_id=72450').status_code==404
        other.post('/api/teams',headers=oh,json={'team_id':'72450','name':'Synthetic other club','country':'FR'})
        assert c.post('/api/stadium-economy',headers=h,json=payload).status_code==200
        assert other.get('/api/stadium-economy?team_id=72450').json()['scenarios']==[]


def test_concurrent_writes_only_one_revision_wins(app):
    with TestClient(app) as c:
        h=login(c); payload={'team_id':'72450','expected_revision':0,'scenarios':[scenario()]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:c.post('/api/stadium-economy',headers=h,json=payload).status_code,range(2)))
        assert sorted(results)==[200,409]


def test_calculate_unsaved_draft_is_read_only_and_validates_bounds(app):
    with TestClient(app) as c:
        h=login(c); payload={'team_id':'72450','scenario':scenario()}
        response=c.post('/api/stadium-economy/calculate',headers=h,json=payload)
        assert response.status_code==200
        assert response.json()['current']['custom']['net_match']=='300.00'
        assert c.get('/api/stadium-economy?team_id=72450').json()['revision']==0
        for capacity,occupancy in [(1.5,'50'),(-1,'50'),(100,'100.01'),(100,'-0.01'),(True,'50')]:
            invalid=scenario(); invalid['project']['seats']['standing'].update(capacity=capacity,occupancy=occupancy)
            assert c.post('/api/stadium-economy/calculate',headers=h,json={**payload,'scenario':invalid}).status_code==422
        assert c.post('/api/stadium-economy/calculate',headers=h,json={**payload,'context':'youth'}).status_code==422
        assert c.get('/api/stadium-economy?team_id=72450&context=youth').status_code==422


def test_verified_capacity_only_initialization_preserves_unknown_tariffs(app):
    with TestClient(app) as c:
        login(c)
        with app.state.store.db() as db:
            db.execute('UPDATE teams SET meta=? WHERE id=?',(json.dumps({'stadium_standing':100,
                'stadium_source':'Synthetic verified import', 'stadium_observed_on':'2026-10-01'}),'72450'))
        initial=c.get('/api/stadium-economy?team_id=72450').json()['initial_current']
        assert initial['seats']['standing']['capacity']==100
        assert initial['seats']['standing']['price'] is None
        assert initial['seats']['covered']['capacity'] is None
        assert initial['weekly_upkeep'] is None


def test_supported_fresh_manager_import_initializes_capacity_then_save_preserves_seed(app,monkeypatch):
    from server.classic import ClassicClient
    async def fake(self,resource,**params):
        if resource=='m':return {'members':{'123':{'id':'123','username':'Synthetic manager','email':'synthetic@example.invalid','teams':['101']}}}
        if resource=='t':return {'teams':{'101':{'id':'101','owner':'123','name':'Synthetic club','country_iso':'FR','stadium_standing':'100'}}}
        if resource=='p':return {'players':{}}
        raise AssertionError(resource)
    monkeypatch.setattr(ClassicClient,'request',fake)
    with TestClient(app) as c:
        h=login(c)
        response=c.post('/api/classic/import',headers=h,json={'access_key':'m=123&mk=SYNTHETIC','developer_id':'1','developer_key':'SYNTHETIC'})
        assert response.status_code==200,response.text
        loaded=c.get('/api/stadium-economy?team_id=101').json()
        assert loaded['initial_current'] is not None
        assert loaded['initial_current']['seats']['standing']['capacity']==100
        assert loaded['initial_current']['source']=='API Classic'
        assert loaded['initial_current']['observed_on']
        assert loaded['initial_current']['seats']['standing']['price'] is None
        saved=c.post('/api/stadium-economy',headers=h,json={'team_id':'101','expected_revision':0,'scenarios':[scenario()]})
        assert saved.status_code==200,saved.text
        assert saved.json()['initial_current']==loaded['initial_current']


def test_accepted_extreme_money_bounds_calculate_roi_without_decimal_overflow():
    m=engine(); project=side(match_fixed_cost='0',weekly_upkeep='0',investment='0.0001')
    for seat in project['seats'].values():
        seat.update(capacity=10_000_000,price='1000000000000',occupancy='100',variable_cost='0')
    result=m.compare(m.Scenario.model_validate(scenario(project=project,matches=10000,weeks=0)))
    assert result['project']['custom']['net_projection']=='500000000000000000000000.00'
    assert result['incremental']['roi_percent']=='499999999999999996999999999900.0000'
