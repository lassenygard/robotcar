import asyncio
import math
import re
import threading
import time
from pathlib import Path
import cv2
import numpy as np
from aiohttp import web
from .common import DATA, RUN, atomic_json, read_json
from .mapping import OccupancyMap, wrap


class Mapper:
    def __init__(self):
        self.map = OccupancyMap()
        self.lock = threading.RLock()
        self.last_scan = 0.0
        self.last_sequence = -1
        self.error = 'Waiting for valid LiDAR scans'
        self.landmark_matches = []
        self.orb = cv2.ORB_create(nfeatures=200)
        self.last_save = time.monotonic()
        self.last_keyframe = 0.0
        self.last_relocalize = 0.0
        (DATA / 'maps').mkdir(parents=True, exist_ok=True)
        name = read_json(DATA/'active_map.json').get('name', '')
        if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name) and (DATA/'maps'/(name+'.npz')).exists():
            self.map = OccupancyMap.load(DATA/'maps'/(name+'.npz'))
            self.error = 'Saved map loaded; waiting for measured localisation'

    def features(self):
        path = RUN / 'front.jpg'
        if not path.exists() or time.time() - path.stat().st_mtime > 1:
            return [], None
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
        return self.orb.detectAndCompute(frame, None)

    def remember(self, name=None):
        if not self.map.localized or time.monotonic()-self.last_scan > 1:
            raise ValueError('A fresh, measured pose is required for a landmark')
        points, descriptors = self.features()
        vision = read_json(RUN / 'vision.json')
        objects = vision.get('objects', []) if time.time() - vision.get('time', 0) < 1 else []
        keyframe = dict(name=(name or 'view')[:80], pose=self.map.pose.tolist(),
                        labels=sorted(set(d['label'] for d in objects)),
                        pixels=[list(k.pt) for k in points],
                        descriptors=descriptors.tolist() if descriptors is not None else [])
        self.map.keyframes.append(keyframe)
        self.map.keyframes = self.map.keyframes[-300:]
        self.last_keyframe = time.monotonic()

    def recognise(self):
        points, descriptors = self.features()
        if descriptors is None or len(descriptors) < 12:
            return []
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = []
        for frame in self.map.keyframes:
            if len(frame.get('descriptors', [])) < 12:
                continue
            pairs = matcher.knnMatch(descriptors, np.asarray(frame['descriptors'], np.uint8), k=2)
            good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .7*p[1].distance]
            if len(good) < 12:
                continue
            source = np.float32([points[m.queryIdx].pt for m in good])
            target = np.float32([frame['pixels'][m.trainIdx] for m in good])
            _, inliers = cv2.findHomography(source, target, cv2.RANSAC, 4)
            count = int(inliers.sum()) if inliers is not None else 0
            if count >= 12 and count/len(good) > .5:
                matches.append(dict(name=frame['name'], pose=frame['pose'], inliers=count,
                                    labels=frame.get('labels', [])))
        self.landmark_matches = sorted(matches, key=lambda m: m['inliers'], reverse=True)[:5]
        return [item['pose'] for item in self.landmark_matches]

    def process(self):
        with self.lock:
            scan = read_json(RUN / 'lidar.json')
            age = time.monotonic() - scan.get('monotonic', 0)
            if scan.get('error') or age > .8 or len(scan.get('points', [])) < 60:
                self.error = scan.get('error') or 'LiDAR is stale or has too few returns'
                if time.monotonic()-self.last_scan > 1:
                    self.map.localized = False
                return
            if scan['seq'] == self.last_sequence:
                return
            self.last_sequence = scan['seq']
            if not self.map.localized and np.count_nonzero(self.map.grid):
                if time.monotonic()-self.last_relocalize < 3:
                    return
                self.last_relocalize = time.monotonic()
                if not self.map.relocalize(scan['points'], self.recognise()):
                    self.error = 'Position unknown: relocalise against saved map'
                    return
                self.last_scan = scan['monotonic']
            success = self.map.update(scan['points'])
            if not success:
                self.error = 'Scan matching uncertain: movement is blocked'
                return
            self.error, self.last_scan = None, scan['monotonic']
            if self.map.mapping and time.monotonic()-self.last_keyframe > 2:
                frames = self.map.keyframes
                if not frames or np.linalg.norm(self.map.pose[:2]-frames[-1]['pose'][:2]) > .4 or abs(wrap(self.map.pose[2]-frames[-1]['pose'][2])) > .35:
                    self.remember()
            if self.map.mapping and time.monotonic()-self.last_save > 30:
                self.map.save(DATA / 'maps' / 'autosave.npz')
                atomic_json(DATA/'active_map.json', {'name':'autosave'})
                self.last_save = time.monotonic()

    def status(self):
        with self.lock:
            return dict(pose=self.map.pose.tolist(), confidence=self.map.confidence,
                        scan_monotonic=self.last_scan,
                        localized=self.map.localized and time.monotonic()-self.last_scan < 1,
                        age_s=round(time.monotonic()-self.last_scan, 2), mapping=self.map.mapping,
                        name=self.map.name, revision=self.map.revision, resolution=self.map.resolution,
                        size=self.map.size, error=self.error, landmarks=len(self.map.keyframes),
                        recognised=self.landmark_matches,
                        maps=sorted(p.stem for p in (DATA/'maps').glob('*.npz')))

    def action(self, msg):
        with self.lock:
            action = msg.get('action')
            if action in ('save', 'load'):
                name = str(msg.get('name', ''))
                if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name):
                    raise ValueError('Map name: use letters, numbers, underscore or hyphen')
                path = DATA / 'maps' / (name + '.npz')
                if action == 'save':
                    if np.count_nonzero(self.map.grid) < 100:
                        raise ValueError('No measured map to save yet')
                    self.map.save(path)
                    self.map.name = name
                else:
                    self.map = OccupancyMap.load(path)
                    self.last_scan = 0.0
                    self.error = 'Map loaded; localisation required'
                atomic_json(DATA/'active_map.json', {'name':name})
            elif action == 'new':
                if np.count_nonzero(self.map.grid):
                    self.map.save(DATA/'maps'/('backup-'+time.strftime('%Y%m%d-%H%M%S')+'.npz'))
                self.map = OccupancyMap()
                atomic_json(DATA/'active_map.json', {'name':''})
                self.last_sequence = -1
            elif action == 'relocalize':
                scan = read_json(RUN/'lidar.json')
                if scan.get('error') or time.monotonic()-scan.get('monotonic', 0) > .8:
                    raise ValueError('Fresh LiDAR scan required')
                if not self.map.relocalize(scan['points'], self.recognise()):
                    raise ValueError('Location ambiguous: collect more views before moving')
                self.last_scan = scan['monotonic']
                self.error = None
            elif action == 'landmark':
                self.remember(str(msg.get('name', 'landmark')))
            elif action == 'resume_mapping':
                if not self.status()['localized']:
                    raise ValueError('Localise before extending a saved map')
                self.map.mapping = True
            elif action == 'plan':
                if not self.status()['localized']:
                    raise ValueError('Current position is unknown')
                return {'path': self.map.plan(msg['goal'])}
            elif action == 'frontiers':
                return {'targets': self.map.frontier_targets()}
            else:
                raise ValueError('Unknown map action')
            return self.status()


