"""
Motor Controller Manager - RPi5
Håndterer motorstyring enten lokalt (GPIO) eller remote (RPi3).
"""

import threading
import os

# Sjekk om vi skal bruke remote motor controller
USE_REMOTE_MOTORS = os.environ.get('USE_REMOTE_MOTORS', 'true').lower() == 'true'

if USE_REMOTE_MOTORS:
    from src.motor.motor_client import RemoteMotorController, MotorClient
    print("🌐 Using REMOTE motor controller (RPi3)")
else:
    from typing import Dict
    try:
        from gpiozero import Motor
        GPIO_AVAILABLE = True
    except ImportError:
        GPIO_AVAILABLE = False
    print("📌 Using LOCAL motor controller (GPIO)")


# Prøv å importere konfig
try:
    from config import RPI3_HOST, RPI3_PORT
except ImportError:
    RPI3_HOST = '192.168.1.43'
    RPI3_PORT = 5001


# GPIO pin configuration (for local mode)
FRONT_LEFT = (24, 27, 5)
FRONT_RIGHT = (6, 22, 17)
REAR_LEFT = (23, 16, 12)
REAR_RIGHT = (18, 13, 25)


class LocalMotorController:
    """Local GPIO motor controller (for single-Pi setup or testing)."""

    def __init__(self):
        self.speed = 0.5
        self.current_movement = "stopped"
        self.motors = None
        self.connected = True  # Always "connected" for local

        if GPIO_AVAILABLE:
            try:
                self.motors = {
                    "front_left": Motor(FRONT_LEFT[0], FRONT_LEFT[1], enable=FRONT_LEFT[2]),
                    "front_right": Motor(FRONT_RIGHT[0], FRONT_RIGHT[1], enable=FRONT_RIGHT[2]),
                    "rear_left": Motor(REAR_LEFT[0], REAR_LEFT[1], enable=REAR_LEFT[2]),
                    "rear_right": Motor(REAR_RIGHT[0], REAR_RIGHT[1], enable=REAR_RIGHT[2])
                }
                print("Initialized local Mecanum wheels controller with GPIO")
            except Exception as e:
                print(f"Error initializing GPIO: {e}")
                self.motors = None
        else:
            print("Initialized simulated Mecanum wheels controller")

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.0, min(1.0, speed))

    def _control_motors(self, motor_speeds: dict) -> None:
        if self.motors:
            for motor_name, speed in motor_speeds.items():
                motor = self.motors[motor_name]
                if speed > 0:
                    motor.forward(abs(speed) * self.speed)
                elif speed < 0:
                    motor.backward(abs(speed) * self.speed)
                else:
                    motor.stop()

    def move_forward(self) -> None:
        self.current_movement = "forward"
        self._control_motors({"front_left": 1, "front_right": 1, "rear_left": 1, "rear_right": 1})

    def move_backward(self) -> None:
        self.current_movement = "backward"
        self._control_motors({"front_left": -1, "front_right": -1, "rear_left": -1, "rear_right": -1})

    def strafe_left(self) -> None:
        self.current_movement = "strafe_left"
        self._control_motors({"front_left": -1, "front_right": 1, "rear_left": 1, "rear_right": -1})

    def strafe_right(self) -> None:
        self.current_movement = "strafe_right"
        self._control_motors({"front_left": 1, "front_right": -1, "rear_left": -1, "rear_right": 1})

    def rotate_clockwise(self) -> None:
        self.current_movement = "rotate_cw"
        self._control_motors({"front_left": 1, "front_right": -1, "rear_left": 1, "rear_right": -1})

    def rotate_counterclockwise(self) -> None:
        self.current_movement = "rotate_ccw"
        self._control_motors({"front_left": -1, "front_right": 1, "rear_left": -1, "rear_right": 1})

    def stop(self) -> None:
        self.current_movement = "stopped"
        if self.motors:
            for motor in self.motors.values():
                motor.stop()

    def cleanup(self) -> None:
        self.stop()
        if self.motors:
            for motor in self.motors.values():
                if hasattr(motor, 'close'):
                    motor.close()


class MotorControlManager:
    """
    Thread-safe motor control manager.
    Automatically uses remote (RPi3) or local controller based on configuration.
    """

    def __init__(self, host: str = None, port: int = None):
        self.lock = threading.Lock()
        self.cleaned_up = False

        if USE_REMOTE_MOTORS:
            # Bruk remote motor controller (RPi3)
            host = host or RPI3_HOST
            port = port or RPI3_PORT

            self.wheels = RemoteMotorController(host, port)
            self.is_remote = True

            print(f"🔌 RPi3 Motor Controller at {host}:{port}")
            print("   (connecting in background...)")
        else:
            # Bruk lokal motor controller
            self.wheels = LocalMotorController()
            self.is_remote = False

    @property
    def connected(self) -> bool:
        """Check if motors are connected."""
        if self.is_remote:
            return self.wheels.connected
        return True  # Local is always "connected"

    def execute_command(self, command: str, speed: float = 0.5) -> bool:
        """Execute a movement command."""
        with self.lock:
            if self.cleaned_up:
                print("Motor manager has been cleaned up; command ignored.")
                return False

            self.wheels.set_speed(speed)

            command_map = {
                'move_forward': self.wheels.move_forward,
                'move_backward': self.wheels.move_backward,
                'strafe_left': self.wheels.strafe_left,
                'strafe_right': self.wheels.strafe_right,
                'rotate_clockwise': self.wheels.rotate_clockwise,
                'rotate_counterclockwise': self.wheels.rotate_counterclockwise,
                'stop': self.wheels.stop
            }

            if command in command_map:
                try:
                    command_map[command]()
                    return True
                except Exception as e:
                    print(f"Error executing motor command '{command}': {e}")
                    return False
            else:
                print(f"Unknown motor command: {command}")
                return False

    def get_status(self) -> dict:
        """Get current motor status."""
        return {
            'movement': self.wheels.current_movement,
            'speed': self.wheels.speed,
            'is_remote': self.is_remote,
            'connected': self.connected
        }

    def cleanup(self) -> None:
        """Clean up motor resources."""
        with self.lock:
            if self.cleaned_up:
                return
            self.cleaned_up = True
            self.wheels.cleanup()
            print("Cleaned up MotorControlManager")
