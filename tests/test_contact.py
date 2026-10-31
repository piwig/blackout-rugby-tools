"""Contact privacy and abuse boundaries; SMTP is replaced at its network edge."""
import importlib.util
import ssl
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ('BRT_CONTACT_TO', 'BRT_SMTP_HOST', 'BRT_SMTP_PORT',
                 'BRT_SMTP_USER', 'BRT_SMTP_PASSWORD', 'BRT_SMTP_FROM'):
        monkeypatch.delenv(name, raising=False)
    application = create_app(tmp_path, 'Testing-password-1234', secure=False)
    if not any(getattr(r, 'path', '') == '/api/contact' for r in application.routes):
        if importlib.util.find_spec('server.contact'):
            from server.contact import register_contact
            state = next(r for r in application.routes if getattr(r, 'path', '') == '/api/state')
            register_contact(application, application.state.accounts, state.dependant.dependencies[0].call, False)
            application.router.routes.sort(key=lambda r: getattr(r, 'path', '') == '/{path:path}')
    return application


def payload(**changes):
    return {'kind': 'bug', 'subject': 'Affichage du calendrier',
            'message': 'La date ne reste pas visible après ouverture.',
            'email': 'manager@example.test', 'website': '', **changes}


def login(client, name='piwig'):
    response = client.post('/api/login', json={'username': name, 'password': 'Testing-password-1234'})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf']}


def test_registered_submission_is_saved_but_cannot_be_read_by_id(app):
    app.state.accounts.create('alice', 'Testing-password-1234')
    with TestClient(app) as manager, TestClient(app) as public, TestClient(app) as admin:
        headers = login(manager, 'alice')
        response = manager.post('/api/contact', headers=headers, json=payload())
        assert response.status_code == 200, response.text
        ticket = response.json()['ticket']
        assert len(ticket['id']) >= 24 and ticket['status'] == 'new'
        assert ticket['revision'] == 1
        assert 'notification_status' not in ticket and 'user_id' not in ticket
        assert public.get('/api/contact').status_code == 401
        assert public.get('/api/contact/admin').status_code == 401
        assert public.get('/api/contact/' + ticket['id']).status_code == 401
        assert manager.get('/api/contact/' + ticket['id']).status_code == 404
        login(admin)
        inbox = admin.get('/api/contact/admin').json()['items']
        assert inbox[0]['id'] == ticket['id']
        assert inbox[0]['author'] == 'alice'
        assert inbox[0]['notification_status'] == 'disabled'
        assert admin.get('/api/contact').json()['items'] == []


def test_authenticated_submit_requires_csrf_and_lists_only_own_messages(app):
    app.state.accounts.create('alice', 'Testing-password-1234')
    app.state.accounts.create('bob', 'Testing-password-1234')
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as admin:
        ah = login(alice, 'alice')
        bh = login(bob, 'bob')
        assert alice.post('/api/contact', json=payload()).status_code == 403
        assert alice.post('/api/contact', headers={'X-CSRF-Token': 'wrong'}, json=payload()).status_code == 403
        own = alice.post('/api/contact', headers=ah, json=payload()).json()['ticket']
        other = bob.post('/api/contact', headers=bh, json=payload(subject='Une autre idée')).json()['ticket']
        assert [t['id'] for t in alice.get('/api/contact').json()['items']] == [own['id']]
        assert [t['id'] for t in bob.get('/api/contact').json()['items']] == [other['id']]
        assert alice.get('/api/contact/admin').status_code == 403
        assert 'notification_status' not in alice.get('/api/contact').text
        login(admin)
        items = admin.get('/api/contact/admin').json()['items']
        assert {t['author'] for t in items} == {'alice', 'bob'}


def test_only_admin_changes_status_with_current_revision(app):
    app.state.accounts.create('alice', 'Testing-password-1234')
    with TestClient(app) as manager, TestClient(app) as admin:
        mh = login(manager, 'alice')
        ticket = manager.post('/api/contact', headers=mh, json=payload()).json()['ticket']
        change = {'ticket_id': ticket['id'], 'status': 'reviewing', 'expected_revision': 1}
        assert manager.post('/api/contact/status', headers=mh, json=change).status_code == 403
        ah = login(admin)
        assert admin.post('/api/contact/status', json=change).status_code == 403
        result = admin.post('/api/contact/status', headers=ah, json=change)
        assert result.status_code == 200
        assert result.json()['ticket']['revision'] == 2
        assert admin.post('/api/contact/status', headers=ah, json={**change, 'status': 'resolved'}).status_code == 409
        assert manager.get('/api/contact').json()['items'][0]['status'] == 'reviewing'
        assert admin.post('/api/contact/status', headers=ah, json={**change, 'ticket_id': 'a'*32}).status_code == 404
        assert admin.post('/api/contact/status', headers=ah, json={**change, 'status': 'deleted'}).status_code == 422


