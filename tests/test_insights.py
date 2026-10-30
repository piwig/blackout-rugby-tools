"""Private manager observations: never manufacture training or progression."""
import json
from itertools import permutations
from pathlib import Path
import shutil
import subprocess
import pytest
from fastapi.testclient import TestClient
from server import main


@pytest.fixture
def client(tmp_path):
    app = main.create_app(tmp_path, 'Testing-password-1234', secure=False)
    # Until the coordinator registers the module, reuse the real route dependencies.
    if not any(route.path == '/api/insights/{team_id}' for route in app.routes):
        import server.insights as insights
        from server.accounts import PrivateStore
        state_route = next(route for route in app.routes if route.path == '/api/state')
        auth = state_route.dependant.dependencies[0].call
        store = PrivateStore()
        def require_team(team_id):
            from fastapi import HTTPException
            with store.db() as db:
                row = db.execute('SELECT id FROM teams WHERE id=?', (team_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Club introuvable.')
        before = len(app.routes)
        insights.register_insights(app, store, auth, require_team, state_route.endpoint)
        added = app.router.routes[before:]
        app.router.routes[before:] = []
        app.router.routes[0:0] = added
    with TestClient(app) as c:
        yield c


def login(client, username='piwig'):
    reply = client.post('/api/login', json={'username': username, 'password': 'Testing-password-1234'})
    assert reply.status_code == 200
    return {'X-CSRF-Token': reply.json()['csrf']}


def save(client, headers, **changes):
    current = client.get('/api/insights/72450').json()['document']
    revision = current.pop('revision')
    current.pop('updated_at', None)
    current.update(changes)
    return client.post('/api/insights/72450', headers=headers,
                       json={'expected_revision': revision, 'document': current})


def test_unknown_skill_revelation_is_not_numeric_progress(client):
    login(client)
    store = client.app.state.store
    for at, strength in [('2026-10-01T09:00:00+00:00', 'Unknown'),
                         ('2026-10-08T09:00:00+00:00', 5),
                         ('2026-10-15T09:00:00+00:00', 6)]:
        store.save_snapshot('72450', True, [{'id': '42', 'name': 'A', 'strength': strength}], 'fixture', at)
    timeline = client.get('/api/insights/72450').json()['academy']['timeline']
    assert [(event['kind'], event['delta']) for event in timeline] == [('revealed', None), ('numeric_change', 1)]
    assert timeline[1]['observed_at'] == '2026-10-15T09:00:00+00:00'


def test_backdated_imports_are_compared_by_observation_date(client):
    login(client)
    store = client.app.state.store
    for at, strength in [('2026-10-15T09:00:00+00:00', 6), ('2026-10-01T09:00:00+00:00', 5)]:
        store.save_snapshot('72450', True, [{'id': '42', 'name': 'A', 'strength': strength}], 'fixture', at)
    timeline = client.get('/api/insights/72450').json()['academy']['timeline']
    assert [event['delta'] for event in timeline] == [1]


def test_training_latest_observation_does_not_become_completed_history(client):
    headers = login(client)
    client.app.state.store.set('training:72450', ['strength'] * 4)
    grid = [[''] * 16 for _ in range(4)]
    grid[0][0] = 'strength'
    grid[1][0] = 'speed'
    client.post('/api/plans', headers=headers, json={'team_id': '72450', 'season': 62, 'grid': grid})
    initial = client.get('/api/insights/72450').json()['academy']
    assert initial['sessions'] == []
    assert initial['planned_count'] == 2
    assert initial['unrecorded_count'] == 2
    response = save(client, headers, sessions=[{'id': 'one', 'season': 62, 'week': 1, 'slot': 1,
                    'skill': 'strength', 'performed_at': '2026-10-10T12:00:00+02:00', 'note': 'Vérifié dans le jeu'}])
    assert response.status_code == 200, response.text
    report = client.get('/api/insights/72450').json()['academy']
    assert report['sessions'][0]['comparison'] == 'matches_plan'
    assert report['sessions'][0]['provenance'] == 'manual'
    assert report['unrecorded_count'] == 1


def test_match_association_is_explicit_and_type_distinguishes_identity(client):
    headers = login(client)
    for kind, events in [(0, [{'field': 1, 'possession': 1, 'att': 'large'}, {'text': '?'}]),
                         (1, [{'field': 1, 'possession': 0, 'att': 'percu'}])]:
        client.post('/api/matches/import', headers=headers, json={'id': '99', 'type': kind, 'home': 'A', 'away': 'B', 'events': events})
    initial = client.get('/api/insights/72450').json()['opponents']
    assert initial['match_count'] == 0
    assert initial['unlinked_count'] == 2
    links = [{'match_id': '99', 'match_type': 0, 'club_side': 'home', 'opponent': 'B', 'season': 62},
             {'match_id': '99', 'match_type': 1, 'club_side': 'away', 'opponent': 'B', 'season': 63}]
    assert save(client, headers, match_links=links).status_code == 200
    report = client.get('/api/insights/72450/opponents?opponent=B').json()
    assert report['match_count'] == 2
    assert report['total_events'] == 3
    assert report['classified'] == 2
    assert report['opponent_actions'] == 2
    assert report['attacks']['Large'] == 1
    assert report['attacks']['Percussion'] == 1
    filtered = client.get('/api/insights/72450/opponents?season=62&match_type=0&club_side=home').json()
    assert filtered['match_count'] == 1
    assert filtered['coverage_pct'] == 50


def scenario():
    return {'id': 'build', 'name': 'Petite extension', 'current': {'standing': 100, 'uncovered': 20, 'covered': 0, 'members': 0, 'corporate': 0},
            'target': {'standing': 120, 'uncovered': 10, 'covered': 0, 'members': 0, 'corporate': 0},
            'unit_costs': {'standing': 3, 'uncovered': 9, 'covered': None, 'members': None, 'corporate': None},
            'treasury': 1000, 'reserve': 100, 'note': ''}


def test_stadium_costs_never_refund_removed_seats_and_subtract_reserve(client):
    headers = login(client)
    assert save(client, headers, stadium_scenarios=[scenario()]).status_code == 200
    result = client.get('/api/insights/72450').json()['stadium'][0]
    assert result['construction_cost'] == 60
    assert result['remaining_available'] == 840
    assert result['reduction_categories'] == ['uncovered']
    changed = scenario()
    changed['unit_costs']['standing'] = None
    assert save(client, headers, stadium_scenarios=[changed]).status_code == 200
    result = client.get('/api/insights/72450').json()['stadium'][0]
    assert result['construction_cost'] is None
    assert result['remaining_available'] is None


def test_private_documents_require_csrf_and_revisions_and_export_excludes_secrets(client):
    assert client.get('/api/insights/72450').status_code == 401
    headers = login(client)
    doc = client.get('/api/insights/72450').json()['document']
    doc.pop('updated_at', None)
    doc.pop('revision')
    payload = {'expected_revision': 0, 'document': doc}
    assert client.post('/api/insights/72450', json=payload).status_code == 403
    assert client.post('/api/insights/72450', headers=headers, json=payload).status_code == 200
    assert client.post('/api/insights/72450', headers=headers, json=payload).status_code == 409
    assert client.get('/api/insights/999999').status_code == 404
    client.app.state.store.save_secrets('72450', {'m': 'secret', 'mk': 'never-export'})
    from server.insights import export_insights
    exported = export_insights(client.app.state.store)
    assert exported['72450']['revision'] == 1
    assert 'never-export' not in json.dumps(exported)
    client.post('/api/admin/users', headers=headers, json={'username': 'other', 'password': 'Testing-password-1234'})
    other_headers = login(client, 'other')
    assert client.get('/api/insights/72450').status_code == 404
    client.post('/api/teams', headers=other_headers, json={'team_id': '72450', 'name': 'Other club'})
    assert client.get('/api/insights/72450').json()['document']['revision'] == 0


@pytest.mark.parametrize('changes', [
    {'goals': [{'player_id': '42', 'text': 'Absent de l’effectif'}]},
    {'match_links': [{'match_id': '404', 'match_type': 0, 'club_side': 'home', 'opponent': 'Absent', 'season': 62}]},
    {'sessions': [{'id': 'x', 'season': 62, 'week': 17, 'slot': 1, 'skill': 'strength', 'performed_at': '2026-10-10T12:00:00+02:00'}]},
    {'sessions': [{'id': 'x', 'season': 62, 'week': 1, 'slot': 1, 'skill': 'strength', 'performed_at': '2026-10-10T12:00:00'}]},
    {'stadium_scenarios': [{**scenario(), 'treasury': -1}]},
    {'stadium_scenarios': [{**scenario(), 'treasury': True}]},
])
def test_invalid_or_stale_references_are_rejected_without_saving(client, changes):
    headers = login(client)
    assert save(client, headers, **changes).status_code == 422
    assert client.get('/api/insights/72450').json()['document']['revision'] == 0


def test_equal_timestamp_observations_are_not_reported_as_numeric_progress(client):
    login(client)
    for strength in [5, 6]:
        client.app.state.store.save_snapshot('72450', True, [{'id': '42', 'name': 'A', 'strength': strength}],
                                            'fixture', '2026-10-01T09:00:00+00:00')
    timeline = client.get('/api/insights/72450').json()['academy']['timeline']
    assert timeline[0]['kind'] == 'conflicting_observation'
    assert timeline[0]['delta'] is None
    client.app.state.store.save_snapshot('72450', True, [{'id': '42', 'name': 'A', 'strength': 7}],
                                        'fixture', '2026-10-02T09:00:00+00:00')
    timeline = client.get('/api/insights/72450').json()['academy']['timeline']
    assert not any(event['kind'] == 'numeric_change' for event in timeline)


@pytest.mark.parametrize('observations', list(permutations([
    ('2026-10-01T09:00:00+00:00', 5),
    ('2026-10-02T09:00:00+00:00', 6),
    ('2026-10-02T09:00:00+00:00', 7),
])))
def test_contradictory_target_date_never_keeps_numeric_progress_from_unique_baseline(client, observations):
    login(client)
    for at, strength in observations:
        client.app.state.store.save_snapshot('72450', True, [{'id': '42', 'name': 'A', 'strength': strength}], 'fixture', at)
    timeline = client.get('/api/insights/72450').json()['academy']['timeline']
    assert [(event['kind'], event['before'], event['after'], event['delta']) for event in timeline] == [
        ('conflicting_observation', 6, 7, None)]
    assert timeline[0]['observed_at'] == '2026-10-02T09:00:00+00:00'


def test_stadium_draft_tracks_observations_until_edited_then_requires_explicit_refresh():
    """Execute the UI reducer without a browser; React/import stubs are not under test."""
    web = Path(__file__).resolve().parents[1] / 'web'
    if not shutil.which('node') or not (web / 'node_modules/typescript').exists():
        pytest.skip('Node and installed frontend development dependencies required for UI reducer validation.')
    script = r'''
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const compiled = ts.transpileModule(fs.readFileSync('src/insights.tsx','utf8'), {
  compilerOptions: {module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}
}).outputText;
const artifact = {exports:{}};
const load = id => id === './App' ? {} : id === './types' ? {} : id.endsWith('.css') ? {} : require(id);
vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:load,structuredClone});
assert.equal(typeof artifact.exports.stadiumDraftReducer, 'function', 'Stadium observation transitions must be explicit');
const reduce = artifact.exports.stadiumDraftReducer;
const values = standing => ({standing,uncovered:0,covered:0,members:0,corporate:0});
const observation = {current:values(100),treasury:1000};
const draft = {id:'draft',name:'',current:values(100),target:values(null),unit_costs:values(null),treasury:1000,reserve:null,note:''};
let state = {draft,observation,dirty:false,stale:false};
state = reduce(state,{type:'observe',observation:{current:values(120),treasury:900}});
assert.equal(state.draft.current.standing,120);
assert.equal(state.draft.treasury,900);
assert.equal(state.stale,false);
state = reduce(state,{type:'edit',draft:{...state.draft,name:'Keep my choices',target:values(250),treasury:850}});
state = reduce(state,{type:'observe',observation:{current:values(140),treasury:800}});
assert.equal(state.draft.current.standing,120);
assert.equal(state.draft.treasury,850);
assert.equal(state.draft.target.standing,250);
assert.equal(state.stale,true);
state = reduce(state,{type:'use_latest'});
assert.equal(state.draft.current.standing,140);
assert.equal(state.draft.treasury,800);
assert.equal(state.draft.target.standing,250);
assert.equal(state.draft.name,'Keep my choices');
assert.equal(state.stale,false);
'''
    result = subprocess.run(['node', '-e', script], cwd=web, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_match_type_boolean_cannot_alias_another_competition(client):
    headers = login(client)
    client.post('/api/matches/import', headers=headers, json={'id': '99', 'type': 1, 'events': []})
    response = save(client, headers, match_links=[{'match_id': '99', 'match_type': True,
                    'club_side': 'home', 'opponent': 'B', 'season': 62}])
    assert response.status_code == 422


def test_goals_roundtrip_generation_and_stale_player_preservation(client):
    headers = login(client)
    store = client.app.state.store
    store.set('game_date', {'season': 62, 'round': 1, 'day': 1})
    store.save_snapshot('72450', True, [{'id': '42', 'name': 'A', 'age': 18, 'birthday': '1:1', 'strength': 5}], 'fixture')
    goal = {'player_id': '42', 'text': 'Développer la force', 'skill': 'strength', 'target': 8, 'due_season': 64}
    assert save(client, headers, goals=[goal]).status_code == 200
    observed = client.get('/api/insights/72450').json()['academy']['generations']['64'][0]
    assert observed['goal'] == goal
    assert observed['target_gap'] == 3
    store.save_snapshot('72450', True, [], 'fixture')
    assert save(client, headers, stadium_scenarios=[scenario()]).status_code == 200
    assert client.get('/api/insights/72450').json()['academy']['stale_goal_ids'] == ['42']
    assert save(client, headers, goals=[{**goal, 'target': 9}]).status_code == 422
    assert save(client, headers, goals=[]).status_code == 200


def test_session_mismatch_and_duplicate_slot_remain_explicit(client):
    headers = login(client)
    grid = [[''] * 16 for _ in range(4)]
    grid[0][0] = 'speed'
    client.post('/api/plans', headers=headers, json={'team_id': '72450', 'season': 62, 'grid': grid})
    session = {'id': 'one', 'season': 62, 'week': 1, 'slot': 1, 'skill': 'strength',
               'performed_at': '2026-10-10T12:00:00+02:00'}
    assert save(client, headers, sessions=[session]).status_code == 200
    assert client.get('/api/insights/72450').json()['academy']['sessions'][0]['comparison'] == 'differs_from_plan'
    assert save(client, headers, sessions=[session, {**session, 'id': 'two'}]).status_code == 422
    assert save(client, headers, sessions=[{**session, 'performed_at': '2099-01-01T00:00:00Z'}]).status_code == 422


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), 1e20, -1])
def test_nonfinite_and_unbounded_stadium_costs_are_rejected(client, bad):
    headers = login(client)
    draft = scenario()
    draft['unit_costs']['standing'] = bad
    doc = client.get('/api/insights/72450').json()['document']
    doc.pop('revision')
    doc.pop('updated_at')
    doc['stadium_scenarios'] = [draft]
    response = client.post('/api/insights/72450', headers={**headers, 'Content-Type': 'application/json'},
                           content=json.dumps({'expected_revision': 0, 'document': doc}))
    assert response.status_code == 422
    assert client.get('/api/insights/72450').json()['document']['revision'] == 0
