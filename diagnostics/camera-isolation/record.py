"""Preserve the last actual frame time even when systemd kills a stuck capture."""
import json
import os
from pathlib import Path
import sys
import time

name = sys.argv[1]
if name not in ('front', 'rear'):
    raise SystemExit('Unknown camera')
source = Path('/run/robotcar-camera-test') / (name + '.json')
if source.exists():
    state = json.loads(source.read_text())
    state.update(stopped_at=time.time(), service_result=os.getenv('SERVICE_RESULT'),
                 exit_code=os.getenv('EXIT_CODE'), exit_status=os.getenv('EXIT_STATUS'))
    target = Path('/var/lib/robotcar-camera-test') / (state['boot_id']+'-'+name+'-stopped.json')
    temporary = target.with_suffix('.next')
    temporary.write_text(json.dumps(state) + '\n')
    os.replace(temporary, target)
