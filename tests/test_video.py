import asyncio
import contextlib
import time
import unittest

from aiohttp import ClientSession, MultipartReader, web
from aiohttp.test_utils import TestClient, TestServer
from robotcar.camera import Frame
from robotcar.video import relay_latest, stream_latest

JPEG = b'\xff\xd8test\xff\xd9'


class BackpressureTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_writer_fetches_only_after_previous_frame_is_sent(self):
        gate = asyncio.Event()
        entered = asyncio.Event()
        fetched, sent = [], []
        latest = 1
        async def fetch():
            fetched.append(latest)
            return Frame(latest, time.monotonic(), JPEG)
        async def send(data):
            sent.append(data)
            if len(sent) == 1:
                entered.set()
                await gate.wait()
            else:
                raise ValueError('test finished')
        task = asyncio.create_task(relay_latest(fetch, send, await fetch()))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            latest = 20
            await asyncio.sleep(.1)
            self.assertEqual(fetched, [1])
            gate.set()
            with self.assertRaisesRegex(ValueError, 'test finished'):
                await asyncio.wait_for(task, 1)
            self.assertEqual(fetched, [1, 20])
            self.assertIn(b'X-Frame-Sequence: 20', sent[1])
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, ValueError):
                await task

    async def test_stalled_writer_has_a_deadline(self):
        async def fetch():
            self.fail('Must not fetch during a blocked write')
        async def send(data):
            await asyncio.Event().wait()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(relay_latest(fetch, send, Frame(1, time.monotonic(), JPEG)), .9)


class VideoHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.age, self.status, self.sequence = 0, 200, 1
        async def snapshot(request):
            return web.Response(status=self.status, body=JPEG, content_type='image/jpeg', headers={
                'X-Frame-Sequence': str(self.sequence), 'X-Frame-Monotonic': str(time.monotonic()-self.age)})
        backend = web.Application()
        backend.router.add_get('/snapshot', snapshot)
        self.backend = TestServer(backend)
        await self.backend.start_server()
        self.http = ClientSession()
        async def video(request):
            return await stream_latest(request, self.http, str(self.backend.make_url('/snapshot')))
        app = web.Application()
        app.router.add_get('/video', video)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.http.close()
        await self.backend.close()

    async def test_latest_images_retain_capture_timestamp_and_sequence(self):
        response = await self.client.get('/video')
        self.assertEqual(response.status, 200)
        reader = MultipartReader.from_response(response)
        part = await reader.next()
        self.assertEqual(await part.read(), JPEG)
        self.assertEqual(part.headers['X-Frame-Sequence'], '1')
        self.assertLess(time.monotonic()-float(part.headers['X-Frame-Monotonic']), 1)
        self.sequence = 25
        async with asyncio.timeout(1):
            while True:
                part = await reader.next()
                await part.read()
                if part.headers['X-Frame-Sequence'] == '25':
                    break
        response.close()

    async def test_stale_or_missing_camera_is_503_before_stream_headers(self):
        for self.age, self.status in ((2, 200), (0, 503)):
            response = await self.client.get('/video')
            self.assertEqual(response.status, 503)
            await response.release()
