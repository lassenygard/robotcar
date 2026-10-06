"""One owner per CSI camera; encode once and discard obsolete frames."""
import asyncio
import os
import threading
import time
from pathlib import Path

from aiohttp import web
from .common import RUN, atomic_json


class Camera:
    def __init__(self, name, number, rotate=False):
        self.name, self.number, self.rotate = name, number, rotate
        self.frame, self.seq, self.when = b'', 0, 0.0
        self.error, self.fps = 'starting', 0.0
        self.stopping = threading.Event()

    def run(self):
        import cv2
        from picamera2 import Picamera2
        cv2.setNumThreads(1)
        while not self.stopping.is_set():
            camera = None
            try:
                camera = Picamera2(self.number)
                camera.configure(camera.create_video_configuration(
                    main={'format': 'RGB888', 'size': (640, 480)},
                    sensor={'output_size': (1640, 1232) if self.number == 0 else (2304, 1296), 'bit_depth': 10},
                    controls={'FrameRate': 20}, buffer_count=3, queue=False))
                camera.start()
                count, start = 0, time.monotonic()
                while not self.stopping.is_set():
                    # RGB888 is BGR byte order on the Pi; OpenCV accepts it directly.
                    frame = camera.capture_array()
                    if self.rotate:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 68])
                    if not ok:
                        continue
                    self.frame, self.when = encoded.tobytes(), time.monotonic()
                    self.seq += 1
                    self.error = None
                    temp = RUN / (self.name + '.tmp.jpg')
                    temp.write_bytes(self.frame)
                    os.replace(temp, RUN / (self.name + '.jpg'))
                    count += 1
                    if self.when - start >= 1:
                        self.fps = count / (self.when - start)
                        count, start = 0, self.when
            except Exception as exc:
                self.error = str(exc)
                self.frame = b''
                self.stopping.wait(2)
            finally:
                if camera:
                    camera.close()

    def status(self):
        return dict(seq=self.seq, fps=round(self.fps, 1), age_s=round(time.monotonic()-self.when, 2),
                    error=self.error, number=self.number)


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    cameras = {'front': Camera('front', 0), 'rear': Camera('rear', 1, rotate=True)}
    for camera in cameras.values():
        threading.Thread(target=camera.run, daemon=True).start()
    app = web.Application()

    async def snapshot(request):
        cam = cameras.get(request.match_info['camera'])
        if cam is None or not cam.frame or time.monotonic() - cam.when > 1:
            raise web.HTTPServiceUnavailable(text='Camera unavailable')
        return web.Response(body=cam.frame, content_type='image/jpeg', headers={
            'Cache-Control': 'no-store', 'X-Frame-Sequence': str(cam.seq),
            'X-Frame-Monotonic': str(cam.when)})

    async def stream(request):
        cam = cameras.get(request.match_info['camera'])
        if cam is None:
            raise web.HTTPNotFound()
        response = web.StreamResponse(headers={'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
                                               'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
        await response.prepare(request)
        seq = -1
        try:
            while True:
                if cam.seq != seq and cam.frame and time.monotonic() - cam.when < 1:
                    seq, frame = cam.seq, cam.frame
                    await asyncio.wait_for(response.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                        + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n'), timeout=1)
                await asyncio.sleep(.025)
        except (ConnectionError, asyncio.TimeoutError, asyncio.CancelledError):
            pass
        return response

    async def state(request):
        return web.json_response({name: cam.status() for name, cam in cameras.items()})

    async def publish(app):
        async def loop():
            while True:
                atomic_json(RUN / 'cameras.json', {name: cam.status() for name, cam in cameras.items()})
                await asyncio.sleep(.5)
        task = asyncio.create_task(loop())
        yield
        task.cancel()
        for cam in cameras.values():
            cam.stopping.set()

    app.cleanup_ctx.append(publish)
    app.router.add_get('/snapshot/{camera}', snapshot)
    app.router.add_get('/stream/{camera}', stream)
    app.router.add_get('/status', state)
    web.run_app(app, host='127.0.0.1', port=8800, access_log=None)


if __name__ == '__main__':
    main()
