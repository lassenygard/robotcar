import json
import os
import tempfile
from pathlib import Path

RUN = Path(os.environ.get('ROBOTCAR_RUN', '/run/robotcar'))
DATA = Path(os.environ.get('ROBOTCAR_DATA', '/var/lib/robotcar'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, allow_nan=False, separators=(',', ':'))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


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
