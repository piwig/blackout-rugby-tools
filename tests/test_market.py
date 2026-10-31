"""Private recruitment scenarios: money, missing evidence and tenant boundaries."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from server.domain import SKILLS
from server.main import create_app


PASSWORD = 'Testing-password-1234'


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, PASSWORD, secure=False)


def login(client, name='piwig'):
    result = client.post('/api/login', json={'username': name, 'password': PASSWORD})
    assert result.status_code == 200
    return {'X-CSRF-Token': result.json()['csrf']}


def plan(**changes):
    return {'cash': 1000, 'weekly_income': 200, 'weekly_expenses': 100,
            'reserve': 100, 'committed_bids': 100, 'complete': True,
            'observed_at': '2026-10-30T12:00:00+00:00', **changes}


def candidate(**changes):
    return {'id': 'a'*32, 'name': 'Candidate', 'classic_id': '42', 'role': 'Pilier',
            'age': 23, 'price': 500, 'weekly_salary': 50, 'fees': 20,
            'skills': dict.fromkeys(SKILLS, 10), 'notes': '', 'status': 'watch', **changes}


def body(**changes):
    return {'team_id': '72450', 'expected_revision': 0, 'plan': plan(),
            'candidates': [candidate()], 'investments': [], **changes}


def analyze(client, headers, **changes):
    result = client.post('/api/market/analyze', headers=headers, json=body(**changes))
    assert result.status_code == 200, result.text
    return result.json()['analysis']


def test_empty_market_preserves_unknowns_and_analysis_is_read_only(app):
    with TestClient(app) as client:
        headers = login(client)
        response = client.get('/api/market?team_id=72450')
        assert response.status_code == 200, response.text
        empty = response.json()
        assert empty['revision'] == 0 and empty['updated_at'] is None
        assert empty['plan']['cash'] is None and empty['plan']['complete'] is False
        assert empty['analysis']['base']['purchase_ceiling'] is None
        analyze(client, headers, expected_revision=999)
        assert client.get('/api/market?team_id=72450').json() == empty


def test_four_week_budget_caps_purchase_by_cash_available_today(app):
    with TestClient(app) as client:
        result = analyze(client, login(client))
        assert result['horizon_weeks'] == 4 and result['confirmed'] is True
        assert result['base'] == {'weekly_net': 100, 'projected_cash': 1300,
                                  'immediate_headroom': 800, 'projected_headroom': 1200,
                                  'purchase_ceiling': 800}
        scenario = result['candidates'][0]
        assert scenario['status'] == 'affordable'
        assert scenario['initial_cost'] == 520 and scenario['four_week_cost'] == 720
        assert scenario['immediate_headroom'] == 280 and scenario['projected_headroom'] == 480
        assert scenario['projected_cash'] == 580 and scenario['purchase_ceiling'] == 780
        # Strong expected income never funds a purchase that cannot be paid now.
        large = analyze(client, login(client), candidates=[candidate(price=900)])['candidates'][0]
        assert large['status'] == 'over_budget' and large['immediate_headroom'] == -120


def test_decimal_calculations_preserve_exact_boundary_and_deficits(app):
    with TestClient(app) as client:
        headers = login(client)
        result = analyze(client, headers, plan=plan(cash=0.3, reserve=0, committed_bids=0,
                        weekly_income=0.1, weekly_expenses=0.1),
                         candidates=[candidate(price=0.1, fees=0.2, weekly_salary=0)])
        assert result['candidates'][0]['status'] == 'affordable'
        assert result['candidates'][0]['immediate_headroom'] == 0
        assert result['candidates'][0]['projected_headroom'] == 0
        deficit = analyze(client, headers, plan=plan(weekly_expenses=500))
        assert deficit['base']['projected_cash'] == -300
        assert deficit['base']['projected_headroom'] == -400
        assert deficit['base']['purchase_ceiling'] == 0
        assert 'projected_deficit' in deficit['warnings']


def test_money_limit_keeps_four_week_arithmetic_in_safe_json_range(app):
    with TestClient(app) as client:
        headers = login(client)
        allowed = analyze(client, headers, plan=plan(cash=1_000_000_000_000))
        assert allowed['base']['projected_cash'] == 1_000_000_000_300
        for change in ({'plan': plan(cash=1_000_000_000_001)},
                       {'candidates': [candidate(price=1_000_000_000_001)]},
                       {'investments': [{'id': 'b'*32, 'name': 'Project', 'initial_cost': 1_000_000_000_001}]}):
            response = client.post('/api/market', headers=headers, json=body(**change))
            assert response.status_code == 422


@pytest.mark.parametrize('change', [
    {'cash': None}, {'weekly_income': None}, {'weekly_expenses': None},
    {'reserve': None}, {'committed_bids': None}, {'complete': False}, {'observed_at': None},
    {'observed_at': '2099-01-01T00:00:00Z'},
])
def test_incomplete_or_unconfirmed_budget_never_recommends_purchase(app, change):
    with TestClient(app) as client:
        result = analyze(client, login(client), plan=plan(**change))
        assert result['confirmed'] is False
        assert result['base']['purchase_ceiling'] is None
        assert result['candidates'][0]['status'] == 'unknown'
        assert result['candidates'][0]['purchase_ceiling'] is None


@pytest.mark.parametrize('field', ['price', 'fees', 'weekly_salary'])
def test_unknown_candidate_cost_never_becomes_free(app, field):
    with TestClient(app) as client:
        scenario = analyze(client, login(client), candidates=[candidate(**{field: None})])['candidates'][0]
        assert scenario['status'] == 'unknown'
        assert scenario['four_week_cost'] is None
        assert field in scenario['missing_fields']


def test_investments_are_independent_and_recurring_costs_constrain_ceiling(app):
    projects = [{'id': c*32, 'name': c, 'initial_cost': 700, 'weekly_cost': 150, 'notes': ''} for c in 'bc']
    with TestClient(app) as client:
        scenarios = analyze(client, login(client), investments=projects)['investments']
        assert [x['status'] for x in scenarios] == ['over_budget', 'over_budget']
        assert all(x['immediate_headroom'] == 100 and x['projected_headroom'] == -100 for x in scenarios)
        assert all(x['purchase_ceiling'] == 600 and x['four_week_cost'] == 1300 for x in scenarios)


@pytest.mark.parametrize('changes', [
    {'plan': plan(cash=True)}, {'plan': plan(cash='100')}, {'plan': plan(cash=-1)},
    {'plan': plan(cash=float('nan'))}, {'plan': plan(cash=float('inf'))},
    {'plan': plan(complete=1)}, {'plan': plan(observed_at='2026-10-30')},
    {'plan': plan(observed_at='2026-10-30T12:00:00')}, {'plan': plan(extra=1)},
    {'expected_revision': True}, {'tenant_id': 'other'},
    {'candidates': [candidate(id='bad')]}, {'candidates': [candidate(classic_id='042')]},
    {'candidates': [candidate(classic_id=42)]}, {'candidates': [candidate(url='https://example.com')]},
    {'candidates': [candidate(role='Winger')]}, {'candidates': [candidate(age=15)]},
    {'candidates': [candidate(age=True)]}, {'candidates': [candidate(name=' ')]},
    {'candidates': [candidate(skills={**dict.fromkeys(SKILLS, 10), 'speed': True})]},
    {'candidates': [candidate(skills={**dict.fromkeys(SKILLS, 10), 'speed': 22})]},
    {'candidates': [candidate(skills={'fake': 5})]},
    {'candidates': [candidate(), candidate()]},
    {'candidates': [candidate(id=f'{i:032x}') for i in range(51)]},
    {'investments': [{'id': f'{i:032x}', 'name': 'Project'} for i in range(21)]},
])
def test_invalid_market_inputs_never_write(app, changes):
    with TestClient(app) as client:
        headers = {**login(client), 'content-type': 'application/json'}
        result = client.post('/api/market', headers=headers, content=json.dumps(body(**changes)))
        assert result.status_code == 422, result.text
        assert client.get('/api/market?team_id=72450').json()['revision'] == 0


def test_role_comparison_uses_current_senior_evidence_with_missing_coverage(app):
    app.state.store.save_snapshot('72450', False, [
        {'id': '1', **dict.fromkeys(SKILLS, 12)},
        {'id': '2', **dict.fromkeys(SKILLS, 8)},
        {'id': '3', 'speed': 20},
    ], 'Synthetic', observed_at='2026-10-30T12:00:00Z')
    app.state.store.save_snapshot('72450', True, [{'id': '9', **dict.fromkeys(SKILLS, 21)}], 'Synthetic')
    with TestClient(app) as client:
        headers = login(client)
        result = analyze(client, headers)
        comparison = result['candidates'][0]['comparison']
        assert comparison['score'] == 10
        assert comparison['squad_total'] == 3 and comparison['squad_known'] == 2
        assert comparison['squad_best'] == 12 and comparison['squad_average'] == 10
        assert comparison['delta_best'] == -2 and comparison['rank'] == 2
        assert 'squad_incomplete' in result['candidates'][0]['warnings']
        partial = analyze(client, headers, candidates=[candidate(skills={'strength': 10})])['candidates'][0]['comparison']
        assert partial['score'] is None and partial['rank'] is None
        assert set(partial['missing_skills']) == {'technique', 'stamina'}


@pytest.mark.parametrize('route', ['get', 'analyze'])
def test_analysis_identifies_the_snapshot_that_produced_its_scores(app, route):
    with TestClient(app) as client:
        headers = login(client)
        saved = client.post('/api/market', headers=headers, json=body())
        assert saved.status_code == 200
        assert saved.json()['analysis']['squad']['snapshot_id'] is None

        def result():
            if route == 'analyze':
                return analyze(client, headers)
            response = client.get('/api/market?team_id=72450')
            assert response.status_code == 200
            return response.json()['analysis']

        app.state.store.save_snapshot('72450', False, [{'id': '1', **dict.fromkeys(SKILLS, 8)}],
                                      'Synthetic', observed_at='2026-10-29T12:00:00Z')
        stale_state = client.get('/api/state?team_id=72450').json()
        before = result()
        assert before['squad']['snapshot_id'] == stale_state['squad_source']['id'] == 1
        assert before['candidates'][0]['comparison']['squad_best'] == 8

        app.state.store.save_snapshot('72450', False, [{'id': '1', **dict.fromkeys(SKILLS, 12)}],
                                      'Synthetic', observed_at='2026-10-30T12:00:00Z')
        # More recent observations in other cohorts/clubs are not the reference.
        app.state.store.save_snapshot('72450', True, [{'id': '2', **dict.fromkeys(SKILLS, 20)}], 'Synthetic')
        app.state.store.save_snapshot('72444', False, [{'id': '3', **dict.fromkeys(SKILLS, 21)}], 'Synthetic')
        after = result()
        assert after['squad']['snapshot_id'] == 2
        assert after['squad']['snapshot_id'] != stale_state['squad_source']['id']
        assert after['squad']['observed_at'] == '2026-10-30T12:00:00Z'
        assert after['candidates'][0]['comparison']['squad_best'] == 12
        assert after['candidates'][0]['comparison']['delta_best'] == -2


def test_auth_csrf_unknown_club_and_selections_are_rejected(app):
    with app.state.store.db() as db:
        db.execute("INSERT INTO teams(id,name,country) VALUES('u20:7','Selection','FR')")
    with TestClient(app) as client:
        assert client.get('/api/market?team_id=72450').status_code == 401
        headers = login(client)
        assert client.post('/api/market', json=body()).status_code == 403
        assert client.post('/api/market/analyze', json=body()).status_code == 403
        for team, status in [('999999', 404), ('u20:7', 422), ('nt:7', 422)]:
            assert client.get('/api/market?team_id='+team).status_code == status
            for route in ['/api/market', '/api/market/analyze']:
                assert client.post(route, headers=headers, json=body(team_id=team)).status_code == status


def test_concurrent_revisions_isolate_clubs_and_managers_and_export_private_documents(app):
    with TestClient(app) as first, TestClient(app) as second:
        h1, h2 = login(first), login(second)
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(c.post, '/api/market', headers=h, json=body(candidates=[candidate(name=name)]))
                    for c, h, name in [(first, h1, 'First'), (second, h2, 'Second')]]
            results = [job.result() for job in jobs]
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(result.json() for result in results if result.status_code == 200)
        assert first.get('/api/market?team_id=72450').json() == winner
        assert first.get('/api/market?team_id=72444').json()['revision'] == 0
        assert first.post('/api/market', headers=h1, json=body()).status_code == 409
        exported = first.get('/api/export').json()
        assert exported['manager_documents']['market:72450']['candidates'] == winner['candidates']
        assert 'password' not in exported['manager_documents']
        first.post('/api/admin/users', headers=h1, json={'username': 'second', 'password': PASSWORD})
        h2 = login(second, 'second')
        assert second.get('/api/market?team_id=72450').status_code == 404
        second.post('/api/teams', headers=h2, json={'team_id': '72450', 'name': 'Other', 'country': 'FR'})
        assert second.get('/api/market?team_id=72450').json()['revision'] == 0
        assert 'market:72450' not in second.get('/api/export').json()['manager_documents']
