import math
import unittest
import numpy as np
from robotcar.mapping import OccupancyMap


class RelocalisationTests(unittest.TestCase):
    def test_visual_seed_must_be_confirmed_by_lidar(self):
        m = OccupancyMap(240, .05)
        y, x = np.linspace(-2.5, 2.7, 160), np.linspace(-3.3, 2.2, 160)
        landmarks = np.vstack([np.c_[np.full_like(y, -3.3), y], np.c_[np.full_like(y, 2.2), y],
                               np.c_[x, np.full_like(x, -2.5)], np.c_[x, np.full_like(x, 2.7)],
                               np.c_[np.linspace(-1.4, 1.1, 160), np.full(160, .4)]])
        for cell in m.cells(landmarks):
            m.grid[cell[1], cell[0]] = 4
        m.keyframes = [{'pose':[0, 0, 0]}]
        expected = np.array([.2, -.1, .17])
        c, s = math.cos(expected[2]), math.sin(expected[2])
        body = (landmarks-expected[:2]) @ np.array([[c, -s], [s, c]])
        scan = np.c_[np.arctan2(body[:, 1], body[:, 0]), np.linalg.norm(body, axis=1), np.full(len(body), 20)]
        self.assertTrue(m.relocalize(scan, [expected+[.05, .03, -.04]]))
        np.testing.assert_allclose(m.pose, expected, atol=.05)
        self.assertGreater(m.confidence, .8)

    def test_symmetric_room_orientation_is_ambiguous(self):
        m = OccupancyMap(240, .05)
        side = np.linspace(-2, 2, 180)
        wall = np.vstack([np.c_[side, np.full_like(side, -2)], np.c_[side, np.full_like(side, 2)],
                          np.c_[np.full_like(side, -2), side], np.c_[np.full_like(side, 2), side]])
        for cell in m.cells(wall):
            m.grid[cell[1],cell[0]] = 4
        m.keyframes = [{'pose':[0,0,0]}]
        scan = np.c_[np.arctan2(wall[:,1],wall[:,0]),np.linalg.norm(wall,axis=1),np.full(len(wall),20)]
        self.assertFalse(m.relocalize(scan))
        self.assertFalse(m.localized)


if __name__ == '__main__':
    unittest.main()
