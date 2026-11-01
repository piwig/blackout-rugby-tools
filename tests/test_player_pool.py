"""Synthetic endpoint checks for provenance, isolation and revisioned pool notes."""
import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path, 'Testing-password-1234', secure=False)
    if not any(getattr(route, 'path', '') == '/api/player-pool' for route in app.routes):
        from server.player_pool import register_player_pool
        state = next(route for route in app.routes if getattr(route, 'path', '') == '/api/state')
        values = inspect.getclosurevars(state.endpoint).nonlocals
        register_player_pool(app, values['store'], state.dependant.dependencies[0].call, values['require_team'])
        app.router.routes.sort(key=lambda route: getattr(route, 'path', '') == '/{path:path}')
    return app


def login(client, username='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def seed(store):
    with store.db() as db:
        db.execute('DELETE FROM teams')
        for tid in ('42', 'u20:42', 'nt:42'):
            db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?)', (tid, 'Synthetic ' + tid, 'FR'))
        db.execute('INSERT INTO notes VALUES(?,?,?,?)', ('42', '7', 'Club-only note', 1))
    store.set('classic_account', {'selection_ids': ['u20:42']})
    store.save_snapshot('42', False, [{'id': '7', 'name': 'Old name', 'age': 18}], 'old.csv', '2025-01-01T00:00:00Z')
    store.save_snapshot('42', False, [{'id': '7', 'name': 'Ada', 'age': 19, 'nationality': 'FR', 'attack': 12, 'injured': '0'}], 'club.csv', '2026-01-01T00:00:00Z')
    store.save_snapshot('42', True, [{'id': '8', 'name': 'Ben', 'age': 17, 'nationality': 'IT', **{k: 10 for k in ('stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking')}}], 'academy.csv', '2026-02-01T00:00:00Z')
    store.save_snapshot('u20:42', False, [{'id': '7', 'name': 'Ada', 'age': 20, 'nationality': 'IT', 'attack': 14}], 'u20.csv', '2026-02-01T00:00:00Z')
    store.save_snapshot('nt:42', False, [{'id': '7', 'name': 'Ada', 'age': 20, 'nationality': 'FR', 'injured': '1'}], 'nt.csv', '2026-03-01T00:00:00Z')


def test_pool_groups_latest_contexts_without_merging_sources(app):
    seed(app.state.store)
    with TestClient(app) as client:
        login(client)
        rows = client.get('/api/player-pool').json()
        assert rows['total'] == 2
        ada = next(p for p in rows['players'] if p['player_id'] == '7')
        assert ada['observation_count'] == 3
        assert ada['nationalities'] == ['FR', 'IT']
        assert ada['ages'] == [19, 20]
        assert {'age', 'nationality', 'attack'} <= set(ada['conflicts'])
        detail = client.get('/api/player-pool/7').json()
        assert [(o['team_id'], o['cohort'], o['archive']) for o in detail['observations']] == [('42', 'squad', False), ('nt:42', 'squad', True), ('u20:42', 'squad', False)]
        assert {o['source'] for o in detail['observations']} == {'club.csv', 'u20.csv', 'nt.csv'}
        assert {o['observed_at'] for o in detail['observations']} == {'2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z', '2026-03-01T00:00:00Z'}
        assert detail['document'] == {'revision': 0, 'watch': False, 'text': '', 'updated_at': None}
        club = detail['observations'][0]
        assert club['player']['attack'] == 12
        assert 'defense' not in club['player']
        assert club['player']['metrics']['roles'] == []
        assert club['player']['metrics']['estimated_csr'] is None


def test_filters_use_one_observation_and_pagination_is_bounded(app):
    seed(app.state.store)
    with TestClient(app) as client:
        login(client)
        def ids(query):
            response = client.get('/api/player-pool?' + query)
            assert response.status_code == 200, response.text
            return [p['player_id'] for p in response.json()['players']]
        assert ids('q=ben&nationality=IT&age_max=18&quality=complete') == ['8']
        assert ids('nationality=FR&age_min=20&availability=healthy') == []
        assert ids('availability=injured&quality=conflicting') == ['7']
        assert ids('availability=unknown') == ['7', '8']
        assert ids('position=Pilier') == ['8']
        assert ids('limit=1&offset=1') == ['8']
        assert client.get('/api/player-pool?limit=101').status_code == 422
        assert client.get('/api/player-pool?age_min=21&age_max=18').status_code == 422


def test_pool_auth_csrf_cas_and_club_notes_remain_separate(app):
    seed(app.state.store)
    with TestClient(app) as client:
        assert client.get('/api/player-pool').status_code == 401
        assert client.get('/api/player-pool/7').status_code == 401
        headers = login(client)
        body = {'expected_revision': 0, 'watch': True, 'text': 'Pool-only note'}
        assert client.post('/api/player-pool/7', json=body).status_code == 403
        saved = client.post('/api/player-pool/7', json=body, headers=headers)
        assert saved.status_code == 200, saved.text
        assert saved.json()['revision'] == 1
        assert client.post('/api/player-pool/7', json={**body, 'text': 'Lost draft'}, headers=headers).status_code == 409
        assert client.get('/api/player-pool/7').json()['document']['text'] == 'Pool-only note'
        assert client.get('/api/player-pool?watch=true').json()['total'] == 1
        assert client.post('/api/player-pool/999', json=body, headers=headers).status_code == 404
        assert client.post('/api/player-pool/7', json={**body, 'user_id': 'other'}, headers=headers).status_code == 422
        assert client.post('/api/player-pool/7', json={**body, 'text': 'x' * 3001}, headers=headers).status_code == 422
        with app.state.store.db() as db:
            assert db.execute('SELECT text FROM notes WHERE team_id=? AND player_id=?', ('42', '7')).fetchone()['text'] == 'Club-only note'


