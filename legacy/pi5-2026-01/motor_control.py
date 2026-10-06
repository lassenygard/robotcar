# motor_control.py / Fungerer utmerket sammen med web_server.py og main.py

from typing import Dict

# Initialize Raspberry Pi detection flag
ON_RASPBERRY_PI = False

# Try to import GPIO libraries
try:
    from gpiozero import Motor
    ON_RASPBERRY_PI = True
except (ImportError, OSError):
    print("Warning: Running in simulation mode - GPIO control not available")

# GPIO pin configuration for Mecanum wheels
FRONT_LEFT = (24, 27, 5)
FRONT_RIGHT = (6, 22, 17)
REAR_LEFT = (23, 16, 12)
REAR_RIGHT = (18, 13, 25)

class MecanumWheels:
    """Mecanum wheels controller with support for both real GPIO and simulation."""
    
    def __init__(self):
        self.speed = 0.5
        self.current_movement = "stopped"
        self.motors = None
        
        if ON_RASPBERRY_PI:
            try:
                self.motors = {
                    "front_left": Motor(FRONT_LEFT[0], FRONT_LEFT[1], enable=FRONT_LEFT[2]),
                    "front_right": Motor(FRONT_RIGHT[0], FRONT_RIGHT[1], enable=FRONT_RIGHT[2]),
                    "rear_left": Motor(REAR_LEFT[0], REAR_LEFT[1], enable=REAR_LEFT[2]),
                    "rear_right": Motor(REAR_RIGHT[0], REAR_RIGHT[1], enable=REAR_RIGHT[2])
                }
                print("Initialized real Mecanum wheels controller with GPIO")
            except Exception as e:
                print(f"Error initializing GPIO: {e}")
                self.motors = None
                print("Falling back to simulation mode")
        else:
            print("Initialized simulated Mecanum wheels controller")

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.0, min(1.0, speed))
        print(f"Speed set to: {self.speed}")

    def _control_motors(self, motor_speeds: Dict[str, float]) -> None:
        if self.motors:
            for motor_name, speed in motor_speeds.items():
                motor = self.motors[motor_name]
                if speed > 0:
                    motor.forward(abs(speed) * self.speed)
                elif speed < 0:
                    motor.backward(abs(speed) * self.speed)
                else:
                    motor.stop()
        else:
            speeds_str = ", ".join(f"{k}: {v}" for k, v in motor_speeds.items())
            print(f"Simulated motor speeds: {speeds_str}")

    def move_forward(self) -> None:
        self.current_movement = "forward"
        self._control_motors({
            "front_left": 1.0,
            "front_right": 1.0,
            "rear_left": 1.0,
            "rear_right": 1.0
        })

    def move_backward(self) -> None:
        self.current_movement = "backward"
        self._control_motors({
            "front_left": -1.0,
            "front_right": -1.0,
            "rear_left": -1.0,
            "rear_right": -1.0
        })

    def strafe_left(self) -> None:
        self.current_movement = "left"
        self._control_motors({
            "front_left": -1.0,
            "front_right": 1.0,
            "rear_left": 1.0,
            "rear_right": -1.0
        })

    def strafe_right(self) -> None:
        self.current_movement = "right"
        self._control_motors({
            "front_left": 1.0,
            "front_right": -1.0,
            "rear_left": -1.0,
            "rear_right": 1.0
        })

    def rotate_clockwise(self) -> None:
        self.current_movement = "rotate_cw"
        self._control_motors({
            "front_left": 1.0,
            "front_right": -1.0,
            "rear_left": 1.0,
            "rear_right": -1.0
        })

    def rotate_counterclockwise(self) -> None:
        self.current_movement = "rotate_ccw"
        self._control_motors({
            "front_left": -1.0,
            "front_right": 1.0,
            "rear_left": -1.0,
            "rear_right": 1.0
        })

    def turn_left(self, speed=0.5) -> None:
        self.set_speed(speed)
        self.rotate_counterclockwise()
        print(f"Turning left at speed: {speed}")

    def turn_right(self, speed=0.5) -> None:
        self.set_speed(speed)
        self.rotate_clockwise()
        print(f"Turning right at speed: {speed}")
        
    def stop(self) -> None:
        self.current_movement = "stopped"
        if self.motors:
            for motor in self.motors.values():
                motor.stop()
        print("Stopped all motors")

    def cleanup(self) -> None:
        self.stop()
        if self.motors:
            for motor in self.motors.values():
                if hasattr(motor, 'close'):
                    motor.close()
        print("Cleaned up Mecanum wheels controller")