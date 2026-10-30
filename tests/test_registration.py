"""Public registration creates only a usable, isolated manager account."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.profile import PROFILE_KEY, get_profile


PASSWORD = '  Registration-password-1234  '


def registration_app(directory, secure=False):
    app = create_app(directory, 'Testing-password-1234', secure=secure)
    if not any(getattr(route, 'path', '') == '/api/register' for route in app.routes):
        if importlib.util.find_spec('server.registration'):
            from server.registration import register_registration
            state = next(route for route in app.routes if getattr(route, 'path', '') == '/api/state')
            register_registration(app, app.state.accounts, state.dependant.dependencies[0].call, secure)
            app.router.routes.sort(key=lambda route: getattr(route, 'path', '') == '/{path:path}')
    return app


def payload(**changes):
    return {'username': 'alice', 'password': PASSWORD, 'email': 'Alice+brt@example.org', **changes}


def test_signup_connects_to_empty_nonadmin_space_and_preserves_password(tmp_path):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/registration/options').json()['enabled'] is True
        response = client.post('/api/register', json=payload(avatar_style='trophy'))
        assert response.status_code == 200, response.text
        assert response.json()['csrf']
        cookie = response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie
        state = client.get('/api/state').json()
        assert state['user']['username'] == 'alice'
        assert state['user']['admin'] is False and state['setup_required'] is True
        assert state['teams'] == []
        assert client.get('/api/admin/users').status_code == 403
        assert client.get('/api/history/72450/42').status_code == 404
        assert client.get('/api/profile').json()['profile']['avatar_style'] == 'trophy'
        assert client.get('/api/account/contact').json()['email'] == 'Alice+brt@example.org'
        assert 'Alice+brt@example.org' not in str(app.state.accounts.list_users())
        client.cookies.clear()
        assert client.get('/api/account/contact').status_code == 401
        assert client.post('/api/login', json={'username': 'alice', 'password': PASSWORD.strip()}).status_code == 401
        assert client.post('/api/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 200


def test_contact_is_only_readable_for_current_manager_and_legacy_accounts_work(tmp_path):
    app = registration_app(tmp_path)
    legacy = app.state.accounts.create('legacy', 'Legacy-password-1234')
    with TestClient(app) as first, TestClient(app) as second:
        assert first.post('/api/register', json=payload()).status_code == 200
        assert second.post('/api/login', json={'username': 'legacy', 'password': 'Legacy-password-1234'}).status_code == 200
        assert second.get('/api/account/contact?user_id=' + app.state.accounts.user('alice')['id']).json()['email'] is None
        assert get_profile(app.state.accounts.store(legacy['id']))['profile']['avatar_style'] == 'jersey'
        assert app.state.accounts.get_contact(legacy['id']) is None
        assert app.state.accounts.get_contact(app.state.accounts.user('alice')['id'])['email'] == 'Alice+brt@example.org'


@pytest.mark.parametrize('changes', [
    {'username': 'ab'}, {'username': 'x' * 41}, {'username': '../alice'},
    {'password': 'short'}, {'password': 'x' * 129}, {'password': 123456789012},
    {'email': ''}, {'email': 'name'}, {'email': 'a@@b.example'},
    {'email': 'a..b@example.org'}, {'email': 'a@-example.org'},
    {'email': 'a@example..org'}, {'email': 'a@x'}, {'email': 'a\n@example.org'},
    {'email': 'a@example.org\n'}, {'email': 'a@example.org\r\n'},
    {'email': '\ta@example.org'}, {'email': 'a\u202e@example.org'},
    {'email': 'a' * 65 + '@example.org'}, {'email': 'a@' + 'x' * 250 + '.org'},
    {'avatar_style': 'https://example.org/avatar.svg'}, {'avatar_style': '<svg>'},
    {'admin': True}, {'user_id': 'primary'}, {'profile': {'admin': True}},
])
def test_invalid_registration_has_no_account_or_private_directory(tmp_path, changes):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        response = client.post('/api/register', json=payload(**changes))
        assert response.status_code == 422, response.text
        assert len(app.state.accounts.list_users()) == 1
        assert not (tmp_path / 'users').exists()
        assert PASSWORD not in response.text


def test_honeypot_and_foreign_origin_reject_without_creating_account(tmp_path):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/register', json=payload(website='https://spam.test')).status_code == 422
        assert client.post('/api/register', headers={'Origin': 'https://foreign.test'}, json=payload()).status_code == 403
        assert app.state.accounts.user('alice') is None
        assert not (tmp_path / 'users').exists()


def test_case_insensitive_duplicate_returns_conflict_without_another_store(tmp_path):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/register', json=payload()).status_code == 200
        client.cookies.clear()
        assert client.post('/api/register', json=payload(username='ALICE')).status_code == 409
        assert len(list((tmp_path / 'users').iterdir())) == 1


def test_concurrent_duplicate_has_one_winner_and_one_private_store(tmp_path):
    app = registration_app(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda c: c.post('/api/register', json=payload()), [first, second]))
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert len(list((tmp_path / 'users').iterdir())) == 1
        winner = first if responses[0].status_code == 200 else second
        assert winner.get('/api/state').json()['teams'] == []


def test_existing_session_cannot_be_replaced_by_registration(tmp_path):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'}).status_code == 200
        assert client.post('/api/register', json=payload()).status_code == 409
        assert client.get('/api/state').json()['user']['username'] == 'piwig'
        assert app.state.accounts.user('alice') is None


def test_concurrent_abuse_cannot_exceed_persisted_ip_limit(tmp_path):
    app = registration_app(tmp_path)
    def submit(_):
        with TestClient(app) as client:
            return client.post('/api/register', json=payload(website='filled')).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(submit, range(8)))
    assert sorted(statuses) == [422] * 5 + [429] * 3
    assert not (tmp_path / 'users').exists()


def test_rate_limit_is_persistent_before_hash_and_private_store(tmp_path, monkeypatch):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        for i in range(5):
            # Honeypots consume attempts without creating identities or computing hashes.
            assert client.post('/api/register', json=payload(username='bot' + str(i), website='filled')).status_code == 422
    reopened = registration_app(tmp_path)
    def forbidden_hash(*args, **kwargs):
        pytest.fail('A blocked registration must never hash a password.')
    monkeypatch.setattr('server.accounts.password_hash', forbidden_hash)
    with TestClient(reopened) as client:
        response = client.post('/api/register', headers={'X-Forwarded-For': '192.0.2.77'}, json=payload())
        assert response.status_code == 429
        assert response.headers.get('retry-after')
        assert not (tmp_path / 'users').exists()


def test_global_limit_applies_across_addresses(tmp_path):
    app = registration_app(tmp_path)
    for i in range(50):
        with TestClient(app, client=('192.0.2.' + str(i + 1), 5000)) as client:
            assert client.post('/api/register', json=payload(website='filled')).status_code == 422
    with TestClient(app, client=('198.51.100.1', 5000)) as client:
        assert client.post('/api/register', json=payload()).status_code == 429
    assert not (tmp_path / 'users').exists()


def test_expired_limit_releases_registration_and_normalizes_domain(tmp_path):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        for _ in range(5):
            assert client.post('/api/register', json=payload(website='filled')).status_code == 422
        with app.state.accounts.db() as db:
            db.execute('UPDATE registration_attempts SET attempted_at=attempted_at-3601')
        response = client.post('/api/register', json=payload(email=' Alice+brt@EXAMPLE.ORG '))
        assert response.status_code == 200
        assert client.get('/api/account/contact').json()['email'] == 'Alice+brt@example.org'


def test_session_failure_explains_created_account_and_login_remains_possible(tmp_path, monkeypatch):
    import sqlite3
    app = registration_app(tmp_path)
    def session_unavailable(user_id):
        raise sqlite3.OperationalError('Simulated session failure')
    with TestClient(app) as client:
        with monkeypatch.context() as patch:
            patch.setattr(app.state.accounts, 'start_session', session_unavailable)
            response = client.post('/api/register', json=payload())
        assert response.status_code == 503
        assert 'compte a été créé' in response.json()['detail']
        assert client.post('/api/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 200
        assert client.get('/api/state').json()['teams'] == []
        assert client.get('/api/account/contact').json()['email'] == 'Alice+brt@example.org'


def test_failed_store_initialization_rolls_back_account_contact_and_directory(tmp_path, monkeypatch):
    app = registration_app(tmp_path)
    from server.storage import Store
    class BrokenStore(Store):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            raise OSError('Simulated disk failure')
    with monkeypatch.context() as patch:
        patch.setattr('server.accounts.Store', BrokenStore)
        with TestClient(app) as client:
            assert client.post('/api/register', json=payload()).status_code == 503
    assert app.state.accounts.user('alice') is None
    assert not list((tmp_path / 'users').iterdir())
    with app.state.accounts.db() as db:
        assert db.execute('SELECT count(*) FROM user_contacts').fetchone()[0] == 0
    with TestClient(app) as client:
        assert client.post('/api/register', json=payload()).status_code == 200


def test_existing_profile_gets_avatar_default_without_losing_saved_fields(tmp_path):
    app = registration_app(tmp_path)
    store = app.state.store
    store.set(PROFILE_KEY, {'revision': 7, 'profile': {'display_name': 'Existing manager', 'density': 'compact'}, 'updated_at': '2026-10-01'})
    document = get_profile(store)
    assert document['profile']['avatar_style'] == 'jersey'
    assert document['profile']['display_name'] == 'Existing manager'
    assert document['profile']['density'] == 'compact'
    assert document['revision'] == 7


@pytest.mark.parametrize('style', ['jersey', 'shield', 'trophy', 'rugby'])
def test_avatar_styles_survive_restart(tmp_path, style):
    app = registration_app(tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/register', json=payload(avatar_style=style)).status_code == 200
    with TestClient(registration_app(tmp_path)) as client:
        assert client.post('/api/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 200
        assert client.get('/api/profile').json()['profile']['avatar_style'] == style


def test_signup_can_be_disabled_and_secure_cookie_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv('BRT_REGISTRATION_ENABLED', '0')
    with TestClient(registration_app(tmp_path)) as client:
        assert client.get('/api/registration/options').json()['enabled'] is False
        assert client.post('/api/register', json=payload()).status_code == 403
    monkeypatch.setenv('BRT_REGISTRATION_ENABLED', '1')
    with TestClient(registration_app(tmp_path, secure=True), base_url='https://testserver') as client:
        response = client.post('/api/register', json=payload())
        assert response.status_code == 200
        assert '; secure' in response.headers['set-cookie'].lower()
