"""Exercise deployment backup scripts with synthetic SQLite and fake Restic I/O."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile
import tempfile

from cryptography.fernet import Fernet
import pytest


DEPLOY = Path(__file__).resolve().parents[1] / 'deploy'
PRIVATE_ID = 'a' * 32


def make_store(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'encryption.key').write_bytes(Fernet.generate_key())
    with closing(sqlite3.connect(root / 'brt.sqlite')) as db:
        db.executescript('''
          CREATE TABLE kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          INSERT INTO kv VALUES('password','{"salt":"synthetic","hash":"synthetic"}');
          CREATE TABLE teams(id TEXT PRIMARY KEY,name TEXT,country TEXT,meta TEXT);
          CREATE TABLE snapshots(id INTEGER PRIMARY KEY,team_id TEXT,youth INTEGER,source TEXT,
            observed_at TEXT,imported_at TEXT,digest TEXT,payload TEXT,game_date TEXT,
            last_observed_at TEXT,last_source TEXT,last_game_date TEXT);
          CREATE TABLE notes(team_id TEXT,player_id TEXT,text TEXT,watch INTEGER);
          CREATE TABLE plans(team_id TEXT,season INTEGER,grid TEXT);
          CREATE TABLE matches(id TEXT,type INTEGER,payload TEXT,updated_at TEXT);
          CREATE TABLE sessions(token TEXT,csrf TEXT,expires INTEGER);
          INSERT INTO notes VALUES('1','2','Synthetic recovery note',1);
        ''')
        db.commit()


def make_data(root):
    make_store(root)
    make_store(root / 'users' / PRIVATE_ID)
    with closing(sqlite3.connect(root / 'accounts.sqlite')) as db:
        db.executescript('''
          CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,password TEXT,admin INTEGER,created_at TEXT);
          CREATE TABLE sessions(token TEXT,user_id TEXT,csrf TEXT,expires INTEGER);
          CREATE TABLE user_contacts(user_id TEXT,email TEXT,created_at TEXT);
        ''')
        db.executemany('INSERT INTO users VALUES(?,?,?,?,?)', [
            ('primary', 'synthetic-admin', '{}', 1, '2026-01-01'),
            (PRIVATE_ID, 'synthetic-manager', '{}', 0, '2026-01-01')])
        db.commit()


def run_entry(name, root, destination, monkeypatch, *, restored=None):
    # Legacy scripts ran on import. Redirect their fixed roots before executing,
    # so the same regression tests safely exercise both old and corrected code.
    source = (DEPLOY / name).read_text(encoding='utf-8')
    source = source.replace("'/var/lib/brt'", repr(str(root)))
    source = source.replace("'/opt/brt/backups'", repr(str(destination)))
    source = source.replace("'/var/tmp'", repr(str(root.parent)))
    monkeypatch.setattr(sys, 'argv', [str(DEPLOY / name)])
    connections = []
    real_connect = sqlite3.connect
    real_tempdir = tempfile.TemporaryDirectory
    def connect(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        connections.append(db)
        return db
    class ClosingTempdir:
        def __init__(self, *args, **kwargs):
            self.manager = real_tempdir(*args, **kwargs)
        def __enter__(self):
            return self.manager.__enter__()
        def __exit__(self, *args):
            # Original verifier left handles open; Linux permits unlinking them.
            for db in connections:
                db.close()
            return self.manager.__exit__(*args)
    def restic(command, *, check):
        if restored is None or command[:3] != ['restic', 'restore', 'latest'] or not check:
            raise AssertionError('Unexpected external command')
        target = Path(command[command.index('--target') + 1])
        shutil.copytree(restored, target, dirs_exist_ok=True)
    with monkeypatch.context() as isolated:
        isolated.setattr(sqlite3, 'connect', connect)
        isolated.setattr(tempfile, 'TemporaryDirectory', ClosingTempdir)
        isolated.setattr('subprocess.run', restic)
        try:
            exec(compile(source, str(DEPLOY / name), 'exec'),
                 {'__name__': '__main__', '__file__': str(DEPLOY / name), '__package__': 'deploy'})
        finally:
            for db in connections:
                db.close()


def snapshot(root, data, *, missing=(), source_valid=True, stamp=None):
    backups = root / 'opt/brt/backups'
    backups.mkdir(parents=True)
    stamp = stamp or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive = backups / ('brt-' + stamp + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as output:
        for path in sorted(data.rglob('*')):
            name = path.relative_to(data).as_posix()
            if path.is_file() and name not in missing:
                output.add(path, arcname=name)
    sources = root / 'opt/brt/source'
    sources.mkdir(parents=True)
    code = sources / 'brt-20261101-abcdef1.tar.gz'
    if source_valid:
        with tarfile.open(code, 'w:gz') as output:
            for name in ('server/main.py', 'server/storage.py', 'server/accounts.py',
                         'web/dist/index.html', 'requirements.txt', 'deploy/brt.service',
                         'deploy/backup.py', 'deploy/verify_backup.py'):
                value = b'Synthetic source\n'
                member = tarfile.TarInfo(name)
                member.size = len(value)
                output.addfile(member, io.BytesIO(value))
    else:
        code.write_bytes(b'not an archive')
    config = root / 'etc/brt'
    config.mkdir(parents=True)
    for name in ('contact.env', 'security.env'):
        (config / name).write_text('SYNTHETIC_TEST=1\n', encoding='utf-8')
    return archive


@pytest.mark.parametrize('missing', ['accounts.sqlite', 'brt.sqlite', 'encryption.key',
                                    'users/' + PRIVATE_ID + '/brt.sqlite'])
def test_backup_refuses_missing_required_source_without_creating_it(tmp_path, monkeypatch, missing):
    data, destination = tmp_path / 'data', tmp_path / 'backups'
    make_data(data)
    absent = data / missing
    absent.unlink()
    with pytest.raises((RuntimeError, ValueError, OSError, sqlite3.DatabaseError)):
        run_entry('backup.py', data, destination, monkeypatch)
    assert not absent.exists()
    assert not list(destination.glob('brt-*.tar.gz'))


def test_backup_refuses_incomplete_schema(tmp_path, monkeypatch):
    data, destination = tmp_path / 'data', tmp_path / 'backups'
    make_data(data)
    with closing(sqlite3.connect(data / 'brt.sqlite')) as db:
        db.execute('DROP TABLE snapshots')
        db.commit()
    with pytest.raises((RuntimeError, ValueError, sqlite3.DatabaseError)):
        run_entry('backup.py', data, destination, monkeypatch)
    assert not list(destination.glob('brt-*.tar.gz'))


def test_backup_captures_committed_wal_without_changing_source_and_preserves_keys(tmp_path, monkeypatch, capsys):
    data, destination = tmp_path / 'data', tmp_path / 'backups'
    make_data(data)
    with closing(sqlite3.connect(data / 'brt.sqlite')) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO notes VALUES('3','4','WAL-only recovery note',0)")
        db.commit()
        watched = [data / 'brt.sqlite', data / 'brt.sqlite-wal', data / 'accounts.sqlite']
        before = [hashlib.sha256(path.read_bytes()).digest() for path in watched]
        run_entry('backup.py', data, destination, monkeypatch)
        assert before == [hashlib.sha256(path.read_bytes()).digest() for path in watched]
    archive, = destination.glob('brt-*.tar.gz')
    with tarfile.open(archive) as saved:
        assert set(saved.getnames()) == {'brt.sqlite', 'accounts.sqlite', 'encryption.key',
            'users/' + PRIVATE_ID + '/brt.sqlite', 'users/' + PRIVATE_ID + '/encryption.key'}
        assert saved.extractfile('encryption.key').read() == (data / 'encryption.key').read_bytes()
        restored = tmp_path / 'copy.sqlite'
        restored.write_bytes(saved.extractfile('brt.sqlite').read())
    with closing(sqlite3.connect(restored)) as db:
        assert db.execute('SELECT text FROM notes ORDER BY team_id').fetchall() == [
            ('Synthetic recovery note',), ('WAL-only recovery note',)]
    output = capsys.readouterr().out
    assert 'Synthetic recovery note' not in output
    assert (data / 'encryption.key').read_text() not in output


def test_failed_archive_write_leaves_previous_backup_unchanged_and_no_partial_published(tmp_path, monkeypatch):
    data, destination = tmp_path / 'data', tmp_path / 'backups'
    make_data(data)
    run_entry('backup.py', data, destination, monkeypatch)
    previous = {path.name: path.read_bytes() for path in destination.glob('brt-*.tar.gz')}
    def fail_write(*args, **kwargs):
        raise OSError('Synthetic storage failure')
    monkeypatch.setattr(tarfile.TarFile, 'add', fail_write)
    with pytest.raises(OSError):
        run_entry('backup.py', data, destination, monkeypatch)
    assert {path.name: path.read_bytes() for path in destination.glob('brt-*.tar.gz')} == previous


@pytest.mark.parametrize('missing', [
    ('brt.sqlite', 'accounts.sqlite', 'encryption.key',
     'users/' + PRIVATE_ID + '/brt.sqlite', 'users/' + PRIVATE_ID + '/encryption.key'),
    ('brt.sqlite', 'encryption.key'),
    ('accounts.sqlite',),
    ('users/' + PRIVATE_ID + '/brt.sqlite',),
])
def test_restore_refuses_incomplete_archive(tmp_path, monkeypatch, missing):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    snapshot(restored, data, missing=missing)
    with pytest.raises((RuntimeError, ValueError, OSError, AssertionError)):
        run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)


def test_restore_refuses_schema_missing_application_data_tables(tmp_path, monkeypatch):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    with closing(sqlite3.connect(data / 'brt.sqlite')) as db:
        db.execute('DROP TABLE snapshots')
        db.commit()
    snapshot(restored, data)
    with pytest.raises((RuntimeError, ValueError, sqlite3.DatabaseError)):
        run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)


@pytest.mark.parametrize('problem', ['invalid-code', 'missing-code', 'missing-config', 'empty-config', 'stale-data'])
def test_restore_refuses_incomplete_disaster_recovery_material(tmp_path, monkeypatch, problem):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    snapshot(restored, data, source_valid=problem != 'invalid-code',
             stamp='20200101T000000Z' if problem == 'stale-data' else None)
    if problem == 'missing-code':
        for source in (restored / 'opt/brt/source').glob('*.tar.gz'):
            source.unlink()
    if problem == 'missing-config':
        shutil.rmtree(restored / 'etc/brt')
    if problem == 'empty-config':
        (restored / 'etc/brt/security.env').write_bytes(b'')
    with pytest.raises((RuntimeError, ValueError, OSError, AssertionError, tarfile.TarError)):
        run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)


def test_restore_accepts_existing_archive_layout_without_decrypting_credentials(tmp_path, monkeypatch, capsys):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    key = (data / 'encryption.key').read_bytes()
    value = Fernet(key).encrypt(b'{"m":"synthetic-member","mk":"synthetic-secret"}').decode()
    with closing(sqlite3.connect(data / 'brt.sqlite')) as db:
        db.execute('INSERT INTO kv VALUES(?,?)', ('api_manager', json.dumps(value)))
        db.commit()
    snapshot(restored, data)
    def forbidden_decrypt(*args, **kwargs):
        raise RuntimeError('Credentials must not be decrypted by the recovery check')
    monkeypatch.setattr(Fernet, 'decrypt', forbidden_decrypt)
    run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)
    output = capsys.readouterr().out
    assert 'synthetic-secret' not in output and value not in output and key.decode() not in output


@pytest.mark.parametrize('target', ['data', 'code'])
def test_restore_rejects_truncated_gzip_even_when_tar_members_are_readable(tmp_path, monkeypatch, target):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    archive = snapshot(restored, data)
    if target == 'code':
        archive, = (restored / 'opt/brt/source').glob('*.tar.gz')
    archive.write_bytes(archive.read_bytes()[:-8])
    with pytest.raises((RuntimeError, ValueError, EOFError, OSError, tarfile.TarError)):
        run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)


@pytest.mark.parametrize('problem', ['unknown-account', 'missing-column', 'invalid-key', 'missing-build'])
def test_restore_refuses_logically_incomplete_material(tmp_path, monkeypatch, problem):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    if problem == 'unknown-account':
        with closing(sqlite3.connect(data / 'accounts.sqlite')) as db:
            db.execute('DELETE FROM users WHERE id=?', (PRIVATE_ID,))
            db.commit()
    if problem == 'missing-column':
        with closing(sqlite3.connect(data / 'brt.sqlite')) as db:
            db.execute('ALTER TABLE snapshots DROP COLUMN last_source')
            db.commit()
    if problem == 'invalid-key':
        (data / 'encryption.key').write_bytes(b'synthetic-invalid-key')
    snapshot(restored, data)
    if problem == 'missing-build':
        code, = (restored / 'opt/brt/source').glob('*.tar.gz')
        with tarfile.open(code, 'w:gz') as archive:
            value = b'Only a source file, without the built frontend\n'
            item = tarfile.TarInfo('server/main.py')
            item.size = len(value)
            archive.addfile(item, io.BytesIO(value))
    with pytest.raises((RuntimeError, ValueError, OSError, sqlite3.DatabaseError)):
        run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)


def test_restore_accepts_legacy_standalone_wal_header_without_writing_archive(tmp_path, monkeypatch):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    with closing(sqlite3.connect(data / 'brt.sqlite')) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO notes VALUES('3','4','Legacy standalone WAL header',0)")
        db.commit()
    archive = snapshot(restored, data)
    original = archive.read_bytes()
    run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)
    assert archive.read_bytes() == original


def test_repeated_timestamp_never_overwrites_an_existing_archive(tmp_path, monkeypatch):
    from deploy import backup
    data, destination = tmp_path / 'data', tmp_path / 'backups'
    make_data(data)
    clock = datetime.now(timezone.utc)
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock
    monkeypatch.setattr(backup, 'datetime', FixedDatetime)
    first = backup.create_backup(data, destination)
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        backup.create_backup(data, destination)
    assert first.read_bytes() == original
    assert list(destination.glob('brt-*.tar.gz')) == [first]


def test_retention_keeps_thirty_archives_and_orders_both_timestamp_formats(tmp_path):
    from deploy import backup
    data, destination = tmp_path / 'data', tmp_path / 'backups'
    make_data(data)
    destination.mkdir()
    oldest = destination / 'brt-20200101T000000Z.tar.gz'
    for day in range(1, 31):
        (destination / f'brt-202001{day:02d}T000000Z.tar.gz').write_bytes(b'Previous synthetic archive')
    newest = backup.create_backup(data, destination)
    assert newest.exists() and not oldest.exists()
    assert len(list(destination.glob('brt-*.tar.gz'))) == 30


@pytest.mark.parametrize('missing', ['assets/app.js', 'assets/app.css', None])
def test_restore_checks_local_assets_referenced_by_source_index(tmp_path, monkeypatch, missing):
    data, restored = tmp_path / 'data', tmp_path / 'snapshot'
    make_data(data)
    snapshot(restored, data)
    code, = (restored / 'opt/brt/source').glob('*.tar.gz')
    with tarfile.open(code) as archive:
        contents = {member.name: archive.extractfile(member).read() for member in archive if member.isfile()}
    contents['web/dist/index.html'] = b'''<!doctype html><html><head>
      <script type="module" src="/assets/app.js?v=1"></script>
      <link rel="stylesheet" href="./assets/app.css#main">
      <script src="https://external.invalid/public.js"></script>
      </head><body></body></html>'''
    for name in ('assets/app.js', 'assets/app.css'):
        if name != missing:
            contents['web/dist/' + name] = b'Synthetic asset'
    with tarfile.open(code, 'w:gz') as archive:
        for name, value in contents.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))
    if missing:
        with pytest.raises(RuntimeError):
            run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)
    else:
        run_entry('verify_backup.py', data, tmp_path / 'unused', monkeypatch, restored=restored)
