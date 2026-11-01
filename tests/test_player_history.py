"""Individual retained observations are scoped before their response limit."""
import json

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, 'Synthetic-history-password', secure=False)
    with TestClient(app) as client:
        reply = client.post('/api/login', json={'username': 'piwig', 'password': 'Synthetic-history-password'})
        assert reply.status_code == 200
        yield client


def retain(client, players, youth=False, team='72450', at='2026-01-01T10:00:00+02:00'):
    with client.app.state.store.db() as db:
        cursor = db.execute('INSERT INTO snapshots(team_id,youth,source,observed_at,imported_at,digest,payload) VALUES(?,?,?,?,?,?,?)',
                            (team, int(youth), 'Synthetic history', at, at, 'fixture', json.dumps(players)))
        return cursor.lastrowid


def history(client, query='', team='72450'):
    response = client.get(f'/api/history/{team}/42' + query)
    assert response.status_code == 200, response.text
    return response.json()


def test_junior_history_survives_more_than_one_hundred_unrelated_snapshots(client):
    retained = retain(client, [{'id': '42', 'attack': None, 'defense': 0}], youth=True)
    for _ in range(110):
        retain(client, [{'id': '99', 'attack': 10}])
        retain(client, [{'id': '99', 'attack': 11}], youth=True)
    rows = history(client, '?cohort=youth')
    assert len(rows) == 1
    assert rows[0]['snapshot_id'] == retained
    assert rows[0]['cohort'] == 'youth' and rows[0]['youth'] is True
    assert rows[0]['player']['attack'] is None and rows[0]['player']['defense'] == 0
    assert rows[0]['observed_at'] == '2026-01-01T10:00:00+02:00'


def test_limit_counts_matching_player_observations_within_chosen_population(client):
    junior_ids = []
    for i in range(105):
        junior_ids.append(retain(client, [{'id': '42', 'csr': i}], youth=True))
        retain(client, [{'id': '42', 'csr': 1000 + i}])
        retain(client, [{'id': '99'}], youth=True)
    rows = history(client, '?cohort=youth')
    assert len(rows) == 100
    assert [row['snapshot_id'] for row in rows] == list(reversed(junior_ids[5:]))
    assert [row['player']['csr'] for row in rows] == list(range(104, 4, -1))
    assert all(row['cohort'] == 'youth' and row['youth'] for row in rows)


def test_legacy_unfiltered_history_labels_both_populations_and_keeps_duplicate_snapshot_single(client):
    retain(client, [{'id': '42', 'strength': 'Unknown'}, {'id': '42', 'strength': 9}], youth=True)
    retain(client, [{'id': '42', 'strength': 0}])
    rows = history(client)
    assert [(row['cohort'], row['youth'], row['player']['strength']) for row in rows] == [
        ('club', False, 0), ('youth', True, 'Unknown')]
    assert [row['player']['strength'] for row in history(client, '?cohort=club')] == [0]


def test_namespaced_selections_never_read_club_or_other_selection_observations(client):
    with client.app.state.store.db() as db:
        for team in ('u20:72450', 'nt:72450'):
            db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?)', (team, 'Synthetic selection', 'FR'))
    for team, value in [('72450', 1), ('u20:72450', 2), ('nt:72450', 3)]:
        retain(client, [{'id': '42', 'strength': value}], team=team)
    for team, cohort, value in [('u20:72450', 'u20', 2), ('nt:72450', 'nt', 3)]:
        rows = history(client, '?cohort=' + cohort, team)
        assert [(row['cohort'], row['player']['strength']) for row in rows] == [(cohort, value)]
        assert history(client, team=team)[0]['cohort'] == cohort
    for team, cohort in [('72450', 'u20'), ('72450', 'nt'), ('u20:72450', 'club'), ('nt:72450', 'youth')]:
        assert client.get(f'/api/history/{team}/42?cohort={cohort}').status_code == 422
    assert client.get('/api/history/72450/42?cohort=other').status_code == 422
    assert client.get('/api/history/99999/42?cohort=youth').status_code == 404


def test_malformed_legacy_payloads_do_not_hide_valid_player_observations(client):
    retain(client, [{'id': '42', 'strength': 5}], youth=True)
    with client.app.state.store.db() as db:
        for payload in ('broken-json', '{"42":{"id":"42"}}', '[null,"bad",42]'):
            db.execute('INSERT INTO snapshots(team_id,youth,source,observed_at,imported_at,digest,payload) VALUES(?,?,?,?,?,?,?)',
                       ('72450', 1, 'Legacy', '2026-01-02', '2026-01-02', 'legacy', payload))
    rows = history(client, '?cohort=youth')
    assert len(rows) == 1 and rows[0]['player']['strength'] == 5


@pytest.mark.parametrize('player_id', [1, '1'])
def test_invalid_legacy_identifiers_cannot_consume_player_observation_limit(client, player_id):
    actual = retain(client, [{'id': player_id, 'strength': 5}], youth=True)
    for _ in range(100):
        retain(client, [{'id': True, 'strength': 7}, {'id': 1.0, 'strength': 8}], youth=True)
    response = client.get('/api/history/72450/1?cohort=youth')
    assert response.status_code == 200
    rows = response.json()
    assert [row['snapshot_id'] for row in rows] == [actual]
    assert rows[0]['player']['strength'] == 5


@pytest.mark.parametrize('player_id', ['1.0', '-1', 'true', 'abc', '1234567890123456'])
def test_history_rejects_noncanonical_player_identifiers(client, player_id):
    retain(client, [{'id': 1.0}], youth=True)
    assert client.get(f'/api/history/72450/{player_id}?cohort=youth').status_code == 422


def test_history_population_filter_does_not_cross_manager_accounts(client):
    retain(client, [{'id': '42', 'name': 'Private junior'}], youth=True)
    headers = {'X-CSRF-Token': client.get('/api/state').json()['csrf']}
    assert client.post('/api/admin/users', headers=headers, json={
        'username': 'othercoach', 'password': 'Another-synthetic-password'}).status_code == 200
    with TestClient(client.app) as other:
        assert other.get('/api/history/72450/42?cohort=youth').status_code == 401
        login = other.post('/api/login', json={'username': 'othercoach', 'password': 'Another-synthetic-password'})
        assert login.status_code == 200
        assert other.post('/api/teams', headers={'X-CSRF-Token': login.json()['csrf']}, json={
            'team_id': '72450', 'name': 'Other private club', 'country': 'FR'}).status_code == 200
        assert other.get('/api/history/72450/42?cohort=youth').json() == []
    assert history(client, '?cohort=youth')[0]['player']['name'] == 'Private junior'
