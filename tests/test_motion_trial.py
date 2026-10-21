import unittest
from scripts.record_motion_trial import rotation_step


class RotationStepTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0
        self.commands = []
        self.state = {'map': {'localized': True, 'confidence': .8, 'age_s': .1},
                      'lidar': {'error': None, 'points': [[0, 2, 15]]}, 'ticket': 'test'}

    async def send(self, action, **kwargs):
        self.commands.append((self.now, action))

    async def sleep(self, delay):
        self.now += max(delay, .001)

    async def run_step(self, seconds=1, left=-.25, right=.25, send=None):
        await rotation_step(send or self.send, lambda: self.state, lambda: None,
                            seconds, left, right, clock=lambda: self.now, sleep=self.sleep)

    async def test_bounded_step_stops_without_any_rearming(self):
        await self.run_step()
        self.assertEqual(self.commands[-1][1], 'stop')
        self.assertLessEqual(max(t for t, a in self.commands if a == 'drive'), 1)
        self.assertEqual(set(a for _, a in self.commands), {'drive', 'stop'})

    async def test_lost_position_stops_before_next_drive(self):
        async def send(action, **kwargs):
            await self.send(action, **kwargs)
            self.state['map']['localized'] = False
        with self.assertRaisesRegex(ValueError, 'localisation'):
            await self.run_step(send=send)
        self.assertEqual([a for _, a in self.commands], ['drive', 'stop'])

    async def test_slow_ack_never_sends_a_drive_after_deadline(self):
        async def send(action, **kwargs):
            await self.send(action, **kwargs)
            if action == 'drive':
                self.now += 1.1
        await self.run_step(send=send)
        self.assertEqual([a for _, a in self.commands], ['drive', 'stop'])

    async def test_bad_limits_and_translation_never_send_commands(self):
        for seconds, left, right in ((2, -.2, .2), (1, .2, .2), (1, -.5, .5), (float('nan'), -.2, .2)):
            with self.assertRaises(ValueError):
                await self.run_step(seconds, left, right)
        self.assertEqual(self.commands, [])

    async def test_obstacle_stops_without_driving(self):
        self.state['lidar']['points'] = [[0, .3, 15]]
        with self.assertRaisesRegex(ValueError, 'obstacle'):
            await self.run_step()
        self.assertEqual([a for _, a in self.commands], ['stop'])


if __name__ == '__main__':
    unittest.main()
