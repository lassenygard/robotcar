import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import ClientSession, ClientTimeout
from aiohttp.test_utils import TestClient, TestServer
from robotcar import camera
from robotcar.cameralink import FrameReceiver, RemoteCamera, fetch_frame

JPEG = b'\xff\xd8test\xff\xd9'
TOKEN = 'camera-test-token-123456789012345'
NONCE = 'a'*32


class ReceiverTests(unittest.TestCase):
    def headers(self, **changes):
        return {'X-Camera-Nonce': NONCE, 'X-Camera-Source': 'b'*32,
                'X-Camera-Role': 'rear', 'X-Camera-Model': 'imx219',
                'X-Frame-Sequence': '1', 'X-Frame-Age': '.1', **changes}

    def test_remote_clock_is_not_compared_and_roundtrip_is_included(self):
        receiver = FrameReceiver('rear')
        headers = self.headers(**{'X-Frame-Monotonic': '999999999'})
        frame = receiver.receive(headers, JPEG, NONCE, 100, 100.2)
        self.assertAlmostEqual(frame.when, 99.9)

    def test_frozen_sequence_cannot_be_rejuvenated(self):
        receiver = FrameReceiver('rear')
        frame = receiver.receive(self.headers(), JPEG, NONCE, 100, 100.1)
        headers = self.headers(**{'X-Frame-Age': '0'})
        self.assertIsNone(receiver.receive(headers, JPEG, NONCE, 100.5, 100.6))
        self.assertIs(receiver.frame, frame)
        with self.assertRaisesRegex(ValueError, 'stopped updating'):
            receiver.receive(headers, JPEG, NONCE, 101, 101.1)

    def test_bad_nonce_wrong_sensor_stale_and_invalid_payloads_are_rejected(self):
        for change in ({'X-Camera-Nonce': 'c'*32}, {'X-Camera-Role':'front'},
                       {'X-Camera-Model':'imx708'}, {'X-Frame-Age':'nan'},
                       {'X-Frame-Age':'-1'}, {'X-Frame-Age':'1'},
                       {'X-Frame-Sequence':'0'}, {'X-Camera-Source':'bad'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                FrameReceiver('rear').receive(self.headers(**change), JPEG, NONCE, 100, 100.2)
        with self.assertRaises(ValueError):
            FrameReceiver('rear').receive(self.headers(), b'not jpeg', NONCE, 100, 100.1)

    def test_backwards_sequence_refused_new_source_can_restart(self):
        receiver = FrameReceiver('rear')
        receiver.receive(self.headers(**{'X-Frame-Sequence':'8'}), JPEG, NONCE, 100, 100.1)
        with self.assertRaises(ValueError):
            receiver.receive(self.headers(), JPEG, NONCE, 100.1, 100.2)
        frame = receiver.receive(self.headers(**{'X-Camera-Source':'c'*32}), JPEG, NONCE, 100.1, 100.2)
        self.assertEqual(frame.seq, 2)

    def test_roles_are_explicit_and_not_duplicated(self):
        with patch.dict(os.environ, {'CAMERA_LOCAL_ROLES':'front', 'CAMERA_REAR_URL':'http://192.168.4.43:8800'}):
            cameras = camera.configured_cameras()
            self.assertEqual(set(cameras), {'front', 'rear'})
            self.assertIsInstance(cameras['rear'], RemoteCamera)
        with patch.dict(os.environ, {'CAMERA_LOCAL_ROLES':'rear', 'CAMERA_REAR_URL':'http://192.168.4.43:8800'}):
            with self.assertRaises(ValueError):
                camera.configured_cameras()
        self.assertEqual(camera.SPECS['front'][0], 'imx708')
        self.assertEqual(camera.SPECS['rear'][0], 'imx219')


class LinkHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = patch.object(camera, 'RUN', Path(self.temp.name))
        self.run.start()
        self.notify = patch.object(camera, 'notify_watchdog')
        self.notify.start()
        self.cam = camera.Camera('rear')
        self.cam.error = None
        self.cam.frame = camera.Frame(1, time.monotonic(), JPEG)
        self.server = TestServer(camera.create_app({'rear':self.cam}, start_workers=False, auth_token=TOKEN))
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.notify.stop()
        self.run.stop()
        self.temp.cleanup()

    async def test_auth_nonce_and_valid_network_transfer(self):
        for path in ('/snapshot/rear', '/status', '/stream/rear'):
            response = await self.client.get(path)
            self.assertEqual(response.status, 401)
            response.release()
        headers = {'Authorization':'Bearer '+TOKEN}
        response = await self.client.get('/snapshot/rear', headers=headers)
        self.assertEqual(response.status, 400)
        response.release()
        async with ClientSession(headers=headers, timeout=ClientTimeout(total=1)) as http:
            frame = await fetch_frame(http, str(self.server.make_url('')).rstrip('/'), FrameReceiver('rear'))
            self.assertEqual(frame.jpeg, JPEG)
            self.assertLess(time.monotonic()-frame.when, .5)
            self.cam.frame = camera.Frame(1, time.monotonic()-2, JPEG)
            with self.assertRaisesRegex(ValueError, '503'):
                await fetch_frame(http, str(self.server.make_url('')).rstrip('/'), FrameReceiver('rear'))

    async def test_link_loss_and_recovery_does_not_refresh_stale_frame(self):
        remote = RemoteCamera('rear', str(self.server.make_url('')).rstrip('/'))
        with patch.dict(os.environ, {'ROBOTCAR_TOKEN':TOKEN}), patch('robotcar.cameralink.RUN', Path(self.temp.name)):
            task = asyncio.create_task(remote.run())
            try:
                async with asyncio.timeout(3):
                    while not remote.fresh_frame():
                        await asyncio.sleep(.02)
                    first = remote.seq
                    self.cam.error = 'simulated source stopped'
                    while not remote.error:
                        await asyncio.sleep(.02)
                    self.assertIsNone(remote.fresh_frame())
                    self.assertEqual(remote.status()['fps'], 0)
                    self.cam.frame = camera.Frame(2, time.monotonic(), JPEG)
                    self.cam.error = None
                    while remote.seq == first or remote.error:
                        await asyncio.sleep(.02)
                    self.assertIsNotNone(remote.fresh_frame())
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
