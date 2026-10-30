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
        for member in archive.getmembers():
            name=Path(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert name.name in ('brt.sqlite','accounts.sqlite','encryption.key')
            path=root/'restored'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
    data=root/'restored'
    for database in data.rglob('*.sqlite'):
        with sqlite3.connect(database) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            if database.name=='brt.sqlite':
                cipher=Fernet((database.parent/'encryption.key').read_bytes())
                for value, in db.execute("SELECT value FROM kv WHERE key IN ('api_developer','api_developer_pending','api_developer_previous_20261030','api_manager') OR key LIKE 'api_member:%'"):
                    assert isinstance(json.loads(cipher.decrypt(json.loads(value).encode())),dict)
            else:
                for ident, in db.execute("SELECT id FROM users WHERE id!='primary'"):
                    assert (data/'users'/ident/'brt.sqlite').is_file()
    assert list((root/'opt/brt/source').glob('*.tar.gz'))
    # Recent releases also retain server-only SMTP/CAPTCHA configuration.
    config=root/'etc/brt'
    if config.exists():
        assert (config/'contact.env').is_file() and (config/'security.env').is_file()
print('Offsite restoration: SQLite integrity, encrypted credentials and source archive OK')
