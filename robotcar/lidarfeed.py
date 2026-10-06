"""Authenticated, latest-scan-only transport from the USB Pi to the mapping Pi.

No wheel GPIO is imported here. Each request carries a nonce. Source age plus
the whole round trip gives a conservative measurement age without comparing
the two machines' monotonic clocks. Frozen/replayed scans cannot become fresh.
"""
import asyncio
import hmac
import json
import math
import os
import re
import secrets
import time

from aiohttp import ClientSession, ClientTimeout, web
from .common import RUN, atomic_json, read_json, secret


MAX_AGE = .65
MAX_BODY = 256 * 1024


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def create_app(token=None, scan_path=None):
    token = token or secret()
    scan_path = scan_path or RUN / 'lidar.json'

    async def latest(request):
        if not hmac.compare_digest(request.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode()):
            raise web.HTTPUnauthorized()
        nonce = request.query.get('nonce', '')
        if not re.fullmatch('[0-9a-f]{32}', nonce):
            raise web.HTTPBadRequest(text='Missing scan request nonce')
        scan = read_json(scan_path)
        measured = scan.get('monotonic')
        age = time.monotonic() - measured if finite(measured) else MAX_AGE + 1
        error = scan.get('error')
        if age < 0 or age > MAX_AGE:
            error = 'LiDAR source is stale'
        result = {key: scan.get(key) for key in ('source_id', 'seq', 'hz')}
        result.update(nonce=nonce, age_s=max(0, age), error=error,
                      points=[] if error else scan.get('points', []))
        return web.json_response(result, headers={'Cache-Control': 'no-store'})

    app = web.Application(client_max_size=4096)
    app.router.add_get('/scan', latest)
    return app


class ScanReceiver:
    def __init__(self):
        self.source = None
        self.remote_seq = -1
        self.local_seq = 0
        self.measured = 0.0

    def receive(self, data, nonce, started, received):
        if not isinstance(data, dict) or data.get('nonce') != nonce:
            raise ValueError('LiDAR reply does not match its request')
        if data.get('error'):
            raise ValueError('LiDAR source: ' + str(data['error'])[:200])
        source, sequence, age = data.get('source_id'), data.get('seq'), data.get('age_s')
        if not isinstance(source, str) or not re.fullmatch('[0-9a-f]{32}', source):
            raise ValueError('Invalid LiDAR source identity')
        if type(sequence) is not int or sequence < 1 or not finite(age) or age < 0:
            raise ValueError('Invalid LiDAR sequence or age')
        age += received - started  # Include even the outbound half of the trip.
        if age > MAX_AGE or age < 0:
            raise ValueError('LiDAR network scan is stale')
        points = data.get('points')
        if not isinstance(points, list) or not 60 <= len(points) <= 4096:
            raise ValueError('LiDAR scan has too few or too many returns')
        for point in points:
            if (not isinstance(point, list) or len(point) != 3 or
                    not all(finite(value) for value in point) or
                    not -math.pi <= point[0] <= math.pi or not .12 <= point[1] <= 8 or
                    type(point[2]) is not int or not 1 <= point[2] <= 63):
                raise ValueError('Invalid LiDAR return')
        measured = received - age
        if source == self.source:
            if sequence < self.remote_seq:
                raise ValueError('LiDAR sequence moved backwards')
            if sequence == self.remote_seq:
                measured = min(measured, self.measured)
        if received - measured > MAX_AGE:
            raise ValueError('LiDAR sequence has stopped updating')
        if (source, sequence) != (self.source, self.remote_seq):
            self.local_seq += 1
        self.source, self.remote_seq, self.measured = source, sequence, measured
        hz = data.get('hz', 0)
        return dict(seq=self.local_seq, source_id=source, monotonic=measured, time=time.time(),
                    hz=hz if finite(hz) and hz >= 0 else 0, points=points, error=None,
                    transport='network', roundtrip_ms=round((received-started)*1000, 2))


async def fetch_scan(http, url, receiver):
    nonce = secrets.token_hex(16)
    started = time.monotonic()
    async with http.get(url.rstrip('/') + '/scan', params={'nonce': nonce}, allow_redirects=False) as response:
        if response.status != 200:
            raise ValueError(f'LiDAR feed returned HTTP {response.status}')
        body = bytearray()
        async for block in response.content.iter_chunked(16384):
            body.extend(block)
            if len(body) > MAX_BODY:
                raise ValueError('LiDAR feed response is too large')
        data = json.loads(body)
    return receiver.receive(data, nonce, started, time.monotonic())


async def collect(url):
    receiver = ScanReceiver()
    async with ClientSession(timeout=ClientTimeout(total=.45, connect=.25),
                             headers={'Authorization': 'Bearer ' + secret()}) as http:
        while True:
            started = time.monotonic()
            try:
                scan = await fetch_scan(http, url, receiver)
            except Exception as error:
                scan = dict(seq=receiver.local_seq, monotonic=time.monotonic(), time=time.time(),
                            hz=0, points=[], error='LiDAR link: ' + (str(error) or type(error).__name__)[:240],
                            transport='network')
            atomic_json(RUN / 'lidar.json', scan)
            await asyncio.sleep(max(.01, .1 - (time.monotonic()-started)))


def main():
    host = os.environ.get('LIDAR_FEED_BIND', '127.0.0.1')
    port = int(os.environ.get('LIDAR_FEED_PORT', '8801'))
    web.run_app(create_app(), host=host, port=port, access_log=None)


if __name__ == '__main__':
    main()
