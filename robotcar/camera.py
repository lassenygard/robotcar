"""Independent CSI capture workers; share only the newest complete JPEG."""
import argparse
import asyncio
import contextlib
import math
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass

from aiohttp import web
from .common import RUN, atomic_json


SPECS = {
    'front': ('imx219', (1640, 1232), False),
    'rear': ('imx708', (2304, 1296), True),
}
HEADER = struct.Struct('!dI')  # Capture-return monotonic time, payload length.
MAX_FRAME_BYTES = 1024 * 1024
MAX_FRAME_AGE = 1.0
START_TIMEOUT = 10.0
FRAME_TIMEOUT = 3.0
RETRY_MIN, RETRY_MAX = 1.0, 30.0


def sensor_number(info, model):
    """A missing front sensor must never turn the rear sensor into the front."""
    matches = [item for item in info if item.get('Model', '').split('_')[0] == model]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one {model} sensor; detected {len(matches)}')
    return matches[0]['Num']


def capture_command(name):
    return (sys.executable, '-m', 'robotcar.camera', '--capture', name)


def capture(name):
    """Native camera calls live only here, in a disposable child process."""
    import cv2
    from picamera2 import Picamera2
    cv2.setNumThreads(1)
    model, size, rotate = SPECS[name]
    camera = None
    try:
        camera = Picamera2(sensor_number(Picamera2.global_camera_info(), model))
        camera.configure(camera.create_video_configuration(
            main={'format': 'RGB888', 'size': (640, 480)},
            sensor={'output_size': size, 'bit_depth': 10},
            controls={'FrameRate': 20}, buffer_count=3, queue=False))
        camera.start()
        while True:
            # RGB888 is BGR byte order on the Pi; OpenCV accepts it directly.
            pixels = camera.capture_array()
            when = time.monotonic()
            if rotate:
                pixels = cv2.rotate(pixels, cv2.ROTATE_180)
            ok, encoded = cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, 68])
            if ok:
                frame = encoded.tobytes()
                sys.stdout.buffer.write(HEADER.pack(when, len(frame)) + frame)
                sys.stdout.buffer.flush()
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'.encode()[:512]
        # Zero timestamp distinguishes a diagnostic from a JPEG packet.
        with contextlib.suppress(BrokenPipeError):
            sys.stdout.buffer.write(HEADER.pack(0, len(error)) + error)
            sys.stdout.buffer.flush()
    finally:
        if camera is not None:
            camera.close()


@dataclass(frozen=True)
class Frame:
    seq: int
    when: float
    jpeg: bytes


def frame_part(frame):
    header = (f'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame.jpeg)}\r\n'
              f'X-Frame-Sequence: {frame.seq}\r\nX-Frame-Monotonic: {frame.when}\r\n\r\n').encode()
    return header + frame.jpeg + b'\r\n'


async def read_frame(reader, timeout):
    async with asyncio.timeout(timeout):
        when, length = HEADER.unpack(await reader.readexactly(HEADER.size))
        if not 0 < length <= MAX_FRAME_BYTES:
            raise ValueError('Invalid camera packet length')
        payload = await reader.readexactly(length)
    if when == 0:
        raise RuntimeError(payload.decode(errors='replace'))
    age = time.monotonic() - when
    if not math.isfinite(when) or not 0 <= age <= MAX_FRAME_AGE:
        raise ValueError('Camera delivered an old or invalid frame timestamp')
    if not (payload.startswith(b'\xff\xd8') and payload.endswith(b'\xff\xd9')):
        raise ValueError('Camera delivered an invalid JPEG')
    return when, payload


async def stop_worker(process):
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 1)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await asyncio.wait_for(process.wait(), 2)


