# main.py
import asyncio
import configparser
import websockets
import time
import numpy as np
import keyboard
from camera_module import PiCameraModule
from camera_rotation import CameraRotation
from command_interface import CommandInterface
from lidar_module import RPLidarModule
from localization import DeadReckoningLocalization
from mapping import Map
from mecanum_wheels import MecanumWheels
from obstacle_detection import ObstacleDetector
from pathfinding import Pathfinder
from q_learning_agent import QlearningAgent


def load_config():
    """
    Load the configuration file (config.ini) and return the settings as a dictionary.
    """
    config = configparser.ConfigParser()
    config.read("config.ini")
    settings = config["settings"]
    return settings


async def update_map_periodically(map_instance, interval):
    """
    Update the map periodically based on the given interval.

    :param map_instance: An instance of the Map class.
    :param interval: Number of seconds between each update.
    """
    while True:
        try:
            map_instance.update_map(obstacle_detector.get_obstacle_data(), localization.get_current_position())
            await asyncio.sleep(interval)
        except Exception as e:
            print(f"Error updating map periodically: {e}")


pause_key = "space"
paused = False

def toggle_pause(e):
    global paused
    paused = not paused
    if paused:
        mecanum_wheels.stop()

keyboard.on_press_key(pause_key, toggle_pause)

async def explore(q_agent, mecanum_wheels, localization, is_exploration_complete):
    wall_distance_threshold = 20  # In centimeters
    angle_adjustment_interval = 1  # In seconds
    last_angle_adjustment_time = time.time()
    explored_area_threshold = 0.8  # Stop exploring when 80% of the map has been explored

    # Variables to track exploration progress
    exploration_progress_tracking_interval = 50  # Track progress every 50 actions
    actions_since_last_tracking = 0
    previous_explored_area = 0
    no_progress_threshold = 0.05  # Consider exploration complete if less than 5% new area is explored since last tracking

    while not is_exploration_complete:
        if paused:
            await asyncio.sleep(1)  # Sleep for a second if paused
            continue

        state = localization.get_current_position()
        action = q_agent.get_action(state)
        
        actions_since_last_tracking += 1

        if actions_since_last_tracking >= exploration_progress_tracking_interval:
            current_explored_area = map_instance.get_explored_area()
            progress = (current_explored_area - previous_explored_area) / current_explored_area

            if progress < no_progress_threshold:
                is_exploration_complete = True

            previous_explored_area = current_explored_area
            actions_since_last_tracking = 0

        # Use LiDAR data if available, otherwise use camera data
        if lidar is not None:
            lidar_data = lidar.get_scan_data()
            right_sector_data = [item for item in lidar_data if 270 <= item[1] <= 450 or -90 <= item[1] <= 90]
            right_wall_distances = [item[0] for item in right_sector_data]
            if right_wall_distances:
                wall_detected = min(right_wall_distances) < wall_distance_threshold
            else:
                wall_detected = False

        else:
            camera_data = obstacle_detector.get_obstacle_data_from_camera()
            wall_detected = camera_data["right_wall_detected"]

        if wall_detected and time.time() - last_angle_adjustment_time > angle_adjustment_interval:
            action = 2  # turn right

        # Perform the action
        if action == q_agent.actions[0]:  # move forward
            mecanum_wheels.forward()
        elif action == q_agent.actions[1]:  # turn left
            mecanum_wheels.rotate_ccw()
        elif action == q_agent.actions[2]:  # turn right
            mecanum_wheels.rotate_cw()
        elif action == q_agent.actions[3]:  # move backward
            mecanum_wheels.backward()

        await asyncio.sleep(1)  # Assuming each action takes 1 second

        # Compute the reward
        new_position, _ = new_position
        state, _ = state
        distance_traveled = np.linalg.norm(np.array(new_position) - np.array(state))
        reward = distance_traveled - 100 if obstacle_detector.is_collision() else distance_traveled

        # Update the Q-table
        q_agent.update(state, action, reward, new_position)

        # Check if exploration is complete
        if map_instance.get_explored_area() / map_instance.get_total_area() >= explored_area_threshold:
            is_exploration_complete = True

        # Stop the wheels
        mecanum_wheels.stop()


async def handle_command(websocket, path):
    json_command = await websocket.recv()
    response = command_interface.parse_command(json_command)
    command_interface.send_response(response)

async def start_websocket_server():
    server = await websockets.serve(handle_command, "localhost", 8018)
    await server.wait_closed()

settings = load_config()
map_update_interval = int(settings["map_update_interval"])
wheel_radius = int(settings['wheel_radius'])
wheel_separation = int(settings['wheel_separation'])
mecanum_wheels = MecanumWheels()
camera = PiCameraModule()
lidar = RPLidarModule()
localization = DeadReckoningLocalization((0, 0), 0, wheel_radius, wheel_separation)
obstacle_detector = ObstacleDetector(camera_module=camera, lidar_module=lidar)
map_instance = Map(width=100, height=100)
map_instance.schedule_map_update(map_update_interval, obstacle_detector, localization)

pathfinder = Pathfinder(map_instance)
command_interface = CommandInterface(robot_controller=localization)

# Read the initial angle from the config.ini file
initial_camera_angle = int(settings["initial_camera_angle"])

# Pass the initial angle to the CameraRotation class
camera_rotation = CameraRotation(pins=[4, 14, 26, 20], initial_angle=initial_camera_angle)

action_list = ['forward', 'left', 'right', 'backward']
q_agent = QlearningAgent(actions=action_list)

is_exploration_complete = False

async def main():
    await asyncio.gather(
        explore(q_agent, mecanum_wheels, localization, is_exploration_complete),
        start_websocket_server()
    )

asyncio.run(main())
