import asyncio
import json
import math
import os
import socket
import time
from .common import DATA, RUN, atomic_json, read_json, secret
from .mapping import wrap


class MotorClient:
    def __init__(self):
        self.host = os.environ.get('MOTOR_HOST', '192.168.4.43')
        self.token = secret()
        self.reader = self.writer = None
        self.lock = asyncio.Lock()
        self.state = {'connected': False, 'armed': False}
        self.seq = 0

    async def request(self, action, **kwargs):
        async with self.lock:
            start = time.monotonic()
            try:
                if not self.writer or self.writer.is_closing():
                    if action == 'drive':
                        raise ValueError('motor connection lost; rearm before driving')
                    self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, 5001), .5)
                    self.writer.get_extra_info('socket').setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.seq += 1
                msg = dict(token=self.token, action=action, seq=self.seq, **kwargs)
                self.writer.write((json.dumps(msg, allow_nan=False)+'\n').encode())
                await asyncio.wait_for(self.writer.drain(), .3)
                reply = await asyncio.wait_for(self.reader.readline(), .5)
                if not reply:
                    raise ConnectionError('motor connection closed')
                self.state = {**json.loads(reply), 'connected': True, 'rtt_ms':round((time.monotonic()-start)*1000, 1)}
                if not self.state.get('ok'):
                    raise ValueError(self.state.get('error', 'motor command refused'))
                return self.state
            except (OSError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
                if self.writer:
                    self.writer.close()
                self.reader = self.writer = None
                self.state = {'connected':False, 'armed':False, 'error':str(exc)}
                raise ValueError('Motor connection unavailable') from exc

    async def stop(self):
        try:
            await self.request('stop')
        except ValueError:
            pass  # Pi 4 independently expires the lease within 0.4 seconds.


class Navigator:
    def __init__(self, motor, map_call):
        self.motor, self.map_call = motor, map_call
        self.task = None
        self.mode, self.error, self.path = 'idle', None, []
        self.goal = None
        self.settings = read_json(DATA/'patrol.json', {'waypoints':[], 'interval_s':300})

    def status(self):
        return dict(mode=self.mode, error=self.error, path=self.path, goal=self.goal,
                    patrol=self.settings, enabled=os.environ.get('AUTONOMY_ENABLED') == '1',
                    calibrated=os.environ.get('MOTION_CALIBRATED') == '1')

    async def stop(self):
        task, self.task = self.task, None
        if task and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.motor.stop()
        self.mode, self.path, self.goal = 'idle', [], None

    def validate_ready(self):
        if os.environ.get('AUTONOMY_ENABLED') != '1':
            raise ValueError('Autonom kjøring venter til du er hjemme og bilen er testet.')
        if os.environ.get('MOTION_CALIBRATED') != '1':
            raise ValueError('Motorretning og LiDAR-vinkel må kalibreres først.')

    def obstacle_check(self, linear, angular):
        lidar = read_json(RUN/'lidar.json')
        if lidar.get('error') or time.monotonic()-lidar.get('monotonic', 0) > .7:
            raise ValueError('LiDAR-data mangler eller er for gamle.')
        points = lidar.get('points', [])
        if len(points) < 60:
            raise ValueError('For få LiDAR-målinger.')
        if abs(angular) > .01:
            distances = [p[1] for p in points]
            limit = .38
        else:
            distances = [p[1] for p in points if abs(p[0]) < .65] if linear >= 0 else [p[1] for p in points if abs(p[0]) > 2.5]
            limit = .55
        if len(distances) < 8 or min(distances) < limit:
            raise ValueError('Hinder eller utilstrekkelig sikt i kjøreretningen.')
        vision = read_json(RUN/'vision.json')
        if time.monotonic()-vision.get('monotonic', 0) < 1:
            for obj in vision.get('objects', []):
                box = obj['box']
                if obj['label'] in ('person','cat','dog') and (box[2]-box[0])*(box[3]-box[1]) > .12:
                    raise ValueError('Person eller dyr nær bilen; stoppet.')

    async def pulse(self, left, right, seconds=.18):
        self.obstacle_check((left+right)/2, (right-left)/2)
        await self.motor.request('arm')
        start = time.monotonic()
        try:
            while time.monotonic()-start < min(seconds, 2.0):
                self.obstacle_check((left+right)/2, (right-left)/2)
                await self.motor.request('drive', left=left, right=right, ttl=.25, mode='autonomous')
                await asyncio.sleep(.08)
        finally:
            await self.motor.stop()
        await asyncio.sleep(1.05)

    async def goto(self, goal):
        self.goal = goal
        result = await self.map_call({'action':'plan', 'goal':goal})
        self.path = result['path']
        began, progress_at = time.monotonic(), time.monotonic()
        best = float('inf')
        while time.monotonic()-began < 300:
            state = read_json(RUN/'map.json')
            if not state.get('localized') or state.get('confidence', 0) < .65 or time.monotonic()-state.get('scan_monotonic', 0) > .8:
                raise ValueError('Kartposisjonen er usikker; bilen står stille.')
            x, y, theta = state['pose']
            distance = math.dist([x,y], goal)
            if distance < .18:
                await self.motor.stop()
                return
            if distance < best-.04:
                best, progress_at = distance, time.monotonic()
            if time.monotonic()-progress_at > 20:
                raise ValueError('Ingen målt fremdrift; kontrollér motorene.')
            result = await self.map_call({'action':'plan', 'goal':goal})
            self.path = result['path']
            target = next((p for p in self.path if math.dist([x,y], p) > .25), goal)
            error = wrap(math.atan2(target[1]-y, target[0]-x)-theta)
            if abs(error) > .20:
                turn = .23 if error > 0 else -.23
                await self.pulse(-turn, turn, .16)
            else:
                await self.pulse(.24, .24, min(.5, distance))
        raise ValueError('Navigasjonen nådde tidsgrensen.')

    async def start(self, mode, message):
        self.validate_ready()
        await self.stop()
        self.mode, self.error = mode, None
        async def run():
            try:
                if mode == 'goto':
                    await self.goto(message['goal'])
                elif mode == 'scan':
                    for _ in range(40):
                        try:
                            result = await self.map_call({'action':'relocalize'})
                            if result.get('localized'):
                                return
                        except ValueError:
                            pass
                        await self.pulse(-.23, .23, .15)
                    raise ValueError('Fant ingen entydig kartposisjon under rotasjon.')
                elif mode == 'explore':
                    for _ in range(100):
                        options = (await self.map_call({'action':'frontiers'}))['targets']
                        selected = None
                        for target in options:
                            try:
                                await self.map_call({'action':'plan', 'goal':target})
                                selected = target
                                break
                            except ValueError:
                                continue
                        if selected is None:
                            await self.map_call({'action':'save', 'name':'apartment'})
                            return
                        await self.goto(selected)
                    raise ValueError('Kartleggingens rundegrense er nådd.')
                elif mode == 'patrol':
                    if not self.settings['waypoints']:
                        raise ValueError('Legg til minst ett vaktpunkt på kartet.')
                    while True:
                        for target in self.settings['waypoints']:
                            await self.goto(target)
                        self.mode = 'patrol_wait'
                        await asyncio.sleep(self.settings['interval_s'])
                        self.mode = 'patrol'
                else:
                    raise ValueError('Ukjent navigasjonsmodus.')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.error = str(exc)
            finally:
                await self.motor.stop()
                self.mode, self.path, self.goal = 'idle', [], None
        self.task = asyncio.create_task(run())

    def save_patrol(self, message):
        waypoints = message.get('waypoints', [])
        interval = float(message.get('interval_s', 300))
        if not 30 <= interval <= 86400 or len(waypoints) > 30:
            raise ValueError('Vaktintervall må være 30–86400 sekunder, maks. 30 punkter.')
        for p in waypoints:
            if len(p) != 2 or not all(math.isfinite(float(v)) and abs(float(v)) < 15 for v in p):
                raise ValueError('Ugyldig vaktpunkt.')
        self.settings = dict(waypoints=waypoints, interval_s=interval)
        atomic_json(DATA/'patrol.json', self.settings)
        return self.settings
