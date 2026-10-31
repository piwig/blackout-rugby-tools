"""Voluntary messages to the administrator, isolated from private club data."""
import hashlib
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from .accounts import normalize_email
from .antibot import verify
from .storage import now


IP_LIMIT = 5
IP_WINDOW = 900
GLOBAL_LIMIT = 100
GLOBAL_WINDOW = 3600
ContactKind = Literal['bug', 'improvement', 'feature']
ContactStatus = Literal['new', 'reviewing', 'planned', 'resolved']
PUBLIC_COLUMNS = ('id', 'kind', 'subject', 'message', 'email', 'status',
                  'revision', 'created_at', 'updated_at')


class ContactMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: ContactKind
    subject: StrictStr = Field(min_length=1, max_length=160)
    message: StrictStr = Field(min_length=1, max_length=4000)
    email: StrictStr = Field(min_length=3, max_length=254)
    website: StrictStr = Field(default='', max_length=160)
    captcha_token: StrictStr = Field(default='', max_length=2048)

    @field_validator('subject', 'message')
    @classmethod
    def meaningful_text(cls, value, info):
        allowed = '\n\r\t' if info.field_name == 'message' else ''
        if any((ord(c) < 32 and c not in allowed) or ord(c) == 127 for c in value):
            raise ValueError('Caractères de contrôle non autorisés.')
        value = value.strip()
        if not value:
            raise ValueError('Ce champ est obligatoire.')
        return value

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        return normalize_email(value)

    @field_validator('website')
    @classmethod
    def empty_honeypot(cls, value):
        if value:
            raise ValueError('Formulaire invalide.')
        return value


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticket_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{24,64}$')
    status: ContactStatus
    expected_revision: int = Field(strict=True, ge=1, le=2147483647)


def _public_ticket(row):
    return {key: row[key] for key in PUBLIC_COLUMNS}


def contact_history(accounts, user_id):
    """Own messages for a private account export; notification metadata stays admin-only."""
    with accounts.db() as db:
        return [_public_ticket(row) for row in db.execute(
            'SELECT * FROM contact_tickets WHERE user_id=? ORDER BY created_at DESC,id DESC',
            (user_id,))]


def _consume_attempt(accounts, address):
    stamp = time.time()
    key = hashlib.sha256(('brt-contact:' + address).encode()).hexdigest()
    with accounts.db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM contact_attempts WHERE attempted_at<?', (stamp-GLOBAL_WINDOW,))
        own = db.execute('SELECT COUNT(*) FROM contact_attempts WHERE address_key=? AND attempted_at>?',
                         (key, stamp-IP_WINDOW)).fetchone()[0]
        total = db.execute('SELECT COUNT(*) FROM contact_attempts WHERE attempted_at>?',
                           (stamp-GLOBAL_WINDOW,)).fetchone()[0]
        if own >= IP_LIMIT or total >= GLOBAL_LIMIT:
            retry = IP_WINDOW if own >= IP_LIMIT else GLOBAL_WINDOW
            raise HTTPException(429, 'Trop de messages. Patientez avant de réessayer.',
                                headers={'Retry-After': str(retry)})
        db.execute('INSERT INTO contact_attempts(address_key,attempted_at) VALUES(?,?)', (key, stamp))


def _notify(ticket_id, secure):
    """Send a bounded notification without message text or visitor-controlled headers."""
    names = ('BRT_CONTACT_TO', 'BRT_SMTP_HOST', 'BRT_SMTP_PORT',
             'BRT_SMTP_USER', 'BRT_SMTP_PASSWORD', 'BRT_SMTP_FROM')
    config = {key: os.getenv(key, '') for key in names}
    if not any(config.values()):
        return 'disabled'
    try:
        destination = normalize_email(config['BRT_CONTACT_TO'])
        sender = normalize_email(config['BRT_SMTP_FROM'])
        host = config['BRT_SMTP_HOST']
        if not host or len(host) > 253 or any(c.isspace() or ord(c) < 32 for c in host):
            return 'failed'
        port = int(config['BRT_SMTP_PORT'] or '587')
        if not 1 <= port <= 65535:
            return 'failed'
        username, password = config['BRT_SMTP_USER'], config['BRT_SMTP_PASSWORD']
        if bool(username) != bool(password):
            return 'failed'
        public_url = os.getenv('BRT_PUBLIC_URL', 'https://brt.bordebat.fr').rstrip('/')
        url = urlsplit(public_url)
        if (len(public_url) > 2048 or url.scheme not in (('https',) if secure else ('http', 'https'))
                or not url.hostname or url.username or url.password or url.query or url.fragment
                or any(c.isspace() or ord(c) < 32 for c in public_url)):
            return 'failed'
        message = EmailMessage()
        message['Subject'] = 'BRT · Nouveau message de contact'
        message['From'], message['To'] = sender, destination
        message.set_content('Un nouveau message est disponible dans Contact & idées.\n\n'
                            'Référence : ' + ticket_id + '\n'
                            'Ouvrir la boîte administrateur : ' + public_url + '/?page=contact\n\n'
                            'Connectez-vous avec votre compte administrateur pour le lire.\n')
        context = ssl.create_default_context()
        transport = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        options = {'timeout': 8}
        if port == 465:
            options['context'] = context
        with transport(host, port, **options) as smtp:
            smtp.ehlo()
            if port != 465:
                smtp.starttls(context=context)
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(message, from_addr=sender, to_addrs=[destination])
        return 'sent'
    except Exception:
        # Provider errors can contain addresses or credentials. Never persist or echo them.
        return 'failed'


