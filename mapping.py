# mapping.py

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import cv2

class Map:
    def __init__(self, width, height):
        try:
            self.width = width
            self.height = height
            self.grid = np.zeros((height, width), dtype=np.uint8)
        except Exception as e:
            print(f"Error in map initialization: {e}")

    def update_map(self, combined_obstacle_data, robot_position):
        try:
            for x, y in combined_obstacle_data:
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.grid[y, x] = 255  # Mark as occupied

            # Mark robot position
            robot_x, robot_y = robot_position
            if 0 <= robot_x < self.width and 0 <= robot_y < self.height:
                self.grid[robot_y, robot_x] = 128  # Mark as robot
        except Exception as e:
            print(f"Error in map updating: {e}")

    def visualize_map(self):
        try:
            plt.imshow(self.grid, cmap='gray', origin='lower')
            plt.show()
        except Exception as e:
            print(f"Error in map visualization: {e}")


    def save_map(self, file_path="map_image.png"):
        try:
            cv2.imwrite(file_path, self.grid)
        except Exception as e:
            print(f"Error in saving map image: {e}")


    def schedule_map_update(self, interval, obstacle_detector, localization):
        import threading

        def periodic_update():
            combined_obstacle_data = obstacle_detector.get_obstacle_data()
            robot_position = localization.get_current_position()
            self.update_map(combined_obstacle_data, robot_position)
            self.save_map()  # Update the save_map() method to include a default file_path
            threading.Timer(interval, periodic_update).start()

        periodic_update()

    def get_path_image(self, path):
        path_image = self.grid.copy()
        path_points = np.array(path, dtype=np.int_)
        path_image[path_points[:, 1], path_points[:, 0]] = 128
        return path_image
