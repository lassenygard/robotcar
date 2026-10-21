import unittest
from unittest.mock import patch
from robotcar.lidar import RPLidar, decode_packet


def packet(angle, distance_mm, quality=20, new=True):
    angle_q6 = round(angle*64)
    distance_q2 = round(distance_mm*4)
    return bytes([(quality<<2) | (1 if new else 2), ((angle_q6 & 127)<<1)|1,
                  angle_q6>>7, distance_q2 & 255, distance_q2>>8])


class LidarProtocolTests(unittest.TestCase):
    def device(self, serial):
        device = RPLidar.__new__(RPLidar)
        device.serial = serial
        return device

    def test_reset_banner_does_not_poison_health_and_scan(self):
        # Fake the sensor boot output and enforce both motor settling periods.
        class UART:
            dtr = False
            rts = False
            incoming = b''
            reset_done = False
            spun_up = False
            stop_settled = False

            def write(self, command):
                if command == b'\xa5\x40':
                    assert self.dtr and self.stop_settled
                    self.incoming = b'RPLIDAR boot banner\r\n'
                elif command == b'\xa5\x52':
                    assert self.reset_done and self.spun_up and not self.dtr
                    self.incoming += b'\xa5\x5a\x03\x00\x00\x00\x06\x00\x00\x00'
                elif command == b'\xa5\x20':
                    self.incoming += b'\xa5\x5a\x05\x00\x00\x40\x81'

            def wait(self, seconds):
                if seconds >= .001:
                    self.stop_settled = True
                if seconds >= 2:
                    if self.dtr:
                        self.reset_done = True
                    else:
                        self.spun_up = True

            def reset_input_buffer(self):
                self.incoming = b''

            def read(self, size):
                result, self.incoming = self.incoming[:size], self.incoming[size:]
                return result

        serial = UART()
        with patch('robotcar.lidar.time.sleep', side_effect=serial.wait):
            self.device(serial).start()
        self.assertEqual(serial.incoming, b'')
        self.assertFalse(serial.dtr)

    def test_sparse_revolutions_still_fail_with_diagnostics(self):
        class UART:
            in_waiting = 4096

            def read(self, size):
                return b''.join(packet(i * 6, 1500, new=i == 0) for i in range(10))

        with patch('robotcar.lidar.time.monotonic', side_effect=[0, 1, 10.1]):
            with self.assertRaisesRegex(TimeoutError, r'bytes=100, packets=10, revolutions=1, max_points=10'):
                next(self.device(UART()).scans())

    def test_warmup_never_yields_sparse_scan_and_does_not_extend_live_watchdog(self):
        class UART:
            in_waiting = 4096
            count = 0

            def read(self, size):
                self.count += 1
                if self.count == 1:
                    return packet(0, 1500) + packet(1, 1500, new=False)
                if self.count == 2:
                    return b''.join(packet(i * 6, 1500, new=i == 0) for i in range(60)) + packet(0, 1500)
                return b''

        with patch('robotcar.lidar.time.monotonic', side_effect=[0, 1, 6, 6, 8.1]):
            scans = self.device(UART()).scans()
            self.assertEqual(len(next(scans)), 60)
            with self.assertRaisesRegex(TimeoutError, 'for 2 seconds'):
                next(scans)

    def test_units_and_new_scan_flag(self):
        new, q, angle, distance = decode_packet(packet(123.25, 1500))
        self.assertEqual((new,q,angle,distance), (True,20,123.25,1.5))

    def test_rejects_corrupt_flags_and_out_of_range_angle(self):
        p=bytearray(packet(10,1000));p[0] |= 3
        self.assertIsNone(decode_packet(p))
        p=bytearray(packet(10,1000));p[1] &= 254
        self.assertIsNone(decode_packet(p))
        self.assertIsNone(decode_packet(packet(400,1000)))
        self.assertIsNone(decode_packet(b'123'))


if __name__ == '__main__':
    unittest.main()
