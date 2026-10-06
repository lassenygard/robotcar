"""
Combined script for Lidar scanning and grid map management.
Based on working lidar scripts with retry/reset on errors.
"""

import threading
import numpy as np
import math
from adafruit_rplidar import RPLidar
import time


class LidarScanner:
    """Lidar scanner for scanning and fetching distance data."""

    def __init__(self, port="/dev/ttyUSB0"):
        """Initialize the Lidar using the same pattern as the working script."""
        self._port = port
        self._lidar = None
        self._is_scanning = False
        self._scan_thread = None
        self.scan_data = []
        self._lock = threading.Lock()

        # Initialize lidar
        self._init_lidar()

    def _init_lidar(self):
        """Initialize or reinitialize the lidar."""
        # Clean up existing connection first
        if self._lidar is not None:
            try:
                self._lidar.stop_motor()
                self._lidar.disconnect()
            except:
                pass
            self._lidar = None
            time.sleep(0.5)

        # Create new connection - exactly like working script:
        # lidar = RPLidar(port='/dev/ttyUSB0', motor_pin=None, timeout=3)
        self._lidar = RPLidar(port=self._port, motor_pin=None, timeout=3)
        print(f"✓ LIDAR initialized on {self._port}")

    def start_scanning(self):
        """Start scanning with the lidar."""
        if self._is_scanning:
            print("Lidar scanning is already running.")
            return

        self._is_scanning = True
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()

    def _scan_loop(self):
        """Lidar scan loop with retry on errors."""
        print("Starting Lidar scanning...")
        retry_count = 0
        max_retries = 5

        while self._is_scanning:
            try:
                # Use iter_scans() like the working script
                for scan in self._lidar.iter_scans():
                    if not self._is_scanning:
                        break

                    # Reset retry count on successful scan
                    retry_count = 0

                    # Store scan data with thread safety
                    # Format: [(angle, distance), ...] like working script
                    with self._lock:
                        self.scan_data = [
                            (quality, angle, distance)
                            for quality, angle, distance in scan
                            if distance > 0  # Ignore invalid measurements
                        ]

            except Exception as e:
                if not self._is_scanning:
                    break

                retry_count += 1
                print(f"Lidar error: {e} (retry {retry_count}/{max_retries})")

                if retry_count >= max_retries:
                    print("Max retries reached, waiting 5 seconds before reset...")
                    time.sleep(5)
                    retry_count = 0

                # Reset lidar on error
                print("Resetting LIDAR...")
                try:
                    self._init_lidar()
                    time.sleep(1)  # Give it time to stabilize
                except Exception as reset_error:
                    print(f"LIDAR reset failed: {reset_error}")
                    time.sleep(2)

        # Cleanup when loop exits
        self._cleanup()
        print("Lidar scanning stopped.")

    def get_scan_data(self):
        """Return the latest scan data (thread-safe)."""
        with self._lock:
            return self.scan_data.copy()

    def stop(self):
        """Stop scanning."""
        print("Stopping LIDAR...")
        self._is_scanning = False

        # Wait for scan thread to finish
        if self._scan_thread and self._scan_thread.is_alive():
            self._scan_thread.join(timeout=3.0)

    def _cleanup(self):
        """Clean up lidar resources - matches working script pattern."""
        try:
            if self._lidar:
                # Working script uses: lidar.stop_motor() then lidar.disconnect()
                self._lidar.stop_motor()
                self._lidar.disconnect()
        except Exception as e:
            print(f"Error stopping Lidar: {e}")


class GridMap:
    """Represents a grid-based map for lidar data."""

    def __init__(self, grid_size=100, resolution=0.05):
        """
        Initialize the grid map.
        Args:
            grid_size (int): Number of cells in each dimension.
            resolution (float): Size of each cell in meters.
        """
        self.grid_size = grid_size
        self.resolution = resolution
        self.grid = np.zeros((grid_size, grid_size), dtype=np.uint8)

    def update_map(self, scan_data, robot_position):
        """
        Update the map with new scan data.
        Args:
            scan_data (list): List of (quality, angle, distance) tuples.
            robot_position (tuple): (x, y, theta) position of the robot.
        """
        robot_x, robot_y, robot_theta = robot_position

        for quality, angle, distance in scan_data:
            angle_rad = math.radians(angle) + robot_theta
            x_rel = math.cos(angle_rad) * distance / 1000.0  # Convert mm to meters
            y_rel = math.sin(angle_rad) * distance / 1000.0

            x_global = robot_x + x_rel
            y_global = robot_y + y_rel

            x_idx = int((x_global + self.grid_size * self.resolution / 2) / self.resolution)
            y_idx = int((y_global + self.grid_size * self.resolution / 2) / self.resolution)

            if 0 <= x_idx < self.grid_size and 0 <= y_idx < self.grid_size:
                self.grid[y_idx, x_idx] = 255  # Mark as an obstacle

    def get_map(self):
        """Return the current grid map."""
        return self.grid

    def reset_map(self):
        """Reset the map to its initial state."""
        self.grid.fill(0)


# Test/Example Usage
if __name__ == "__main__":
    print("Testing LidarScanner with auto-retry...")

    lidar_scanner = LidarScanner()

    try:
        lidar_scanner.start_scanning()

        for i in range(30):  # Run for 30 seconds
            time.sleep(1)
            scan_data = lidar_scanner.get_scan_data()
            print(f"Scan {i+1}: {len(scan_data)} points")

            # Print some sample data
            if scan_data:
                sample = scan_data[0]
                print(f"  Sample: angle={sample[1]:.1f}°, distance={sample[2]:.0f}mm")

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        lidar_scanner.stop()
        print("Test complete.")
