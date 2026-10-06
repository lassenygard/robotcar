import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('robotcar_release', Path(__file__).parents[1]/'deploy'/'release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source, self.root = Path(self.temp.name)/'source', Path(self.temp.name)/'installed'
        package = self.source/'robotcar'
        package.mkdir(parents=True)
        for name in ('__init__', 'common', 'motor', 'camera', 'lidar', 'vision', 'mapping', 'mapworker', 'navigation', 'webapp'):
            (package/(name+'.py')).write_text('version = 1\n')
        self.first = release.stage_release(self.source, self.root)
        release.activate_release(self.first, self.root)

    def test_write_failure_preserves_active_release(self):
        (self.source/'robotcar/camera.py').write_text('version = 2\n')
        write = release.write_file
        calls = 0
        def interrupted(path, data):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('simulated storage interruption')
            write(path, data)
        with patch.object(release, 'write_file', side_effect=interrupted):
            with self.assertRaises(OSError):
                release.stage_release(self.source, self.root)
        self.assertEqual((self.root/'current').resolve(), self.first)
        self.assertEqual((self.root/'current/robotcar/camera.py').read_text(), 'version = 1\n')

    def test_corrupt_source_and_corrupt_staged_release_are_not_activated(self):
        (self.source/'robotcar/camera.py').write_bytes(b'\0'*100)
        with self.assertRaises((SyntaxError, ValueError)):
            release.stage_release(self.source, self.root)
        (self.source/'robotcar/camera.py').write_text('version = 2\n')
        second = release.stage_release(self.source, self.root)
        (second/'robotcar/camera.py').write_bytes(b'')
        with self.assertRaises(ValueError):
            release.activate_release(second, self.root)
        self.assertEqual((self.root/'current').resolve(), self.first)

    def test_complete_release_switch_keeps_previous_version(self):
        (self.source/'robotcar/camera.py').write_text('version = 2\n')
        second = release.stage_release(self.source, self.root)
        self.assertEqual((self.root/'current').resolve(), self.first)
        release.activate_release(second, self.root)
        self.assertEqual((self.root/'current/robotcar/camera.py').read_text(), 'version = 2\n')
        self.assertEqual((self.first/'robotcar/camera.py').read_text(), 'version = 1\n')
        release.activate_release(self.first, self.root)
        self.assertEqual((self.root/'current').resolve(), self.first)
