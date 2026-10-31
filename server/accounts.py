"""Application identities and isolated data stores. Never trust a client tenant ID."""
import hashlib,json,secrets,sqlite3,time,uuid,re,shutil,unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from .storage import Store,password_hash,pack,now

active_store=ContextVar('brt_private_store')

class UsernameTaken(ValueError):
    pass


def normalize_email(value):
    """Validate a bounded mailbox syntax; this does not verify its ownership."""
    if not isinstance(value,str) or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Adresse e-mail invalide.')
    value=value.strip()
    if len(value)>254 or value.count('@')!=1:
        raise ValueError('Adresse e-mail invalide.')
    local,domain=value.rsplit('@',1)
    if (not 1<=len(local)<=64 or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+",local)
            or local.startswith('.') or local.endswith('.') or '..' in local):
        raise ValueError('Adresse e-mail invalide.')
    try:domain=domain.encode('idna').decode('ascii').lower()
    except UnicodeError:raise ValueError('Adresse e-mail invalide.') from None
    labels=domain.split('.')
    if len(labels)<2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in labels):
        raise ValueError('Adresse e-mail invalide.')
    email=local+'@'+domain
    if len(email)>254:raise ValueError('Adresse e-mail invalide.')
    return email

class PrivateStore:
    def __getattr__(self,name):
        # No default: a missing authentication context must fail closed.
        return getattr(active_store.get(),name)

class Accounts:
    def __init__(self,root,primary):
        self.root=root;self.primary=primary;self.path=root/'accounts.sqlite'
        self.stores={'primary':primary}
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,admin INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS user_contacts(user_id TEXT PRIMARY KEY REFERENCES users(id),email TEXT NOT NULL,created_at TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)',('primary','piwig',pack(primary.get('password')),1,now()))
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db:yield db
        finally:db.close()
    def store(self,user_id):
        if user_id not in self.stores:
            if not re.fullmatch(r'[0-9a-f]{32}',user_id):raise ValueError('Espace invalide.')
            self.stores[user_id]=Store(self.root/'users'/user_id,seed=False)
        return self.stores[user_id]
    def user(self,username):
        with self.db() as db:r=db.execute('SELECT * FROM users WHERE username=?',(username.lower(),)).fetchone()
        return dict(r) if r else None
    def verify(self,user,password):
        p=json.loads(user['password']) if user else self.primary.get('password')
        valid=secrets.compare_digest(p['hash'],password_hash(password,bytes.fromhex(p['salt'])))
        return bool(user and valid)
    def create(self,username,password,*,email=None,avatar_style=None,language=None):
        from .profile import PROFILE_KEY,ProfilePreferences
        username=username.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}',username):raise ValueError('Identifiant : 3 à 40 lettres, chiffres, tirets ou points.')
        if not 12<=len(password)<=128:raise ValueError('Mot de passe : 12 à 128 caractères.')
        email=normalize_email(email) if email is not None else None
        profile=ProfilePreferences(avatar_style=avatar_style or 'jersey',language=language or 'fr').model_dump() if avatar_style is not None or language is not None else None
        ident=uuid.uuid4().hex;salt=secrets.token_bytes(16)
        directory=self.root/'users'/ident;owned=False
        try:
            with self.db() as db:
                # Serialize the uniqueness check and every identity side effect.
                # A failed store/contact/profile write rolls back the registry too.
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
                    raise UsernameTaken('Cet identifiant est déjà utilisé.')
                hashed=pack({'salt':salt.hex(),'hash':password_hash(password,salt)})
                directory.parent.mkdir(parents=True,exist_ok=True)
                directory.mkdir(exist_ok=False);owned=True
                private=Store(directory,password,seed=False)
                if profile is not None:
                    private.set(PROFILE_KEY,{'revision':1,'profile':profile,'updated_at':now()})
                db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(ident,username,hashed,0,now()))
                if email is not None:
                    db.execute('INSERT INTO user_contacts VALUES(?,?,?)',(ident,email,now()))
        except Exception:
            # Delete only the random directory exclusively created by this call.
            if owned and directory.resolve().parent==(self.root/'users').resolve() and not directory.is_symlink():
                shutil.rmtree(directory)
            raise
        self.stores[ident]=private
        return {'id':ident,'username':username,'admin':False}
    def get_contact(self,user_id):
        with self.db() as db:
            row=db.execute('SELECT email,created_at FROM user_contacts WHERE user_id=?',(user_id,)).fetchone()
        return dict(row) if row else None
    def start_session(self,user_id):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user_id,csrf,int(time.time())+604800))
        return token,csrf
    def session(self,token):
        if not token or len(token)>200:return None
        with self.db() as db:r=db.execute('SELECT s.*,u.username,u.admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        return dict(r) if r else None
    def logout(self,token_hash):
        with self.db() as db:db.execute('DELETE FROM sessions WHERE token=?',(token_hash,))
    def change_password(self,user_id,password):
        salt=secrets.token_bytes(16)
        hashed={'salt':salt.hex(),'hash':password_hash(password,salt)}
        with self.db() as db:
            db.execute('UPDATE users SET password=? WHERE id=?',(pack(hashed),user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        self.store(user_id).set('password',hashed)
    def list_users(self):
        with self.db() as db:return [dict(r) for r in db.execute('SELECT username,admin,created_at FROM users ORDER BY created_at')]
