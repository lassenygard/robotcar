import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

RUN = Path(os.environ.get('ROBOTCAR_RUN', '/run/robotcar'))
DATA = Path(os.environ.get('ROBOTCAR_DATA', '/var/lib/robotcar'))


@contextmanager
def atomic_file(path, mode='wb'):
    """Replace only after complete file contents have reached the filesystem."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, mode) as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_json(path, value):
    with atomic_file(path, 'w') as stream:
        json.dump(value, stream, allow_nan=False, separators=(',', ':'))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def secret(name='ROBOTCAR_TOKEN'):
    value = os.environ.get(name, '')
    if len(value) < 24:
        raise RuntimeError(name + ' must be set to a private random value (24+ characters)')
    return value
