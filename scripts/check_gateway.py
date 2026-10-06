"""Verify HTTPS, login, both video streams and WSS without moving the robot.

Run from another network to measure that network's actual connection.
Credentials stay local; only summary measurements are printed.
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, MultipartReader, WSMsgType


async def check(base, credentials):
    assert base.startswith('https://'), 'Use HTTPS for remote login.'
    async with ClientSession(timeout=ClientTimeout(total=15)) as http:
        for path in ('/video/front', '/video/rear', '/map.png', '/ws'):
            async with http.get(base+path, allow_redirects=False) as response:
                assert response.status == 401, f'{path}: expected 401, got {response.status}'
        config = dict(line.split('=',1) for line in credentials.read_text().splitlines() if '=' in line)
        async with http.post(base+'/login', data=config, allow_redirects=False) as response:
            assert response.status == 302, f'Login failed: {response.status}'
            cookie = response.cookies.get('robotcar_session')
            assert cookie and cookie['secure'] and cookie['httponly'], 'Missing secure session cookie'
        async with http.get(base+'/', allow_redirects=False) as response:
            assert response.status == 200
            assert 'Robotcar' in await response.text()
        async with http.get(base+'/ws', headers={'Origin':'https://unrelated.example'}) as response:
            assert response.status == 403, 'Cross-origin WebSocket was not refused'

        async def video(name):
            async with http.get(base+'/video/'+name) as response:
                assert response.status == 200
                reader = MultipartReader.from_response(response)
                stamps, sizes = [], []
                for _ in range(10):
                    part = await reader.next()
                    assert part is not None, 'Camera stream ended'
                    frame = await part.read()
                    assert frame.startswith(b'\xff\xd8') and frame.endswith(b'\xff\xd9'), 'Invalid JPEG'
                    stamps.append(time.monotonic())
                    sizes.append(len(frame))
                return {'fps_received':round(9/(stamps[-1]-stamps[0]),1),
                        'average_jpeg_bytes':round(statistics.mean(sizes))}

        streams = dict(zip(('front','rear'), await asyncio.gather(video('front'),video('rear'))))
        pings, state = [], {}
        async with http.ws_connect(base+'/ws', origin=base, heartbeat=5) as ws:
            for number in range(10):
                started = time.monotonic()
                await ws.send_json({'action':'ping','sent':number})
                async with asyncio.timeout(3):
                    while True:
                        message = await ws.receive()
                        assert message.type == WSMsgType.TEXT, 'WebSocket closed unexpectedly'
                        data = json.loads(message.data)
                        if data.get('type') == 'state':
                            state = data
                        if data.get('type') == 'pong' and data['sent'] == number:
                            pings.append((time.monotonic()-started)*1000)
                            break
                await asyncio.sleep(.1)
        return dict(url=base, authentication='passed', cross_origin='refused', video=streams,
                    websocket_ping_median_ms=round(statistics.median(pings),1),
                    websocket_ping_max_ms=round(max(pings),1),
                    motor={k:state.get('motor',{}).get(k) for k in ('connected','armed','left','right')},
                    lidar_error=state.get('lidar',{}).get('error'),
                    localized=state.get('map',{}).get('localized'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://robotcar.nygardene.no')
    parser.add_argument('--credentials', type=Path, default=Path.home()/'.ssh/robotcar-web-login.conf')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.url.rstrip('/'), args.credentials)), indent=2))
