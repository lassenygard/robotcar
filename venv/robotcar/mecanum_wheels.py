#mecanum_wheels.py

from gpiozero import Motor, OutputDevice

# Define constants for GPIO pins connected to motor drivers for each wheel
FRONT_LEFT = (24, 27, 5)
FRONT_RIGHT = (6, 22, 17)
REAR_LEFT = (23, 16, 12)
REAR_RIGHT = (13, 18, 25)

class MecanumWheels:
    def __init__(self):
        self.enable_devices = {
            "front_left": OutputDevice(FRONT_LEFT[2], initial_value=True),
            "front_right": OutputDevice(FRONT_RIGHT[2], initial_value=True),
            "rear_left": OutputDevice(REAR_LEFT[2], initial_value=True),
            "rear_right": OutputDevice(REAR_RIGHT[2], initial_value=True),
        }

        self.motors = {
            "front_left": Motor(FRONT_LEFT[0], FRONT_LEFT[1]),
            "front_right": Motor(FRONT_RIGHT[0], FRONT_RIGHT[1]),
            "rear_left": Motor(REAR_LEFT[0], REAR_LEFT[1]),
            "rear_right": Motor(REAR_RIGHT[0], REAR_RIGHT[1]),
        }

        self.speed = 1

    def set_speed(self, speed):
        self.speed = speed

    def enable_motors(self):
        for device in self.enable_devices.values():
            device.on()

    def disable_motors(self):
        for device in self.enable_devices.values():
            device.off()

    def forward(self):
        self.enable_motors()
        for motor in self.motors.values():
            motor.forward(self.speed)

    def backward(self):
        self.enable_motors()
        for motor in self.motors.values():
            motor.backward(self.speed)

    def strafe_left(self):
        self.enable_motors()
        self.motors["front_left"].backward(self.speed)
        self.motors["front_right"].forward(self.speed)
        self.motors["rear_left"].forward(self.speed)
        self.motors["rear_right"].backward(self.speed)

    def strafe_right(self):
        self.enable_motors()
        self.motors["front_left"].forward(self.speed)
        self.motors["front_right"].backward(self.speed)
        self.motors["rear_left"].backward(self.speed)
        self.motors["rear_right"].forward(self.speed)

    def rotate_cw(self):
        self.enable_motors()
        self.motors["front_left"].forward(self.speed)
        self.motors["front_right"].backward(self.speed)
        self.motors["rear_left"].forward(self.speed)
        self.motors["rear_right"].backward(self.speed)

    def rotate_ccw(self):
        self.enable_motors()
        self.motors["front_left"].backward(self.speed)
        self.motors["front_right"].forward(self.speed)
        self.motors["rear_left"].backward(self.speed)
        self.motors["rear_right"].forward(self.speed)

    def stop(self):
        for motor in self.motors.values():
            motor.stop()
        self.disable_motors()

    def cleanup(self):
        try:
            self.stop()
        except Exception as e:
            print(f"Error cleaning up motor resources: {e}")
