# localization.py

import math

class DeadReckoningLocalization:
    def __init__(self, initial_position, initial_orientation, wheel_radius, wheel_separation):
        self.position = initial_position
        self.orientation = initial_orientation
        self.wheel_radius = wheel_radius
        self.wheel_separation = wheel_separation

    def update_odometry(self, wheel_speeds, dt):
        try:
            # Calculate the linear and angular velocities
            v_left = wheel_speeds[0] * self.wheel_radius
            v_right = wheel_speeds[1] * self.wheel_radius
            v = (v_right + v_left) / 2.0
            w = (v_right - v_left) / self.wheel_separation

            # Update the robot's orientation
            self.orientation += w * dt
            self.orientation %= 2 * math.pi

            # Update the robot's position
            dx = v * math.cos(self.orientation) * dt
            dy = v * math.sin(self.orientation) * dt
            self.position[0] += dx
            self.position[1] += dy
        except Exception as e:
            print(f"Error updating odometry: {e}")

    def get_current_position(self):
        return self.position, self.orientation

    def reset_position(self, new_position=None):
        if new_position is None:
            self.position = [0, 0]
            self.orientation = 0
        else:
            self.position = new_position[0]
            self.orientation = new_position[1]
