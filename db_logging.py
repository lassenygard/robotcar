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
        
        
        
# def create_tables():
    # conn = mysql.connector.connect(**db_config)
    # cursor = conn.cursor()

# # Create tables if they don't exist
# cursor.execute("""
    # CREATE TABLE IF NOT EXISTS maps (
        # id INT AUTO_INCREMENT PRIMARY KEY,
        # timestamp DATETIME,
        # map_id VARCHAR(32),
        # map_name VARCHAR(255),
        # version_number INT,
        # perimeter_coordinates TEXT,
        # obstacle_coordinates TEXT
        # -- Add other columns here
    # )
# """)

# cursor.execute("""
    # CREATE TABLE IF NOT EXISTS paths (
        # id INT AUTO_INCREMENT PRIMARY KEY,
        # timestamp DATETIME,
        # map_id VARCHAR(32),
        # map_name VARCHAR(255),
        # path_route TEXT
    # )
# """)

# cursor.execute("""
    # CREATE TABLE IF NOT EXISTS error_logs (
        # id INT AUTO_INCREMENT PRIMARY KEY,
        # timestamp DATETIME,
        # error_message TEXT
    # )
# """)

# cursor.execute("""
    # CREATE TABLE IF NOT EXISTS console_logs (
        # id INT AUTO_INCREMENT PRIMARY KEY,
        # timestamp DATETIME,
        # message TEXT
    # )
# """)

# # Add other tables here

# conn.commit()
# cursor.close()
# conn.close()

# def insert_map_log(map_data):
    # conn = mysql.connector.connect(**db_config)
    # cursor = conn.cursor()

    # cursor.execute("""
        # INSERT INTO maps (timestamp, map_id, map_name, version_number, perimeter_coordinates, obstacle_coordinates)
        # VALUES (%s, %s, %s, %s, %s, %s)
    # """, (map_data["timestamp"], map_data["map_id"], map_data["map_name"], map_data["version_number"],
          # map_data["perimeter_coordinates"], map_data["obstacle_coordinates"]))

    # conn.commit()
    # cursor.close()
    # conn.close()

# def insert_path_log(path_data):
    # conn = mysql.connector.connect(**db_config)
    # cursor = conn.cursor()

    # cursor.execute("""
        # INSERT INTO paths (timestamp, map_id, map_name, path_route)
        # VALUES (%s, %s, %s, %s)
    # """, (path_data["timestamp"], path_data["map_id"], path_data["map_name"], path_data["path"]))

    # conn.commit()
    # cursor.close()
    # conn.close()

# def insert_error_log(error_message):
    # conn = mysql.connector.connect(**db_config)
    # cursor = conn.cursor()

    # timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # cursor.execute("""
        # INSERT INTO error_logs (timestamp, error_message)
        # VALUES (%s, %s)
    # """, (timestamp, error_message))

    # conn.commit()
    # cursor.close()
    # conn.close()

# def insert_console_log(message):
    # conn = mysql.connector.connect(**db_config)
    # cursor = conn.cursor()

    # timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # cursor.execute("""
        # INSERT INTO console_logs (timestamp, message)
        # VALUES (%s, %s)
    # """, (timestamp, message))

    # conn.commit()
    # cursor.close()
    # conn.close()

# # Save map data to the database
# map_data = save_map_data(map_instance)
# insert_map_log(map_data)

# # Save path data to the database
# path_data = save_path_data(path, map_data)
# insert_path_log(path_data)

# # Save error logs
# try:
    # # ... your main code ...
# except Exception as e:
    # error_message = f"Unexpected error: {e}"
    # print(error_message)
    # insert_error_log(error_message)

# # Save console logs
# console_message = f"Current position: {current_position}"
# print(console_message)
# insert_console_log(console_message)


