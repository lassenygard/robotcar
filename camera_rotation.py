# camera_rotation.py

import RPi.GPIO as GPIO
import time

class CameraRotation:
    def __init__(self, pins, initial_angle=0):
        self.pins = pins
        self.current_angle = initial_angle
        GPIO.setmode(GPIO.BCM) # type: ignore
        for pin in self.pins:
            GPIO.setup(pin, GPIO.OUT) # type: ignore
            GPIO.output(pin, 0) # type: ignore
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
                GPIO.output(pin, value) # type: ignore
            time.sleep(0.001)
            self.current_step += direction
            if self.current_step >= self.step_count:
                self.current_step = 0
            if self.current_step < 0:
                self.current_step = self.step_count - 1

    def rotate_left(self, angle):
        if self.current_angle + angle <= 60:
            steps = self.angle_to_steps(angle)
            self.rotate(1, steps)
            self.current_angle += angle

    def rotate_right(self, angle):
        if self.current_angle - angle >= -60:
            steps = self.angle_to_steps(angle)
            self.rotate(-1, steps)
            self.current_angle -= angle

    def angle_to_steps(self, angle):
        steps_per_revolution = 200  # Update this value based on your stepper motor's specifications
        degrees_per_step = 360 / steps_per_revolution
        return int(angle / degrees_per_step)

    def cleanup(self):
        for pin in self.pins:
            GPIO.output(pin, 0) # type: ignore
        GPIO.cleanup() # type: ignore