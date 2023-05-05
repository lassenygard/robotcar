# save_imgs.py

import os
import hashlib
from datetime import datetime
import cv2

def save_map_data(map_instance, base_path="maps"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    map_id = hashlib.md5(timestamp.encode()).hexdigest()
    map_name = f"map{len(os.listdir(base_path)) + 1}"
    version_number = 1

    map_data = {
        "timestamp": timestamp,
        "map_id": map_id,
        "map_name": map_name,
        "version_number": version_number,
    }

    # Save map as an image
    img_path = os.path.join(base_path, map_name, "img")
    os.makedirs(img_path, exist_ok=True)
    map_image = map_instance.grid
    cv2.imwrite(os.path.join(img_path, f"{map_name}_{version_number}.png"), map_image)
    print(f"Saving map: {map_data['map_name']}")
    
    return map_data


def save_path_data(path, map_data, map_instance, base_path="paths"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path_data = {
        "timestamp": timestamp,
        "map_id": map_data["map_id"],
        "map_name": map_data["map_name"],
        "path": path,
    }

    # Save path as an image
    img_path = os.path.join(base_path, map_data["map_name"], "img")
    os.makedirs(img_path, exist_ok=True)
    path_image = map_instance.get_path_image(path)
    cv2.imwrite(os.path.join(img_path, f"path_{timestamp}.png"), path_image)
    print(f"Saving path: {path_data['path']}")
    
    return path_data