@pytest.mark.parametrize('changes', [
    {'kind': 'other'}, {'subject': ''}, {'subject': ' '*4}, {'subject': 'x'*161},
    {'subject': 'New\r\nBcc: other@example.test'}, {'message': ''}, {'message': 'x'*4001},
    {'email': 'not-an-address'}, {'email': 'a..b@example.test'}, {'email': 'a@-example.test'},
    {'email': 'a@example.test\r\nBcc: victim@example.test'}, {'email': 'a@example.test\n'},
    {'email': 'a@example.test,b@example.test'}, {'email': 'x'*245+'@example.test'},
    {'website': 'bot'}, {'user_id': 'primary'}, {'notification_status': 'sent'},
])
def test_validation_rejects_invalid_fields_without_saving(app, changes):
    with TestClient(app) as client:
        headers = login(client)
        assert client.post('/api/contact', headers=headers, json=payload(**changes)).status_code == 422
        assert client.get('/api/contact/admin').json()['items'] == []


def test_html_is_preserved_as_plain_text_and_never_returned_as_html(app):
    text = '<script>alert("contact")</script><img src=x onerror=alert(1)>'
    with TestClient(app) as client:
        headers = login(client)
        result = client.post('/api/contact', headers=headers, json=payload(subject=text, message=text))
        assert result.status_code == 200
        assert result.headers['content-type'].startswith('application/json')
        assert result.json()['ticket']['message'] == text
        assert result.headers['x-content-type-options'] == 'nosniff'


def test_contact_rejects_cross_origin_posts(app):
    with TestClient(app) as client:
        headers = login(client)
        assert client.post('/api/contact', headers={**headers, 'Origin': 'https://external.example'}, json=payload()).status_code == 403


def test_rate_limit_survives_new_client_and_cannot_use_forwarded_header(app):
    with TestClient(app) as client:
        headers = login(client)
        for _ in range(5):
            assert client.post('/api/contact', headers=headers, json=payload()).status_code == 200
    with TestClient(app) as restarted:
        headers = login(restarted)
        limited = restarted.post('/api/contact', headers={**headers, 'X-Forwarded-For': '203.0.113.41'}, json=payload())
        assert limited.status_code == 429
        assert int(limited.headers['retry-after']) > 0
        assert len(restarted.get('/api/contact/admin').json()['items']) == 5


def test_rate_limit_survives_application_restart(app):
    with TestClient(app) as client:
        headers = login(client)
        for _ in range(5):
            assert client.post('/api/contact', headers=headers, json=payload()).status_code == 200
    reopened = create_app(app.state.accounts.root, 'Testing-password-1234', secure=False)
    if not any(getattr(r, 'path', '') == '/api/contact' for r in reopened.routes):
        from server.contact import register_contact
        state = next(r for r in reopened.routes if getattr(r, 'path', '') == '/api/state')
        register_contact(reopened, reopened.state.accounts, state.dependant.dependencies[0].call, False)
        reopened.router.routes.sort(key=lambda r: getattr(r, 'path', '') == '/{path:path}')
    with TestClient(reopened) as client:
        headers = login(client)
        assert client.post('/api/contact', headers=headers, json=payload()).status_code == 429
        assert len(client.get('/api/contact/admin').json()['items']) == 5


def test_rate_limit_counts_concurrent_requests_atomically(app):
    with TestClient(app) as client:
        headers = login(client)
        def send(_):
            return client.post('/api/contact', headers=headers, json=payload()).status_code
        with ThreadPoolExecutor(max_workers=6) as pool:
            assert sorted(pool.map(send, range(6))) == [200, 200, 200, 200, 200, 429]


def test_invalid_attempts_consume_the_limit_without_creating_tickets(app):
    with TestClient(app) as client:
        headers = login(client)
        for _ in range(5):
            assert client.post('/api/contact', headers=headers, json=payload(website='robot')).status_code == 422
        assert client.post('/api/contact', headers=headers, json=payload()).status_code == 429
        assert client.get('/api/contact/admin').json()['items'] == []


