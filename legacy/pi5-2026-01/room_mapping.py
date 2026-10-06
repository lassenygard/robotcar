from lidar_navigation import adjust_angle, check_obstacles
from motor_control import MecanumWheels
from adafruit_rplidar import RPLidar
import time

# Initialize motors and lidar
wheels = MecanumWheels()
lidar = RPLidar(port='/dev/ttyUSB0', motor_pin=None, timeout=3)

# State variables
current_state = "FIND_WALL"  # Other states: FOLLOW_WALL, HANDLE_CORNER, HANDLE_OBSTACLE
perimeter_mapped = False

def find_wall(scan_data, safe_distance=500):
    """
    Move forward until a wall is detected.
    """
    print("State: FIND_WALL")
    if not check_obstacles(scan_data, safe_distance=safe_distance):
        wheels.move_forward()
        return False  # Still searching for the wall
    wheels.stop()
    return True  # Wall found

def follow_wall(scan_data, safe_distance=500, offset=-105):
    """
    Follow the wall while avoiding obstacles and handling corners.
    """
    print("State: FOLLOW_WALL")
    for angle, distance in scan_data:
        adjusted_angle = adjust_angle(angle, offset)

        # Handle obstacle directly ahead
        if -30 <= adjusted_angle <= 30 and distance < safe_distance:
            wheels.stop()
            return "HANDLE_OBSTACLE"

        # Handle a left-side corner or obstacle
        if 60 <= adjusted_angle <= 120 and distance < safe_distance:
            wheels.strafe_right()
            time.sleep(0.3)
            wheels.stop()
            return "FOLLOW_WALL"

        # Handle a right-side corner
        if -120 <= adjusted_angle <= -60 and distance < safe_distance:
            wheels.strafe_left()
            time.sleep(0.3)
            wheels.stop()
            return "FOLLOW_WALL"

    # Default: move forward while following the wall
    wheels.move_forward()
    return "FOLLOW_WALL"

def handle_corner(scan_data, safe_distance=500, offset=-105):
    """
    Turn left slightly to align with the next wall.
    """
    print("State: HANDLE_CORNER")
    wheels.rotate_counterclockwise()
    time.sleep(0.3)
    wheels.stop()
    return "FOLLOW_WALL"

def handle_obstacle(scan_data, safe_distance=500, offset=-105):
    """
    Navigate around an obstacle by holding to the right.
    """
    print("State: HANDLE_OBSTACLE")
    wheels.strafe_right()
    time.sleep(0.5)
    wheels.stop()
    return "FOLLOW_WALL"

def navigate_room():
    """
    Main navigation loop.
    """
    global current_state, perimeter_mapped

    try:
        for scan in lidar.iter_scans():
            scan_data = [(angle, distance) for (_, angle, distance) in scan]

            if perimeter_mapped:
                print("Perimeter mapping complete!")
                wheels.stop()
                break

            if current_state == "FIND_WALL":
                if find_wall(scan_data):
                    current_state = "FOLLOW_WALL"

            elif current_state == "FOLLOW_WALL":
                next_state = follow_wall(scan_data)
                if next_state != "FOLLOW_WALL":
                    current_state = next_state

            elif current_state == "HANDLE_CORNER":
                current_state = handle_corner(scan_data)

            elif current_state == "HANDLE_OBSTACLE":
                current_state = handle_obstacle(scan_data)

            # Implement a termination condition for perimeter mapping
            # (e.g., detecting overlap with starting point or time limit)
            # perimeter_mapped = True  # Replace with actual completion logic

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        wheels.cleanup()
        lidar.stop_motor()
        lidar.disconnect()

if __name__ == "__main__":
    navigate_room()
