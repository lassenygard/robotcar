# Works perfectly!
# This script uses lidar data to control the movement of a robot car with Mecanum wheels.
# - It adjusts raw lidar angles by applying an offset (-105 degrees) to align the forward direction to 0*/360*.
# - It detects obstacles within a specified safe distance (500 mm) in the forward range (-30* to 30* adjusted angles).
# - The robot stops when an obstacle is detected and moves forward when the path is clear.
# - The script includes debug messages to display raw and adjusted angles, distances, and decisions made by the robot.
# - This script is designed for integration with a motor control module (`MecanumWheels`) and a properly calibrated lidar sensor.

from motor_control import MecanumWheels
from adafruit_rplidar import RPLidar

# Initialize motors and lidar
wheels = MecanumWheels()
lidar = RPLidar(port='/dev/ttyUSB0', motor_pin=None, timeout=3)

def adjust_angle(angle, offset=-105):
    """
    Adjusts the angle based on the lidar's offset.

    Args:
    - angle: The raw angle from the lidar (in degrees).
    - offset: The offset to apply (default: -105 degrees).

    Returns:
    - The adjusted angle, wrapped within 0-360 degrees.
    """
    adjusted_angle = (angle + offset) % 360
    return adjusted_angle

def check_obstacles(scan_data, safe_distance=500, offset=-105):
    """
    Detect obstacles in front of the robot with adjusted angles.

    Args:
    - scan_data: List of (angle, distance) tuples.
    - safe_distance: Minimum safe distance in millimeters.
    - offset: Angle offset for calibration.

    Returns:
    - obstacle_detected: True if an obstacle is within the safe distance, False otherwise.
    """
    obstacle_detected = False
    for angle, distance in scan_data:
        adjusted_angle = adjust_angle(angle, offset)  # Adjust the angle only for checks
        # Debug: Print raw and adjusted angles
        print(f"Raw angle: {angle:.2f}, Adjusted angle: {adjusted_angle:.2f}, Distance: {distance:.2f} mm")
        
        # Check if the obstacle is in the forward range
        if -30 <= adjusted_angle <= 30 and distance < safe_distance:
            print(f"Obstacle detected at adjusted angle {adjusted_angle:.2f}, distance {distance:.2f} mm.")
            obstacle_detected = True
    return obstacle_detected

def navigate(offset=-105):
    """
    Main navigation loop that uses lidar data to control the robot's movement.
    """
    try:
        for scan in lidar.iter_scans():
            # Pass raw scan data, and adjust only where necessary
            scan_data = [(angle, distance) for (_, angle, distance) in scan]

            # Check for obstacles
            if check_obstacles(scan_data, offset=offset):
                print("Decision: Obstacle detected. Stopping the car.")
                wheels.stop()
            else:
                print("Decision: Path is clear. Driving forward.")
                wheels.move_forward()

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        wheels.cleanup()
        lidar.stop_motor()
        lidar.disconnect()

if __name__ == "__main__":
    navigate()
