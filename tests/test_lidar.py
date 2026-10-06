import unittest
from robotcar.lidar import decode_packet


def packet(angle, distance_mm, quality=20, new=True):
    angle_q6 = round(angle*64)
    distance_q2 = round(distance_mm*4)
    return bytes([(quality<<2) | (1 if new else 2), ((angle_q6 & 127)<<1)|1,
                  angle_q6>>7, distance_q2 & 255, distance_q2>>8])


class LidarProtocolTests(unittest.TestCase):
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
