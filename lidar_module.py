# lidar_module.py

from rplidar import RPLidar

class RPLidarModule:
    def __init__(self):
        self.lidar = None

        try:
            if self.is_lidar_available():
                self.lidar = RPLidar('/dev/ttyUSB0')
                self.lidar.set_pwm(660)  # Set the motor speed
                self.lidar.connect()  # Connect to the RPLidar device
                print("RPLidar successfully initialized.")
            else:
                print("RPLidar not available.")
        except Exception as e:
            print(f"Error initializing RPLidar: {e}")

    def is_lidar_available(self):
        import os

        return os.path.exists('/dev/ttyUSB0')

    def get_scan_data(self):
        if self.lidar is None:
            return []

        try:
            for scan in self.lidar.iter_scans(max_buf_meas=500):
                return scan
        except Exception as e:
            print(f"Error getting scan data: {e}")
            return []

    def stop(self):
        if self.lidar is None:
            return

        try:
            self.lidar.stop()  # Stop the RPLidar device
            self.lidar.stop_motor()  # Stop the RPLidar motor
            print("RPLidar successfully stopped.")
        except Exception as e:
            print(f"Error stopping RPLidar: {e}")

    def cleanup(self):
        if self.lidar is None:
            return

        try:
            self.lidar.disconnect()  # Disconnect from the RPLidar device
            print("RPLidar successfully disconnected.")
        except Exception as e:
            print(f"Error cleaning up RPLidar resources: {e}")
