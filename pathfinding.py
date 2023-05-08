# pathfinding.py

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from scipy.interpolate import CubicSpline
from queue import PriorityQueue

class Pathfinder:
    def __init__(self, map_instance):
        self.map = map_instance

    def find_path(self, start, goal):
        def heuristic(a, b):
            return np.sqrt((b[0] - a[0])**2 + (b[1] - a[1])**2)

        def reconstruct_path(came_from, current):
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]

        frontier = PriorityQueue()
        frontier.put((0, start))
        came_from = {}
        cost_so_far = {}
        came_from[start] = None
        cost_so_far[start] = 0

        while not frontier.empty():
            _, current = frontier.get()

            if current == goal:
                break

            for neighbor in self.map.get_neighbors(current):
                new_cost = cost_so_far[current] + self.map.cost(current, neighbor)
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    priority = new_cost + heuristic(goal, neighbor)
                    frontier.put((priority, neighbor))
                    came_from[neighbor] = current

        return reconstruct_path(came_from, goal)

    def get_smoothed_path(self, raw_path):
        x = [point[0] for point in raw_path]
        y = [point[1] for point in raw_path]
        t = np.arange(len(raw_path))

        cs_x = CubicSpline(t, x)
        cs_y = CubicSpline(t, y)
        t_smooth = np.linspace(0, len(raw_path) - 1, num=100)
        smoothed_path = np.array([cs_x(t_smooth), cs_y(t_smooth)]).T
        
        return smoothed_path

    def visualize_path(self, path):
        plt.imshow(self.map.grid, cmap='gray', origin='lower')
        plt.plot([point[0] for point in path], [point[1] for point in path], 'r-')
        plt.scatter([path[0][0], path[-1][0]], [path[0][1], path[-1][1]], c='blue', marker=MarkerStyle('o'), s=50)
        plt.title('Pathfinding Visualization')
        plt.xlabel('X-axis')
        plt.ylabel('Y-axis')
        plt.show()
