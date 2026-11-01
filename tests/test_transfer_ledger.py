"""Synthetic actual-transfer ledger: cashflows, audit, atomic imports and tenancy."""
import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    if not any(getattr(r, 'path', '') == '/api/transfer-ledger' for r in app.routes):
        from server.transfer_ledger import register_transfer_ledger
        endpoint = next(r for r in app.routes if getattr(r, 'path', '') == '/api/state')
        context = inspect.getclosurevars(endpoint.endpoint).nonlocals
        register_transfer_ledger(app, context['store'], endpoint.dependant.dependencies[0].call, context['require_team'])
        app.router.routes.sort(key=lambda r: getattr(r, 'path', '') == '/{path:path}')
    return app


def login(client):
    result = client.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
    assert result.status_code == 200
    return {'X-CSRF-Token': result.json()['csrf']}


def entry(**changes):
    return {'id': 'synthetic-buy-1', 'player_id': '42', 'player_name': 'Synthetic player', 'kind': 'buy',
            'occurred_at': '2026-01-01T12:00:00+01:00', 'season': 'S50', 'amount': '100.10', 'fees': '2.20',
            'counterparty': 'Synthetic club', 'source': 'Synthetic notebook', 'notes': '', **changes}


def save(client, headers, row=None, revision=0, action='create', reason=''):
    return client.post('/api/transfer-ledger', headers=headers, json={'team_id': '72450', 'expected_revision': revision,
                       'entry': row or entry(), 'action': action, 'reason': reason})


def report(client, query=''):
    response = client.get('/api/transfer-ledger?team_id=72450'+query)
    assert response.status_code == 200, response.text
    return response.json()


def preview(client, headers, rows, revision=0, **changes):
    return client.post('/api/transfer-ledger/preview', headers=headers, json={'team_id':'72450', 'expected_revision': revision,
        'format':'json', 'content':json.dumps(rows,ensure_ascii=False), 'mode':'append', 'reason':'', **changes})


def confirm(client, headers, result, revision=None, team_id='72450'):
    assert result.status_code == 200, result.text
    data = result.json()
    return client.post('/api/transfer-ledger/confirm', headers=headers, json={'team_id':team_id,
        'expected_revision':data['revision'] if revision is None else revision, 'preview_id':data['preview_id']})


def test_decimal_balance_averages_and_records_do_not_pair_multiple_cycles(app):
    with TestClient(app) as c:
        h=login(c)
        rows=[entry(),entry(id='sale-1',kind='sell',amount='160.30',fees='3.40'),
              entry(id='buy-2',amount='50',fees='1'),entry(id='sale-2',kind='sell',amount='80',fees='0.10')]
        assert confirm(c,h,preview(c,h,rows)).status_code == 200
        r=report(c)
        s=r['statistics']
        assert (s['buy_count'],s['sell_count'],s['purchases'],s['sales'],s['fees'],s['balance']) == (2,2,'150.10','240.30','6.70','83.50')
        assert s['average_buy_gross']=='75.05' and s['average_sell_gross']=='120.15'
        assert s['largest_purchase_gross']['amount']=='100.10'
        assert s['largest_sale_gross']['amount']=='160.30'
        assert s['largest_sale_net']['amount']=='156.90'
        assert r['by_player'][0]['balance']=='83.50'
        assert 'profit' not in r['by_player'][0]
        assert r['entries'][0]['occurred_at']=='2026-01-01T11:00:00+00:00'