def test_global_limit_blocks_new_addresses_before_saving(app, monkeypatch):
    import server.contact as contact
    monkeypatch.setattr(contact, 'GLOBAL_LIMIT', 2)
    for i in range(3):
        with TestClient(app, client=(f'192.0.2.{i+1}', 50000)) as client:
            headers = login(client)
            response = client.post('/api/contact', headers=headers, json=payload())
            assert response.status_code == (200 if i < 2 else 429)
    with TestClient(app) as admin:
        login(admin)
        assert len(admin.get('/api/contact/admin').json()['items']) == 2


def test_racing_status_updates_do_not_overwrite_one_another(app):
    with TestClient(app) as admin:
        headers = login(admin)
        ticket = admin.post('/api/contact', headers=headers, json=payload()).json()['ticket']
        def update(status):
            return admin.post('/api/contact/status', headers=headers, json={
                'ticket_id': ticket['id'], 'expected_revision': 1, 'status': status}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(update, ['planned', 'resolved'])) == [200, 409]


def configure_mail(monkeypatch):
    monkeypatch.setenv('BRT_CONTACT_TO', 'owner@example.test')
    monkeypatch.setenv('BRT_SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('BRT_SMTP_PORT', '587')
    monkeypatch.setenv('BRT_SMTP_FROM', 'tools@example.test')
    monkeypatch.setenv('BRT_PUBLIC_URL', 'https://tools.example.test')


def test_mail_failure_keeps_ticket_and_exposes_only_generic_admin_status(app, monkeypatch):
    import server.contact as contact
    configure_mail(monkeypatch)
    def failed(*args, **kwargs):
        raise OSError('secret-provider-credential')
    monkeypatch.setattr(contact.smtplib, 'SMTP', failed)
    with TestClient(app) as manager, TestClient(app) as admin:
        headers = login(manager)
        result = manager.post('/api/contact', headers=headers, json=payload())
        assert result.status_code == 200 and 'secret-provider-credential' not in result.text
        assert 'notification_status' not in result.text
        login(admin)
        items = admin.get('/api/contact/admin').json()['items']
        assert items[0]['notification_status'] == 'failed'
        assert 'secret-provider-credential' not in str(items)


def test_mail_uses_tls_fixed_recipient_and_no_user_content(app, monkeypatch):
    import server.contact as contact
    configure_mail(monkeypatch)
    delivered = []
    class SMTP:
        def __init__(self, host, port, timeout):
            assert host == 'smtp.example.test' and port == 587 and timeout <= 10
            self.tls = False
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context):
            assert context.verify_mode == ssl.CERT_REQUIRED
            self.tls = True
        def send_message(self, message, from_addr, to_addrs):
            assert self.tls
            delivered.append((message, from_addr, to_addrs))
    monkeypatch.setattr(contact.smtplib, 'SMTP', SMTP)
    with TestClient(app) as client:
        headers = login(client)
        result = client.post('/api/contact', headers=headers, json=payload(subject='untrusted-header', message='private-content'))
        assert result.status_code == 200
        message, sender, recipients = delivered[0]
        assert recipients == ['owner@example.test'] and sender == 'tools@example.test'
        assert message['Reply-To'] is None and message.get_content_type() == 'text/plain'
        assert 'untrusted-header' not in str(message) and 'private-content' not in str(message)
        assert 'https://tools.example.test' in message.get_content()
        assert client.get('/api/contact/admin').json()['items'][0]['notification_status'] == 'sent'


def test_private_export_has_only_own_messages_and_no_notification_metadata(app):
    from server.contact import contact_history
    user = app.state.accounts.create('alice', 'Testing-password-1234')
    with TestClient(app) as client:
        headers = login(client)
        assert client.post('/api/contact', headers=headers, json=payload(subject='Other manager message')).status_code == 200
        assert client.post('/api/logout', headers=headers).status_code == 200
        headers = login(client, 'alice')
        assert client.post('/api/contact', headers=headers, json=payload(subject='Own message')).status_code == 200
    exported = contact_history(app.state.accounts, user['id'])
    assert len(exported) == 1 and exported[0]['subject'] == 'Own message'
    assert 'notification_status' not in exported[0] and 'author' not in exported[0]
