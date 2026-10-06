import os
import time
import unittest
from unittest.mock import patch
from robotcar.navigation import Navigator


class NavigationTests(unittest.TestCase):
    def test_unattended_autonomy_is_refused(self):
        with patch.dict(os.environ, {'AUTONOMY_ENABLED':'0','MOTION_CALIBRATED':'1'}):
            nav=Navigator(None,None)
            with self.assertRaises(ValueError):
                nav.validate_ready()

    def test_uncalibrated_autonomy_is_refused(self):
        with patch.dict(os.environ, {'AUTONOMY_ENABLED':'1','MOTION_CALIBRATED':'0'}):
            nav=Navigator(None,None)
            with self.assertRaises(ValueError):
                nav.validate_ready()

    def test_missing_stale_or_close_lidar_blocks_motion(self):
        nav=Navigator(None,None)
        for scan in [{}, {'monotonic':time.monotonic()-2, 'points':[[0,2,10]]*100},
                     {'monotonic':time.monotonic(), 'points':[[0,.3,10]]*100}]:
            with patch('robotcar.navigation.read_json',return_value=scan):
                with self.assertRaises(ValueError):
                    nav.obstacle_check(.25,0)

    def test_rotation_checks_all_directions(self):
        scan={'monotonic':time.monotonic(), 'points':[[0,2,10]]*100+[[3.14,.2,10]]}
        with patch('robotcar.navigation.read_json',return_value=scan):
            with self.assertRaises(ValueError):
                Navigator(None,None).obstacle_check(0,.25)


if __name__ == '__main__':
    unittest.main()
