# main.py
import asyncio
import configparser
import websockets
import time
import numpy as np
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


async def explore(q_agent, mecanum_wheels, localization, is_exploration_complete):
    wall_distance_threshold = 20  # In centimeters
    angle_adjustment_interval = 1  # In seconds
    last_angle_adjustment_time = time.time()

    while not is_exploration_complete:
        state = localization.get_current_position()
        action = q_agent.get_action(state)
        lidar_data = lidar.get_scan_data()
        right_sector_data = [item for item in lidar_data if 270 <= item[1] <= 450 or -90 <= item[1] <= 90]
        right_wall_distances = [item[0] for item in right_sector_data]
        wall_detected = min(right_wall_distances) < wall_distance_threshold

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

        # Get the new position and orientation
        new_position = localization.get_current_position()

        # Compute the reward
        distance_traveled = np.linalg.norm(np.array(new_position) - np.array(state))
        reward = distance_traveled - 100 if obstacle_detector.is_collision() else distance_traveled

        # Update the Q-table
        q_agent.update(state, action, reward, new_position)

        # Stop the wheels
        mecanum_wheels.stop()



async def handle_command(websocket, path):
    json_command = await websocket.recv()
    response = command_interface.parse_command(json_command)
    command_interface.send_response(response)


settings = load_config()
map_update_interval = int(settings["map_update_interval"])
start_server = websockets.serve(handle_command, "localhost", 8080)
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
camera_rotation = CameraRotation(pins=[2, 3, 4, 14], initial_angle=initial_camera_angle)

"""
GPIO 2 (Physical Pin 3)
GPIO 3 (Physical Pin 5)
GPIO 4 (Physical Pin 7)
GPIO 14 (Physical Pin 8)

 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20
21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40
The physical pins are numbered sequentially from left to right and top to bottom.
"""

q_agent = QlearningAgent()

is_exploration_complete = False

asyncio.run(asyncio.gather(
    explore(q_agent, mecanum_wheels, localization, is_exploration_complete),
    start_server
))
