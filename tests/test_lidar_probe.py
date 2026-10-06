import unittest

from scripts.probe_lidar import DESCRIPTOR, summarize
from test_lidar import packet


class LidarProbeTests(unittest.TestCase):
    def test_empty_measurements_are_not_usable_scans(self):
        data = DESCRIPTOR + b''.join(packet(i, 0, quality=0, new=(i % 120 == 0)) for i in range(360))
        result = summarize(data, 'force-scan')
        self.assertEqual(result['packets'], 360)
        self.assertEqual(result['valid_returns'], 0)
        self.assertEqual(result['complete_revolutions_with_60_returns'], 0)

    def test_requires_descriptor_and_complete_revolution(self):
        revolution = b''.join(packet(i * 3, 1500, new=(i == 0)) for i in range(120))
        self.assertNotIn('valid_returns', summarize(revolution, 'scan'))
        result = summarize(DESCRIPTOR + revolution + revolution[:5], 'scan')
        self.assertEqual(result['complete_revolutions_with_60_returns'], 1)
        self.assertEqual(result['distance_min_m'], 1.5)
        self.assertEqual(result['distance_max_m'], 1.5)

    def test_does_not_report_truncated_information_as_complete(self):
        descriptor = bytes.fromhex('a55a1400000004')
        payload = bytes([24, 29, 1, 7]) + bytes(16)
        self.assertNotIn('model', summarize(descriptor + payload[:-1], 'info'))
        result = summarize(descriptor + payload, 'info')
        self.assertEqual((result['model'], result['firmware'], result['hardware']), (24, '1.29', 7))


if __name__ == '__main__':
    unittest.main()
