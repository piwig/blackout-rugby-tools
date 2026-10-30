"""Consistent local SQLite backup, including the encryption key for recovery."""
import os,sqlite3,shutil,tarfile,tempfile
from datetime import datetime,timezone
from pathlib import Path

root=Path('/var/lib/brt');destination=Path('/opt/brt/backups');destination.mkdir(mode=0o700,parents=True,exist_ok=True)
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
os.umask(0o077)
with tempfile.TemporaryDirectory(dir=destination) as temporary:
    temp=Path(temporary)
    with sqlite3.connect(root/'brt.sqlite') as source,sqlite3.connect(temp/'brt.sqlite') as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite backup integrity check failed')
    shutil.copy2(root/'encryption.key',temp/'encryption.key')
    archive=destination/f'brt-{stamp}.tar.gz'
    with tarfile.open(archive,'w:gz') as output:
        for name in ['brt.sqlite','encryption.key']:output.add(temp/name,arcname=name)
for old in sorted(destination.glob('brt-*.tar.gz'),reverse=True)[30:]:old.unlink()
print('BRT backup created, SQLite integrity checked.')
