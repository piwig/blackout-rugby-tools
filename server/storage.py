import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from cryptography.fernet import Fernet

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def pack(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def password_hash(password,salt):return hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()

class Store:
    def __init__(self,directory,password=None,seed=True):
        directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
        self.path=directory/'brt.sqlite'
        key=directory/'encryption.key'
        if not key.exists():
            fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
        self.cipher=Fernet(key.read_bytes())
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY,name TEXT NOT NULL,country TEXT NOT NULL,meta TEXT NOT NULL DEFAULT '{}');
              CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,team_id TEXT NOT NULL,youth INTEGER NOT NULL,source TEXT NOT NULL,observed_at TEXT NOT NULL,imported_at TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL,game_date TEXT);
              CREATE TABLE IF NOT EXISTS notes(team_id TEXT,player_id TEXT,text TEXT,watch INTEGER,PRIMARY KEY(team_id,player_id));
              CREATE TABLE IF NOT EXISTS plans(team_id TEXT,season INTEGER,grid TEXT,PRIMARY KEY(team_id,season));
              CREATE TABLE IF NOT EXISTS matches(id TEXT,type INTEGER,payload TEXT,updated_at TEXT,PRIMARY KEY(id,type));
              CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,csrf TEXT,expires INTEGER);
              CREATE INDEX IF NOT EXISTS snapshots_latest ON snapshots(team_id,youth,id DESC);
            ''')
            # Migrate the development schema that incorrectly deduplicated all history.
            schema=db.execute("SELECT sql FROM sqlite_master WHERE name='snapshots'").fetchone()[0]
            if 'UNIQUE(team_id,youth,digest)' in schema:
                db.executescript('''ALTER TABLE snapshots RENAME TO snapshots_old;
                CREATE TABLE snapshots(id INTEGER PRIMARY KEY,team_id TEXT NOT NULL,youth INTEGER NOT NULL,source TEXT NOT NULL,observed_at TEXT NOT NULL,imported_at TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL,game_date TEXT);
                INSERT INTO snapshots SELECT * FROM snapshots_old;
                DROP TABLE snapshots_old;
                CREATE INDEX snapshots_latest ON snapshots(team_id,youth,id DESC);''')
            initial=[('72450','Moeskroen','BE'),('72444','LaTouff','LT'),('57627','XV Manchot','FR'),('71184','Rapa Nui','CL'),('77847','Harragas','GE'),('81242','Pif Paf Pastèque','NL'),('41988','Strathclyde United','SL')] if seed and not db.execute("SELECT 1 FROM kv WHERE key='initial_seed_done'").fetchone() else []
            for tid,name,country in initial:
                db.execute('INSERT OR IGNORE INTO teams(id,name,country) VALUES(?,?,?)',(tid,name,country))
            db.execute("INSERT OR IGNORE INTO kv VALUES('initial_seed_done','true')")
        if self.get('password') is None:
            if not password or len(password)<12:raise ValueError('BRT_PASSWORD requis au premier démarrage (12 caractères minimum).')
            salt=secrets.token_bytes(16);self.set('password',{'salt':salt.hex(),'hash':password_hash(password,salt)})
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row;db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=15000')
        try:
            with db:yield db
        finally:db.close()
    def get(self,key,default=None):
        with self.db() as db:r=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
        return json.loads(r['value']) if r else default
    def set(self,key,value):
        with self.db() as db:db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key,pack(value)))
    def secrets(self,team_id):
        common=self.get('api_developer');member=self.get('api_member:'+team_id)
        out={}
        for raw in [common,member]:
            if raw:out.update(json.loads(self.cipher.decrypt(raw.encode())))
        return out
    def save_secrets(self,team_id,values):
        existing=self.secrets(team_id)
        if not values.get('iv') and any(values.get(k) and values[k]!=existing.get(k) for k in ['d','dk']):existing.pop('iv',None)
        existing.update({k:v for k,v in values.items() if v})
        for key,fields in [('api_developer',['d','dk','iv']),('api_member:'+team_id,['m','mk'])]:
            doc={k:existing[k] for k in fields if k in existing}
            if doc:self.set(key,self.cipher.encrypt(pack(doc).encode()).decode())
    def verify(self,password):
        p=self.get('password');return secrets.compare_digest(p['hash'],password_hash(password,bytes.fromhex(p['salt'])))
    def save_snapshot(self,team_id,youth,players,source,observed_at=None,game_date=None,db=None):
        payload=pack(players); digest=hashlib.sha256(payload.encode()).hexdigest()
        values=(team_id,int(youth),str(source)[:500],str(observed_at or now())[:80],now(),digest,payload,pack(game_date) if game_date else None)
        sql='INSERT INTO snapshots(team_id,youth,source,observed_at,imported_at,digest,payload,game_date) VALUES(?,?,?,?,?,?,?,?)'
        def save(conn):
            last=conn.execute('SELECT digest FROM snapshots WHERE team_id=? AND youth=? ORDER BY id DESC LIMIT 1',(team_id,int(youth))).fetchone()
            if not last or last['digest']!=digest:conn.execute(sql,values)
        if db is not None:save(db)
        else:
            with self.db() as conn:save(conn)
    def import_result(self,result,team_id,youth,filename,observed_at=None):
        datasets=result['datasets'] or [{'players':result['players'],'youth':youth,'team_hint':None}]
        count=0
        with self.db() as db:
            for dataset in datasets:
                tid={'moeskroen':'72450','latouff':'72444'}.get(dataset.get('team_hint'),team_id)
                if dataset.get('team_hint'):db.execute('INSERT OR IGNORE INTO teams(id,name,country) VALUES(?,?,?)',(tid,'LaTouff' if tid=='72444' else 'Moeskroen','LT' if tid=='72444' else 'BE'))
                self.save_snapshot(tid,dataset['youth'],dataset['players'],filename+(' · '+dataset['sheet'] if 'sheet' in dataset else ''),observed_at or result.get('team',{}).get('date_maj'),result['game_date'],db)
                count+=len(dataset['players'])
            if result.get('team'):db.execute('UPDATE teams SET meta=? WHERE id=?',(pack(result['team']),'72450'))
            for season,grid in result.get('plans',{}).items():db.execute('INSERT OR IGNORE INTO plans VALUES(?,?,?)',('72450',int(season),pack(grid)))
            for tr in result.get('training',[]):
                tid=tr['teamid'];db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('training:'+tid,pack([tr.get('s'+str(i),'') for i in range(1,5)])))
        if result['game_date']:self.set('game_date',result['game_date'])
        return count
    def session(self,token):
        if not token:return None
        with self.db() as db:
            r=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        return dict(r) if r else None
