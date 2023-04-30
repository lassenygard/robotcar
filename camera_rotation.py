# camera_rotation.py

import RPi.GPIO as GPIO
import time

class CameraRotation:
    def __init__(self, pins):
        self.pins = pins
        GPIO.setmode(GPIO.BCM)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 0)
        self.seq = [
            [1, 0, 0, 1],
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1]
        ]
        self.step_count = len(self.seq)
        self.current_step = 0

    def rotate(self, direction, steps):
        for _ in range(steps):
            for pin, value in zip(self.pins, self.seq[self.current_step]):
                GPIO.output(pin, value)
            time.sleep(0.001)
            self.current_step += direction
            if self.current_step >= self.step_count:
                self.current_step = 0
            if self.current_step < 0:
                self.current_step = self.step_count - 1

    def rotate_left(self, steps):
        self.rotate(1, steps)

    def rotate_right(self, steps):
        self.rotate(-1, steps)

    def cleanup(self):
        for pin in self.pins:
            GPIO.output(pin, 0)
        GPIO.cleanup()
