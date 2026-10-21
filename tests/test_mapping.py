import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from robotcar.mapping import OccupancyMap, align_scan, transform, scan_points


class MappingTests(unittest.TestCase):
    def test_sparse_pose_uses_known_map_without_integrating_or_double_counting(self):
        m = OccupancyMap(240, .05)
        x, y = np.linspace(-3, 2, 160), np.linspace(-2, 3, 160)
        world = np.vstack([np.c_[x, x*0-2], np.c_[x, x*0+3],
                           np.c_[y*0-3, y], np.c_[y*0+2, y],
                           np.c_[np.linspace(-1, .7, 160), np.full(160, .6)]])
        for cell in m.cells(world):
            m.grid[cell[1], cell[0]] = 4
        m.localized = True
        original = m.grid.copy()

        def scan(pose, step):
            c, s = np.cos(pose[2]), np.sin(pose[2])
            body = (world[::step]-pose[:2]) @ np.array([[c, -s], [s, c]])
            return np.c_[np.arctan2(body[:, 1], body[:, 0]), np.linalg.norm(body, axis=1), np.full(len(body), 15)]

        first = np.array([.04, -.02, .04])
        self.assertTrue(m.update(scan(first, 16)))  # 50 returns
        np.testing.assert_allclose(m.pose, first, atol=.06)
        np.testing.assert_array_equal(m.grid, original)
        self.assertEqual(m.revision, 0)
        second = np.array([.08, -.04, .07])
        self.assertTrue(m.update(scan(second, 8)))  # Dense again, newer pose
        np.testing.assert_allclose(m.pose, second, atol=.06)
        self.assertEqual(m.revision, 1)

    def test_sparse_input_cannot_create_map_or_localise_on_a_single_wall(self):
        m = OccupancyMap()
        scan = [[a, 2, 15] for a in np.linspace(-math.pi, math.pi, 45)]
        self.assertFalse(m.update(scan))
        self.assertFalse(m.localized)
        self.assertEqual(np.count_nonzero(m.grid), 0)
        wall = np.c_[np.linspace(-2, 2, 45), np.full(45, 1.)]
        scan = np.c_[np.arctan2(wall[:, 1], wall[:, 0]), np.linalg.norm(wall, axis=1), np.full(45, 15)]
        m.localized = True
        self.assertFalse(m.update(scan))
        self.assertFalse(m.relocalize(scan))

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

    def test_failed_storage_flush_keeps_previous_map(self):
        m = OccupancyMap(100, .1)
        m.grid[20:30, 20:30] = 4
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'apartment.npz'
            m.save(path)
            original = path.read_bytes()
            m.grid[:] = -4
            with patch('robotcar.common.os.fsync', side_effect=OSError('storage unavailable')):
                with self.assertRaises(OSError):
                    m.save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(OccupancyMap.load(path).grid[25,25], 4)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_invalid_saved_geometry_cannot_be_used_for_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invalid.npz'
            for resolution, pose in [(0, [0,0,0]), (float('nan'), [0,0,0]), (.05, [0,float('inf'),0])]:
                np.savez_compressed(path, grid=np.zeros((100,100)), resolution=resolution,
                                    pose=pose, keyframes='[]', version=1)
                with self.assertRaises(ValueError):
                    OccupancyMap.load(path)


if __name__ == '__main__':
    unittest.main()