class Camera:
    def __init__(self, name):
        self.name = name
        self.frame = None
        self.seq, self.fps = 0, 0.0
        self.error = 'Camera is starting'
        self.pid, self.restarts = None, 0

    def fresh_frame(self):
        frame = self.frame
        if frame and not self.error and 0 <= time.monotonic() - frame.when <= MAX_FRAME_AGE:
            return frame
        return None

    def status(self):
        fresh = self.fresh_frame()
        age = time.monotonic() - self.frame.when if self.frame else 99.0
        return dict(seq=self.seq, fps=round(self.fps, 1) if fresh else 0.0,
                    age_s=round(age, 2), error=None if fresh else self.error or 'Camera stopped updating',
                    model=SPECS[self.name][0], pid=self.pid, restarts=self.restarts)

    async def run(self):
        delay = RETRY_MIN
        while True:
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *capture_command(self.name), stdout=asyncio.subprocess.PIPE,
                    limit=MAX_FRAME_BYTES + HEADER.size)
                self.pid = process.pid
                count, started = 0, time.monotonic()
                window_count, window_start = 0, started
                while True:
                    when, jpeg = await read_frame(process.stdout, START_TIMEOUT if count == 0 else FRAME_TIMEOUT)
                    temp = RUN / (self.name + '.tmp.jpg')
                    temp.write_bytes(jpeg)
                    os.replace(temp, RUN / (self.name + '.jpg'))
                    self.seq += 1
                    self.frame = Frame(self.seq, when, jpeg)
                    self.error = None
                    count += 1
                    window_count += 1
                    elapsed = time.monotonic() - started
                    window_elapsed = time.monotonic() - window_start
                    if window_elapsed >= 1:
                        self.fps = window_count / window_elapsed
                        window_count, window_start = 0, time.monotonic()
                    # A single lucky frame must not cause a rapid restart loop.
                    if elapsed >= 5:
                        delay = RETRY_MIN
            except (OSError, ValueError, RuntimeError, asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
                self.error = str(exc) or 'Camera capture timed out'
                self.fps = 0.0
                print(f'{self.name}: {self.error}; retry in {delay:g}s', file=sys.stderr, flush=True)
            finally:
                if process is not None:
                    await stop_worker(process)
                self.pid = None
            await asyncio.sleep(delay)
            self.restarts += 1
            delay = min(RETRY_MAX, delay * 2)


def notify_watchdog():
    """Only the HTTP/supervisor process notifies systemd, never capture children."""
    address = os.environ.get('NOTIFY_SOCKET')
    if not address:
        return
    if address.startswith('@'):
        address = '\0' + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.settimeout(.1)
        sock.sendto(b'WATCHDOG=1', address)


def create_app(cameras=None, start_workers=True):
    cameras = cameras if cameras is not None else {name: Camera(name) for name in SPECS}
    app = web.Application()

    def get_frame(request):
        cam = cameras.get(request.match_info['camera'])
        if cam is None:
            raise web.HTTPNotFound()
        frame = cam.fresh_frame()
        if frame is None:
            raise web.HTTPServiceUnavailable(text='Camera unavailable')
        return cam, frame

    async def snapshot(request):
        _, frame = get_frame(request)
        return web.Response(body=frame.jpeg, content_type='image/jpeg', headers={
            'Cache-Control': 'no-store', 'X-Frame-Sequence': str(frame.seq),
            'X-Frame-Monotonic': str(frame.when)})

    async def stream(request):
        cam, _ = get_frame(request)
        response = web.StreamResponse(headers={'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
                                               'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
        await response.prepare(request)
        seq = -1
        try:
            while True:
                frame = cam.fresh_frame()
                if frame is None:
                    await asyncio.wait_for(response.write(b'--frame--\r\n'), timeout=1)
                    break
                if frame.seq != seq:
                    seq = frame.seq
                    await asyncio.wait_for(response.write(frame_part(frame)), timeout=1)
                await asyncio.sleep(.025)
        except (ConnectionError, asyncio.TimeoutError):
            if request.transport:
                request.transport.close()
        response.force_close()
        return response

    async def state(request):
        return web.json_response({name: cam.status() for name, cam in cameras.items()})

    async def publish(app):
        RUN.mkdir(parents=True, exist_ok=True)
        workers = [asyncio.create_task(cam.run()) for cam in cameras.values()] if start_workers else []

        async def loop():
            while True:
                # Let systemd restart us if the publisher or any supervisor dies.
                for worker in workers:
                    if worker.done():
                        worker.result()
                        raise RuntimeError('Camera supervisor exited')
                atomic_json(RUN / 'cameras.json', {name: cam.status() for name, cam in cameras.items()})
                notify_watchdog()
                await asyncio.sleep(.5)

        task = asyncio.create_task(loop())
        yield
        for pending in [task, *workers]:
            pending.cancel()
        await asyncio.gather(task, *workers, return_exceptions=True)

    app.cleanup_ctx.append(publish)
    app.router.add_get('/snapshot/{camera}', snapshot)
    app.router.add_get('/stream/{camera}', stream)
    app.router.add_get('/status', state)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', choices=SPECS)
    args = parser.parse_args()
    if args.capture:
        capture(args.capture)
    else:
        web.run_app(create_app(), host='127.0.0.1', port=8800, access_log=None)
