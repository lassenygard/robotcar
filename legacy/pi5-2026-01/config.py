"""
Konfigurasjon for RPi5 (Master)
"""

import os

# Finn prosjektets rotmappe
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# RPi3 Motor Controller tilkobling
# VIKTIG: Oppdater denne til din RPi3/RPi4 sin faktiske IP-adresse!
RPI3_HOST = '192.168.4.43'  # <-- SJEKK AT DENNE ER RIKTIG!
RPI3_PORT = 5001

# Reconnect-innstillinger
RPI3_RECONNECT_DELAY = 2.0      # Sekunder mellom tilkoblingsforsøk
RPI3_RECONNECT_ATTEMPTS = 30    # Økt fra 10 til 30 forsøk
RPI3_COMMAND_TIMEOUT = 5.0      # Timeout for kommandoer

# LIDAR-innstillinger
LIDAR_PORT = '/dev/ttyUSB0'
LIDAR_BAUDRATE = 115200

# Kamera-innstillinger
CAMERA_FRONT = 0    # Kamera-indeks for frontkamera
CAMERA_REAR = 1     # Kamera-indeks for bakkamera
CAMERA_RESOLUTION = (640, 480)
CAMERA_FPS = 30

# Webserver
WEB_HOST = '0.0.0.0'
WEB_PORT = 5000

# Navigasjon
DEFAULT_SAFE_DISTANCE = 500     # mm
DEFAULT_LIDAR_OFFSET = -105     # grader

# Hailo AI - bruk absolutt sti
HEF_PATH = os.path.join(PROJECT_ROOT, 'yolov5m_wo_spp_60p.hef')
LABELS_PATH = os.path.join(PROJECT_ROOT, 'coco.txt')
DETECTION_THRESHOLD = 0.5
