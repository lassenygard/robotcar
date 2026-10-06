"""Metric occupancy mapping and conservative lidar/visual place localisation.

Right-handed frame: metres, x forward at startup, y left, yaw counterclockwise.
Unknown space is never traversable. Pose confidence is based on actual returns,
not elapsed motor command time. Map files contain private apartment data.
"""
import heapq
import math
import os
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt, binary_dilation
from scipy.optimize import minimize
from scipy.spatial import cKDTree


def wrap(angle):
    return (angle + math.pi) % (2*math.pi) - math.pi


def transform(points, pose):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return points @ np.array([[c, s], [-s, c]]) + np.asarray(pose[:2])


def scan_points(scan):
    a = np.asarray(scan, dtype=float)
    if a.ndim != 2 or a.shape[0] < 60 or a.shape[1] < 2:
        raise ValueError('at least 60 valid lidar returns are required')
    a = a[np.isfinite(a).all(axis=1) & (a[:, 1] > .12) & (a[:, 1] < 8)]
    if len(a) < 60:
        raise ValueError('not enough valid lidar returns')
    return np.column_stack((np.cos(a[:, 0])*a[:, 1], np.sin(a[:, 0])*a[:, 1]))[::max(1, len(a)//300)]


def align_scan(points, reference, max_distance=.45):
    """Robust point-to-point ICP; returns current frame pose in reference frame."""
    tree = cKDTree(reference)
    pose = np.zeros(3)
    for _ in range(18):
        moved = transform(points, pose)
        distance, indexes = tree.query(moved)
        keep = distance < min(max_distance, max(.08, float(np.percentile(distance, 75))))
        if keep.sum() < 40:
            return pose, 0.0
        source, target = moved[keep], reference[indexes[keep]]
        p, q = source.mean(axis=0), target.mean(axis=0)
        u, _, vt = np.linalg.svd((source-p).T @ (target-q))
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0:
            vt[-1] *= -1
            rotation = vt.T @ u.T
        delta = math.atan2(rotation[1, 0], rotation[0, 0])
        shift = q - rotation @ p
        pose[:2] = rotation @ pose[:2] + shift
        pose[2] = wrap(pose[2] + delta)
        if np.linalg.norm(shift) < .0005 and abs(delta) < .0005:
            break
    distance, _ = tree.query(transform(points, pose))
    score = float(np.mean(distance < .10))
    if np.linalg.norm(pose[:2]) > .5 or abs(pose[2]) > .6:
        score = 0.0
    return pose, score


class OccupancyMap:
    def __init__(self, size=600, resolution=.05):
        self.size, self.resolution = size, resolution
        self.grid = np.zeros((size, size), dtype=np.float32)
        self.pose = np.zeros(3)
        self.confidence = 0.0
        self.previous = None
        self.keyframes = []
        self.mapping = True
        self.localized = False
        self.revision = 0
        self.name = None

    def cells(self, points):
        return np.floor(np.asarray(points)/self.resolution + self.size/2).astype(int)

    def world(self, cell):
        return (np.asarray(cell) + .5 - self.size/2)*self.resolution

    def distance_field(self):
        return distance_transform_edt(self.grid < .8)*self.resolution

    def score(self, points, pose, field=None):
        if field is None:
            field = self.distance_field()
        cells = self.cells(transform(points, pose))
        inside = ((cells >= 0) & (cells < self.size)).all(axis=1)
        distances = np.ones(len(cells))
        c = cells[inside]
        distances[inside] = field[c[:, 1], c[:, 0]]
        return float(np.mean(np.exp(-distances**2 / (.12**2))))

    def refine(self, points, seed, field=None, radius=.3, yaw=.25):
        if field is None:
            field = self.distance_field()
        bounds = [(seed[0]-radius, seed[0]+radius), (seed[1]-radius, seed[1]+radius),
                  (seed[2]-yaw, seed[2]+yaw)]
        result = minimize(lambda p: -self.score(points, p, field), np.asarray(seed), method='Powell',
                          bounds=bounds, options={'maxiter': 14, 'xtol': .008, 'ftol': .005})
        pose = result.x
        pose[2] = wrap(pose[2])
        return pose, self.score(points, pose, field)

    def update(self, scan):
        points = scan_points(scan)
        if self.previous is None:
            if np.count_nonzero(self.grid) == 0:
                self.pose[:] = 0
                self.localized, self.confidence = True, 1.0
            elif not self.localized:
                return False
        else:
            delta, score = align_scan(points, self.previous)
            if score < .60:
                self.confidence, self.localized = score, False
                return False
            pose = self.pose.copy()
            pose[:2] = transform(delta[:2][None, :], pose)[0]
            pose[2] = wrap(pose[2] + delta[2])
            if self.revision >= 5:
                refined, map_score = self.refine(points, pose, radius=.12, yaw=.10)
                if map_score < .5:
                    self.confidence, self.localized = map_score, False
                    return False
                pose, score = refined, min(score, map_score)
            self.pose, self.confidence, self.localized = pose, score, True
        self.previous = points
        if self.mapping:
            self.integrate(points)
        return True

    def integrate(self, points):
        origin = self.cells(self.pose[:2])
        endpoints = self.cells(transform(points, self.pose))
        free = np.zeros(self.grid.shape, np.uint8)
        occupied = np.zeros_like(free)
        for target in endpoints:
            if np.all((target >= 0) & (target < self.size)):
                cv2.line(free, tuple(origin), tuple(target), 1, 1)
                occupied[target[1], target[0]] = 1
        self.grid[free.astype(bool)] -= .35
        self.grid[occupied.astype(bool)] += 1.2
        np.clip(self.grid, -4, 4, out=self.grid)
        self.revision += 1

    def relocalize(self, scan, visual_candidates=None):
        points = scan_points(scan)
        field = self.distance_field()
        if np.count_nonzero(self.grid > .8) < 30:
            raise ValueError('map has too few occupied cells')
        seeds = [np.asarray(p) for p in (visual_candidates or [])]
        # Saved positions provide discrete global hypotheses; all headings are checked.
        for keyframe in self.keyframes[::max(1, len(self.keyframes)//60)]:
            for heading in np.linspace(-math.pi, math.pi, 24, endpoint=False):
                seeds.append(np.array([*keyframe['pose'][:2], heading]))
        if not seeds:
            seeds = [np.array([0, 0, a]) for a in np.linspace(-math.pi, math.pi, 24, endpoint=False)]
        ranked = sorted(((self.score(points, s, field), s) for s in seeds),
                        key=lambda x: x[0], reverse=True)
        candidates = []
        for score, seed in ranked:
            if all(np.linalg.norm(seed[:2]-other[:2]) > .5 or abs(wrap(seed[2]-other[2])) > .3
                   for _, other in candidates):
                candidates.append((score, seed))
            if len(candidates) >= 8:
                break
        fits = [self.refine(points, seed, field, radius=.7, yaw=.3) for _, seed in candidates]
        fits.sort(key=lambda x: x[1], reverse=True)
        best, score = fits[0]
        # Do not localise in repeated corridors if a distant hypothesis fits equally well.
        ambiguous = any(s > score-.06 and (np.linalg.norm(p[:2]-best[:2]) > .8 or
                        abs(wrap(p[2]-best[2])) > .6) for p, s in fits[1:])
        if score < .65 or ambiguous:
            self.localized, self.confidence = False, score
            return False
        self.pose, self.confidence, self.localized = best, score, True
        self.previous = points
        return True

    def traversable(self, radius=.32):
        blocked = self.grid >= -.3  # Unknown and occupied are both blocked.
        return distance_transform_edt(~blocked)*self.resolution > radius

    def plan(self, goal, radius=.32):
        goal = np.asarray(goal, dtype=float)
        if goal.shape != (2,) or not np.isfinite(goal).all():
            raise ValueError('invalid target')
        start, end = tuple(self.cells(self.pose[:2])), tuple(self.cells(goal))
        allowed = self.traversable(radius)
        for p in [start, end]:
            if not (0 <= p[0] < self.size and 0 <= p[1] < self.size and allowed[p[1], p[0]]):
                raise ValueError('robot or target is in unknown/occupied space or too close to a wall')
        queue, cost, parent = [(0.0, start)], {start: 0.0}, {}
        visited = set()
        while queue:
            _, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current == end:
                path = [current]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                return [self.world(p).tolist() for p in reversed(path)]
            for dx, dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
                nxt = current[0]+dx, current[1]+dy
                if not (0 <= nxt[0] < self.size and 0 <= nxt[1] < self.size and allowed[nxt[1], nxt[0]]):
                    continue
                if dx and dy and not (allowed[current[1], nxt[0]] and allowed[nxt[1], current[0]]):
                    continue
                value = cost[current] + math.hypot(dx, dy)
                if value < cost.get(nxt, float('inf')):
                    cost[nxt], parent[nxt] = value, current
                    heapq.heappush(queue, (value + math.dist(nxt, end), nxt))
        raise ValueError('no collision-free path through known free space')

    def frontier_targets(self):
        free = self.traversable()
        near_unknown = binary_dilation(abs(self.grid) < .1, iterations=9)
        count, labels, stats, centers = cv2.connectedComponentsWithStats((free & near_unknown).astype(np.uint8))
        targets = []
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_AREA] < 4:
                continue
            ys, xs = np.where(labels == i)
            nearest = np.argmin((xs-centers[i, 0])**2 + (ys-centers[i, 1])**2)
            target = self.world([xs[nearest], ys[nearest]])
            if np.linalg.norm(target-self.pose[:2]) > .5:
                targets.append(target.tolist())
        return sorted(targets, key=lambda p: np.linalg.norm(np.asarray(p)-self.pose[:2]))

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp.npz')
        import json
        np.savez_compressed(temp, grid=self.grid, resolution=self.resolution, pose=self.pose,
                            keyframes=json.dumps(self.keyframes), version=1)
        os.replace(temp, path)

    @classmethod
    def load(cls, path):
        import json
        with np.load(path, allow_pickle=False) as data:
            grid = data['grid']
            if grid.ndim != 2 or grid.shape[0] != grid.shape[1] or grid.shape[0] > 2000 or not np.isfinite(grid).all():
                raise ValueError('invalid map dimensions or values')
            result = cls(grid.shape[0], float(data['resolution']))
            result.grid = grid.astype(np.float32)
            result.keyframes = json.loads(str(data['keyframes']))
            result.pose = data['pose'].copy()
        result.mapping, result.localized = False, False  # A saved pose is not a live location.
        result.revision = 5  # Enable scan-to-map correction immediately after localisation.
        result.name = Path(path).stem
        return result

    def image(self):
        img = np.full(self.grid.shape, 115, np.uint8)
        img[self.grid < -.3] = 235
        img[self.grid > .8] = 25
        return cv2.imencode('.png', np.flipud(img))[1].tobytes()
