"""Bounded public registration, with persistent admission limits before hashing."""
import hashlib
import os
import re
import sqlite3
import time
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .accounts import UsernameTaken, normalize_email
from .antibot import verify


AVATAR_STYLES = ('jersey', 'shield', 'trophy', 'rugby')


class Registration(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=128)
    email: str = Field(min_length=3, max_length=254)
    avatar_style: Literal['jersey', 'shield', 'trophy', 'rugby'] = 'jersey'
    language: Literal['fr', 'en', 'es', 'it'] = 'fr'
    website: str = Field(default='', max_length=200)
    captcha_token: str = Field(default='', max_length=2048)

    @field_validator('username')
    @classmethod
    def username_syntax(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', value):
            raise ValueError('Identifiant invalide.')
        return value

    @field_validator('email')
    @classmethod
    def email_syntax(cls, value):
        return normalize_email(value)


def reserve_registration(accounts, request):
    # Trust only the ASGI client set by the server/proxy configuration, never a
    # browser-supplied forwarding header. No address is stored in plain text.
    host = request.client.host if request.client else 'unknown'
    ip_key = hashlib.sha256(('registration:' + host).encode()).hexdigest()
    stamp = time.time()
    with accounts.db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM registration_attempts WHERE attempted_at<=?', (stamp - 86400,))
        counts = db.execute('''SELECT count(*) AS daily,
            coalesce(sum(attempted_at>?),0) AS hourly,
            coalesce(sum(ip_key=? AND attempted_at>?),0) AS ip_hourly
            FROM registration_attempts''', (stamp - 3600, ip_key, stamp - 3600)).fetchone()
        if counts['ip_hourly'] >= 5 or counts['hourly'] >= 50 or counts['daily'] >= 200:
            raise HTTPException(429, 'Trop de demandes d’inscription. Réessayez plus tard.',
                                headers={'Retry-After': '3600'})
        db.execute('INSERT INTO registration_attempts(ip_key,attempted_at) VALUES(?,?)', (ip_key, stamp))


def register_registration(app, accounts, auth, secure):
    enabled = os.getenv('BRT_REGISTRATION_ENABLED', '1') == '1'
    with accounts.db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS registration_attempts(id INTEGER PRIMARY KEY,ip_key TEXT NOT NULL,attempted_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS registration_attempts_time ON registration_attempts(attempted_at);
        ''')

    @app.get('/api/registration/options')
    def options():
        return {'enabled': enabled, 'avatar_styles': list(AVATAR_STYLES)}

    @app.post('/api/register')
    def register(body: Registration, request: Request, response: Response):
        if not enabled:
            raise HTTPException(403, 'Les inscriptions sont momentanément fermées.')
        if getattr(request.state, 'session', None):
            raise HTTPException(409, 'Déconnectez-vous avant de créer un autre compte.')
        reserve_registration(accounts, request)
        if body.website:
            raise HTTPException(422, 'Vérifiez les champs du formulaire.')
        verify(request, body.captcha_token, 'register')
        try:
            user = accounts.create(body.username, body.password, email=body.email, avatar_style=body.avatar_style, language=body.language)
        except UsernameTaken:
            raise HTTPException(409, 'Cet identifiant est déjà utilisé.') from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, 'L’inscription n’a pas abouti. Réessayez ou contactez l’administrateur.') from None
        try:
            token, csrf = accounts.start_session(user['id'])
        except (OSError, sqlite3.Error):
            # Identity creation is already committed and the password is usable.
            raise HTTPException(503, 'Votre compte a été créé. Revenez à la connexion pour ouvrir votre espace.') from None
        response.set_cookie('brt_session', token, httponly=True, secure=secure,
                            samesite='strict', max_age=604800, path='/')
        return {'ok': True, 'csrf': csrf, 'user': user}

    @app.get('/api/account/contact')
    def contact(session=Depends(auth)):
        return accounts.get_contact(session['user_id']) or {'email': None, 'created_at': None}