def register_contact(app, accounts, auth, secure):
    with accounts.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS contact_tickets(
            id TEXT PRIMARY KEY, user_id TEXT, kind TEXT NOT NULL, subject TEXT NOT NULL,
            message TEXT NOT NULL, email TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
            revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            notification_status TEXT NOT NULL DEFAULT 'pending');
        CREATE INDEX IF NOT EXISTS contact_tickets_author ON contact_tickets(user_id,created_at);
        CREATE TABLE IF NOT EXISTS contact_attempts(address_key TEXT NOT NULL,attempted_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS contact_attempts_address ON contact_attempts(address_key,attempted_at);
        CREATE INDEX IF NOT EXISTS contact_attempts_time ON contact_attempts(attempted_at);
        ''')

    async def sender(request: Request, session=Depends(auth)):
        address = request.client.host if request.client else 'unknown'
        _consume_attempt(accounts, address)
        return session

    async def administrator(session=Depends(auth)):
        if not session['admin']:
            raise HTTPException(403, 'Réservé à l’administrateur.')
        return session

    @app.post('/api/contact')
    def submit(body: ContactMessage, request: Request, session=Depends(sender)):
        verify(request, body.captcha_token, 'contact')
        ticket_id, stamp = secrets.token_urlsafe(24), now()
        with accounts.db() as db:
            db.execute('''INSERT INTO contact_tickets
                (id,user_id,kind,subject,message,email,status,revision,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'new',1,?,?)''',
                (ticket_id, session['user_id'], body.kind,
                 body.subject, body.message, body.email, stamp, stamp))
            ticket = _public_ticket(db.execute('SELECT * FROM contact_tickets WHERE id=?', (ticket_id,)).fetchone())
        notification = _notify(ticket_id, secure)
        with accounts.db() as db:
            db.execute('UPDATE contact_tickets SET notification_status=? WHERE id=?', (notification, ticket_id))
        return {'ok': True, 'ticket': ticket}

    @app.get('/api/contact')
    def own_messages(session=Depends(auth), limit: int = Query(default=50, ge=1, le=100),
                     offset: int = Query(default=0, ge=0, le=1000000)):
        with accounts.db() as db:
            rows = db.execute('SELECT * FROM contact_tickets WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                              (session['user_id'], limit+1, offset)).fetchall()
        return {'items': [_public_ticket(row) for row in rows[:limit]], 'has_more': len(rows) > limit}

    @app.get('/api/contact/admin', dependencies=[Depends(administrator)])
    def inbox(limit: int = Query(default=50, ge=1, le=100),
              offset: int = Query(default=0, ge=0, le=1000000)):
        with accounts.db() as db:
            rows = db.execute('''SELECT t.*,u.username AS author FROM contact_tickets t
                LEFT JOIN users u ON t.user_id=u.id ORDER BY t.created_at DESC,t.id DESC LIMIT ? OFFSET ?''',
                              (limit+1, offset)).fetchall()
        return {'items': [{**_public_ticket(row), 'author': row['author'],
                           'notification_status': row['notification_status']} for row in rows[:limit]],
                'has_more': len(rows) > limit}

    @app.post('/api/contact/status', dependencies=[Depends(administrator)])
    def update_status(body: ContactUpdate):
        with accounts.db() as db:
            changed = db.execute('''UPDATE contact_tickets SET status=?,revision=revision+1,updated_at=?
                WHERE id=? AND revision=?''', (body.status, now(), body.ticket_id, body.expected_revision))
            if not changed.rowcount:
                if not db.execute('SELECT 1 FROM contact_tickets WHERE id=?', (body.ticket_id,)).fetchone():
                    raise HTTPException(404, 'Message introuvable.')
                raise HTTPException(409, 'Ce message a changé. Rechargez la boîte avant de modifier son suivi.')
            row = db.execute('SELECT * FROM contact_tickets WHERE id=?', (body.ticket_id,)).fetchone()
        return {'ok': True, 'ticket': _public_ticket(row)}
