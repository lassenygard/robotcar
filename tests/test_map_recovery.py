import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from robotcar.common import atomic_json
from robotcar.mapworker import Mapper


class MapRecoveryTests(unittest.TestCase):
    def test_replacing_map_clears_old_visual_matches_and_live_scan(self):
        with tempfile.TemporaryDirectory() as directory, patch('robotcar.mapworker.DATA', Path(directory)):
            mapper = Mapper()
            for action in ({'action': 'new'}, {'action': 'load', 'name': 'saved'}):
                mapper.map.save(Path(directory)/'maps'/'saved.npz')
                mapper.landmark_matches = [{'name': 'previous room'}]
                mapper.last_scan, mapper.last_sequence = 500, 20
                mapper.last_relocalize = 500
                mapper.action(action)
                self.assertEqual(mapper.status()['recognised'], [])
                self.assertEqual(mapper.last_scan, 0)
                self.assertEqual(mapper.last_sequence, -1)
                self.assertEqual(mapper.last_relocalize, 0)
                self.assertFalse(mapper.status()['localized'])
            mapper.landmark_matches = [{'name': 'old view'}]
            with patch.object(mapper, 'features', return_value=([], None)):
                self.assertEqual(mapper.recognise(), [])
            self.assertEqual(mapper.status()['recognised'], [])

    def test_corrupt_active_map_requires_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data/'maps').mkdir()
            corrupt = data/'maps'/'apartment.npz'
            corrupt.write_bytes(b'\0' * 200)
            atomic_json(data/'active_map.json', {'name': 'apartment'})
            with patch('robotcar.mapworker.DATA', data):
                mapper = Mapper()
                self.assertFalse(mapper.status()['localized'])
                self.assertFalse(mapper.status()['mapping'])
                with patch.object(mapper.map, 'update') as update:
                    mapper.process()
                    update.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'Saved map'):
                    mapper.action({'action': 'plan', 'goal': [1, 1]})
                with self.assertRaisesRegex(ValueError, 'Saved map'):
                    mapper.action({'action': 'save', 'name': 'apartment'})
                self.assertEqual(corrupt.read_bytes(), b'\0' * 200)
                mapper.action({'action': 'new'})
                self.assertIsNone(mapper.load_error)
                self.assertTrue(mapper.status()['mapping'])
                self.assertFalse(mapper.status()['localized'])
                self.assertEqual(corrupt.read_bytes(), b'\0' * 200)


if __name__ == '__main__':
    unittest.main()
