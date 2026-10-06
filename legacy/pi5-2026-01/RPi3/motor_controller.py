"""
Motor Controller for Mecanum Wheels - RPi3
Håndterer GPIO-styring av 4 DC-motorer for omnidirectional bevegelse.
"""

from typing import Dict
import time

# Importer konfigurasjon
from config import MOTOR_PINS, DEFAULT_SPEED

# Prøv å importere GPIO
try:
    from gpiozero import Motor, PWMOutputDevice
    GPIO_AVAILABLE = True
except (ImportError, OSError) as e:
    GPIO_AVAILABLE = False
    print(f"Warning: GPIO not available - {e}")


class MecanumWheels:
    """
    Controller for Mecanum wheels.
    Støtter omnidirectional bevegelse: frem, bak, sidelengs, rotasjon.
    """
    
    def __init__(self):
        self.speed = DEFAULT_SPEED
        self.current_movement = "stopped"
        self.motors = None
        self.last_command_time = time.time()
        
        if GPIO_AVAILABLE:
            try:
                self.motors = {
                    name: Motor(
                        forward=pins[0],
                        backward=pins[1],
                        enable=pins[2]
                    )
                    for name, pins in MOTOR_PINS.items()
                }
                print(f"✓ Initialized Mecanum wheels with GPIO")
                print(f"  Motors: {list(self.motors.keys())}")
            except Exception as e:
                print(f"✗ Error initializing GPIO: {e}")
                self.motors = None
        else:
            print("⚠ Running in simulation mode (no GPIO)")

    def set_speed(self, speed: float) -> None:
        """Set speed for all motors (0.0 to 1.0)."""
        self.speed = max(0.0, min(1.0, speed))
        print(f"Speed set to: {self.speed:.0%}")

    def _control_motors(self, motor_speeds: Dict[str, float]) -> None:
        """
        Control individual motors with specified speeds.
        Positive = forward, Negative = backward, 0 = stop
        """
        self.last_command_time = time.time()
        
        if self.motors:
            for motor_name, speed in motor_speeds.items():
                motor = self.motors[motor_name]
                actual_speed = abs(speed) * self.speed
                
                if speed > 0:
                    motor.forward(actual_speed)
                elif speed < 0:
                    motor.backward(actual_speed)
                else:
                    motor.stop()
        else:
            # Simuleringsmodus - logg bevegelse
            active = [f"{k}:{v:+.1f}" for k, v in motor_speeds.items() if v != 0]
            if active:
                print(f"[SIM] Motors: {', '.join(active)}")

    def move_forward(self) -> None:
        """Move robot forward."""
        self.current_movement = "forward"
        self._control_motors({
            "front_left": 1.0,
            "front_right": 1.0,
            "rear_left": 1.0,
            "rear_right": 1.0
        })

    def move_backward(self) -> None:
        """Move robot backward."""
        self.current_movement = "backward"
        self._control_motors({
            "front_left": -1.0,
            "front_right": -1.0,
            "rear_left": -1.0,
            "rear_right": -1.0
        })

    def strafe_left(self) -> None:
        """Strafe robot to the left."""
        self.current_movement = "strafe_left"
        self._control_motors({
            "front_left": -1.0,
            "front_right": 1.0,
            "rear_left": 1.0,
            "rear_right": -1.0
        })

    def strafe_right(self) -> None:
        """Strafe robot to the right."""
        self.current_movement = "strafe_right"
        self._control_motors({
            "front_left": 1.0,
            "front_right": -1.0,
            "rear_left": -1.0,
            "rear_right": 1.0
        })

    def rotate_clockwise(self) -> None:
        """Rotate robot clockwise (turn right)."""
        self.current_movement = "rotate_cw"
        self._control_motors({
            "front_left": 1.0,
            "front_right": -1.0,
            "rear_left": 1.0,
            "rear_right": -1.0
        })

    def rotate_counterclockwise(self) -> None:
        """Rotate robot counter-clockwise (turn left)."""
        self.current_movement = "rotate_ccw"
        self._control_motors({
            "front_left": -1.0,
            "front_right": 1.0,
            "rear_left": -1.0,
            "rear_right": 1.0
        })

    def diagonal_forward_left(self) -> None:
        """Move diagonally forward-left."""
        self.current_movement = "diagonal_fl"
        self._control_motors({
            "front_left": 0.0,
            "front_right": 1.0,
            "rear_left": 1.0,
            "rear_right": 0.0
        })

    def diagonal_forward_right(self) -> None:
        """Move diagonally forward-right."""
        self.current_movement = "diagonal_fr"
        self._control_motors({
            "front_left": 1.0,
            "front_right": 0.0,
            "rear_left": 0.0,
            "rear_right": 1.0
        })

    def diagonal_backward_left(self) -> None:
        """Move diagonally backward-left."""
        self.current_movement = "diagonal_bl"
        self._control_motors({
            "front_left": -1.0,
            "front_right": 0.0,
            "rear_left": 0.0,
            "rear_right": -1.0
        })

    def diagonal_backward_right(self) -> None:
        """Move diagonally backward-right."""
        self.current_movement = "diagonal_br"
        self._control_motors({
            "front_left": 0.0,
            "front_right": -1.0,
            "rear_left": -1.0,
            "rear_right": 0.0
        })

    def stop(self) -> None:
        """Stop all motors."""
        self.current_movement = "stopped"
        if self.motors:
            for motor in self.motors.values():
                motor.stop()
        print("Motors stopped")

    def get_status(self) -> dict:
        """Get current motor status."""
        return {
            "movement": self.current_movement,
            "speed": self.speed,
            "gpio_available": GPIO_AVAILABLE,
            "motors_initialized": self.motors is not None,
            "last_command": time.time() - self.last_command_time
        }

    def cleanup(self) -> None:
        """Clean up GPIO resources."""
        self.stop()
        if self.motors:
            for motor in self.motors.values():
                if hasattr(motor, 'close'):
                    motor.close()
        print("Motor controller cleaned up")


# Test-funksjon
if __name__ == "__main__":
    print("Testing MecanumWheels...")
    wheels = MecanumWheels()
    
    try:
        print("\nTest: Forward")
        wheels.move_forward()
        time.sleep(1)
        
        print("\nTest: Stop")
        wheels.stop()
        time.sleep(0.5)
        
        print("\nTest: Strafe Left")
        wheels.strafe_left()
        time.sleep(1)
        
        print("\nTest: Stop")
        wheels.stop()
        time.sleep(0.5)
        
        print("\nTest: Rotate CW")
        wheels.rotate_clockwise()
        time.sleep(1)
        
        print("\nStatus:", wheels.get_status())
        
    finally:
        wheels.cleanup()
        print("\nTest complete!")
