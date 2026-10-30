"""Persistent admission limits shared by all login outcomes and processes."""
import hashlib
import time
from fastapi import HTTPException


def init_login_security(accounts):
    with accounts.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS login_attempts(ip_key TEXT NOT NULL,account_key TEXT NOT NULL,attempted_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS login_attempts_time ON login_attempts(attempted_at);
        ''')


def consume_login(accounts,address,username):
    stamp=time.time()
    ip=hashlib.sha256(('brt-login-ip:'+address).encode()).hexdigest()
    account=hashlib.sha256(('brt-login-user:'+username.lower()).encode()).hexdigest()
    with accounts.db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE attempted_at<=?',(stamp-900,))
        counts=db.execute('''SELECT count(*) AS total,
            coalesce(sum(ip_key=?),0) AS ip_count,
            coalesce(sum(account_key=?),0) AS account_count FROM login_attempts''',(ip,account)).fetchone()
        if counts['ip_count']>=10 or counts['account_count']>=30 or counts['total']>=300:
            raise HTTPException(429,'Trop de tentatives. Patientez 15 minutes.',headers={'Retry-After':'900'})
        db.execute('INSERT INTO login_attempts VALUES(?,?,?)',(ip,account,stamp))
