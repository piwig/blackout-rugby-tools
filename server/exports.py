"""Stream private exports one database row at a time, never the whole history."""
import sqlite3
from contextlib import contextmanager
from .storage import pack,now
from .contact import PUBLIC_COLUMNS


@contextmanager
def readonly_database(path):
    # StreamingResponse may advance successive chunks on different pool threads.
    # A generator is advanced sequentially; this connection belongs only to it.
    db=sqlite3.connect(path,timeout=15,check_same_thread=False)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    try:yield db
    finally:db.close()


def export_chunks(private_store,accounts,user_id):
    # Capture the concrete store before leaving the authenticated request context.
    with readonly_database(private_store.path) as db:
        db.execute('BEGIN')
        yield '{'
        for index,table in enumerate(('teams','snapshots','notes','plans','matches')):
            if index:yield ','
            yield pack(table)+':['
            for row_index,row in enumerate(db.execute('SELECT * FROM '+table)):
                if row_index:yield ','
                yield pack(dict(row))
            yield ']'
        yield ',"manager_documents":{'
        for index,row in enumerate(db.execute("SELECT key,value FROM kv WHERE key GLOB 'lineup_lab:*' OR key GLOB 'insights:*' OR key GLOB 'workbench:*' OR key GLOB 'match_review:*' OR key='profile:preferences' ORDER BY key")):
            if index:yield ','
            yield pack(row['key'])+':'+row['value']
        yield '}'
        for prefix,default in (('lineup','{}'),('training','[]')):
            yield ','+pack('lineups' if prefix=='lineup' else prefix)+':{'
            for index,team in enumerate(db.execute('SELECT id FROM teams ORDER BY id')):
                if index:yield ','
                row=db.execute('SELECT value FROM kv WHERE key=?',(prefix+':'+team['id'],)).fetchone()
                yield pack(team['id'])+':'+(row['value'] if row else default)
            yield '}'
        row=db.execute("SELECT value FROM kv WHERE key='game_date'").fetchone()
        yield ',"game_date":'+(row['value'] if row else 'null')
        yield ',"exported_at":'+pack(now())
    yield ',"account_contact":'+pack(accounts.get_contact(user_id))
    yield ',"contact_messages":['
    with readonly_database(accounts.path) as db:
        for index,row in enumerate(db.execute('SELECT * FROM contact_tickets WHERE user_id=? ORDER BY created_at DESC,id DESC',(user_id,))):
            if index:yield ','
            yield pack({key:row[key] for key in PUBLIC_COLUMNS})
    yield ']}'