def test_competing_pool_notes_have_one_winner(app):
    seed(app.state.store)
    with TestClient(app) as first, TestClient(app) as second:
        fh, sh = login(first), login(second)
        def write(args):
            client, headers, text = args
            return client.post('/api/player-pool/7', json={'expected_revision': 0, 'watch': True, 'text': text}, headers=headers)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(write, [(first, fh, 'First'), (second, sh, 'Second')]))
        assert sorted(r.status_code for r in results) == [200, 409]
        winner = next(r.json() for r in results if r.status_code == 200)
        assert first.get('/api/player-pool/7').json()['document'] == winner


def test_pool_isolated_even_with_identical_player_and_team_ids(app):
    seed(app.state.store)
    with TestClient(app) as first, TestClient(app) as second:
        fh = login(first)
        response = first.post('/api/admin/users', headers=fh, json={'username': 'alice', 'password': 'Another-password-5678'})
        assert response.status_code == 200
        sh = login(second, 'alice', 'Another-password-5678')
        assert second.get('/api/player-pool').json()['players'] == []
        assert second.get('/api/player-pool/7').status_code == 404
        other = app.state.accounts.store(app.state.accounts.user('alice')['id'])
        seed(other)
        assert second.post('/api/player-pool/7', headers=sh, json={'expected_revision': 0, 'watch': True, 'text': 'Alice private'}).status_code == 200
        assert first.get('/api/player-pool/7').json()['document']['text'] == ''
        assert second.get('/api/player-pool/7', headers=fh).status_code == 403


def test_pool_retains_original_and_latest_successful_observation_dates(app):
    seed(app.state.store)
    store = app.state.store
    players = [{'id': '7', 'name': 'Ada', 'age': 19, 'nationality': 'FR', 'attack': 12, 'injured': '0'}]
    store.save_snapshot('42', False, players, 'fresh.csv', '2026-04-01T00:00:00Z')
    with TestClient(app) as client:
        login(client)
        row = client.get('/api/player-pool/7').json()['observations'][0]
        assert row['observed_at'] == '2026-04-01T00:00:00Z'
        assert row['first_observed_at'] == '2026-01-01T00:00:00Z'
        assert row['source'] == 'fresh.csv'
        assert row['first_source'] == 'club.csv'


def test_pool_rejects_oversized_latest_payload_without_silent_truncation(app):
    seed(app.state.store)
    with app.state.store.db() as db:
        db.execute("UPDATE snapshots SET payload=? WHERE id=(SELECT MAX(id) FROM snapshots)", (' ' * 4_000_001,))
    with TestClient(app) as client:
        login(client)
        response = client.get('/api/player-pool')
        assert response.status_code == 413


def test_masked_skills_and_unknown_injury_remain_unknown_and_observation_does_not_age(app):
    seed(app.state.store)
    app.state.store.save_snapshot('42', True, [{'id': '9', 'name': 'Masked', 'strength': 'Unknown', 'attack': 0, 'injured': '2026-02-10T00:00:00Z', 'reveals': ['attack']}], 'masked.csv', '2026-02-01T00:00:00Z')
    with TestClient(app) as client:
        login(client)
        detail = client.get('/api/player-pool/9').json()
        row = detail['observations'][0]
        assert row['player']['attack'] == 0
        assert 'strength' not in row['player']
        assert row['player']['reveals'] == ['attack']
        assert row['player']['metrics']['known_skills'] == 1
        assert row['player']['metrics']['roles'] == []
        assert row['availability'] == 'injured'  # At the source date, even after February.


def test_pool_rejects_too_many_contexts_without_omitting_teams(app):
    store = app.state.store
    with store.db() as db:
        db.execute('DELETE FROM teams')
        for i in range(257):
            tid = str(1000+i)
            db.execute('INSERT INTO teams(id,name,country) VALUES(?,?,?)', (tid, 'Synthetic', 'FR'))
            store.save_snapshot(tid, False, [{'id': str(i), 'name': 'Synthetic'}], 'bounded.csv', db=db)
    with TestClient(app) as client:
        login(client)
        assert client.get('/api/player-pool').status_code == 413


def test_pool_reports_divergence_in_secondary_known_player_fields(app):
    seed(app.state.store)
    app.state.store.save_snapshot('42', False, [{'id': '7', 'name': 'Ada', 'salary': 2000, 'stars': 3}], 'club-secondary.csv')
    app.state.store.save_snapshot('u20:42', False, [{'id': '7', 'name': 'Ada', 'salary': 3000, 'stars': 4}], 'selection-secondary.csv')
    with TestClient(app) as client:
        login(client)
        detail = client.get('/api/player-pool/7').json()
        assert detail['conflicts']['salary'] == [2000, 3000]
        assert detail['conflicts']['stars'] == [3, 4]
