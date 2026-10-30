"""Private profile behavior through the real session and per-manager store."""
import importlib.util
import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


def profile_app(directory):
    app = create_app(directory, 'Testing-password-1234', secure=False)
    # Keep this module testable while main.py integration is being coordinated.
    if not any(getattr(route, 'path', '') == '/api/profile' for route in app.routes):
        if importlib.util.find_spec('server.profile'):
            from server.profile import register_profile
            state = next(route for route in app.routes if getattr(route, 'path', '') == '/api/state')
            store = inspect.getclosurevars(state.endpoint).nonlocals['store']
            register_profile(app, store, state.dependant.dependencies[0].call)
            app.router.routes.sort(key=lambda route: getattr(route, 'path', '') == '/{path:path}')
    return app


@pytest.fixture
def app(tmp_path):
    return profile_app(tmp_path)


def login(client, username='piwig', password='Testing-password-1234'):
    response = client.post('/api/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def save(client, headers, profile=None, revision=0, **extra):
    return client.post('/api/profile', headers=headers, json={
        'expected_revision': revision, 'profile': profile or {}, **extra})


def test_profile_requires_authentication_and_csrf(app):
    with TestClient(app) as client:
        assert client.get('/api/profile').status_code == 401
        assert save(client, {}).status_code == 401
        headers = login(client)
        assert client.get('/api/profile').status_code == 200
        assert save(client, {}).status_code == 403
        assert save(client, {'X-CSRF-Token': 'wrong'}).status_code == 403
        assert save(client, headers).status_code == 200
        client.post('/api/logout', headers=headers)
        assert client.get('/api/profile').status_code == 401


def test_profile_defaults_and_normalized_roundtrip(app):
    with TestClient(app) as client:
        headers = login(client)
        initial = client.get('/api/profile').json()
        assert initial['revision'] == 0
        assert initial['updated_at'] is None
        assert initial['profile']['dashboard_sections'] == ['priorities', 'metrics', 'progress', 'talents', 'actions', 'gallery']
        assert initial['profile']['density'] == 'comfortable'
        response = save(client, headers, {'display_name': '  Cécile du XV  ', 'initials': ' cé ',
            'jersey_number': 0, 'favorite_club': 'toulouse', 'density': 'compact',
            'text_size': 'large', 'motion': 'reduced', 'start_page': 'progression',
            'banner': 'clubhouse', 'dashboard_sections': ['progress', 'priorities']})
        assert response.status_code == 200, response.text
        document = response.json()
        assert document['revision'] == 1 and document['updated_at']
        assert document['profile']['display_name'] == 'Cécile du XV'
        assert document['profile']['initials'] == 'CÉ'
        assert document['profile']['jersey_number'] == 0
        assert document['profile']['dashboard_sections'] == ['progress', 'priorities']
        assert client.get('/api/profile').json() == document


def test_profiles_are_manager_private_even_before_adding_a_club(app):
    with TestClient(app) as admin, TestClient(app) as other:
        ah = login(admin)
        created = admin.post('/api/admin/users', headers=ah, json={
            'username': 'alice', 'password': 'Another-password-5678'})
        assert created.status_code == 200
        oh = login(other, 'alice', 'Another-password-5678')
        assert other.get('/api/state').json()['setup_required'] is True
        assert save(admin, ah, {'display_name': 'Private admin', 'initials': 'PA'}).status_code == 200
        before = other.get('/api/profile').json()
        assert before['revision'] == 0 and before['profile']['display_name'] == ''
        assert save(other, oh, {'display_name': 'Private Alice', 'initials': 'AL'}).status_code == 200
        assert admin.get('/api/profile').json()['profile']['display_name'] == 'Private admin'
        assert other.get('/api/profile').json()['profile']['display_name'] == 'Private Alice'
        assert save(other, oh, {'display_name': 'Other manager'}, revision=1, user_id='primary').status_code == 422


def test_stale_revision_does_not_overwrite_saved_profile(app):
    with TestClient(app) as client:
        headers = login(client)
        assert save(client, headers, {'display_name': 'First'}).status_code == 200
        stale = save(client, headers, {'display_name': 'Lost draft'})
        assert stale.status_code == 409
        assert client.get('/api/profile').json()['profile']['display_name'] == 'First'
        updated = save(client, headers, {'display_name': 'Second', 'dashboard_sections': []}, revision=1)
        assert updated.status_code == 200
        assert updated.json()['revision'] == 2
        assert updated.json()['profile']['dashboard_sections'] == []


def test_concurrent_profile_writers_cannot_both_win(app):
    with TestClient(app) as first, TestClient(app) as second:
        fh, sh = login(first), login(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda item: save(*item), [
                (first, fh, {'display_name': 'First writer'}),
                (second, sh, {'display_name': 'Second writer'})]))
        assert sorted(response.status_code for response in results) == [200, 409]
        winner = next(response.json() for response in results if response.status_code == 200)
        assert first.get('/api/profile').json() == winner


@pytest.mark.parametrize('profile', [
    {'display_name': 'x' * 61}, {'display_name': '<svg onload=alert(1)>'},
    {'display_name': 'A\x00B'}, {'display_name': 'A\u202eB'},
    {'initials': ''}, {'initials': 'ABCD'}, {'initials': '<x>'},
    {'jersey_number': -1}, {'jersey_number': 100}, {'jersey_number': True},
    {'jersey_number': 1.5}, {'jersey_number': '12'},
    {'favorite_club': 'https://example.test/logo.svg'}, {'favorite_club': 'unknown'},
    {'density': 'tiny'}, {'text_size': 'huge'}, {'motion': 'always'},
    {'start_page': 'admin'}, {'banner': 'https://example.test/image.png'},
    {'dashboard_sections': ['metrics', 'metrics']}, {'dashboard_sections': ['password']},
    {'avatar_url': 'https://example.test/logo.png'}, {'team_id': '72450'},
])
def test_invalid_profile_fields_are_rejected_without_writing(app, profile):
    with TestClient(app) as client:
        headers = login(client)
        response = save(client, headers, profile)
        assert response.status_code == 422, response.text
        assert client.get('/api/profile').json()['revision'] == 0


@pytest.mark.parametrize('revision', [-1, True, 1.1, '0', 2147483648])
def test_profile_revision_must_be_a_bounded_integer(app, revision):
    with TestClient(app) as client:
        headers = login(client)
        assert save(client, headers, revision=revision).status_code == 422


def test_profile_persists_after_reopening_application(tmp_path):
    with TestClient(profile_app(tmp_path)) as client:
        headers = login(client)
        response = save(client, headers, {'display_name': 'Persisted', 'jersey_number': 99})
        assert response.status_code == 200
        saved = response.json()
    with TestClient(profile_app(tmp_path)) as reopened:
        login(reopened)
        assert reopened.get('/api/profile').json() == saved
