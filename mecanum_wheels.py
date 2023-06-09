#mecanum_wheels.py

from gpiozero import Motor, OutputDevice


# Define constants for GPIO pins connected to motor drivers for each wheel
FRONT_LEFT = (24, 27, 5)
FRONT_RIGHT = (6, 22, 17)
REAR_LEFT = (23, 16, 12)
REAR_RIGHT = (13, 18, 25)

class MecanumWheels:
    def __init__(self):
        self.enable_pins = {
            "front_left": FRONT_LEFT[2],
            "front_right": FRONT_RIGHT[2],
            "rear_left": REAR_LEFT[2],
            "rear_right": REAR_RIGHT[2],
        }

        OutputDevice(self.enable_pins["front_left"], initial_value=True)
        OutputDevice(self.enable_pins["front_right"], initial_value=True)
        OutputDevice(self.enable_pins["rear_left"], initial_value=True)
        OutputDevice(self.enable_pins["rear_right"], initial_value=True)

        self.motors = {
            "front_left": Motor(FRONT_LEFT[0], FRONT_LEFT[1], enable=self.enable_pins["front_left"]),
            "front_right": Motor(FRONT_RIGHT[0], FRONT_RIGHT[1], enable=self.enable_pins["front_right"]),
            "rear_left": Motor(REAR_LEFT[0], REAR_LEFT[1], enable=self.enable_pins["rear_left"]),
            "rear_right": Motor(REAR_RIGHT[0], REAR_RIGHT[1], enable=self.enable_pins["rear_right"]),
        }
        self.set_speed(0)


    def set_speed(self, speed):
        self.speed = speed

    def forward(self):
        for motor in self.motors.values():
            motor.forward(self.speed)

    def backward(self):
        for motor in self.motors.values():
            motor.backward(self.speed)

    def strafe_left(self):
        self.motors["front_left"].backward(self.speed)
        self.motors["front_right"].forward(self.speed)
        self.motors["rear_left"].forward(self.speed)
        self.motors["rear_right"].backward(self.speed)

    def strafe_right(self):
        self.motors["front_left"].forward(self.speed)
        self.motors["front_right"].backward(self.speed)
        self.motors["rear_left"].backward(self.speed)
        self.motors["rear_right"].forward(self.speed)

    def rotate_cw(self):
        self.motors["front_left"].forward(self.speed)
        self.motors["front_right"].backward(self.speed)
        self.motors["rear_left"].forward(self.speed)
        self.motors["rear_right"].backward(self.speed)

    def rotate_ccw(self):
        self.motors["front_left"].backward(self.speed)
        self.motors["front_right"].forward(self.speed)
        self.motors["rear_left"].backward(self.speed)
        self.motors["rear_right"].forward(self.speed)

    def stop(self):
        self.set_speed(0)
        self.forward()

    def cleanup(self):
        try:
            self.stop()
        except Exception as e:
            print(f"Error cleaning up motor resources: {e}")