def test_correct_cancel_restore_append_immutable_snapshots_and_require_reasons(app):
    with TestClient(app) as c:
        h=login(c)
        assert save(c,h).status_code==200
        assert save(c,h,entry(amount='120'),1,'correct').status_code==422
        assert save(c,h,entry(amount='120'),1,'correct','Receipt correction').status_code==200
        assert c.post('/api/transfer-ledger/cancel',headers=h,json={'team_id':'72450','expected_revision':2,'id':'synthetic-buy-1','reason':'Duplicate receipt'}).status_code==200
        r=report(c)
        assert r['statistics']['balance']=='0.00' and r['statistics']['cancelled_count']==1
        row=r['entries'][0]
        assert row['status']=='cancelled' and len(row['versions'])==3
        assert row['versions'][0]['entry']['amount']=='100.10'
        assert row['versions'][1]['entry']['amount']=='120.00'
        assert row['versions'][2]['reason']=='Duplicate receipt'
        assert c.post('/api/transfer-ledger/restore',headers=h,json={'team_id':'72450','expected_revision':3,'id':row['id'],'reason':'Receipt verified'}).status_code==200
        r=report(c)
        assert r['statistics']['balance']=='-122.20' and len(r['entries'][0]['versions'])==4
        assert r['entries'][0]['versions'][2]['entry']['status']=='cancelled'


def test_import_duplicates_are_idempotent_conflicts_require_explicit_correction(app):
    with TestClient(app) as c:
        h=login(c)
        p=preview(c,h,[entry(),entry()]);assert p.json()['duplicates']==1
        assert confirm(c,h,p).json()['revision']==1
        p=preview(c,h,[entry()],1)
        assert p.json()['duplicates']==1 and p.json()['added']==0
        assert confirm(c,h,p).json()['revision']==1
        assert confirm(c,h,p).status_code==409
        assert preview(c,h,[entry(amount='200')],1).status_code==409
        assert preview(c,h,[entry(amount='200')],1,mode='correct').status_code==422
        p=preview(c,h,[entry(amount='200')],1,mode='correct',reason='Verified amount')
        assert p.json()['corrected']==1
        assert report(c)['entries'][0]['amount']=='100.10'
        assert confirm(c,h,p).json()['revision']==2
        assert report(c)['entries'][0]['versions'][1]['reason']=='Verified amount'


@pytest.mark.parametrize('change',[{'amount':'NaN'},{'fees':'Infinity'},{'amount':True},{'amount':'-0.01'},
    {'amount':'0.001'},{'amount':'1000000000001'},{'fees':None},{'occurred_at':'2026-01-01'},
    {'occurred_at':'2026-01-01T12:00:00'},{'occurred_at':'2099-01-01T00:00:00Z'},
    {'source':''},{'player_id':''},{'season':''}])
def test_invalid_import_is_atomic_and_never_turns_unknown_money_into_zero(app,change):
    with TestClient(app) as c:
        h=login(c)
        p=preview(c,h,[entry(),entry(id='bad',**change)])
        assert p.status_code==422,p.text
        assert report(c)['revision']==0 and report(c)['entries']==[]


def test_conflicting_ids_inside_one_file_are_rejected_even_in_correction_mode(app):
    with TestClient(app) as c:
        h=login(c)
        assert preview(c,h,[entry(),entry(amount='300')],mode='correct',reason='Correction').status_code==409
        assert report(c)['revision']==0


def test_preview_revision_owner_ttl_and_team_bindings(app):
    with TestClient(app) as c:
        h=login(c)
        p=preview(c,h,[entry()])
        assert confirm(c,h,p,team_id='72444').status_code==409
        with TestClient(app) as other:
            other_h=login(other)
            assert confirm(other,other_h,p).status_code==409
        assert save(c,h,entry(id='another')).status_code==200
        assert confirm(c,h,p).status_code==409
        assert confirm(c,h,p,revision=1).status_code==409
        p=preview(c,h,[entry()],1)
        app.state.accounts.primary.set('transfer_preview:'+p.json()['preview_id'], {
            **app.state.accounts.primary.get('transfer_preview:'+p.json()['preview_id']), 'expires_at':time.time()-1})
        assert confirm(c,h,p).status_code==409


