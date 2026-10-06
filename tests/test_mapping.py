import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from robotcar.mapping import OccupancyMap, align_scan, transform, scan_points


class MappingTests(unittest.TestCase):
    def test_icp_recovers_measured_motion(self):
        rng = np.random.default_rng(7)
        reference = rng.uniform(-3, 3, (300, 2))
        expected = np.array([.06, -.04, .03])
        c, s = math.cos(expected[2]), math.sin(expected[2])
        points = (reference-expected[:2]) @ np.array([[c,-s],[s,c]])
        recovered, score = align_scan(points, reference)
        np.testing.assert_allclose(recovered, expected, atol=.005)
        self.assertGreater(score, .95)

    def test_unknown_space_and_walls_are_not_paths(self):
        m = OccupancyMap(100, .1)
        with self.assertRaises(ValueError):
            m.plan([1, 1])
        m.grid[10:90, 10:90] = -4
        m.grid[:, 60] = 4
        with self.assertRaises(ValueError):
            m.plan([2, 0])
        path = m.plan([-2, 1])
        self.assertGreater(len(path), 10)
        self.assertTrue(all(p[0] < 1 for p in path))

    def test_load_does_not_claim_old_pose_as_current(self):
        m = OccupancyMap(100, .1)
        m.grid[15:50, 20:30] = 4
        m.pose[:] = [.2, .4, 1]
        m.keyframes = [{'pose': m.pose.tolist()}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'map.npz'
            m.save(p)
            restored = OccupancyMap.load(p)
            np.testing.assert_equal(restored.grid, m.grid)
            self.assertFalse(restored.localized)
            self.assertFalse(restored.mapping)
            self.assertEqual(restored.keyframes, m.keyframes)

    def test_lidar_units_and_invalid_scan(self):
        with self.assertRaises(ValueError):
            scan_points([])
        points = scan_points([[0, 2, 10]]*60)
        np.testing.assert_allclose(points[0], [2, 0])


if __name__ == '__main__':
    unittest.main()
