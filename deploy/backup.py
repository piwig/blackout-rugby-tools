"""Consistent local SQLite backup, including the encryption key for recovery."""
import os,sqlite3,shutil,tarfile,tempfile
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

root=Path('/var/lib/brt');destination=Path('/opt/brt/backups');destination.mkdir(mode=0o700,parents=True,exist_ok=True)
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
os.umask(0o077)
with tempfile.TemporaryDirectory(dir=destination) as temporary:
    temp=Path(temporary)
    def copy_database(database):
        saved=temp/database.relative_to(root);saved.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(database)) as source,closing(sqlite3.connect(saved)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite backup integrity check failed')
        if database.name=='brt.sqlite':shutil.copy2(database.parent/'encryption.key',saved.parent/'encryption.key')
    databases=[root/'brt.sqlite']
    if (root/'accounts.sqlite').exists():
        copy_database(root/'accounts.sqlite')
        with closing(sqlite3.connect(temp/'accounts.sqlite')) as registry:
            for ident, in registry.execute("SELECT id FROM users WHERE id!='primary'"):
                if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):raise RuntimeError('Invalid private space ID')
                database=root/'users'/ident/'brt.sqlite'
                if not database.is_file():raise RuntimeError('Private space missing from backup')
                databases.append(database)
    for database in databases:copy_database(database)
    archive=destination/f'brt-{stamp}.tar.gz'
    with tarfile.open(archive,'w:gz') as output:
        for path in sorted(temp.rglob('*')):
            if path.is_file():output.add(path,arcname=path.relative_to(temp).as_posix())
for old in sorted(destination.glob('brt-*.tar.gz'),reverse=True)[30:]:old.unlink()
print('BRT backup created, SQLite integrity checked.')
