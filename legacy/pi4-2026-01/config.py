"""
Konfigurasjon for RPi3 Motor Controller Service
"""

# Nettverksinnstillinger
HOST = '0.0.0.0'  # Lytt på alle interfaces
PORT = 5001       # Port for motorkommandoer

# GPIO pin-konfigurasjon for Mecanum-hjul
# Format: (forward_pin, backward_pin, enable_pin)
MOTOR_PINS = {
    'front_left':  (24, 27, 5),
    'front_right': (6, 22, 17),
    'rear_left':   (23, 16, 12),
    'rear_right':  (18, 13, 25),
}

# Standard hastighet (0.0 - 1.0)
DEFAULT_SPEED = 0.5

# Timeout for socket-tilkoblinger (sekunder)
SOCKET_TIMEOUT = 30

# Heartbeat-intervall (sekunder) - 0 for å deaktivere
HEARTBEAT_INTERVAL = 5

# Logging
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = '/var/log/motor_controller.log'  # None for kun konsoll
