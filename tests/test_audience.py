"""Audience config is public, optional and never weakens private API defaults."""

import pytest
from fastapi.testclient import TestClient
from server.main import create_app


@pytest.fixture(autouse=True)
def clean_audience_env(monkeypatch):
    for name in ('ENABLED', 'SCRIPT_URL', 'WEBSITE_ID', 'HOSTNAME'):
        monkeypatch.delenv('BRT_AUDIENCE_' + name, raising=False)


def test_audience_is_disabled_by_default_without_auth(tmp_path):
    with TestClient(create_app(tmp_path, 'Testing-password-1234', secure=False)) as client:
        response = client.get('/api/audience/options')
        assert response.status_code == 200
        assert response.json() == {'enabled': False}
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/api/audience/private').status_code == 401
        assert client.post('/api/audience/options', json={}).status_code == 401
        assert 'mesure.example' not in response.headers['content-security-policy']


def enable(monkeypatch):
    values = {
        'ENABLED': '1',
        'SCRIPT_URL': 'https://mesure.example/mesure.js',
        'WEBSITE_ID': '2b69bd47-cb54-416e-ad12-e206df20427f',
        'HOSTNAME': 'brt.example',
    }
    for name, value in values.items():
        monkeypatch.setenv('BRT_AUDIENCE_' + name, value)


def test_public_options_expose_only_tracker_configuration_and_precise_csp(tmp_path, monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('UMAMI_BRT_PASSWORD', 'NEVER-EXPOSE-THIS')
    with TestClient(create_app(tmp_path, 'Testing-password-1234', secure=False)) as client:
        response = client.get('/api/audience/options')
        assert response.status_code == 200
        assert response.json() == {
            'enabled': True,
            'script_url': 'https://mesure.example/mesure.js',
            'website_id': '2b69bd47-cb54-416e-ad12-e206df20427f',
            'hostname': 'brt.example',
        }
        directives = dict(part.strip().split(' ', 1) for part in response.headers['content-security-policy'].split(';') if part.strip())
        assert directives['script-src'].split() == ["'self'", 'https://challenges.cloudflare.com', 'https://mesure.example']
        assert directives['connect-src'].split() == ["'self'", 'https://challenges.cloudflare.com', 'https://mesure.example']
        assert directives['frame-ancestors'] == "'none'"
        assert 'NEVER-EXPOSE' not in response.text
        assert client.get('/api/state').status_code == 401


@pytest.mark.parametrize(('name', 'value'), [
    ('SCRIPT_URL', 'http://mesure.example/script.js'),
    ('SCRIPT_URL', 'https://user:password@mesure.example/script.js'),
    ('SCRIPT_URL', 'https://mesure.example/script.js?token=PRIVATE'),
    ('SCRIPT_URL', 'https://mesure.example/script.js#private'),
    ('SCRIPT_URL', "https://mesure.example/script.js; script-src *"),
    ('SCRIPT_URL', 'https://mesure.example:invalid/script.js'),
    ('SCRIPT_URL', 'https://mesure.example/mesure.js\n'),
    ('SCRIPT_URL', 'https://K.example/mesure.js'),
    ('SCRIPT_URL', 'https://127.0.0.1/script.js'),
    ('SCRIPT_URL', 'https://mesure.example/'),
    ('WEBSITE_ID', 'not-a-uuid'),
    ('HOSTNAME', 'brt.example/path'),
    ('HOSTNAME', "brt.example' *"),
    ('HOSTNAME', 'localhost'),
])
def test_malformed_settings_disable_collection_without_broadening_csp(tmp_path, monkeypatch, name, value):
    enable(monkeypatch)
    monkeypatch.setenv('BRT_AUDIENCE_' + name, value)
    with TestClient(create_app(tmp_path, 'Testing-password-1234', secure=False)) as client:
        response = client.get('/api/audience/options')
        assert response.status_code == 200
        assert response.json() == {'enabled': False}
        assert 'mesure.example' not in response.headers['content-security-policy']
        assert client.get('/api/health').json()['ok'] is True
