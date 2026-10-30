"""Package committed sources and built frontend, never local databases or keys."""
import argparse
import hashlib
import io
import subprocess
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    dist = root / 'web' / 'dist'
    if not (dist / 'index.html').is_file():
        raise SystemExit('Build the frontend before packaging.')
    # git archive otherwise follows core.autocrlf on Windows and breaks bash.
    source_bytes = subprocess.check_output(['git', '-c', 'core.autocrlf=false', 'archive', 'HEAD'], cwd=root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(source_bytes)) as source, tarfile.open(args.output, 'w:gz') as output:
        for member in source:
            if member.name.startswith(('data/', 'private-source/', 'review/')) or member.name == '.env':
                raise SystemExit('Private data was unexpectedly tracked; archive refused.')
            if member.isfile():
                content = source.extractfile(member).read()
                if member.name.endswith(('.sh', '.service', '.timer', '.conf')):
                    content = content.replace(b'\r\n', b'\n')
                    member.size = len(content)
                output.addfile(member, io.BytesIO(content))
            else:
                output.addfile(member)
        output.add(dist, arcname='web/dist')
    print(args.output.name, hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
