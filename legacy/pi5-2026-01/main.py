"""
Main script for RPi5 (Master) - Robot Control System
Initializes and runs the robot system with remote motor control via RPi3.
"""

import threading
import signal
import sys
import os

# Set environment variable for remote motors (can be overridden)
if 'USE_REMOTE_MOTORS' not in os.environ:
    os.environ['USE_REMOTE_MOTORS'] = 'true'

from src.motor.motor_controller import MotorControlManager
from src.web.server import WebServer

# Import ObjectDetector (with fallback)
try:
    from src.visionmapping.vision_combined import ObjectDetector
except ImportError:
    class ObjectDetector:
        def __init__(self):
            self.detected_objects = set()


class RobotSystem:
    """Main robot system controller for RPi5."""

    def __init__(self):
        print("\n" + "="*60)
        print("   🤖 INITIALIZING ROBOT SYSTEM (RPi5 Master)")
        print("="*60 + "\n")

        # Initialize components
        print("Initializing motor controller...")
        self.motor_controller = MotorControlManager()

        print("Initializing object detector...")
        self.object_detector = ObjectDetector()

        print("Initializing web server...")
        self.web_server = WebServer(self)

        # Setup signal handlers
        self._setup_signal_handlers()

        print("\n✓ Robot system initialized\n")

    def _setup_signal_handlers(self):
        """Set up signal handlers for safe shutdown."""
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def start(self):
        """Start all robot subsystems."""
        try:
            print("Starting robot system...")
            self.web_server.run()
        except Exception as e:
            print(f"Error starting robot system: {e}")
            self.shutdown()

    def shutdown(self, *args):
        """Shutdown all robot subsystems."""
        print("\n" + "="*60)
        print("   SHUTTING DOWN ROBOT SYSTEM")
        print("="*60 + "\n")

        print("Stopping web server...")
        self.web_server.stop()

        print("Cleaning up motor controller...")
        self.motor_controller.cleanup()

        print("\n✓ Robot system stopped\n")
        sys.exit(0)


def main():
    """Main entry point."""
    # Print startup info
    print("\n" + "="*60)
    print("   RPi5 ROBOT CONTROL SYSTEM")
    print("   Version 2.0 - Dual Pi Architecture")
    print("="*60)
    print("\n   This is the MASTER controller (RPi5)")
    print("   Motor commands will be sent to RPi3 over WiFi")
    print("\n   Make sure RPi3 motor_service.py is running!")
    print("="*60 + "\n")

    # Check for config
    try:
        from config import RPI3_HOST, RPI3_PORT
        print(f"   RPi3 configured at: {RPI3_HOST}:{RPI3_PORT}")
    except ImportError:
        print("   ⚠ No config.py found - using defaults")
        print("   Create config.py with RPI3_HOST to set RPi3 address")

    print("\n")

    # Start system
    robot_system = RobotSystem()
    robot_system.start()


if __name__ == "__main__":
    main()
