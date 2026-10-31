"""Private starter declarations: no inferred or transmitted Classic actions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('BRT_VACATION_WORKER', '0')
    return create_app(tmp_path, 'Testing-password-1234', secure=False)


def login(client, username='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token': response.json()['csrf']}


def save(client, headers, completed, revision=0, collapsed=False, team_id='72450'):
    return client.post('/api/workbench/starter/' + team_id, headers=headers, json={
        'expected_revision': revision, 'completed': completed, 'collapsed': collapsed,
    })


def test_starter_requires_authentication_for_reads_and_writes(app):
    with TestClient(app) as client:
        assert client.get('/api/workbench/starter/72450').status_code == 401
        assert save(client, {}, []).status_code == 401


def test_starter_requires_csrf_and_does_not_write_after_rejection(app):
    with TestClient(app) as client:
        headers = login(client)
        assert save(client, {}, ['mentor']).status_code == 403
        assert save(client, {'X-CSRF-Token': 'invalid'}, ['mentor']).status_code == 403
        assert client.get('/api/workbench/starter/72450', headers=headers).json()['revision'] == 0


@pytest.mark.parametrize('headers', [{}, {'X-CSRF-Token': 'obsolete'}])
def test_starter_read_requires_proof_of_the_browser_tab_session(app, headers):
    with TestClient(app) as client:
        current = login(client)
        saved = save(client, current, ['mentor'])
        assert saved.status_code == 200, saved.text
        response = client.get('/api/workbench/starter/72450', headers=headers)
        assert response.status_code == 403
        assert 'completed' not in response.json()
        assert client.get('/api/workbench/starter/72450', headers=current).json() == saved.json()


def test_starter_read_rejects_old_tab_token_after_cookie_switch_to_another_manager(app):
    with TestClient(app) as client:
        first = login(client)
        created = client.post('/api/admin/users', headers=first,
                              json={'username': 'alice', 'password': 'Another-password-5678'})
        assert created.status_code == 200, created.text
        assert save(client, first, ['mentor']).status_code == 200

        # A second browser tab logs in; its cookie replaces the first tab's cookie.
        current = login(client, 'alice', 'Another-password-5678')
        created = client.post('/api/teams', headers=current,
                              json={'team_id': '72450', 'name': 'Private club', 'country': 'FR'})
        assert created.status_code == 200, created.text
        saved = save(client, current, ['stadium'])
        assert saved.status_code == 200, saved.text

        stale = client.get('/api/workbench/starter/72450', headers=first)
        assert stale.status_code == 403
        assert 'completed' not in stale.json()
        assert client.get('/api/workbench/starter/72450', headers=current).json() == saved.json()


def test_starter_defaults_are_unsaved_declarations(app):
    with TestClient(app) as client:
        headers = login(client)
        response = client.get('/api/workbench/starter/72450', headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {
            'team_id': '72450', 'revision': 0, 'updated_at': None,
            'completed': [], 'collapsed': False,
        }
        assert 'workbench:starter:72450' not in client.get('/api/export').json()['manager_documents']


def test_starter_rejects_unknown_clubs_for_reads_and_writes(app):
    with TestClient(app) as client:
        headers = login(client)
        assert client.get('/api/workbench/starter/9999999', headers=headers).status_code == 404
        assert save(client, headers, ['mentor'], team_id='9999999').status_code == 404
        assert 'workbench:starter:9999999' not in client.get('/api/export').json()['manager_documents']


@pytest.mark.parametrize('team_id', ['bad', '0', '1234567890123456'])
def test_starter_rejects_invalid_club_identifiers(app, team_id):
    with TestClient(app) as client:
        headers = login(client)
        assert client.get('/api/workbench/starter/' + team_id, headers=headers).status_code == 422
        assert save(client, headers, [], team_id=team_id).status_code == 422


def test_starter_roundtrips_all_stages_and_allows_unchecking(app):
    completed = ['mentor', 'treasury', 'transfers', 'staff', 'stadium', 'economy', 'lineup']
    with TestClient(app) as client:
        headers = login(client)
        response = save(client, headers, completed, collapsed=True)
        assert response.status_code == 200, response.text
        document = response.json()
        assert set(document) == {'team_id', 'revision', 'updated_at', 'completed', 'collapsed'}
        assert document['team_id'] == '72450'
        assert document['revision'] == 1
        assert document['completed'] == completed
        assert document['collapsed'] is True
        assert datetime.fromisoformat(document['updated_at']).tzinfo is not None
        assert client.get('/api/workbench/starter/72450', headers=headers).json() == document
        cleared = save(client, headers, [], revision=1)
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()['revision'] == 2
        assert cleared.json()['completed'] == []
        assert cleared.json()['collapsed'] is False


@pytest.mark.parametrize('changes', [
    {'completed': ['unknown']}, {'completed': ['mentor', 'mentor']},
    {'completed': [1]}, {'completed': 'mentor'}, {'completed': None},
    {'collapsed': 'true'}, {'collapsed': 1}, {'collapsed': None},
    {'expected_revision': -1}, {'expected_revision': 2147483648},
    {'expected_revision': True}, {'expected_revision': '0'},
    {'user_id': 'primary'}, {'team_id': '9999999'},
])
def test_starter_rejects_invalid_documents_without_changes(app, changes):
    with TestClient(app) as client:
        headers = login(client)
        body = {'expected_revision': 0, 'completed': [], 'collapsed': False, **changes}
        assert client.post('/api/workbench/starter/72450', headers=headers, json=body).status_code == 422
        document = client.get('/api/workbench/starter/72450', headers=headers).json()
        assert document['revision'] == 0
        assert document['completed'] == []


@pytest.mark.parametrize('missing', ['expected_revision', 'completed', 'collapsed'])
def test_starter_requires_complete_save_payload(app, missing):
    with TestClient(app) as client:
        headers = login(client)
        body = {'expected_revision': 0, 'completed': [], 'collapsed': False}
        del body[missing]
        assert client.post('/api/workbench/starter/72450', headers=headers, json=body).status_code == 422


def test_starter_stale_revision_preserves_current_declarations(app):
    with TestClient(app) as client:
        headers = login(client)
        first = save(client, headers, ['mentor'], collapsed=True)
        assert first.status_code == 200, first.text
        assert save(client, headers, ['stadium']).status_code == 409
        assert client.get('/api/workbench/starter/72450', headers=headers).json() == first.json()


def test_starter_concurrent_writers_only_commit_one_revision(app):
    with TestClient(app) as first, TestClient(app) as second:
        h1, h2 = login(first), login(second)
        ready = Barrier(2)

        def competing_save(client, headers, stage):
            ready.wait(timeout=10)
            return save(client, headers, [stage])

        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(competing_save, first, h1, 'mentor'),
                    pool.submit(competing_save, second, h2, 'stadium')]
            responses = [job.result() for job in jobs]
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(response.json() for response in responses if response.status_code == 200)
        assert winner['revision'] == 1
        assert first.get('/api/workbench/starter/72450', headers=h1).json() == winner


def test_starter_separates_clubs_in_one_manager_workspace(app):
    with TestClient(app) as client:
        headers = login(client)
        created = client.post('/api/teams', headers=headers,
                              json={'team_id': '81234', 'name': 'Second club', 'country': 'FR'})
        assert created.status_code == 200, created.text
        assert save(client, headers, ['mentor']).status_code == 200
        second = client.get('/api/workbench/starter/81234', headers=headers).json()
        assert second['completed'] == []
        assert second['revision'] == 0
        assert second['team_id'] == '81234'
        assert save(client, headers, ['stadium'], team_id='81234').status_code == 200
        assert client.get('/api/workbench/starter/72450', headers=headers).json()['completed'] == ['mentor']


def test_starter_same_club_is_private_between_managers_and_in_exports(app):
    with TestClient(app) as first, TestClient(app) as other:
        h1 = login(first)
        created = first.post('/api/admin/users', headers=h1,
                             json={'username': 'alice', 'password': 'Another-password-5678'})
        assert created.status_code == 200, created.text
        h2 = login(other, 'alice', 'Another-password-5678')
        assert other.get('/api/workbench/starter/72450', headers=h2).status_code == 404
        created = other.post('/api/teams', headers=h2,
                             json={'team_id': '72450', 'name': 'Private club', 'country': 'FR'})
        assert created.status_code == 200, created.text
        saved = save(first, h1, ['mentor'], collapsed=True)
        assert saved.status_code == 200, saved.text
        assert other.get('/api/workbench/starter/72450', headers=h2).json()['completed'] == []
        assert 'workbench:starter:72450' not in other.get('/api/export').json()['manager_documents']
        other_saved = save(other, h2, ['stadium'])
        assert other_saved.status_code == 200, other_saved.text
        assert first.get('/api/workbench/starter/72450', headers=h1).json() == saved.json()
        assert first.get('/api/export').json()['manager_documents']['workbench:starter:72450'] == saved.json()
        assert other.get('/api/export').json()['manager_documents']['workbench:starter:72450'] == other_saved.json()
