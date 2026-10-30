"""Dated observations must never manufacture progress or cross manager spaces."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path
import shutil
import subprocess
import tracemalloc

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import main


@pytest.fixture
def client(tmp_path):
    app = main.create_app(tmp_path, 'Testing-password-1234', secure=False)
    if not any(route.path == '/api/progression' for route in app.routes) and importlib.util.find_spec('server.progression'):
        from server.accounts import PrivateStore
        from server.progression import register_progression
        store = PrivateStore()
        auth = next(route for route in app.routes if route.path == '/api/state').dependant.dependencies[0].call

        def require_team(team_id):
            with store.db() as db:
                if not db.execute('SELECT id FROM teams WHERE id=?', (team_id,)).fetchone():
                    raise HTTPException(404, 'Club introuvable.')

        before = len(app.routes)
        register_progression(app, store, auth, require_team)
        added = app.router.routes[before:]
        app.router.routes[before:] = []
        app.router.routes[0:0] = added
    with TestClient(app) as c:
        yield c


def login(client, username='piwig', password='Testing-password-1234'):
    result = client.post('/api/login', json={'username': username, 'password': password})
    assert result.status_code == 200
    return {'X-CSRF-Token': result.json()['csrf']}


def snapshot(client, stamp, players, youth=False, source='Test observation'):
    # Deliberately retain unchanged observations, duplicate timestamps and malformed
    # legacy payloads as already-stored input; ingestion deduplication is unrelated.
    with client.app.state.store.db() as db:
        db.execute('INSERT INTO snapshots(team_id,youth,source,observed_at,imported_at,digest,payload) VALUES(?,?,?,?,?,?,?)',
                   ('72450', int(youth), source, stamp, '2026-10-30T00:00:00Z', 'fixture', json.dumps(players)))


def report(client, population='seniors'):
    reply = client.get('/api/progression?team_id=72450')
    assert reply.status_code == 200, reply.text[:200]
    return reply.json()[population]


def test_progression_authentication_and_team_access(client):
    assert client.get('/api/progression?team_id=72450').status_code == 401
    login(client)
    assert client.get('/api/progression?team_id=99999').status_code == 404
    assert client.get('/api/progression?team_id=not-a-club').status_code == 422
    assert report(client)['points'] == []


def test_multiple_observations_are_sorted_by_date_and_keep_sources(client):
    login(client)
    snapshot(client, '2026-10-15T10:00:00+02:00', [{'id': '42', 'name': 'A', 'csr': 120, 'strength': 6}], source='CSV récent')
    snapshot(client, '2026-10-01', [{'id': '42', 'name': 'A', 'csr': 100, 'strength': 5}], source='ODS initial')
    points = report(client)['points']
    assert [point['players']['42']['values']['csr'] for point in points] == [100, 120]
    assert points[1]['players']['42']['deltas']['csr'] == 20
    assert points[1]['metrics']['csr']['delta'] == 20
    assert points[0]['sources'] == [{'observed_at': '2026-10-01', 'source': 'ODS initial', 'precision': 'day'}]
    assert points[1]['at'] == '2026-10-15T08:00:00+00:00'
    assert report(client, 'academy')['points'] == []


def test_unknown_reveal_and_absence_break_numeric_comparison(client):
    login(client)
    for stamp, players in [
        ('2026-10-01', [{'id': '42', 'strength': 'Unknown'}]),
        ('2026-10-02', [{'id': '42', 'strength': 5}]),
        ('2026-10-03', [{'id': '42', 'strength': 6}]),
        ('2026-10-04', []),
        ('2026-10-05', [{'id': '42', 'strength': 9}]),
    ]:
        snapshot(client, stamp, players, youth=True)
    points = report(client, 'academy')['points']
    assert points[0]['players']['42']['values']['strength'] is None
    assert points[1]['players']['42']['revealed'] == ['strength']
    assert 'strength' not in points[1]['players']['42']['deltas']
    assert points[2]['players']['42']['deltas']['strength'] == 1
    assert points[4]['players']['42']['deltas'] == {}
    assert points[1]['metrics']['strength']['delta'] is None


@pytest.mark.parametrize('values', list(permutations([None, 5, 7])))
def test_same_timestamp_conflicts_are_order_independent(client, values):
    login(client)
    snapshot(client, '2026-09-30', [{'id': '42', 'strength': 4}], youth=True)
    for index, value in enumerate(values):
        stamp = ['2026-10-01T08:00:00Z', '2026-10-01T10:00:00+02:00', '2026-10-01T08:00:00+00:00'][index]
        snapshot(client, stamp, [{'id': '42', 'strength': value}], youth=True, source='Source ' + str(value))
    snapshot(client, '2026-10-02', [{'id': '42', 'strength': 8}], youth=True)
    points = report(client, 'academy')['points']
    assert len(points) == 3
    assert points[1]['players']['42']['values']['strength'] is None
    assert points[1]['players']['42']['conflicts'] == ['strength']
    assert points[1]['metrics']['strength']['conflict_count'] == 1
    assert points[2]['players']['42']['deltas'] == {}
    assert points[2]['players']['42']['revealed'] == []


def test_changed_roster_or_coverage_does_not_claim_collective_progress(client):
    login(client)
    snapshot(client, '2026-10-01', [{'id': '1', 'csr': 100}, {'id': '2', 'csr': 200}])
    snapshot(client, '2026-10-02', [{'id': '1', 'csr': 110}, {'id': '3', 'csr': 900}])
    snapshot(client, '2026-10-03', [{'id': '1', 'csr': 120}, {'id': '3', 'csr': None}])
    points = report(client)['points']
    assert points[1]['metrics']['csr']['value'] == 505
    assert points[1]['metrics']['csr']['delta'] is None
    assert points[1]['roster_changed'] is True
    assert points[1]['entered'] == ['3']
    assert points[1]['left'] == ['2']
    assert points[2]['metrics']['csr']['value'] == 120
    assert points[2]['metrics']['csr']['known_count'] == 1
    assert points[2]['metrics']['csr']['delta'] is None
    assert points[2]['metrics']['csr']['comparison'] == 'coverage_changed'


def test_disagreeing_rosters_at_one_instant_block_collective_comparison(client):
    login(client)
    snapshot(client, '2026-10-01', [{'id': '1', 'csr': 100}])
    snapshot(client, '2026-10-02', [{'id': '1', 'csr': 110}])
    snapshot(client, '2026-10-02', [{'id': '1', 'csr': 110}, {'id': '2', 'csr': 900}])
    snapshot(client, '2026-10-03', [{'id': '1', 'csr': 120}, {'id': '2', 'csr': 1000}])
    points = report(client)['points']
    assert points[1]['roster_conflict'] is True
    assert points[1]['metrics']['csr']['delta'] is None
    assert points[2]['metrics']['csr']['delta'] is None


def test_invalid_dates_and_nonfinite_metrics_are_not_chart_data(client):
    login(client)
    for stamp in ['not-a-date', '2026-02-30', '2026-10-01T25:00:00Z']:
        snapshot(client, stamp, [{'id': '42', 'csr': 99}])
    snapshot(client, '2026-10-02', [{'id': '42', 'csr': float('inf'), 'strength': float('nan'), 'speed': True, 'handling': -2, 'attack': 99}])
    result = report(client)
    assert result['invalid_dates'] == 3
    assert len(result['points']) == 1
    assert all(value is None for value in result['points'][0]['players']['42']['values'].values())


def test_truncation_drops_an_incomplete_same_time_group(client):
    login(client)
    snapshot(client, '2026-01-01', [{'id': '42', 'strength': 2}])
    snapshot(client, '2026-01-01', [{'id': '42', 'strength': 9}])
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    for i in range(239):
        snapshot(client, (start + timedelta(days=i)).isoformat(), [{'id': '42', 'strength': 4 + i % 2}])
    result = report(client)
    assert result['history_truncated'] is True
    assert result['total_snapshots'] == 241
    assert result['snapshot_limit'] == 240
    assert len(result['points']) == 239
    assert result['excluded_boundary_snapshots'] == 1
    assert result['points'][0]['players']['42']['deltas'] == {}


def test_unreadable_snapshot_breaks_comparison_instead_of_bridging_a_gap(client):
    login(client)
    snapshot(client, '2026-10-01', [{'id': '42', 'csr': 100}])
    snapshot(client, '2026-10-02', {'broken': 'not a roster'})
    snapshot(client, '2026-10-03', [{'id': '42', 'csr': 200}])
    result = report(client)
    assert result['invalid_payloads'] == 1
    assert result['points'][-1]['players']['42']['deltas'] == {}
    assert result['points'][-1]['metrics']['csr']['delta'] is None


def test_equal_coverage_count_with_different_players_is_not_comparable(client):
    login(client)
    snapshot(client, '2026-10-01', [{'id': '1', 'csr': 100}, {'id': '2', 'csr': None}])
    snapshot(client, '2026-10-02', [{'id': '1', 'csr': None}, {'id': '2', 'csr': 900}])
    point = report(client)['points'][-1]
    assert point['metrics']['csr']['known_count'] == 1
    assert point['metrics']['csr']['comparison'] == 'coverage_changed'
    assert point['metrics']['csr']['delta'] is None


def test_day_only_date_does_not_create_a_same_day_numeric_change(client):
    login(client)
    snapshot(client, '2026-10-01', [{'id': '42', 'csr': 100}])
    snapshot(client, '2026-10-01T12:00:00Z', [{'id': '42', 'csr': 200}])
    points = report(client)['points']
    assert points[1]['players']['42']['deltas'] == {}
    assert points[1]['metrics']['csr']['delta'] is None
    assert points[1]['metrics']['csr']['comparison'] == 'date_precision'


@pytest.mark.parametrize('same_time', [False, True])
def test_snapshot_payloads_are_not_all_retained_in_memory(client, same_time):
    from server.progression import progression_series
    login(client)
    for i in range(40):
        stamp = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=0 if same_time else i)).isoformat()
        snapshot(client, stamp, [{'id': '42', 'name': 'A', 'csr': 100 + i, 'legacy_metadata': 'x' * 220_000}])
    tracemalloc.start()
    try:
        result = progression_series(client.app.state.store, '72450', False)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(result['points']) == (1 if same_time else 40)
    # Forty retained JSON strings alone exceed 8 MiB. Reading one at a time
    # keeps this deliberately padded legacy history below a 4 MiB budget.
    assert peak < 4_000_000, f'History payload memory peaked at {peak:,} bytes'


def test_response_budget_keeps_complete_recent_dates_without_arbitrary_player_samples(client, monkeypatch):
    import server.progression as progression
    monkeypatch.setattr(progression, 'PLAYER_POINT_LIMIT', 3, raising=False)
    login(client)
    for day in [1, 2, 3]:
        snapshot(client, f'2026-10-0{day}', [{'id': '1', 'csr': day * 100}, {'id': '2', 'csr': day * 200}])
    result = report(client)
    assert len(result['points']) == 1
    assert result['points'][0]['at'] == '2026-10-03T00:00:00+00:00'
    assert result['points'][0]['roster_count'] == 2
    assert result['points'][0]['metrics']['csr']['delta'] is None
    assert result['budget_truncated_snapshots'] == 2
    assert result['history_truncated'] is True


def test_same_time_large_rosters_are_merged_without_retaining_every_entry(client):
    from server.progression import progression_series
    login(client)
    players = [{'id': str(i), 'name': 'A'} for i in range(1, 4001)]
    for i in range(40):
        players[0]['name'] = str(i)
        snapshot(client, '2026-10-01', players)
    tracemalloc.start()
    try:
        result = progression_series(client.app.state.store, '72450', False)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(result['points']) == 1
    assert len(result['points'][0]['players']) == 300
    assert result['points'][0]['metrics']['csr']['value'] is None
    assert peak < 12_000_000, f'Same-time merge peaked at {peak:,} bytes'


@pytest.mark.parametrize('reverse', [False, True])
def test_large_roster_sampling_preserves_conflicts_and_presence_independent_of_order(client, reverse):
    login(client)
    first = [{'id': str(i), 'strength': 5} for i in range(1, 401)]
    second = [{'id': str(i), 'strength': 6 if i == 1 else 5} for i in range(1, 401) if i != 2]
    for roster in ([second, first] if reverse else [first, second]):
        snapshot(client, '2026-10-01', list(reversed(roster)) if reverse else roster)
    point = report(client)['points'][0]
    assert sorted(point['players']) == sorted(str(i) for i in range(1, 401))[:300]
    assert point['players']['1']['values']['strength'] is None
    assert point['players']['1']['conflicts'] == ['strength']
    assert point['players']['2']['presence_conflict'] is True
    assert point['players_truncated'] is True
    assert point['roster_count'] == 400
    assert point['roster_count_exact'] is False
    assert point['metrics']['strength']['value'] is None


def test_progression_stays_in_authenticated_manager_database(client):
    headers = login(client)
    snapshot(client, '2026-10-01', [{'id': '42', 'name': 'Private original', 'csr': 100}])
    assert client.post('/api/admin/users', headers=headers, json={'username': 'reader', 'password': 'Another-password-5678'}).status_code == 200
    with TestClient(client.app) as other:
        oh = login(other, 'reader', 'Another-password-5678')
        assert other.get('/api/progression?team_id=72450').status_code == 404
        assert other.post('/api/teams', headers=oh, json={'team_id': '72450', 'name': 'Independent', 'country': 'BE'}).status_code == 200
        assert report(other)['points'] == []
        assert 'Private original' not in other.get('/api/progression?team_id=72450').text
        assert report(client)['players'] == [{'id': '42', 'name': 'Private original'}]


def test_chart_and_table_keep_unknown_reveals_and_absence_as_gaps():
    """Execute the UI's data adapter; fail if it turns missing/revealed data into gain."""
    web = Path(__file__).resolve().parents[1] / 'web'
    if not shutil.which('node') or not (web / 'node_modules/typescript').exists():
        pytest.skip('Node and frontend dependencies required for chart adapter validation.')
    script = r'''
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const source = ts.transpileModule(fs.readFileSync('src/progression.tsx','utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}
}).outputText;
const artifact = {exports:{}};
const load = id => id === './App' ? {} : id === './types' ? {skills:[],labels:{}} : id.endsWith('.css') ? {} : require(id);
vm.runInNewContext(source,{module:artifact,exports:artifact.exports,require:load});
const point = (at, player) => ({at,players:player?{'42':player}:{},roster_count:player?1:0,roster_conflict:false,players_truncated:false,metrics:{csr:{value:100,known_count:1,unknown_count:0,delta:null,comparison:'coverage_changed',conflict_count:0}}});
const player = (value,extra={}) => ({values:{csr:value},conflicts:[],revealed:[],deltas:{},presence_conflict:false,...extra});
const rows = artifact.exports.buildProgressionRows([
  point('2026-01-01',player(null)),
  point('2026-01-02',player(100,{revealed:['csr']})),
  point('2026-01-03',player(120,{deltas:{csr:20}})),
  point('2026-01-04',null),
  point('2026-01-05',player(null,{conflicts:['csr']})),
  point('2026-01-06',player(140)),
], 'csr', '42');
assert.equal(rows[0].value,null);
assert.equal(rows[1].delta,null);
assert.match(rows[1].status,/Dévoilement/);
assert.equal(rows[2].delta,20);
assert.equal(rows[3].value,null);
assert.equal(rows[4].conflict,true);
assert.equal(rows[5].delta,null);
const collective = artifact.exports.buildProgressionRows([point('2026-01-01',player(100))],'csr','');
assert.equal(collective[0].value,100);
assert.equal(collective[0].delta,null);
assert.equal(collective[0].known,1);
assert.match(collective[0].status,/différents/);
'''
    result = subprocess.run(['node', '-e', script], cwd=web, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
