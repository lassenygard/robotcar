"""Latest JPEG transport between Pis, without comparing their monotonic clocks."""
import asyncio
import math
import re
import secrets
import time
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout
from .camera import Camera, Frame, SPECS, MAX_FRAME_AGE, MAX_FRAME_BYTES
from .common import RUN, secret


class FrameReceiver:
    def __init__(self, name):
        self.name = name
        self.source = None
        self.remote_seq = -1
        self.local_seq = 0
        self.frame = None

    def receive(self, headers, jpeg, nonce, started, received):
        if headers.get('X-Camera-Nonce') != nonce:
            raise ValueError('Camera reply does not match request')
        if (headers.get('X-Camera-Role') != self.name or
                headers.get('X-Camera-Model') != SPECS[self.name][0]):
            raise ValueError('Unexpected camera role or sensor')
        source = headers.get('X-Camera-Source', '')
        if not re.fullmatch('[0-9a-f]{32}', source):
            raise ValueError('Invalid camera source identity')
        seq = int(headers['X-Frame-Sequence'])
        age = float(headers['X-Frame-Age'])
        trip = received - started
        if seq < 1 or not math.isfinite(age) or age < 0 or trip < 0 or age + trip > MAX_FRAME_AGE:
            raise ValueError('Camera image is stale or has invalid sequence/age')
        if not 4 <= len(jpeg) <= MAX_FRAME_BYTES or not (jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9')):
            raise ValueError('Invalid camera JPEG')
        if source == self.source:
            if seq < self.remote_seq:
                raise ValueError('Camera sequence moved backwards')
            if seq == self.remote_seq:
                # Repeated packets cannot renew the lifetime of the last image.
                if self.frame is None or received - self.frame.when > MAX_FRAME_AGE:
                    raise ValueError('Camera sequence has stopped updating')
                return None
        self.source, self.remote_seq = source, seq
        self.local_seq += 1
        self.frame = Frame(self.local_seq, received - age - trip, jpeg)
        return self.frame


async def fetch_frame(http, url, receiver):
    nonce = secrets.token_hex(16)
    started = time.monotonic()
    async with http.get(url.rstrip('/') + '/snapshot/' + receiver.name,
                        params={'nonce': nonce}, allow_redirects=False) as response:
        if response.status != 200 or response.content_type != 'image/jpeg':
            raise ValueError(f'Camera feed returned HTTP {response.status}')
        length = response.content_length
        if length is None or not 4 <= length <= MAX_FRAME_BYTES:
            raise ValueError('Invalid camera response length')
        jpeg = await response.content.readexactly(length)
        headers = response.headers
    return receiver.receive(headers, jpeg, nonce, started, time.monotonic())


class RemoteCamera(Camera):
    def __init__(self, name, url):
        super().__init__(name)
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Invalid camera feed URL')
        self.url = url
        self.roundtrip_ms = None

    def status(self):
        return dict(super().status(), transport='network', roundtrip_ms=self.roundtrip_ms)

    async def run(self):
        receiver = FrameReceiver(self.name)
        token = secret()
        count, window = 0, time.monotonic()
        async with ClientSession(timeout=ClientTimeout(total=.7, connect=.3),
                                 headers={'Authorization': 'Bearer ' + token}) as http:
            while True:
                began = time.monotonic()
                try:
                    frame = await fetch_frame(http, self.url, receiver)
                    self.roundtrip_ms = round((time.monotonic()-began)*1000, 1)
                    if frame is not None:
                        temporary = RUN / (self.name + '.tmp.jpg')
                        temporary.write_bytes(frame.jpeg)
                        temporary.replace(RUN / (self.name + '.jpg'))
                        self.frame, self.seq, self.error = frame, frame.seq, None
                        count += 1
                    now = time.monotonic()
                    if now-window >= 1:
                        self.fps = count/(now-window)
                        count, window = 0, now
                except Exception as exc:
                    self.error = 'Camera link: ' + (str(exc) or type(exc).__name__)[:180]
                    self.fps = 0.
                    count, window = 0, time.monotonic()
                    await asyncio.sleep(.3)
                await asyncio.sleep(max(0, .05-(time.monotonic()-began)))
