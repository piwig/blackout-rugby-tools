"""Every application API requires an account, including future route additions."""
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from server.main import create_app


PASSWORD = 'Testing-password-1234'
PUBLIC_URL = 'https://brt.example.test'
PUBLIC_REQUESTS = {
    ('GET', '/api/health'), ('GET', '/api/security/options'),
    ('GET', '/api/registration/options'), ('POST', '/api/login'),
    ('POST', '/api/register'),
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ('BRT_CONTACT_TO', 'BRT_SMTP_HOST', 'BRT_SMTP_PORT',
                 'BRT_SMTP_USER', 'BRT_SMTP_PASSWORD', 'BRT_SMTP_FROM'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('BRT_PUBLIC_URL', PUBLIC_URL)
    monkeypatch.setenv('BRT_REGISTRATION_ENABLED', '1')
    monkeypatch.setenv('BRT_TURNSTILE_ENABLED', '1')
    monkeypatch.setenv('BRT_TURNSTILE_SITE_KEY', 'synthetic-site-key')
    monkeypatch.setenv('BRT_TURNSTILE_SECRET_KEY', 'synthetic-private-key')
    application = create_app(tmp_path, PASSWORD, secure=True)
    calls = []
    real_client = httpx.Client

    def upstream(request):
        token = parse_qs(request.content.decode())['response'][0]
        calls.append(token)
        return httpx.Response(200, json={
            'success': True, 'hostname': 'brt.example.test',
            'action': {'login-token': 'login', 'register-token': 'register',
                       'contact-token': 'contact'}.get(token, 'invalid'),
        })

    monkeypatch.setattr('server.antibot.httpx.Client',
                        lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))

    mail_calls = []

    def forbidden_mail(*args, **kwargs):
        mail_calls.append('attempted')
        raise OSError('SMTP disabled in tests.')

    monkeypatch.setattr('server.contact.smtplib.SMTP', forbidden_mail)
    monkeypatch.setattr('server.contact.smtplib.SMTP_SSL', forbidden_mail)
    application.state.provider_calls = calls
    application.state.mail_calls = mail_calls
    return application


def contact_payload():
    return {'kind': 'bug', 'subject': 'Calendrier', 'message': 'Une date à vérifier.',
            'email': 'manager@example.test', 'captcha_token': 'contact-token'}


def login(client, username='piwig'):
    response = client.post('/api/login', json={
        'username': username, 'password': PASSWORD, 'captcha_token': 'login-token'})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def assert_no_contact_side_effects(app):
    with app.state.accounts.db() as db:
        assert db.execute('SELECT count(*) FROM contact_tickets').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM contact_attempts').fetchone()[0] == 0


@pytest.mark.parametrize('headers', [{}, {'X-CSRF-Token': 'untrusted-token'}])
def test_anonymous_contact_is_rejected_before_captcha_quota_or_mail(app, monkeypatch, headers):
    monkeypatch.setenv('BRT_CONTACT_TO', 'owner@example.test')
    monkeypatch.setenv('BRT_SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('BRT_SMTP_PORT', '587')
    monkeypatch.setenv('BRT_SMTP_FROM', 'tools@example.test')
    with TestClient(app, base_url=PUBLIC_URL) as client:
        result = client.post('/api/contact', json=contact_payload(), headers=headers)
        assert result.status_code == 401
        assert result.headers['cache-control'] == 'no-store'
        assert result.headers['x-content-type-options'] == 'nosniff'
    assert app.state.provider_calls == []
    assert app.state.mail_calls == []
    assert_no_contact_side_effects(app)


def test_every_registered_business_route_rejects_anonymous_requests(app):
    with TestClient(app, base_url=PUBLIC_URL) as client:
        for route in app.routes:
            path = getattr(route, 'path', '')
            if not path.startswith('/api/'):
                continue
            for method in route.methods:
                if (method, path) not in PUBLIC_REQUESTS:
                    response = client.request(method, path, json={})
                    assert response.status_code == 401, (method, path, response.status_code)
    assert app.state.provider_calls == []
    assert_no_contact_side_effects(app)


def test_future_route_is_private_by_default_and_requires_csrf_for_writes(app):
    saved = []

    @app.post('/api/future-feature')
    def future_feature():
        saved.append('saved')
        return {'ok': True}

    with TestClient(app, base_url=PUBLIC_URL) as client:
        assert client.post('/api/future-feature').status_code == 401
        headers = login(client)
        assert client.post('/api/future-feature').status_code == 403
        assert client.post('/api/future-feature', headers={'X-CSRF-Token': 'wrong'}).status_code == 403
        assert saved == []
        assert client.post('/api/future-feature', headers=headers).json() == {'ok': True}
        assert saved == ['saved']


@pytest.mark.parametrize('method,path', [
    ('POST', '/api/health'), ('POST', '/api/security/options'),
    ('POST', '/api/registration/options'), ('GET', '/api/login'),
    ('GET', '/api/register'), ('OPTIONS', '/api/contact'),
])
def test_public_allowlist_cannot_authorize_another_method(app, method, path):
    app.add_api_route(path, lambda: {'unintended_access': True}, methods=[method])
    app.router.routes.sort(key=lambda route: getattr(route, 'path', '') == '/{path:path}')
    with TestClient(app, base_url=PUBLIC_URL) as client:
        assert client.request(method, path).status_code == 401


@pytest.mark.parametrize('with_csrf', [False, True])
def test_expired_session_cannot_submit_contact_or_read_application(app, with_csrf):
    with TestClient(app, base_url=PUBLIC_URL) as client:
        headers = login(client)
        with app.state.accounts.db() as db:
            db.execute('UPDATE sessions SET expires=0')
        app.state.provider_calls.clear()
        assert client.get('/api/state').status_code == 401
        assert client.post('/api/contact', json=contact_payload(),
                           headers=headers if with_csrf else {}).status_code == 401
    assert app.state.provider_calls == []
    assert_no_contact_side_effects(app)


def test_contact_csrf_is_checked_before_captcha_quota_or_ticket(app):
    with TestClient(app, base_url=PUBLIC_URL) as client:
        login(client)
        app.state.provider_calls.clear()
        assert client.post('/api/contact', json=contact_payload()).status_code == 403
        assert client.post('/api/contact', json=contact_payload(),
                           headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    assert app.state.provider_calls == []
    assert_no_contact_side_effects(app)


def test_registration_and_existing_accounts_can_use_the_private_application(app):
    app.state.accounts.create('legacy', PASSWORD)
    with TestClient(app, base_url=PUBLIC_URL) as client:
        for path in ('/api/health', '/api/security/options', '/api/registration/options'):
            assert client.get(path).status_code == 200
        signup = client.post('/api/register', json={
            'username': 'new-manager', 'password': PASSWORD,
            'email': 'new@example.test', 'captcha_token': 'register-token'})
        assert signup.status_code == 200
        cookie = signup.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        headers = {'X-CSRF-Token': signup.json()['csrf']}
        state = client.get('/api/state').json()
        assert state['user'] == {'username': 'new-manager', 'admin': False}
        assert state['teams'] == []
        ticket = client.post('/api/contact', json=contact_payload(), headers=headers)
        assert ticket.status_code == 200
        assert client.get('/api/contact').json()['items'][0]['id'] == ticket.json()['ticket']['id']
        assert client.post('/api/logout', headers=headers).status_code == 200
        login(client, 'legacy')
        assert client.get('/api/state').json()['user']['username'] == 'legacy'
        assert client.get('/api/contact').json()['items'] == []
    assert app.state.provider_calls == ['register-token', 'contact-token', 'login-token']
