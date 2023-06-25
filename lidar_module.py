# lidar_module.py

from math import floor
from adafruit_rplidar import RPLidar

class RPLidarModule:
    def __init__(self):
        self.lidar = None
        self.scan_data = [0] * 360
        self.PORT_NAME = "/dev/ttyUSB0"

        try:
            if self.is_lidar_available():
                self.lidar = RPLidar(None, self.PORT_NAME, timeout=3)
                print("RPLidar successfully initialized.")
            else:
                print("RPLidar not available.")
        except Exception as e:
            print(f"Error initializing RPLidar: {e}")

    def is_lidar_available(self):
        import os
        return os.path.exists(self.PORT_NAME)

    def get_scan_data(self):
        if self.lidar is None:
            return []

        try:
            for scan in self.lidar.iter_scans():
                for _, angle, distance in scan:
                    self.scan_data[min([359, floor(angle)])] = distance
                return self.scan_data
        except Exception as e:
            print(f"Error getting scan data: {e}")
            return []

    def stop(self):
        if self.lidar is None:
            return

        try:
            self.lidar.stop()
            print("RPLidar successfully stopped.")
        except Exception as e:
            print(f"Error stopping RPLidar: {e}")

    def cleanup(self):
        if self.lidar is None:
            return

        try:
            self.lidar.disconnect()
            print("RPLidar successfully disconnected.")
        except Exception as e:
            print(f"Error cleaning up RPLidar resources: {e}")
