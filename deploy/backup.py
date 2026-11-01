"""Publish complete, consistent SQLite backups without modifying source databases."""
import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import gzip
import os
from pathlib import Path
import re
import sqlite3
import tarfile
import tempfile


STORE_SCHEMA = {
    'kv': {'key', 'value'},
    'teams': {'id', 'name', 'country', 'meta'},
    'snapshots': {'id', 'team_id', 'youth', 'source', 'observed_at', 'imported_at',
                  'digest', 'payload', 'game_date', 'last_observed_at', 'last_source', 'last_game_date'},
    'notes': {'team_id', 'player_id', 'text', 'watch'},
    'plans': {'team_id', 'season', 'grid'},
    'matches': {'id', 'type', 'payload', 'updated_at'},
    'sessions': {'token', 'csrf', 'expires'},
}
ACCOUNT_SCHEMA = {
    'users': {'id', 'username', 'password', 'admin', 'created_at'},
    'sessions': {'token', 'user_id', 'csrf', 'expires'},
    'user_contacts': {'user_id', 'email', 'created_at'},
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def regular_file(path):
    require(path.is_file() and not path.is_symlink(), 'Required regular file is missing')


def read_only_database(path, *, standalone=False):
    regular_file(path)
    # mode=ro includes committed WAL records, unlike immutable=1 on a live store.
    query = '?mode=ro&immutable=1' if standalone else '?mode=ro'
    db = sqlite3.connect(path.resolve().as_uri() + query, uri=True, timeout=15)
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    return db


def inspect_database(db, schema):
    require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLite integrity check failed')
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    require(set(schema) <= tables, 'Required application tables are missing')
    for table, columns in schema.items():
        found = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
        require(columns <= found, 'Required application columns are missing')
    if schema is STORE_SCHEMA:
        require(db.execute("SELECT COUNT(*) FROM kv WHERE key='password'").fetchone()[0] == 1,
                'Required application password record is missing')


def account_ids(path):
    with closing(read_only_database(path, standalone=True)) as db:
        inspect_database(db, ACCOUNT_SCHEMA)
        identifiers = {row[0] for row in db.execute('SELECT id FROM users')}
        require('primary' in identifiers, 'Primary account is missing')
        require(all(value == 'primary' or isinstance(value, str) and re.fullmatch('[0-9a-f]{32}', value)
                    for value in identifiers), 'Invalid private space ID')
        require(db.execute('SELECT COUNT(*) FROM user_contacts c LEFT JOIN users u ON c.user_id=u.id WHERE u.id IS NULL').fetchone()[0] == 0,
                'Account contact refers to a missing account')
        return identifiers


def read_key(path):
    regular_file(path)
    value = path.read_bytes()
    try:
        valid = len(base64.b64decode(value, altchars=b'-_', validate=True)) == 32
    except ValueError:
        valid = False
    require(valid, 'Encryption key format is invalid')
    return value


def validate_data_tree(root):
    identifiers = account_ids(root / 'accounts.sqlite')
    expected = {'accounts.sqlite', 'brt.sqlite', 'encryption.key'}
    totals = dict.fromkeys(('teams', 'snapshots', 'notes', 'plans', 'matches', 'kv'), 0)
    for ident in sorted(identifiers):
        directory = root if ident == 'primary' else root / 'users' / ident
        read_key(directory / 'encryption.key')  # Encoding only; no credentials are decrypted.
        with closing(read_only_database(directory / 'brt.sqlite', standalone=True)) as db:
            inspect_database(db, STORE_SCHEMA)
            for table in totals:
                totals[table] += db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
        if ident != 'primary':
            expected.update({f'users/{ident}/brt.sqlite', f'users/{ident}/encryption.key'})
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
    require(actual == expected, 'Backup files do not match the account registry')
    return {'stores_verified': len(identifiers), 'row_counts': totals,
            'key_encoding_valid': True, 'credentials_decrypted': False}


def archive_timestamp(path):
    match = re.fullmatch(r'brt-(\d{8}T\d{6})(\d{0,6})Z\.tar\.gz', path.name)
    require(match is not None, 'Unrecognized backup archive name')
    return datetime.strptime(match[1], '%Y%m%dT%H%M%S').replace(
        microsecond=int(match[2].ljust(6, '0') or '0'), tzinfo=timezone.utc)


def check_compressed_archive(path):
    # Tar can stop at its end markers without reading the gzip checksum/trailer.
    with gzip.open(path, 'rb') as stream:
        while stream.read(1024 * 1024):
            pass


def create_backup(root, destination):
    root, destination = Path(root), Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    old_mask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(dir=destination) as temporary:
            temp = Path(temporary)
            data = temp / 'data'
            data.mkdir(mode=0o700)

            def copy_database(relative, schema):
                saved = data / relative
                saved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with closing(read_only_database(root / relative)) as source, closing(sqlite3.connect(saved)) as target:
                    inspect_database(source, schema)
                    source.backup(target)
                    # Only the private copy changes journal mode. Every committed
                    # record is already in this standalone backup, including WAL.
                    target.execute('PRAGMA journal_mode=DELETE')
                    inspect_database(target, schema)
                if schema is STORE_SCHEMA:
                    (saved.parent / 'encryption.key').write_bytes(read_key((root / relative).parent / 'encryption.key'))

            copy_database(Path('accounts.sqlite'), ACCOUNT_SCHEMA)
            identifiers = account_ids(data / 'accounts.sqlite')
            copy_database(Path('brt.sqlite'), STORE_SCHEMA)
            for ident in sorted(identifiers - {'primary'}):
                copy_database(Path('users') / ident / 'brt.sqlite', STORE_SCHEMA)
            validate_data_tree(data)
            staged = temp / 'archive.tar.gz'
            with tarfile.open(staged, 'w:gz') as output:
                for path in sorted(data.rglob('*')):
                    if path.is_file():
                        output.add(path, arcname=path.relative_to(data).as_posix())
            with staged.open('r+b') as stream:
                os.fsync(stream.fileno())
            check_compressed_archive(staged)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            archive = destination / f'brt-{stamp}.tar.gz'
            # An atomic hard link publishes only the finished file and refuses
            # collisions, preserving every existing archive on write failure.
            os.link(staged, archive)
        for old in sorted(destination.glob('brt-*.tar.gz'), key=archive_timestamp, reverse=True)[30:]:
            old.unlink()
        return archive
    finally:
        os.umask(old_mask)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('/var/lib/brt'))
    parser.add_argument('--destination', type=Path, default=Path('/opt/brt/backups'))
    args = parser.parse_args()
    create_backup(args.data_root, args.destination)
    print('BRT backup created; account inventory, SQLite schema/integrity and key files checked.')


if __name__ == '__main__':
    main()
