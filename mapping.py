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

    def update_map(self, obstacle_data, robot_position):
        try:
            for x, y in obstacle_data:
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

    def save_map(self, file_path):
        try:
            cv2.imwrite(file_path, self.grid)
        except Exception as e:
            print(f"Error in saving map image: {e}")

    def schedule_map_update(self, interval):
        try:
            import time
            import threading

            def periodic_update():
                self.update_map()
                self.save_map()
                threading.Timer(interval, periodic_update).start()

            periodic_update()
        except Exception as e:
            print(f"Error in scheduling map updates: {e}")

    def get_path_image(self, path):
        path_image = self.grid.copy()
        path_points = np.array(path, dtype=np.int)
        path_image[path_points[:, 1], path_points[:, 0]] = 128
        return path_image
