import unittest
from robotcar.motor import MotorGuard, GPIOWheels, PINS


class Wheels:
    def apply(self, left, right):
        self.value = (left, right)


class MotorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.time = 0.0
        self.wheels = Wheels()
        self.guard = MotorGuard(self.wheels, clock=lambda: self.time)
        self.guard.handle({'action': 'arm'}, 'client')

    def drive(self, seq, **kwargs):
        return self.guard.handle(dict(action='drive', left=.2, right=.2,
                                      ttl=.3, seq=seq, **kwargs), 'client')

    def test_lost_heartbeat_stops_without_network_handler(self):
        self.drive(1)
        self.time = .31
        self.guard.tick()
        self.assertEqual(self.wheels.value, (0, 0))
        self.assertFalse(self.guard.armed)

    def test_repeated_commands_cannot_extend_run(self):
        for i in range(25):
            self.time = i * .1
            self.drive(i)
        self.time = 2.5
        self.guard.tick()
        self.assertEqual(self.guard.reason, 'continuous_limit')
        with self.assertRaises(ValueError):
            self.drive(26)
        with self.assertRaises(ValueError):
            self.guard.handle({'action': 'arm'}, 'client')
        self.time = 3.6
        self.guard.handle({'action': 'arm'}, 'client')
        self.drive(27)

    def test_stop_cannot_be_used_to_bypass_cooldown(self):
        self.drive(1)
        self.guard.handle({'action': 'stop'}, 'client')
        with self.assertRaises(ValueError):
            self.guard.handle({'action': 'arm'}, 'client')

    def test_autonomy_is_denied(self):
        with self.assertRaises(ValueError):
            self.drive(1, mode='autonomous')
        self.assertEqual(self.wheels.value, (0, 0))

    def test_other_operator_and_replay_denied(self):
        self.drive(1)
        with self.assertRaises(ValueError):
            self.drive(1)
        with self.assertRaises(ValueError):
            self.guard.handle({'action': 'arm'}, 'other')

    def test_nan_and_excessive_ttl_denied(self):
        for left, ttl in [(float('nan'), .3), (.2, 4), (float('inf'), .3)]:
            with self.assertRaises(ValueError):
                self.guard.handle(dict(action='drive', left=left, right=.2, ttl=ttl, seq=1), 'client')

    def test_recovered_wiring_maps_body_sides_and_polarity(self):
        class PinMotor:
            def forward(self, value): self.value = value
            def backward(self, value): self.value = -value
            def stop(self): self.value = 0
        wheels = GPIOWheels.__new__(GPIOWheels)
        wheels.motors = {name: PinMotor() for name in PINS}
        wheels.signs = {'front_right':-1, 'rear_right':-1}
        wheels.swap_sides = True
        wheels.apply(.2,.3)
        self.assertEqual(wheels.motors['front_left'].value, .3)
        self.assertEqual(wheels.motors['rear_left'].value, .3)
        self.assertEqual(wheels.motors['front_right'].value, -.2)
        self.assertEqual(wheels.motors['rear_right'].value, -.2)
        wheels.apply(0,0)
        self.assertTrue(all(m.value == 0 for m in wheels.motors.values()))


if __name__ == '__main__':
    unittest.main()