@pytest.mark.parametrize('format',['json','csv'])
def test_export_reimport_preserves_ids_amounts_dates_and_cancellation(format,app):
    with TestClient(app) as c:
        h=login(c)
        assert save(c,h,entry(notes='Comma, quote " and\nnewline')).status_code==200
        assert c.post('/api/transfer-ledger/cancel',headers=h,json={'team_id':'72450','expected_revision':1,'id':'synthetic-buy-1','reason':'Example cancellation'}).status_code==200
        e=c.get('/api/transfer-ledger/export?team_id=72450&format='+format).json()
        p=preview(c,h,[],2,format=format,content=e['content'])
        assert p.json()['duplicates']==1 and confirm(c,h,p).json()['revision']==2
        # Import the same portable document into another owned club.
        p=c.post('/api/transfer-ledger/preview',headers=h,json={'team_id':'72444','expected_revision':0,'format':format,'content':e['content']})
        assert confirm(c,h,p,team_id='72444').status_code==200
        r=c.get('/api/transfer-ledger?team_id=72444').json()
        assert r['entries'][0]['status']=='cancelled'
        assert r['entries'][0]['notes']=='Comma, quote " and\nnewline'
        assert r['statistics']['balance']=='0.00'


def test_filters_use_utc_days_declared_seasons_and_player_identifiers(app):
    with TestClient(app) as c:
        h=login(c)
        rows=[entry(occurred_at='2026-01-02T00:30:00+02:00'),entry(id='s51',season='S51',player_id='43',player_name='Second',occurred_at='2026-01-03T00:00:00Z')]
        assert confirm(c,h,preview(c,h,rows)).status_code==200
        assert report(c,'&start=2026-01-02')['total']==1
        assert report(c,'&season=S50')['statistics']['purchases']=='100.10'
        assert report(c,'&player_id=43')['total']==1
        assert report(c,'&search=synthetic')['total']==1
        assert c.get('/api/transfer-ledger?team_id=72450&start=2026-02-01&end=2026-01-01').status_code==422


def test_concurrent_writers_cannot_lose_an_entry(app):
    with TestClient(app) as c:
        h=login(c)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda n:save(c,h,entry(id='row-'+str(n))),range(2)))
        assert sorted(r.status_code for r in results)==[200,409]
        assert report(c)['total']==1


def test_private_routes_csrf_clubs_and_manager_isolation(app):
    with TestClient(app) as c:
        assert c.get('/api/transfer-ledger?team_id=72450').status_code==401
        h=login(c)
        assert save(c,{}).status_code==403
        assert c.get('/api/transfer-ledger?team_id=nt:72450').status_code==422
        assert c.get('/api/transfer-ledger?team_id=999999999').status_code==404
        assert save(c,h).status_code==200
        app.state.accounts.create('ledger-other','Testing-password-1234')
        c.post('/api/logout',headers=h)
        c.post('/api/login',json={'username':'ledger-other','password':'Testing-password-1234'})
        assert c.get('/api/transfer-ledger?team_id=72450').status_code==404


def test_preview_statistics_describe_projected_ledger_after_deduplication(app):
    with TestClient(app) as c:
        h=login(c)
        assert save(c,h).status_code==200
        p=preview(c,h,[entry(id='sale',kind='sell',amount='200',fees='4'),entry(id='sale',kind='sell',amount='200',fees='4')],1)
        assert p.status_code==200,p.text
        assert p.json()['statistics']['purchases']=='100.10'
        assert p.json()['statistics']['sales']=='200.00'
        assert p.json()['statistics']['balance']=='93.70'
        assert report(c)['statistics']['balance']=='-102.30'


@pytest.mark.parametrize('format',['csv','json'])
def test_empty_export_is_a_reimportable_noop(format,app):
    with TestClient(app) as c:
        h=login(c)
        exported=c.get('/api/transfer-ledger/export?team_id=72450&format='+format).json()
        p=preview(c,h,[],format=format,content=exported['content'])
        assert p.status_code==200,p.text
        assert confirm(c,h,p).json()['revision']==0


