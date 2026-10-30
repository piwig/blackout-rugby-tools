"""Cloudflare Turnstile validation. Browser tokens never authorize an action alone."""
import json
import os
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request


VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
TEST_SITE_KEYS = frozenset({
    '1x00000000000000000000AA', '1x00000000000000000000BB',
    '2x00000000000000000000AB', '2x00000000000000000000BB',
    '3x00000000000000000000FF',
})
TEST_SECRET_KEYS = frozenset({
    '1x0000000000000000000000000000000AA',
    '2x0000000000000000000000000000000AA',
    '3x0000000000000000000000000000000AA',
})
UNAVAILABLE = 'La vérification de sécurité est indisponible. Réessayez dans un instant.'
REJECTED = 'La vérification de sécurité a expiré ou a échoué. Recommencez-la avant de réessayer.'


class AntiBotSettings:
    def __init__(self, public_url, secure):
        mode = os.getenv('BRT_TURNSTILE_ENABLED', '0')
        # A mistyped enabled flag must never silently disable production protection.
        self.enabled = mode != '0'
        self.site_key = os.getenv('BRT_TURNSTILE_SITE_KEY', '').strip()
        self.secret_key = os.getenv('BRT_TURNSTILE_SECRET_KEY', '').strip()
        try:
            url = urlsplit(public_url)
            self.hostname = (url.hostname or '').lower()
            valid_url = (url.scheme in (('https',) if secure else ('http', 'https'))
                         and bool(self.hostname) and not url.username and not url.password
                         and not url.query and not url.fragment)
        except ValueError:
            self.hostname = ''
            valid_url = False
        self.configured = bool(mode == '1' and valid_url and self.site_key and self.secret_key
                               and len(self.site_key) <= 256 and len(self.secret_key) <= 256
                               and not any(c.isspace() for c in self.site_key + self.secret_key)
                               and not (secure and (self.site_key in TEST_SITE_KEYS
                                                    or self.secret_key in TEST_SECRET_KEYS)))

    def options(self):
        return {'enabled': self.enabled, 'site_key': self.site_key if self.enabled and self.configured else ''}


def register_antibot(app, public_url, secure):
    app.state.antibot = AntiBotSettings(public_url, secure)
    if not any(getattr(route, 'path', '') == '/api/security/options' for route in app.routes):
        @app.get('/api/security/options')
        def options():
            return app.state.antibot.options()
    return app.state.antibot


def verify(request: Request, token: str, action: str):
    settings = getattr(request.app.state, 'antibot', None)
    if settings is None:
        # Fail closed when this helper is used before the central route registrar.
        settings = AntiBotSettings(os.getenv('BRT_PUBLIC_URL', 'https://brt.bordebat.fr'),
                                   os.getenv('BRT_SECURE', '1') == '1')
    if not settings.enabled:
        return
    if not settings.configured or action not in ('register', 'login', 'contact'):
        raise HTTPException(503, UNAVAILABLE)
    if not isinstance(token, str) or not 1 <= len(token) <= 2048 or any(c.isspace() or ord(c) < 32 for c in token):
        raise HTTPException(403, REJECTED)
    try:
        # One attempt only: tokens are single-use, including after ambiguous timeouts.
        # No remoteip is required; never trust a client forwarding header here.
        with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
            with client.stream('POST', VERIFY_URL,
                               data={'secret': settings.secret_key, 'response': token}) as response:
                if response.status_code != 200:
                    raise ValueError('Provider unavailable')
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 16384:
                        raise ValueError('Provider response too large')
                    chunks.append(chunk)
                result = json.loads(b''.join(chunks))
                if not isinstance(result, dict):
                    raise ValueError('Invalid provider response')
    except (httpx.HTTPError, ValueError):
        # Never return or log provider exceptions, tokens, secret keys or response bodies.
        raise HTTPException(503, UNAVAILABLE) from None
    if (result.get('success') is not True or result.get('hostname') != settings.hostname
            or result.get('action') != action):
        raise HTTPException(403, REJECTED)
