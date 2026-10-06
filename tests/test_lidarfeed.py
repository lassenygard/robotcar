import tempfile
import time
import unittest
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout
from aiohttp.test_utils import TestClient, TestServer
from robotcar.common import atomic_json
from robotcar.lidarfeed import ScanReceiver, create_app, fetch_scan


TOKEN = 'test-only-' + 'a' * 32
NONCE = 'b' * 32


def frame(sequence=1):
    return dict(source_id='a' * 32, seq=sequence, age_s=.1, nonce=NONCE,
                hz=7, error=None, points=[[i / 20 - 1.5, 2.0, 15] for i in range(60)])


class ScanAgeTests(unittest.TestCase):
    def test_network_delay_is_counted_without_sharing_clocks(self):
        scan = ScanReceiver().receive(frame(), NONCE, 1000, 1000.05)
        self.assertAlmostEqual(scan['monotonic'], 999.9)
        self.assertAlmostEqual(scan['roundtrip_ms'], 50)

    def test_frozen_sequence_cannot_be_refreshed_by_polling(self):
        receiver = ScanReceiver()
        first = receiver.receive(frame(), NONCE, 10, 10.05)
        frozen = frame()
        frozen['age_s'] = 0
        repeat = receiver.receive(frozen, NONCE, 10.4, 10.45)
        self.assertEqual(repeat['seq'], first['seq'])
        self.assertEqual(repeat['monotonic'], first['monotonic'])
        with self.assertRaisesRegex(ValueError, 'stopped updating'):
            receiver.receive(frozen, NONCE, 10.7, 10.75)

    def test_source_restart_is_distinct_but_old_sequence_is_rejected(self):
        receiver = ScanReceiver()
        first = receiver.receive(frame(15), NONCE, 10, 10.05)
        with self.assertRaisesRegex(ValueError, 'backwards'):
            receiver.receive(frame(14), NONCE, 10.1, 10.15)
        reboot = frame(1)
        reboot['source_id'] = 'c' * 32
        after = receiver.receive(reboot, NONCE, 10.2, 10.25)
        self.assertEqual(after['seq'], first['seq'] + 1)

    def test_stale_corrupt_and_mismatched_replies_are_rejected(self):
        corruptions = [dict(age_s=.64), dict(age_s=-1), dict(age_s=float('nan')),
                       dict(nonce='c' * 32), dict(points=[]), dict(seq=True),
                       dict(error='sensor offline')]
        for change in corruptions:
            with self.subTest(change=change), self.assertRaises(ValueError):
                ScanReceiver().receive({**frame(), **change}, NONCE, 10, 10.1)
        for bad in ([float('inf'), 2, 15], [0, 0, 15], [0, 2, 0], [0, 2, True]):
            value = frame()
            value['points'][0] = bad
            with self.subTest(point=bad), self.assertRaises(ValueError):
                ScanReceiver().receive(value, NONCE, 10, 10.05)


class ScanFeedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'lidar.json'
        self.client = TestClient(TestServer(create_app(TOKEN, self.path)))
        await self.client.start_server()
        self.headers = {'Authorization': 'Bearer ' + TOKEN}

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_authentication_and_no_stale_source_data(self):
        state = frame()
        state['monotonic'] = time.monotonic() - 2
        atomic_json(self.path, state)
        response = await self.client.get('/scan', params={'nonce': NONCE})
        self.assertEqual(response.status, 401)
        response = await self.client.get('/scan', headers=self.headers)
        self.assertEqual(response.status, 400)
        response = await self.client.get('/scan', headers=self.headers, params={'nonce': NONCE})
        result = await response.json()
        self.assertEqual(result['points'], [])
        self.assertIn('stale', result['error'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    async def test_real_http_fetch_and_source_failure(self):
        state = frame()
        state['monotonic'] = time.monotonic()
        atomic_json(self.path, state)
        url = str(self.client.make_url('')).rstrip('/')
        async with ClientSession(headers=self.headers, timeout=ClientTimeout(total=.45)) as http:
            scan = await fetch_scan(http, url, ScanReceiver())
            self.assertEqual(len(scan['points']), 60)
            self.assertIsNone(scan['error'])
            state['error'] = 'USB disconnected'
            atomic_json(self.path, state)
            with self.assertRaisesRegex(ValueError, 'USB disconnected'):
                await fetch_scan(http, url, ScanReceiver())


if __name__ == '__main__':
    unittest.main()
