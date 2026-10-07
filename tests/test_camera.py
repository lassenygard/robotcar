import asyncio
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import MultipartReader
from aiohttp.test_utils import TestClient, TestServer
from robotcar import camera


JPEG = b'\xff\xd8test\xff\xd9'


class CameraStateTests(unittest.TestCase):
    def test_missing_sensor_does_not_swap_front_and_rear(self):
        info = [{'Num': 0, 'Model': 'imx708_wide'}]
        with self.assertRaisesRegex(RuntimeError, 'imx219'):
            camera.sensor_number(info, 'imx219')
        self.assertEqual(camera.sensor_number(info, 'imx708'), 0)
        self.assertEqual(camera.sensor_number([{'Num': 1, 'Model': 'imx219'}], 'imx219'), 1)

    def test_stale_capture_reports_failure_even_when_supervisor_is_alive(self):
        cam = camera.Camera('rear')
        cam.frame = camera.Frame(3, time.monotonic()-2, JPEG)
        cam.error, cam.fps = None, 20
        self.assertEqual(cam.status()['fps'], 0)
        self.assertIsNotNone(cam.status()['error'])
        self.assertIsNone(cam.fresh_frame())

    def test_watchdog_reaches_systemd_notification_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'notify')
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(path)
                receiver.settimeout(1)
                with patch.dict(os.environ, {'NOTIFY_SOCKET': path}):
                    camera.notify_watchdog()
                self.assertEqual(receiver.recv(128), b'WATCHDOG=1')


class CameraPacketTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_packet_times_out(self):
        reader = asyncio.StreamReader()
        reader.feed_data(camera.HEADER.pack(time.monotonic(), 100) + b'partial')
        with self.assertRaises(asyncio.TimeoutError):
            await camera.read_frame(reader, .05)

    async def test_old_invalid_and_oversized_frames_are_refused(self):
        for stamp, payload, length in (
            (time.monotonic()-2, JPEG, len(JPEG)),
            (float('nan'), JPEG, len(JPEG)),
            (time.monotonic()+10, JPEG, len(JPEG)),
            (time.monotonic(), b'broken', 6),
            (time.monotonic(), b'', camera.MAX_FRAME_BYTES+1),
        ):
            reader = asyncio.StreamReader()
            reader.feed_data(camera.HEADER.pack(stamp, length) + payload)
            reader.feed_eof()
            with self.assertRaises(ValueError):
                await camera.read_frame(reader, 1)

    async def test_sensor_diagnostic_is_preserved(self):
        reader = asyncio.StreamReader()
        reason = b'Expected one imx219 sensor; detected 0'
        reader.feed_data(camera.HEADER.pack(0, len(reason)) + reason)
        with self.assertRaisesRegex(RuntimeError, 'detected 0'):
            await camera.read_frame(reader, 1)


class CameraHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = patch.object(camera, 'RUN', Path(self.temp.name))
        self.run.start()
        self.notify = patch.object(camera, 'notify_watchdog')
        self.notify.start()
        self.cam = camera.Camera('front')
        self.client = TestClient(TestServer(camera.create_app({'front': self.cam}, start_workers=False)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.notify.stop()
        self.run.stop()
        self.temp.cleanup()

    async def test_dead_camera_never_opens_a_successful_video_stream(self):
        for route in ('snapshot', 'stream'):
            response = await self.client.get('/'+route+'/front')
            self.assertEqual(response.status, 503)
            await response.release()

    async def test_live_stream_ends_when_capture_stalls(self):
        self.cam.error = None
        self.cam.frame = camera.Frame(8, time.monotonic(), JPEG)
        response = await self.client.get('/stream/front')
        self.assertEqual(response.status, 200)
        reader = MultipartReader.from_response(response)
        async with asyncio.timeout(2):
            part = await reader.next()
            self.assertEqual(part.headers['X-Frame-Sequence'], '8')
            self.assertEqual(await part.read(), JPEG)
            self.cam.frame = camera.Frame(8, time.monotonic()-2, JPEG)
            self.assertIsNone(await reader.next())
        response.close()


class CameraRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_frozen_child_is_killed_without_interrupting_other_camera(self):
        # Real subprocesses and pipes exercise blocked native-call recovery.
        # The fake rear ignores SIGTERM; the front keeps producing frames.
        producer = '''import os, signal, struct, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True:
    image = b'\\xff\\xd8test\\xff\\xd9'
    os.write(1, struct.pack('!dI', time.monotonic(), len(image))+image)
    time.sleep(60 if sys.argv[1] == 'rear' else .04)
'''
        front, rear = camera.Camera('front'), camera.Camera('rear')
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(camera, 'RUN', Path(directory)), \
                patch.object(camera, 'capture_command', side_effect=lambda name: (sys.executable, '-c', producer, name)), \
                patch.object(camera, 'FRAME_TIMEOUT', .3), \
                patch.object(camera, 'RETRY_MIN', .05), \
                patch.object(camera, 'RETRY_MAX', .1):
            tasks = [asyncio.create_task(cam.run()) for cam in (front, rear)]
            try:
                async with asyncio.timeout(5):
                    while front.seq < 2 or rear.seq < 1:
                        await asyncio.sleep(.02)
                    front_pid, rear_pid = front.pid, rear.pid
                    first_seq = front.seq
                    while rear.restarts < 1 or rear.seq < 2:
                        await asyncio.sleep(.02)
                self.assertEqual(front.pid, front_pid)
                self.assertEqual(front.restarts, 0)
                self.assertGreater(front.seq, first_seq+10)
                self.assertIsNotNone(front.fresh_frame())
                self.assertNotEqual(rear.pid, rear_pid)
                with self.assertRaises(ProcessLookupError):
                    os.kill(rear_pid, 0)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            self.assertIsNone(front.pid)
            self.assertIsNone(rear.pid)


if __name__ == '__main__':
    unittest.main()
