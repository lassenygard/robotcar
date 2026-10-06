"""Durable, verified releases; a power cut must not overwrite the active code."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


FOLDERS = ('robotcar', 'deploy', 'tests', 'scripts', 'docs')
FILES = ('README.md', 'requirements-runtime.txt', 'REVISION')


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        stream.write(content)
        os.fchmod(stream.fileno(), 0o644)
        stream.flush()
        os.fsync(stream.fileno())


def source_files(source):
    result = {}
    paths = [source/name for name in FILES if (source/name).is_file()]
    for name in FOLDERS:
        paths.extend(p for p in (source/name).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo'))
    for path in paths:
        if path.is_symlink():
            raise ValueError(f'Release source may not contain symlinks: {path}')
        relative = path.relative_to(source).as_posix()
        data = path.read_bytes()
        if path.suffix == '.py':
            if not data.strip():
                raise ValueError(f'Empty Python source: {relative}')
            compile(data, relative, 'exec')
        result[relative] = data
    required = {'robotcar/'+name+'.py' for name in
                ('__init__', 'common', 'motor', 'camera', 'lidar', 'lidarfeed', 'vision', 'mapping', 'mapworker', 'navigation', 'webapp')}
    if not required.issubset(result):
        raise ValueError('Release is missing required robotcar modules')
    return result


def verify_release(release):
    manifest = json.loads((release/'MANIFEST.json').read_text())
    for name, digest in manifest.items():
        path = release/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Release checksum mismatch: {name}')
    return manifest


def stage_release(source, root):
    files = source_files(Path(source))
    manifest = {name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    name = hashlib.sha256(encoded).hexdigest()[:20]
    releases = Path(root)/'releases'
    releases.mkdir(parents=True, exist_ok=True)
    releases.chmod(0o755)
    sync_directory(releases.parent)
    destination = releases/name
    if destination.exists():
        if verify_release(destination) != manifest:
            raise ValueError('Existing release manifest does not match source')
        return destination
    staging = Path(tempfile.mkdtemp(prefix='.stage-', dir=releases))
    staging.chmod(0o755)
    try:
        for relative, content in files.items():
            write_file(staging/relative, content)
        write_file(staging/'MANIFEST.json', encoded)
        for directory in sorted((p for p in staging.rglob('*') if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
            directory.chmod(0o755)
            sync_directory(directory)
        sync_directory(staging)
        verify_release(staging)
        os.replace(staging, destination)
        sync_directory(releases)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def activate_release(release, root):
    root, release = Path(root).resolve(), Path(release).resolve()
    if release.parent != root/'releases':
        raise ValueError('Release must be inside the installation release directory')
    verify_release(release)
    temporary = root/'.current-next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release.relative_to(root))
    os.replace(temporary, root/'current')
    sync_directory(root)
    # The manifest in current/ is authoritative, even if this status file is old.
    revision = (release/'REVISION').read_bytes() if (release/'REVISION').exists() else (release.name+'\n').encode()
    write_file(root/'.REVISION-next', revision)
    os.replace(root/'.REVISION-next', root/'REVISION')
    sync_directory(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('stage', 'activate', 'verify'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--root', type=Path, default=Path('/opt/robotcar'))
    args = parser.parse_args()
    if args.operation == 'stage':
        print(stage_release(args.path, args.root))
    elif args.operation == 'activate':
        activate_release(args.path, args.root)
    else:
        verify_release(args.path)
