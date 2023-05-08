# db_logging.py

import mariadb
import hashlib
import json
from datetime import datetime

def load_db_config(file_path='db_config.json'):
    try:
        with open(file_path, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"Database configuration file '{file_path}' not found.")
        return None
    except json.JSONDecodeError:
        print("Error decoding database configuration JSON.")
        return None

# Database connection parameters
DB_CONFIG = load_db_config()

def create_connection():
    if DB_CONFIG is None:
        return None

    try:
        conn = mariadb.connect(**DB_CONFIG)
        return conn
    except mariadb.Error as e:
        print(f"Error connecting to MariaDB: {e}")
        return None
        
def close_connection(conn):
    if conn:
        conn.close()

def generate_map_id(map_name):
    hash_object = hashlib.md5(map_name.encode())
    return hash_object.hexdigest()

def log_map(map_data):
    conn = create_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        timestamp = map_data['timestamp']
        map_id = map_data['map_id']
        map_name = map_data['map_name']
        version = map_data['version_number']

        # Add other columns if necessary
        map_insert_query = f"""
        INSERT INTO maps (timestamp, map_id, map_name, version)
        VALUES (?, ?, ?, ?);
        """
        cursor.execute(map_insert_query, (timestamp, map_id, map_name, version))

        for obstacle in map_data["obstacles"]:
            obstacle_insert_query = f"""
            INSERT INTO obstacles (map_id, x, y, width, height)
            VALUES (?, ?, ?, ?, ?);
            """
            cursor.execute(obstacle_insert_query, (map_id, *obstacle))

        conn.commit()

    except mariadb.Error as e:
        print(f"Error logging map data: {e}")

    finally:
        close_connection(conn)

def log_path(path_data):
    conn = create_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        timestamp = path_data['timestamp']
        map_id = path_data['map_id']
        map_name = path_data['map_name']
        path = path_data['path']

        path_insert_query = f"""
        INSERT INTO paths (timestamp, map_id, map_name, path)
        VALUES (?, ?, ?, ?);
        """
        cursor.execute(path_insert_query, (timestamp, map_id, map_name, path))

        conn.commit()
        print(f"Saving path for map: {path_data['map_name']}")

    except mariadb.Error as e:
        print(f"Error logging path data: {e}")

    finally:
        close_connection(conn)

def log_error(error_message):
    conn = create_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        timestamp = datetime.now()

        error_insert_query = f"""
        INSERT INTO error_logs (timestamp, error_message)
        VALUES (?, ?);
        """
        cursor.execute(error_insert_query, (timestamp, error_message))

        conn.commit()

    except mariadb.Error as e:
        print(f"Error logging error message: {e}")

    finally:
        close_connection(conn)

def log_console(console_message):
    conn = create_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        timestamp = datetime.now()

        console_insert_query = f"""
        INSERT INTO console_logs (timestamp, console_message)
        VALUES (?, ?);
        """
        cursor.execute(console_insert_query, (timestamp, console_message))

        conn.commit()

    except mariadb.Error as e:
        print(f"Error logging console message: {e}")

    finally:
        close_connection(conn)
