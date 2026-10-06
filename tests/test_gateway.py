import asyncio
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer
from robotcar.common import atomic_json
from robotcar.webapp import create_app


class FakeMotor:
    """No GPIO or real motor connections; exposes scheduling races in the gateway."""
    def __init__(self):
        self.state = {'connected':True, 'armed':False}
        self.actions = []
        self.arm_started = asyncio.Event()
        self.arm_gate = asyncio.Event()
        self.arm_gate.set()

    async def request(self, action, **kwargs):
        self.actions.append(action)
        if action == 'arm':
            self.arm_started.set()
            await self.arm_gate.wait()
            self.state['armed'] = True
        elif action == 'stop':
            self.state['armed'] = False
        return dict(self.state, ok=True)

    async def stop(self):
        await self.request('stop')

    def disconnect(self):
        self.state.update(connected=False, armed=False)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name)
        salt = '11'*16
        hashed = hashlib.pbkdf2_hmac('sha256', b'test-password', bytes.fromhex(salt), 200000).hex()
        self.env = patch.dict(os.environ, {'WEB_USERNAME':'test', 'WEB_PASSWORD_HASH':salt+':'+hashed,
                                         'AUTONOMY_ENABLED':'0', 'MOTION_CALIBRATED':'0'})
        self.env.start()
        self.run_patch = patch('robotcar.webapp.RUN', self.run)
        self.run_patch.start()
        self.motor = FakeMotor()
        self.client = TestClient(TestServer(create_app(self.motor)), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        response = await self.client.post('/login', data={'username':'test', 'password':'test-password'},
                                          allow_redirects=False)
        self.assertEqual(response.status, 302)
        await response.release()
        atomic_json(self.run/'cameras.json', {name:{'age_s':0, 'fps':20} for name in ('front','rear')})

    async def asyncTearDown(self):
        self.motor.arm_gate.set()
        await self.client.close()
        self.run_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    async def message(self, ws, kind):
        async with asyncio.timeout(2):
            while True:
                msg = await ws.receive_json()
                if msg.get('type') == kind:
                    return msg

    async def test_two_browsers_cannot_claim_control_at_once(self):
        first, second = await self.client.ws_connect('/ws'), await self.client.ws_connect('/ws')
        self.motor.arm_gate.clear()
        await first.send_json({'action':'arm'})
        await asyncio.wait_for(self.motor.arm_started.wait(), 1)
        await second.send_json({'action':'arm'})
        await asyncio.sleep(.03)
        self.motor.arm_gate.set()
        self.assertEqual((await self.message(first, 'ack'))['action'], 'arm')
        self.assertIn('annen nettleser', (await self.message(second, 'error'))['error'])
        self.assertEqual(self.motor.actions.count('arm'), 1)
        # A denied observer may disconnect without stopping the actual operator.
        await second.close()
        self.assertTrue(self.motor.state['armed'])
        await first.close()
        async with asyncio.timeout(1):
            while self.motor.state['armed']:
                await asyncio.sleep(.01)

    async def test_expired_ticket_stops_and_never_reaches_motor(self):
        ws = await self.client.ws_connect('/ws')
        old_ticket = (await self.message(ws, 'state'))['ticket']
        await ws.send_json({'action':'arm'})
        await self.message(ws, 'ack')
        await asyncio.sleep(.4)
        await ws.send_json({'action':'drive', 'left':.2, 'right':.2, 'ticket':old_ticket})
        self.assertIn('for gammel', (await self.message(ws, 'error'))['error'])
        self.assertNotIn('drive', self.motor.actions)
        self.assertFalse(self.motor.state['armed'])

    async def test_camera_process_crash_blocks_drive_and_updates_status(self):
        old = time.time()-3
        os.utime(self.run/'cameras.json', (old,old))
        ws = await self.client.ws_connect('/ws')
        state = await self.message(ws, 'state')
        self.assertEqual(state['cameras']['front']['fps'], 0)
        self.assertGreater(state['cameras']['front']['age_s'], 3)
        await ws.send_json({'action':'arm'})
        await self.message(ws, 'ack')
        await ws.send_json({'action':'drive', 'left':.2, 'right':.2, 'ticket':state['ticket']})
        self.assertIn('Kameraet', (await self.message(ws, 'error'))['error'])
        self.assertNotIn('drive', self.motor.actions)
        self.assertFalse(self.motor.state['armed'])

    async def test_invalid_json_shape_returns_client_error(self):
        for body in ('[]', '{broken'):
            response = await self.client.post('/api/action', data=body,
                                               headers={'Content-Type':'application/json'})
            self.assertEqual(response.status, 400)
            self.assertFalse((await response.json())['ok'])
        ws = await self.client.ws_connect('/ws')
        await ws.send_str(json.dumps([]))
        self.assertIn('JSON-objekt', (await self.message(ws, 'error'))['error'])

    async def test_session_probe_requires_a_valid_login(self):
        response = await self.client.get('/api/session')
        self.assertEqual(response.status, 200)
        self.client.session.cookie_jar.clear()
        response = await self.client.get('/api/session')
        self.assertEqual(response.status, 401)


if __name__ == '__main__':
    unittest.main()