def test_money_text_is_bounded_even_when_its_numeric_value_is_small(app):
    with TestClient(app) as c:
        h=login(c)
        assert save(c,h,entry(amount='0'*10000+'1')).status_code==422
        assert report(c)['total']==0


@pytest.mark.parametrize('notes,count',[('😀'*1000,900),('\x00'*1000,620)])
def test_near_limit_unicode_and_controls_roundtrip_and_reject_oversize_batch_atomically(app,notes,count):
    with TestClient(app) as c:
        h=login(c)
        rows=[entry(id=f'large-{n}',notes=notes) for n in range(count)]
        assert confirm(c,h,preview(c,h,rows[:450])).status_code==200
        assert confirm(c,h,preview(c,h,rows[450:],1)).status_code==200
        before=report(c)
        for format in ('csv','json'):
            exported=c.get('/api/transfer-ledger/export?team_id=72450&format='+format).json()
            size=len(exported['content'].encode('utf-8'))
            assert size<=4_000_000
            if format=='json':assert size>3_700_000
            payload={'team_id':'72444','expected_revision':0,'format':format,'content':exported['content'],
                     'mode':'correct','reason':'\x00'*500}
            wrapped=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
            assert len(wrapped)<8_200_000
            imported=c.post('/api/transfer-ledger/preview',headers={**h,'Content-Type':'application/json'},content=wrapped)
            assert imported.status_code==200,imported.text
            assert confirm(c,h,imported,team_id='72444').status_code==200
            # Restore the second club to empty only inside this synthetic test fixture.
            with app.state.accounts.primary.db() as db:db.execute("DELETE FROM kv WHERE key='transfer_ledger:72444'")
        # The next individually valid batch would break whole-club export round trips.
        extra=[entry(id=f'extra-{n}',notes=notes) for n in range(100)]
        p=preview(c,h,extra,2)
        if p.status_code==200:
            rejected=confirm(c,h,p)
            assert rejected.status_code==422,rejected.text
        else:
            assert p.status_code==422,p.text
        after=report(c)
        assert after==before


@pytest.mark.parametrize('operation',['create','correct','cancel','restore','confirm'])
def test_every_persistence_path_rechecks_portable_budget_and_preserves_old_state(app,monkeypatch,operation):
    import server.transfer_ledger as ledger
    with TestClient(app) as c:
        h=login(c)
        assert save(c,h).status_code==200
        revision=1
        if operation=='restore':
            assert c.post('/api/transfer-ledger/cancel',headers=h,json={'team_id':'72450','expected_revision':1,'id':'synthetic-buy-1','reason':'Synthetic cancellation'}).status_code==200
            revision=2
        p=preview(c,h,[entry(id='new-import')],revision) if operation=='confirm' else None
        before=report(c)
        # A lower configured budget models a pre-existing ledger above the new bound.
        monkeypatch.setattr(ledger,'MAX_CONTENT',1)
        if operation in ('create','correct'):
            result=save(c,h,entry(id='second' if operation=='create' else 'synthetic-buy-1',amount='123'),revision,operation,'Verified correction')
        elif operation=='confirm':
            result=confirm(c,h,p)
        else:
            result=c.post('/api/transfer-ledger/'+operation,headers=h,json={'team_id':'72450','expected_revision':revision,'id':'synthetic-buy-1','reason':'Verified status change'})
        assert result.status_code==422,result.text
        assert report(c)==before
        if p:
            assert app.state.accounts.primary.get('transfer_preview:'+p.json()['preview_id']) is not None


def test_portable_budget_also_checks_encoded_http_envelope(app,monkeypatch):
    import server.transfer_ledger as ledger
    with TestClient(app) as c:
        h=login(c)
        assert save(c,h).status_code==200
        before=report(c)
        monkeypatch.setattr(ledger,'MAX_REQUEST_BYTES',1)
        assert save(c,h,entry(id='wrapped'),1).status_code==422
        assert report(c)==before
