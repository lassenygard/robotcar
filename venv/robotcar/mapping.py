# mapping.py

import numpy as np
import matplotlib.pyplot as plt
import cv2
import threading

class Map:
    def __init__(self, width, height):
        try:
            self.width = int(width)
            self.height = int(height)
            self.grid = np.zeros((self.height, self.width), dtype=np.uint8)
        except Exception as e:
            print(f"Error in map initialization: {e}")

        self.lock = threading.RLock()  # Add a lock for thread safety

    def update_map(self, combined_obstacle_data, robot_position):
        with self.lock:
            try:
#               print(f"combined_obstacle_data: {combined_obstacle_data}")
#               print(f"type(combined_obstacle_data): {type(combined_obstacle_data)}")

                for contour in combined_obstacle_data:
                    try:
                        # Convert contour to a numpy array of points
                        contour = np.array([contour])

                        # Find the bounding box of the contour
                        x, y, w, h = cv2.boundingRect(contour)

#                        print(f"x: {x}, y: {y}, w: {w}, h: {h}")

                        # Update the map with the obstacle data
                        if 0 <= x < self.width and 0 <= y < self.height:
                            self.grid[y, x] = 255  # Mark as occupied
                    except Exception as e:
                        print(f"Error in updating map with contour: {e}")

                # Mark robot position
                (robot_x, robot_y), _ = robot_position

                print(f"robot_position: {robot_position}")
                print(f"type(robot_position): {type(robot_position)}")

                if 0 <= robot_x < self.width and 0 <= robot_y < self.height:
                    self.grid[robot_y, robot_x] = 128  # Mark as robot
            except Exception as e:
                print(f"Error in map updating: {e}")

    def visualize_map(self):
        with self.lock:
            try:
                plt.imshow(self.grid, cmap='gray', origin='lower')
                plt.show()
            except Exception as e:
                print(f"Error in map visualization: {e}")

    def save_map(self, file_path="map_image.png"):
        with self.lock:
            try:
                cv2.imwrite(file_path, self.grid)
            except Exception as e:
                print(f"Error in saving map image: {e}")

    def schedule_map_update(self, interval, obstacle_detector, localization):
        def periodic_update():
            combined_obstacle_data = obstacle_detector.get_obstacle_data()
            robot_position = localization.get_current_position()
            with self.lock:  # Make sure to acquire the lock before updating the map
                self.update_map(combined_obstacle_data, robot_position)
                self.save_map()  # Update the save_map() method to include a default file_path
            threading.Timer(interval, periodic_update).start()

        periodic_update()

    def get_path_image(self, path):
        with self.lock:
            path_image = self.grid.copy()
            path_points = np.array(path, dtype=np.int_)
            path_image[path_points[:, 1], path_points[:, 0]] = 128
            return path_image
