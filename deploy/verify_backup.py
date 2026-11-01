"""Verify a restored offsite snapshot without starting BRT or decrypting credentials."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import unquote, urlsplit

if __package__:
    from .backup import archive_timestamp, check_compressed_archive, regular_file, require, validate_data_tree
else:
    from backup import archive_timestamp, check_compressed_archive, regular_file, require, validate_data_tree


def safe_member(member):
    path = PurePosixPath(member.name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in member.name
            and (member.isfile() or member.isdir()), 'Unsafe archive member')
    return path


def verify_archive(path, *, temp_parent=None, max_age_hours=36):
    regular_file(path)
    check_compressed_archive(path)
    age = (datetime.now(timezone.utc) - archive_timestamp(path)).total_seconds() / 3600
    require(0 < max_age_hours and -0.1 <= age <= max_age_hours, 'Backup is outside the selected freshness window')
    with tempfile.TemporaryDirectory(prefix='brt-data-check-', dir=temp_parent) as temporary:
        root = Path(temporary)
        with tarfile.open(path, 'r:gz') as archive:
            members = archive.getmembers()
            names = set()
            for member in members:
                name = safe_member(member)
                require(member.isfile() and name.as_posix() == member.name, 'Unexpected data archive member')
                require(member.name in ('brt.sqlite', 'accounts.sqlite', 'encryption.key')
                        or re.fullmatch(r'users/[0-9a-f]{32}/(?:brt\.sqlite|encryption\.key)', member.name),
                        'Unexpected data archive path')
                require(member.name not in names, 'Duplicate data archive member')
                names.add(member.name)
            require({'brt.sqlite', 'accounts.sqlite', 'encryption.key'} <= names, 'Required data archive members are missing')
            for member in members:
                target = root.joinpath(*PurePosixPath(member.name).parts)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('xb') as saved:
                    shutil.copyfileobj(source, saved)
        result = validate_data_tree(root)
    return {**result, 'archive_age_hours': round(age, 2), 'sqlite_integrity': 'ok', 'core_schema': 'ok'}


def verify_source_archive(path):
    regular_file(path)
    check_compressed_archive(path)
    required = {'server/main.py', 'server/storage.py', 'server/accounts.py', 'web/dist/index.html',
                'requirements.txt', 'deploy/brt.service', 'deploy/backup.py', 'deploy/verify_backup.py'}
    names = set()
    nonempty = set()
    index = None
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            name = safe_member(member).as_posix()
            if member.isfile():
                require(name not in names, 'Duplicate source archive member')
                names.add(name)
                if member.size > 0:
                    nonempty.add(name)
                if name in required:
                    require(member.size > 0, 'Required source file is empty')
                # Read the whole payload, without extracting or executing it.
                with archive.extractfile(member) as source:
                    if name == 'web/dist/index.html':
                        require(member.size <= 1024 * 1024, 'Frontend index exceeds verification limit')
                        index = source.read().decode('utf-8')
                    else:
                        while source.read(1024 * 1024):
                            pass
    require(required <= names, 'Required source/build files are missing')
    class IndexAssets(HTMLParser):
        def handle_starttag(self, tag, attributes):
            attributes = dict(attributes)
            reference = attributes.get('src') if tag in ('script', 'img', 'source') else attributes.get('href') if tag == 'link' else None
            if not reference:
                return
            parsed = urlsplit(reference)
            if parsed.scheme or parsed.netloc or not parsed.path:
                return
            asset = PurePosixPath(unquote(parsed.path).lstrip('/'))
            require('..' not in asset.parts and '\\' not in str(asset), 'Unexpected frontend asset path')
            require('web/dist/' + asset.as_posix() in nonempty, 'Referenced frontend asset is missing or empty')
    parser = IndexAssets()
    parser.feed(index)
    parser.close()


def verify_snapshot(root, *, max_age_hours=36, temp_parent=None):
    root = Path(root)
    archives = list((root / 'opt/brt/backups').glob('brt-*.tar.gz'))
    require(archives, 'No backup archive found')
    result = verify_archive(max(archives, key=archive_timestamp), temp_parent=temp_parent, max_age_hours=max_age_hours)
    sources = list((root / 'opt/brt/source').glob('*.tar.gz'))
    require(sources, 'No source archive found')
    # Release names include a commit, not a chronological sequence within a day.
    verify_source_archive(max(sources, key=lambda path: (path.stat().st_mtime_ns, path.name)))
    for name in ('contact.env', 'security.env'):
        path = root / 'etc/brt' / name
        regular_file(path)
        require(path.stat().st_size > 0, 'Required server configuration is empty')
    return {**result, 'source_archive': 'ok', 'server_configuration_files': 'present', 'app_started': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--restored-root', type=Path, help='Verify an already restored, isolated snapshot; no network')
    mode.add_argument('--archive', type=Path, help='Verify one local data archive only; no network or source/config check')
    parser.add_argument('--temp-parent', type=Path, default=Path('/var/tmp'))
    parser.add_argument('--max-age-hours', type=float, default=36)
    args = parser.parse_args()
    options = {'temp_parent': args.temp_parent, 'max_age_hours': args.max_age_hours}
    if args.archive:
        result = {'mode': 'data-archive-only', **verify_archive(args.archive, **options)}
    elif args.restored_root:
        result = {'mode': 'offsite-snapshot', **verify_snapshot(args.restored_root, **options)}
    else:
        with tempfile.TemporaryDirectory(prefix='brt-restore-', dir=args.temp_parent) as folder:
            subprocess.run(['restic', 'restore', 'latest', '--tag', 'brt', '--target', folder, '--quiet'], check=True)
            result = {'mode': 'offsite-snapshot', **verify_snapshot(Path(folder), **options)}
    print(json.dumps({'ok': True, **result}))


if __name__ == '__main__':
    main()
