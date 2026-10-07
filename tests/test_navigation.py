import os
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
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


class ExplorationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'AUTONOMY_ENABLED':'1', 'MOTION_CALIBRATED':'1'})
        self.env.start()
        self.data = patch('robotcar.navigation.DATA', Path(self.temp.name))
        self.data.start()
        self.motor = AsyncMock()

    async def asyncTearDown(self):
        self.data.stop()
        self.env.stop()
        self.temp.cleanup()

    async def run_exploration(self, callback):
        nav = Navigator(self.motor, callback)
        nav.goto = AsyncMock()
        await nav.start('explore', {})
        await asyncio.wait_for(nav.task, 2)
        self.motor.request.assert_not_called()
        self.assertEqual(nav.mode, 'idle')
        return nav

    async def test_loaded_map_is_extended_and_saved_under_its_own_name(self):
        calls, mapping, goals = [], False, [[[1, 0]], [[2, 0]], []]
        async def map_call(msg):
            nonlocal mapping
            calls.append(msg)
            if msg['action'] == 'resume_mapping':
                mapping = True
                return {'pose': [0, 0, 0], 'name': 'living-room'}
            if msg['action'] == 'frontiers':
                if not mapping:
                    raise ValueError('Map updates are disabled')
                return {'targets': goals.pop(0)}
            return {'path': [[0, 0], msg.get('goal', [0, 0])]}
        nav = await self.run_exploration(map_call)
        self.assertIsNone(nav.error)
        self.assertEqual(nav.goto.await_count, 2)
        self.assertEqual(calls[-1], {'action': 'save', 'name': 'living-room'})

    async def test_unreachable_frontiers_save_partial_map_and_report_blockage(self):
        calls = []
        async def map_call(msg):
            calls.append(msg)
            if msg['action'] == 'resume_mapping':
                return {'pose': [0, 0, 0], 'name': 'living-room'}
            if msg['action'] == 'frontiers':
                return {'targets': [[2, 0], [0, 2]]}
            if msg['action'] == 'plan' and msg['goal'] != [0, 0]:
                raise ValueError('No safe route')
            return {}
        nav = await self.run_exploration(map_call)
        self.assertIn('Delkartet', nav.error)
        nav.goto.assert_not_called()
        self.assertEqual(calls[-1], {'action': 'save', 'name': 'living-room'})

    async def test_invalid_start_clearance_is_not_success_with_empty_frontiers(self):
        calls = []
        async def map_call(msg):
            calls.append(msg['action'])
            if msg['action'] == 'resume_mapping':
                return {'pose': [0, 0, 0], 'name': 'living-room'}
            if msg['action'] == 'plan':
                raise ValueError('Robot footprint overlaps unknown space')
            return {'targets': []}
        nav = await self.run_exploration(map_call)
        self.assertIn('unknown space', nav.error)
        nav.goto.assert_not_called()
        self.assertNotIn('save', calls)


if __name__ == '__main__':
    unittest.main()
