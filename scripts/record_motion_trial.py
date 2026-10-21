"""Record ONE short, explicitly requested manual wheel pulse through HTTPS/WSS.

Use only after inspecting the surroundings and commissioning the motor service.
The operator must review each trial before choosing the next direction. This
tool does not enable autonomy, remove motor inhibits, or bypass the gateway.
One drive command is sent: the server's independent 0.3 s lease bounds the
pulse if this process or the network fails. No lease renewal is performed.
"""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import time

from aiohttp import ClientSession, ClientTimeout, WSMsgType


DIRECTIONS = {'forward': (1, 1), 'backward': (-1, -1),
              'counterclockwise': (-1, 1), 'clockwise': (1, -1)}


async def trial(args):
    if not args.drive:
        raise ValueError('A physical trial requires --drive. Use record_video.py for recording only.')
    if not args.url.startswith('https://'):
        raise ValueError('HTTPS is required.')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= .25:
        raise ValueError('A single trial must be at most 0.25 s; no lease renewals are sent.')
    if not math.isfinite(args.speed) or not 0 < args.speed <= .3:
        raise ValueError('Trial speed must be in (0, 0.3].')
    os.umask(0o077)
    output = args.output.resolve()
    ready = output.with_suffix('.ready.json')
    evidence = output.with_suffix('.motion.json')
    if any(p.exists() for p in (output, output.with_suffix('.json'), ready, evidence)):
        raise ValueError('Choose new filenames for each trial.')
    output.parent.mkdir(parents=True, exist_ok=True)
    credentials = dict(l.split('=', 1) for l in args.credentials.read_text().splitlines() if '=' in l)
    events, state, errors = [], {}, []
    acks = asyncio.Queue()
    recorder = receiver = None
    arm_attempted = False
    base = args.url.rstrip('/')

    def event(name, **details):
        events.append(dict(event=name, monotonic=time.monotonic(), time=time.time(), **details))

    async with ClientSession(timeout=ClientTimeout(total=10)) as http:
        async with http.post(base+'/login', data=credentials, allow_redirects=False) as response:
            if response.status != 302:
                raise ValueError('Login failed.')
        async with http.ws_connect(base+'/ws', origin=base, heartbeat=2) as ws:
            async def receive():
                nonlocal state
                async for message in ws:
                    if message.type != WSMsgType.TEXT:
                        continue
                    data = json.loads(message.data)
                    if data.get('type') == 'state':
                        state = dict(data, received=time.monotonic())
                    elif data.get('type') == 'ack':
                        await acks.put(data['action'])
                    elif data.get('type') == 'error':
                        errors.append(data['error'])

            async def send(action, **values):
                event('send', action=action)
                await ws.send_json(dict(action=action, **values))
                ack = await asyncio.wait_for(acks.get(), .7)
                if ack != action:
                    raise ValueError('Unexpected acknowledgement.')
                event('ack', action=action)

            def check_video():
                front = state.get('cameras', {}).get('front', {})
                if (time.monotonic()-state.get('received', 0) > .25 or
                        front.get('error') or front.get('age_s', 99) > .75):
                    raise ValueError('No fresh front video and control state: '+str(front))
                if errors:
                    raise ValueError(errors[-1])

            receiver = asyncio.create_task(receive())
            try:
                async with asyncio.timeout(3):
                    while not state:
                        await asyncio.sleep(.02)
                check_video()
                motor = state.get('motor', {})
                if not motor.get('connected') or motor.get('armed') or motor.get('left') or motor.get('right'):
                    raise ValueError('Motor service must be connected, stopped and disarmed.')
                event('preflight', motor=motor)
                recorder = await asyncio.create_subprocess_exec(
                    sys.executable, str(Path(__file__).with_name('record_video.py')),
                    '--url', base, '--credentials', str(args.credentials), '--seconds', '6',
                    '--camera', 'front', '--label', args.direction,
                    '--output', str(output), '--ready-file', str(ready),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                async with asyncio.timeout(5):
                    while not ready.exists():
                        if recorder.returncode is not None:
                            raise ValueError('Recording failed before motion.')
                        await asyncio.sleep(.03)
                event('video_ready')
                await asyncio.sleep(1.5)
                check_video()
                arm_attempted = True
                await send('arm')
                # Wait for a fresh ticket after the arm acknowledgement.
                armed_at = time.monotonic()
                async with asyncio.timeout(.5):
                    while state.get('received', 0) <= armed_at:
                        await asyncio.sleep(.01)
                check_video()
                left, right = [s*args.speed for s in DIRECTIONS[args.direction]]
                drive_at = time.monotonic()
                await send('drive', left=left, right=right, ticket=state['ticket'])
                await asyncio.sleep(max(0, args.seconds-(time.monotonic()-drive_at)))
                await send('stop')
                async with asyncio.timeout(2):
                    while state.get('motor', {}).get('armed') or state.get('motor', {}).get('left') or state.get('motor', {}).get('right'):
                        await asyncio.sleep(.03)
                event('stopped', motor=state.get('motor'))
            finally:
                # Even an exception after arming must request a stop. Closing the
                # socket also relinquishes control; the motor lease is independent.
                try:
                    if arm_attempted:
                        await ws.send_json({'action': 'stop'})
                        await asyncio.sleep(.15)
                finally:
                    receiver.cancel()
                    await asyncio.gather(receiver, return_exceptions=True)
                    evidence.write_text(json.dumps(dict(direction=args.direction, speed=args.speed,
                        requested_pulse_s=args.seconds, server_lease_s=.3, events=events,
                        errors=errors), indent=2)+'\n')
                    if recorder:
                        stdout, stderr = await asyncio.wait_for(recorder.communicate(), 100)
                        if recorder.returncode:
                            raise RuntimeError('Recording failed: '+stderr.decode(errors='replace'))
                        print(stdout.decode(), end='')
    print(json.dumps(dict(direction=args.direction, motion_log=str(evidence), events=events), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('direction', choices=DIRECTIONS)
    parser.add_argument('--drive', action='store_true')
    parser.add_argument('--speed', type=float, default=.25)
    parser.add_argument('--seconds', type=float, default=.18)
    parser.add_argument('--url', default='https://robotcar.nygardene.no')
    parser.add_argument('--credentials', type=Path, default=Path.home()/'.ssh/robotcar-web-login.conf')
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(trial(parser.parse_args()))