def main():
    cv2.setNumThreads(1)
    mapper = Mapper()
    app = web.Application(client_max_size=4096)

    async def state(request):
        return web.json_response(await asyncio.to_thread(mapper.status))

    async def image(request):
        def render():
            with mapper.lock:
                return mapper.map.image()
        return web.Response(body=await asyncio.to_thread(render), content_type='image/png', headers={'Cache-Control':'no-store'})

    async def action(request):
        try:
            result = await asyncio.to_thread(mapper.action, await request.json())
            return web.json_response({'ok':True, **result})
        except (ValueError, KeyError, OSError) as exc:
            return web.json_response({'ok':False, 'error':str(exc)}, status=400)

    async def background(app):
        async def loop():
            while True:
                try:
                    await asyncio.to_thread(mapper.process)
                    atomic_json(RUN/'map.json', await asyncio.to_thread(mapper.status))
                except Exception as exc:
                    mapper.error = str(exc)
                await asyncio.sleep(.15)
        task = asyncio.create_task(loop())
        yield
        task.cancel()
    app.cleanup_ctx.append(background)
    app.router.add_get('/status', state)
    app.router.add_get('/map.png', image)
    app.router.add_post('/action', action)
    web.run_app(app, host='127.0.0.1', port=8810, access_log=None)


if __name__ == '__main__':
    main()
