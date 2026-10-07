"""Authenticated operator gateway. Sensor processing never runs on this event loop."""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web
from .common import DATA, RUN, read_json
from .navigation import MotorClient, Navigator
from .video import stream_latest


def password_matches(password, encoded):
    salt, expected = encoded.split(':', 1)
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 200000).hex()
    return hmac.compare_digest(actual, expected)


def create_app(motor=None, camera_base='http://127.0.0.1:8800'):
    username = os.environ.get('WEB_USERNAME', 'pi')
    password_hash = os.environ.get('WEB_PASSWORD_HASH', '')
    if not password_hash:
        raise RuntimeError('WEB_PASSWORD_HASH must be configured before starting the gateway')
    sessions, attempts = {}, deque()
    motor = motor if motor is not None else MotorClient()
    controller = None
    control_lock = asyncio.Lock()
    connections = set()
    releases = set()

    @web.middleware
    async def auth(request, handler):
        if request.path not in ('/login', '/health'):
            session = request.cookies.get('robotcar_session', '')
            if sessions.get(session, 0) < time.monotonic():
                if request.path == '/':
                    raise web.HTTPFound('/login')
                raise web.HTTPUnauthorized(text='Logg inn på nytt.')
        if request.method != 'GET' or request.path == '/ws':
            origin = request.headers.get('Origin', '')
            if origin and urlsplit(origin).netloc != request.host:
                raise web.HTTPForbidden(text='Invalid origin')
        response = await handler(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    app = web.Application(middlewares=[auth], client_max_size=16384)
    http = None

    async def map_call(msg):
        async with http.post('http://127.0.0.1:8810/action', json=msg, timeout=ClientTimeout(total=12)) as response:
            data = await response.json()
            if not data.get('ok'):
                raise ValueError(data.get('error', 'Karttjenesten avviste forespørselen.'))
            return data
    navigator = Navigator(motor, map_call)

    async def login(request):
        error = ''
        if request.method == 'POST':
            now = time.monotonic()
            while attempts and now-attempts[0] > 60:
                attempts.popleft()
            if len(attempts) >= 10:
                raise web.HTTPTooManyRequests(text='Vent ett minutt før nytt forsøk.')
            attempts.append(now)
            data = await request.post()
            valid = hmac.compare_digest(str(data.get('username', '')), username)
            valid = valid and await asyncio.to_thread(password_matches, str(data.get('password', '')), password_hash)
            if valid:
                token = secrets.token_urlsafe(32)
                sessions[token] = now+12*3600
                response = web.HTTPFound('/')
                response.set_cookie('robotcar_session', token, httponly=True, samesite='Strict', max_age=43200,
                                    secure=request.secure or request.headers.get('X-Forwarded-Proto') == 'https')
                raise response
            error = '<p>Feil brukernavn eller passord.</p>'
        return web.Response(content_type='text/html', text='''<!doctype html><html lang="no"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Robotcar · Logg inn</title><style>body{background:#101722;color:#eef5fb;font:18px system-ui;max-width:380px;margin:12vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;border-radius:8px;border:1px solid #526272}button{background:#62d7b6;font-weight:700}h1{font-size:32px}</style><h1>Robotcar</h1><p>Live-kjøring og kart</p>'''+error+'''<form method="post"><label>Brukernavn<input name="username" autocomplete="username" required></label><label>Passord<input type="password" name="password" autocomplete="current-password" required></label><button>Logg inn</button></form></html>''')

    async def index(request):
        return web.FileResponse(Path(__file__).parent/'static'/'index.html', headers={'Cache-Control':'no-store'})

    async def health(request):
        return web.json_response({'service':'robotcar', 'online':True})

    async def proxy(request):
        response = None
        camera = request.match_info.get('camera')
        if camera:
            if camera not in ('front', 'rear'):
                raise web.HTTPNotFound()
            return await stream_latest(request, http, camera_base+'/snapshot/'+camera)
        else:
            url = 'http://127.0.0.1:8810/map.png'
        try:
            params = {'map_id':request.query['map_id']} if 'map_id' in request.query else {}
            async with http.get(url, params=params, timeout=ClientTimeout(total=None, sock_connect=2, sock_read=3)) as upstream:
                response = web.StreamResponse(status=upstream.status, headers={
                    'Content-Type':upstream.headers.get('Content-Type','application/octet-stream'),
                    'Cache-Control':'no-store', 'X-Accel-Buffering':'no'})
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(65536):
                    await asyncio.wait_for(response.write(chunk), 1)
                return response
        except (ClientError, OSError, asyncio.TimeoutError):
            # Once video headers have been sent, close the failed stream.
            # A second HTTP response here would corrupt the multipart body.
            if response is not None and response.prepared:
                if request.transport:
                    request.transport.close()
                return response
            raise web.HTTPServiceUnavailable(text='Videostrøm eller kart er utilgjengelig.')

    async def action(request):
        nonlocal controller
        try:
            msg = await request.json()
            if not isinstance(msg, dict):
                raise ValueError('Forespørselen må være et JSON-objekt.')
            async with control_lock:
                name = msg.get('action')
                if name in ('stop', 'estop'):
                    await navigator.stop()
                    controller = None
                    return web.json_response({'ok':True})
                if controller is not None:
                    raise ValueError('Stopp manuell kjøring før du endrer kart eller navigasjon.')
                if name in ('goto','explore','patrol','scan'):
                    await navigator.start(name, msg)
                    result = navigator.status()
                elif name == 'patrol_settings':
                    result = await navigator.save_patrol(msg)
                else:
                    if navigator.mode != 'idle':
                        await navigator.stop()
                    result = await map_call(msg)
            return web.json_response({'ok':True, **result})
        except (ValueError, KeyError, TypeError, OSError, asyncio.TimeoutError) as exc:
            return web.json_response({'ok':False, 'error':str(exc)}, status=400)

    async def state():
        lidar = read_json(RUN/'lidar.json')
        map_state = read_json(RUN/'map.json')
        vision = read_json(RUN/'vision.json')
        cameras = read_json(RUN/'cameras.json')
        try:
            camera_file_age = max(0, time.time()-(RUN/'cameras.json').stat().st_mtime)
        except OSError:
            camera_file_age = 99
        for name in ('front', 'rear'):
            camera = cameras.setdefault(name, {})
            camera['age_s'] = camera.get('age_s', 99)+camera_file_age
            if camera['age_s'] > 1:
                camera.update(fps=0, error='Kameraet har sluttet å oppdatere.')
        # A dead sensor process cannot leave a permanently green indicator.
        lidar['age_s'] = time.monotonic()-lidar.get('monotonic', 0)
        if lidar['age_s'] > 1:
            lidar['error'] = 'LiDAR har sluttet å oppdatere.'
        if time.monotonic()-vision.get('monotonic', 0) > 2:
            vision['error'], vision['objects'] = 'Objektdeteksjonen er utilgjengelig.', []
        try:
            if time.time()-(RUN/'map.json').stat().st_mtime > 1:
                map_state['localized'] = False
                map_state['error'] = 'Karttjenesten har sluttet å oppdatere.'
        except OSError:
            map_state = {'localized':False, 'error':'Karttjenesten starter.'}
        return dict(motor=motor.state, cameras=cameras, lidar=lidar,
                    map=map_state, vision=vision, navigation=navigator.status())

    async def websocket(request):
        nonlocal controller
        ws = web.WebSocketResponse(heartbeat=5, max_msg_size=4096)
        await ws.prepare(request)
        connections.add(ws)
        tickets = {}
        session_id = request.cookies.get('robotcar_session', '')

        async def publish():
            while not ws.closed:
                now = time.monotonic()
                if sessions.get(session_id, 0) < now:
                    await ws.close(code=1008, message=b'Session expired')
                    break
                for ticket in list(tickets):
                    if now-tickets[ticket] > .35:
                        del tickets[ticket]
                ticket = secrets.token_hex(8)
                tickets[ticket] = now
                data = await state()
                data.update(type='state', ticket=ticket, server_time=time.time(), owns_control=controller is ws)
                await asyncio.wait_for(ws.send_json(data), .5)
                await asyncio.sleep(.1)
        task = asyncio.create_task(publish())
        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(message.data)
                    if not isinstance(msg, dict):
                        raise ValueError('Kommandoen må være et JSON-objekt.')
                    if sessions.get(session_id, 0) < time.monotonic():
                        raise ValueError('Innloggingen er utløpt.')
                    command = msg.get('action')
                    if command == 'ping':
                        await ws.send_json({'type':'pong', 'sent':msg.get('sent'),
                                            'server_monotonic':time.monotonic()})
                        continue
                    async with control_lock:
                        if command == 'stop':
                            await navigator.stop()
                            controller = None
                        elif command == 'arm':
                            if controller not in (None, ws):
                                raise ValueError('En annen nettleser styrer bilen.')
                            await navigator.stop()
                            await motor.request('arm')
                            controller = ws
                        elif command == 'drive':
                            if controller is not ws:
                                raise ValueError('Aktiver motorene først.')
                            if time.monotonic()-tickets.get(msg.get('ticket'), -100) > .35:
                                await motor.stop()
                                controller = None
                                raise ValueError('Kjørekommandoen var for gammel. Bilen er stoppet.')
                            cameras = read_json(RUN/'cameras.json')
                            try:
                                camera_file_age = time.time()-(RUN/'cameras.json').stat().st_mtime
                            except OSError:
                                camera_file_age = 99
                            front = cameras.get('front', {})
                            if camera_file_age > 1 or front.get('age_s',99) > 1 or front.get('error'):
                                raise ValueError('Kameraet er utilgjengelig; kjøring er stoppet.')
                            left, right = float(msg['left']), float(msg['right'])
                            await motor.request('drive', left=left, right=right, ttl=.3, mode='manual')
                        else:
                            raise ValueError('Ukjent kommando.')
                    await ws.send_json({'type':'ack','action':command})
                except (ValueError, KeyError, TypeError) as exc:
                    async with control_lock:
                        if controller is ws:
                            await motor.stop()
                            controller = None
                    await ws.send_json({'type':'error', 'error':str(exc)})
        finally:
            task.cancel()
            connections.discard(ws)
            async def release_control():
                nonlocal controller
                async with control_lock:
                    if controller is ws:
                        controller = None
                        await motor.stop()
            # aiohttp can cancel this handler when its TCP connection closes.
            # The stop must finish even if that cancellation arrives in cleanup.
            release = asyncio.create_task(release_control())
            releases.add(release)
            release.add_done_callback(releases.discard)
            try:
                await asyncio.shield(release)
            finally:
                await asyncio.gather(task, return_exceptions=True)
        return ws

    async def startup(app):
        nonlocal http, controller
        http = ClientSession()
        async def poll_motor():
            nonlocal controller
            while True:
                async with control_lock:
                    try:
                        await motor.request('status')
                        if not motor.state.get('armed'):
                            controller = None
                    except ValueError:
                        controller = None
                await asyncio.sleep(.15)
        task = asyncio.create_task(poll_motor())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await navigator.stop()
        for ws in list(connections):
            await ws.close()
        await asyncio.gather(*releases, return_exceptions=True)
        await http.close()
        motor.disconnect()

    app.cleanup_ctx.append(startup)
    app.router.add_route('*', '/login', login)
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    app.router.add_get('/api/session', health)  # Auth middleware distinguishes expiry from a network outage.
    app.router.add_get('/ws', websocket)
    app.router.add_get('/video/{camera}', proxy)
    app.router.add_get('/map.png', proxy)
    app.router.add_post('/api/action', action)
    return app


def main():
    app = create_app()
    web.run_app(app, host=os.environ.get('WEB_BIND', '0.0.0.0'), port=8080, access_log=None)


if __name__ == '__main__':
    main()
