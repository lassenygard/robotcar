from adafruit_rplidar import RPLidar, RPLidarException
import sys

# Set up the RPLidar
PORT_NAME = '/dev/ttyUSB0'  # Update this with your port

# Function to fetch and print lidar data
def get_lidar_data(lidar, offset=-96):
    """
    Fetches and processes lidar data with an optional angle offset.
    
    Args:
    - lidar: RPLidar object
    - offset: Angle offset in degrees (default: -96 to align forward direction)
    
    Returns:
    - Processed scan data
    """
    try:
        for scan in lidar.iter_scans():
            for (_, angle, distance) in scan:
                adjusted_angle = (angle + offset) % 360  # Apply the offset and wrap around
                print(f'Adjusted Angle: {adjusted_angle:.2f}, Distance: {distance:.2f}')
    except RPLidarException as e:
        print(f'Error: {e}')
        return False
    return True

# Main function to run the lidar
def run_lidar():
    lidar = RPLidar(port=PORT_NAME, motor_pin=None, timeout=3)
    try:
        lidar.connect()
        lidar.start_motor()

        print('Lidar started. Collecting data...')
        while True:
            success = get_lidar_data(lidar)
            if not success:
                break

    except KeyboardInterrupt:
        print('Stopping...')

    finally:
        lidar.stop_motor()
        lidar.disconnect()
        print('Lidar stopped.')

if __name__ == '__main__':
    run_lidar()
