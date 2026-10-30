"""Server-side CAPTCHA gates writes, using a fake provider transport only."""
import importlib.util
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from server.main import create_app


def app_with_captcha(tmp_path, monkeypatch, *, enabled=True, secure=False):
    for name in ('BRT_CONTACT_TO', 'BRT_SMTP_HOST', 'BRT_SMTP_PORT',
                 'BRT_SMTP_USER', 'BRT_SMTP_PASSWORD', 'BRT_SMTP_FROM'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED', '1' if enabled else '0')
    monkeypatch.setenv('BRT_TURNSTILE_SITE_KEY', 'synthetic-public-site-key')
    monkeypatch.setenv('BRT_TURNSTILE_SECRET_KEY', 'synthetic-private-secret')
    monkeypatch.setenv('BRT_PUBLIC_URL', 'https://brt.example.test')
    app = create_app(tmp_path, 'Testing-password-1234', secure=secure)
    if not any(getattr(route, 'path', '') == '/api/security/options' for route in app.routes):
        if importlib.util.find_spec('server.antibot'):
            from server.antibot import register_antibot
            register_antibot(app, 'https://brt.example.test', secure)
            app.router.routes.sort(key=lambda route: getattr(route, 'path', '') == '/{path:path}')
    return app


def signup(**changes):
    return {'username': 'alice', 'password': 'Registration-password-1234',
            'email': 'alice@example.test', 'captcha_token': 'synthetic-token', **changes}


def contact(**changes):
    return {'kind': 'bug', 'subject': 'Test contact', 'message': 'Un message volontaire.',
            'email': 'alice@example.test', 'captcha_token': 'synthetic-token', **changes}


def provider(monkeypatch, handler):
    import server.antibot as antibot
    real_client = httpx.Client
    calls = []
    def wrapped(request):
        calls.append(request)
        return handler(request)
    def factory(**kwargs):
        assert kwargs['timeout'] == 8
        assert kwargs['follow_redirects'] is False
        return real_client(transport=httpx.MockTransport(wrapped), **kwargs)
    monkeypatch.setattr(antibot.httpx, 'Client', factory)
    return calls


def accepted(action='register', **changes):
    return httpx.Response(200, json={'success': True, 'hostname': 'brt.example.test', 'action': action, **changes})


def test_enabled_signup_requires_captcha_before_creating_account(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post('/api/register', json=signup(captcha_token=''))
        assert response.status_code == 403
        assert app.state.accounts.user('alice') is None
        assert not (tmp_path / 'users').exists()


def test_expired_contact_session_is_not_silently_converted_to_public_message(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch, enabled=False)
    with TestClient(app) as client:
        login = client.post('/api/login', json={'username': 'piwig', 'password': 'Testing-password-1234'})
        headers = {'X-CSRF-Token': login.json()['csrf']}
        with app.state.accounts.db() as db:
            db.execute('DELETE FROM sessions')
        body = contact()
        body.pop('captcha_token')
        assert client.post('/api/contact', json=body, headers=headers).status_code == 401
        with app.state.accounts.db() as db:
            assert db.execute('SELECT count(*) FROM contact_tickets').fetchone()[0] == 0


def test_public_options_never_disclose_secret(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch)
    with TestClient(app) as client:
        result = client.get('/api/security/options')
        assert result.json() == {'enabled': True, 'site_key': 'synthetic-public-site-key'}
        assert 'synthetic-private-secret' not in result.text


def test_valid_provider_response_creates_account_and_binds_server_action(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch)
    calls = provider(monkeypatch, lambda request: accepted())
    with TestClient(app) as client:
        response = client.post('/api/register', json=signup())
        assert response.status_code == 200
        assert client.get('/api/state').json()['user']['username'] == 'alice'
    assert len(calls) == 1
    assert str(calls[0].url) == 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    assert calls[0].method == 'POST'
    assert parse_qs(calls[0].content.decode()) == {
        'secret': ['synthetic-private-secret'], 'response': ['synthetic-token']}


@pytest.mark.parametrize('changes', [
    {'success': False}, {'success': 1}, {'success': 'true'},
    {'hostname': 'other.example.test'}, {'hostname': None}, {'hostname': ''},
    {'action': 'login'}, {'action': 'contact'}, {'action': None},
])
def test_provider_mismatch_rejects_before_account_or_store(tmp_path, monkeypatch, changes):
    app = app_with_captcha(tmp_path, monkeypatch)
    provider(monkeypatch, lambda request: accepted(**changes))
    with TestClient(app) as client:
        response = client.post('/api/register', json=signup())
        assert response.status_code == 403
        assert 'synthetic' not in response.text
    assert app.state.accounts.user('alice') is None
    assert not (tmp_path / 'users').exists()


@pytest.mark.parametrize('response', [
    httpx.Response(503), httpx.Response(302, headers={'location': 'https://other.test'}),
    httpx.Response(200, text='not json'), httpx.Response(200, json=[]),
    httpx.Response(200, content=b'x' * 20000),
])
def test_provider_unavailable_is_generic_and_never_retries(tmp_path, monkeypatch, response):
    app = app_with_captcha(tmp_path, monkeypatch)
    calls = provider(monkeypatch, lambda request: response)
    with TestClient(app) as client:
        result = client.post('/api/register', json=signup())
        assert result.status_code == 503
        assert 'synthetic' not in result.text
    assert len(calls) == 1
    assert app.state.accounts.user('alice') is None


def test_provider_timeout_keeps_secrets_out_of_error_and_does_not_retry(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch)
    def timeout(request):
        raise httpx.ReadTimeout('synthetic-private-secret synthetic-token', request=request)
    calls = provider(monkeypatch, timeout)
    with TestClient(app) as client:
        result = client.post('/api/contact', json=contact())
        assert result.status_code == 503 and 'synthetic' not in result.text
    assert len(calls) == 1
    with app.state.accounts.db() as db:
        assert db.execute('SELECT count(*) FROM contact_tickets').fetchone()[0] == 0


def test_rate_limit_is_consumed_before_provider_and_replayed_token_is_rejected(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch)
    used = set()
    def upstream(request):
        token = parse_qs(request.content.decode())['response'][0]
        if token in used:
            return httpx.Response(200, json={'success': False, 'error-codes': ['timeout-or-duplicate']})
        used.add(token)
        return accepted('contact')
    calls = provider(monkeypatch, upstream)
    with TestClient(app) as client:
        assert client.post('/api/contact', json=contact()).status_code == 200
        for _ in range(4):
            assert client.post('/api/contact', json=contact()).status_code == 403
        assert client.post('/api/contact', json=contact(captcha_token='new-token')).status_code == 429
    assert len(calls) == 5
    with app.state.accounts.db() as db:
        assert db.execute('SELECT count(*) FROM contact_tickets').fetchone()[0] == 1


@pytest.mark.parametrize('token', ['x' * 2049, 123, ['token']])
def test_token_must_be_bounded_string(tmp_path, monkeypatch, token):
    app = app_with_captcha(tmp_path, monkeypatch)
    def forbidden(request):
        pytest.fail('Invalid token must never reach provider.')
    provider(monkeypatch, forbidden)
    with TestClient(app) as client:
        assert client.post('/api/register', json=signup(captcha_token=token)).status_code == 422


def test_registration_quota_blocks_before_another_provider_call(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch)
    calls = provider(monkeypatch, lambda request: accepted(success=False))
    with TestClient(app) as client:
        for _ in range(5):
            assert client.post('/api/register', json=signup()).status_code == 403
        assert client.post('/api/register', json=signup()).status_code == 429
    assert len(calls) == 5
    assert not (tmp_path / 'users').exists()


@pytest.mark.parametrize('setting,value', [
    ('BRT_TURNSTILE_SECRET_KEY', ''), ('BRT_TURNSTILE_SITE_KEY', ''),
    ('BRT_TURNSTILE_SITE_KEY', '1x00000000000000000000AA'),
    ('BRT_TURNSTILE_SITE_KEY', '1x00000000000000000000BB'),
    ('BRT_TURNSTILE_SITE_KEY', '2x00000000000000000000AB'),
    ('BRT_TURNSTILE_SITE_KEY', '2x00000000000000000000BB'),
    ('BRT_TURNSTILE_SITE_KEY', '3x00000000000000000000FF'),
    ('BRT_TURNSTILE_SECRET_KEY', '1x0000000000000000000000000000000AA'),
    ('BRT_TURNSTILE_SECRET_KEY', '2x0000000000000000000000000000000AA'),
    ('BRT_TURNSTILE_SECRET_KEY', '3x0000000000000000000000000000000AA'),
])
def test_incomplete_or_test_config_fails_closed_in_production(tmp_path, monkeypatch, setting, value):
    app = app_with_captcha(tmp_path, monkeypatch, secure=True)
    monkeypatch.setenv(setting, value)
    from server.antibot import register_antibot
    register_antibot(app, 'https://brt.example.test', True)
    def forbidden(request):
        pytest.fail('Invalid production config must not make network request.')
    provider(monkeypatch, forbidden)
    with TestClient(app, base_url='https://brt.example.test') as client:
        options = client.get('/api/security/options').json()
        assert options['enabled'] is True
        assert client.post('/api/register', json=signup()).status_code == 503


def test_disabled_configuration_does_not_contact_cloudflare(tmp_path, monkeypatch):
    app = app_with_captcha(tmp_path, monkeypatch, enabled=False)
    def forbidden(request):
        pytest.fail('Disabled CAPTCHA must not contact provider.')
    provider(monkeypatch, forbidden)
    with TestClient(app) as client:
        assert client.get('/api/security/options').json() == {'enabled': False, 'site_key': ''}
        assert client.post('/api/register', json=signup(captcha_token='')).status_code == 200
