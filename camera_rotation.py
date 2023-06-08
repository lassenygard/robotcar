import time
import RPi.GPIO as GPIO
from RpiMotorLib import RpiMotorLib

class CameraRotation:
    def __init__(self, pins, initial_angle=0):
        self.pins = pins
        self.current_angle = initial_angle
        self.stepper_motor = RpiMotorLib.BYJMotor("MyMotorOne", "28BYJ")
        self.step_sleep = 0.001
        self.steps_per_revolution = 4076  # Update this value based on your stepper motor's specifications
        self.degrees_per_step = 360 / self.steps_per_revolution

    def rotate(self, direction, steps):
        self.stepper_motor.motor_run(self.pins, self.step_sleep, steps, direction, True, "half", .05)
        self.current_angle += steps * self.degrees_per_step * (1 if direction else -1)

    def rotate_left(self, angle):
        if self.current_angle + angle <= 60:
            steps = self.angle_to_steps(angle)
            self.rotate(False, steps)

    def rotate_right(self, angle):
        if self.current_angle - angle >= -60:
            steps = self.angle_to_steps(angle)
            self.rotate(True, steps)

    def angle_to_steps(self, angle):
        return int(angle / self.degrees_per_step)

    def cleanup(self):
        self.stepper_motor.motor_stop(self.pins)

    def startup_test(self):
        print("Rotation test...")
        self.rotate_right(60)
        time.sleep(2)
        self.rotate_left(120)
        time.sleep(2)
        self.rotate_right(60)
        print("Rotation test completed!")

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)

    # Define your GPIO pins connected to the ULN2003 driver board
    gpio_pins = [4, 14, 26, 20]  # in1, in2, in3, in4

    cr = CameraRotation(gpio_pins, 0)
    
    # Run startup test
    cr.startup_test()

    cr.cleanup()
    GPIO.cleanup()
