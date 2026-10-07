import asyncio
import json
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
from robotcar.common import atomic_json, read_json
from robotcar.mapping import OccupancyMap
from robotcar.mapworker import Mapper
from robotcar.navigation import Navigator


class MapIdentityTests(unittest.TestCase):
    def test_save_as_and_expansion_preserve_frame_but_new_map_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory)/'first.npz', Path(directory)/'second.npz'
            original = OccupancyMap(100)
            original.save(first)
            loaded = OccupancyMap.load(first)
            self.assertEqual(original.map_id, loaded.map_id)
            loaded.grid[20:30, 20:30] = -4
            loaded.pose[:] = [1, 2, .3]
            loaded.save(second)
            self.assertEqual(original.map_id, OccupancyMap.load(second).map_id)
            self.assertNotEqual(original.map_id, OccupancyMap(100).map_id)

    def test_legacy_map_identity_is_stable_without_modifying_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path, other = Path(directory)/'old.npz', Path(directory)/'other.npz'
            np.savez_compressed(path, grid=np.zeros((100,100)), resolution=.05,
                                pose=[0,0,0], keyframes='[]', version=1)
            content = path.read_bytes()
            first = OccupancyMap.load(path)
            self.assertEqual(first.map_id, OccupancyMap.load(path).map_id)
            self.assertEqual(content, path.read_bytes())
            other.write_bytes(content)
            self.assertNotEqual(first.map_id, OccupancyMap.load(other).map_id)
            first.save(other)
            self.assertEqual(first.map_id, OccupancyMap.load(other).map_id)

    def test_invalid_explicit_identity_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.npz'
            np.savez_compressed(path, grid=np.zeros((100,100)), resolution=.05,
                                pose=[0,0,0], keyframes='[]', version=1, map_id='broken')
            with self.assertRaises(ValueError):
                OccupancyMap.load(path)

    def test_old_context_cannot_render_plan_or_mutate_new_map(self):
        with tempfile.TemporaryDirectory() as directory, patch('robotcar.mapworker.DATA', Path(directory)):
            mapper = Mapper()
            old = mapper.status()['map_id']
            mapper.action({'action':'new', 'map_id':old})
            current = mapper.status()['map_id']
            for action in ('plan', 'resume_mapping', 'save', 'load', 'new', 'frontiers', 'landmark', 'relocalize'):
                with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'Kartet er byttet'):
                    mapper.action({'action':action, 'map_id':old})
            with self.assertRaisesRegex(ValueError, 'Kartet er byttet'):
                mapper.image(old)
            self.assertTrue(mapper.image(current).startswith(b'\x89PNG'))
            self.assertEqual(current, mapper.status()['map_id'])


class NavigationContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.data = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for module in ('mapworker', 'navigation'):
            self.stack.enter_context(patch('robotcar.'+module+'.DATA', self.data))
        self.stack.enter_context(patch('robotcar.navigation.RUN', self.data))
        self.stack.enter_context(patch.dict(os.environ, {'AUTONOMY_ENABLED':'1', 'MOTION_CALIBRATED':'1'}))
        self.mapper = Mapper()
        self.mapper.map.grid[:] = -4
        self.mapper.map.localized = True
        self.mapper.map.confidence = 1
        self.mapper.last_scan = time.monotonic()
        self.map_id = self.mapper.map.map_id
        atomic_json(self.data/'map.json', self.mapper.status())
        self.motor = AsyncMock()
        async def map_call(message):
            return self.mapper.action(message)
        self.nav = Navigator(self.motor, map_call)
        self.addAsyncCleanup(self.nav.stop)

    async def test_stale_browser_and_legacy_routes_never_arm_motors(self):
        for message in ({}, {'map_id':'old-map', 'goal':[1,0]}):
            with self.assertRaises(ValueError):
                await self.nav.start('goto', message)
        for saved_id in (None, 'other-map'):
            self.nav.settings = {'waypoints':[[1,0]], 'interval_s':300, 'map_id':saved_id}
            with self.assertRaisesRegex(ValueError, 'Vaktruten'):
                await self.nav.start('patrol', {'map_id':self.map_id})
        self.motor.request.assert_not_called()
        self.assertIsNone(self.nav.task)

    async def test_route_round_trip_preserves_coordinates_and_frame(self):
        saved = await self.nav.save_patrol({'map_id':self.map_id, 'waypoints':[['1','2']], 'interval_s':45})
        self.assertEqual(saved['waypoints'], [[1.,2.]])
        self.assertEqual(saved['map_id'], self.map_id)
        restored = Navigator(self.motor, self.nav.map_call)
        self.assertEqual(restored.settings, saved)
        original = (self.data/'patrol.json').read_bytes()
        with self.assertRaises(ValueError):
            await self.nav.save_patrol({'map_id':'stale', 'waypoints':[[3,4]]})
        self.assertEqual(original, (self.data/'patrol.json').read_bytes())
        self.assertEqual(restored.settings, self.nav.settings)

    async def test_failed_route_save_does_not_replace_active_settings(self):
        original = dict(self.nav.settings)
        with patch('robotcar.navigation.atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                await self.nav.save_patrol({'map_id':self.map_id, 'waypoints':[[1,2]]})
        self.assertEqual(self.nav.settings, original)

    async def test_switch_between_patrol_rounds_stops_before_another_move(self):
        await self.nav.save_patrol({'map_id':self.map_id, 'waypoints':[[0,0]], 'interval_s':30})
        async def switch_during_pause(seconds):
            self.assertEqual(seconds, 30)
            self.mapper.action({'action':'new'})
            atomic_json(self.data/'map.json', self.mapper.status())
        with patch('robotcar.navigation.asyncio.sleep', switch_during_pause):
            await self.nav.start('patrol', {'map_id':self.map_id})
            await asyncio.wait_for(self.nav.task, 2)
        self.assertIn('Kartet er byttet', self.nav.error)
        self.motor.request.assert_not_called()
        self.assertEqual(self.nav.mode, 'idle')

    async def test_switch_during_pulse_stops_before_second_drive(self):
        self.nav.map_id = self.map_id
        async def command(action, **kwargs):
            if action == 'drive':
                self.mapper.action({'action':'new'})
                atomic_json(self.data/'map.json', self.mapper.status())
        self.motor.request.side_effect = command
        with patch.object(self.nav, 'obstacle_check'):
            with self.assertRaisesRegex(ValueError, 'Kartet er byttet'):
                await self.nav.pulse(.2, .2, .3)
        self.assertEqual([c.args[0] for c in self.motor.request.call_args_list], ['arm', 'drive'])
        self.motor.stop.assert_awaited_once()

    async def test_stale_mapper_prevents_motor_arming(self):
        self.nav.map_id = self.map_id
        old = time.time()-2
        os.utime(self.data/'map.json', (old, old))
        with self.assertRaisesRegex(ValueError, 'sluttet å oppdatere'):
            await self.nav.pulse(.2, .2)
        self.motor.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
