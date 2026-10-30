"""Restore a brt-tagged offsite snapshot to a temporary directory and verify it."""
import json,sqlite3,subprocess,tarfile,tempfile
from pathlib import Path
from cryptography.fernet import Fernet

with tempfile.TemporaryDirectory(prefix='brt-restore-',dir='/var/tmp') as folder:
    root=Path(folder)
    subprocess.run(['restic','restore','latest','--tag','brt','--target',folder,'--quiet'],check=True)
    archives=sorted((root/'opt/brt/backups').glob('brt-*.tar.gz'))
    assert archives,'No backup archive found'
    with tarfile.open(archives[-1]) as archive:
        for name in ('brt.sqlite','encryption.key'):
            member=archive.extractfile(name)
            assert member is not None
            (root/name).write_bytes(member.read())
    cipher=Fernet((root/'encryption.key').read_bytes())
    with sqlite3.connect(root/'brt.sqlite') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for value, in db.execute("SELECT value FROM kv WHERE key='api_developer' OR key LIKE 'api_member:%'"):
            assert isinstance(json.loads(cipher.decrypt(json.loads(value).encode())),dict)
        assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0]>=4
    assert list((root/'opt/brt/source').glob('*.tar.gz'))
print('Offsite restoration: SQLite integrity, encrypted credentials and source archive OK')
