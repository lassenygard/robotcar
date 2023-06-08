# obstacle_detection.py

import cv2
import numpy as np
from camera_module import PiCameraModule
from lidar_module import RPLidarModule
from camera_rotation import CameraRotation


class ObstacleDetector:
    def __init__(self, camera_module, lidar_module=None, camera_settings=None, detection_thresholds=None):
        self.camera_module = camera_module
        self.lidar_module = lidar_module
        self.camera_settings = camera_settings or {}
        self.detection_thresholds = detection_thresholds or {}
        self.camera_rotation = CameraRotation(pins=[4, 14, 26, 20])

    def preprocess_frame(self, frame):
        try:
            # Apply preprocessing steps, such as resizing or color conversion
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return gray_frame
        except Exception as e:
            print(f"Error in frame preprocessing: {e}")
            return None

    def detect_obstacles(self, frame):
        try:
            # Use edge detection and contour extraction for obstacle detection
            edges = cv2.Canny(frame, 100, 200)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            return contours
        except Exception as e:
            print(f"Error in obstacle detection: {e}")
            return []

    def localize_obstacles(self, obstacles):
        try:
            # Convert obstacle positions and sizes from image space to robot coordinate system
            localized_obstacles = []
            for contour in obstacles:
                # Calculate the obstacle's centroid
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])

                    localized_obstacles.append((cx, cy))

            return localized_obstacles
        except Exception as e:
            print(f"Error in obstacle localization: {e}")
            return []

    def process_lidar_data(self, scan_data):
        try:
            processed_data = []
            for angle, distance in scan_data:
                x = distance * np.cos(np.radians(angle))
                y = distance * np.sin(np.radians(angle))
                processed_data.append((x, y))
            return processed_data
        except Exception as e:
            print(f"Error in lidar data processing: {e}")
            return []

    def get_obstacle_data(self):
        try:
            obstacle_data = []
            num_frames = 3
            rotation_steps = 512 // num_frames
            for i in range(num_frames):
                # Capture a frame from the camera module
                frame = self.camera_module.capture_image()

                # Apply Gaussian blur and edge detection
                blur = cv2.GaussianBlur(frame, (5, 5), 0)
                edges = cv2.Canny(blur, 50, 150)

                # Find contours in the edges image
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                # Localize the obstacles
                localized_obstacles = self.localize_obstacles(contours)
                obstacle_data.extend(localized_obstacles)

                if i < num_frames - 1:
                    self.camera_rotation.rotate_right(rotation_steps)

            # Reset the camera rotation to its original position
            self.camera_rotation.rotate_left(rotation_steps * (num_frames - 1))

            if self.lidar_module is not None:
                try:
                    # Get scan data from the lidar module
                    scan_data = self.lidar_module.get_scan_data()

                    # Process the lidar data
                    lidar_obstacles = self.process_lidar_data(scan_data)

                    # Combine camera and lidar obstacle data
                    combined_obstacle_data = obstacle_data + lidar_obstacles
                except Exception as e:
                    print(f"Error in lidar data acquisition and processing: {e}")
                    combined_obstacle_data = obstacle_data
            else:
                combined_obstacle_data = obstacle_data

            return combined_obstacle_data
        except Exception as e:
            print(f"Error in obstacle data acquisition and processing: {e}")
            return obstacle_data  # Return camera-obtained obstacle data even if an error occurs


    def get_obstacle_data_from_camera(self):
        try:
            wall_detected = False

            # Capture a frame from the camera module
            frame = self.camera_module.capture_image()

            # Preprocess the frame
            preprocessed_frame = self.preprocess_frame(frame)

            # Detect obstacles in the frame
            obstacles = self.detect_obstacles(preprocessed_frame)

            # Localize the obstacles
            localized_obstacles = self.localize_obstacles(obstacles)
            
            # Check if there's a wall detected on the right side of the robot
            # You can adjust the threshold and range according to your requirements
            threshold = 50
            right_obstacles = [obst for obst in localized_obstacles if obst[0] > threshold and 0 < obst[1] < 200]

            if len(right_obstacles) > 0:
                wall_detected = True

            return {"right_wall_detected": wall_detected}
        except Exception as e:
            print(f"Error in getting obstacle data from camera: {e}")
            return {"right_wall_detected": False}
