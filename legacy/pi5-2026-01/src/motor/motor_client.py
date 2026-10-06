"""
Motor Client - RPi5
TCP-klient som sender motorkommandoer til RPi3.
Starter automatisk reconnect i bakgrunnen ved oppstart.
"""

import socket
import json
import threading
import time
from typing import Optional, Callable
from queue import Queue, Empty

# Prøv å importere lokal konfig
try:
    from config import (
        RPI3_HOST, RPI3_PORT, 
        RPI3_RECONNECT_DELAY, RPI3_RECONNECT_ATTEMPTS, RPI3_COMMAND_TIMEOUT
    )
except ImportError:
    RPI3_HOST = '192.168.1.43'
    RPI3_PORT = 5001
    RPI3_RECONNECT_DELAY = 2.0
    RPI3_RECONNECT_ATTEMPTS = 30
    RPI3_COMMAND_TIMEOUT = 5.0


class MotorClient:
    """
    TCP-klient for kommunikasjon med RPi3 Motor Controller.
    Håndterer automatisk reconnect i bakgrunnen.
    """
    
    def __init__(
        self, 
        host: str = RPI3_HOST, 
        port: int = RPI3_PORT,
        on_status_update: Optional[Callable] = None,
        on_connection_change: Optional[Callable] = None
    ):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = True  # Start as running
        
        # Callbacks
        self.on_status_update = on_status_update
        self.on_connection_change = on_connection_change
        
        # Threading
        self.lock = threading.Lock()
        self.receive_thread: Optional[threading.Thread] = None
        self.reconnect_thread: Optional[threading.Thread] = None
        
        # State (speilet fra RPi3)
        self.current_movement = "stopped"
        self.speed = 0.5
        self.last_response_time = 0
        
    def connect(self, timeout: float = 3.0) -> bool:
        """
        Try to connect to RPi3 motor controller.
        Returns True if connected, False otherwise.
        """
        with self.lock:
            if self.connected:
                return True
                
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(timeout)
                self.socket.connect((self.host, self.port))
                self.connected = True
                
                # Start mottakstråd
                self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
                self.receive_thread.start()
                
                print(f"✓ Connected to RPi3 Motor Controller at {self.host}:{self.port}")
                
                if self.on_connection_change:
                    self.on_connection_change(True)
                    
                return True
                
            except socket.timeout:
                print(f"⚠ Connection to RPi3 timed out")
                self.connected = False
                return False
            except ConnectionRefusedError:
                print(f"⚠ Connection to RPi3 refused - is motor_service.py running?")
                self.connected = False
                return False
            except Exception as e:
                print(f"⚠ Failed to connect to RPi3: {e}")
                self.connected = False
                return False

    def start_background_connect(self):
        """
        Start trying to connect in the background.
        This doesn't block the main thread.
        """
        if self.reconnect_thread is None or not self.reconnect_thread.is_alive():
            self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self.reconnect_thread.start()

    def disconnect(self):
        """Disconnect from RPi3."""
        print("Disconnecting from RPi3...")
        self.running = False  # Stop all loops first
        
        # Wait for reconnect thread to stop
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=1.0)
        
        with self.lock:
            if self.socket:
                try:
                    # Try to send stop command (don't wait for response)
                    self.socket.settimeout(0.5)
                    self._send_raw({"command": "stop"})
                except:
                    pass
                    
                try:
                    self.socket.close()
                except:
                    pass
                    
                self.socket = None
                
            self.connected = False
            
        if self.on_connection_change:
            self.on_connection_change(False)
            
        print("Disconnected from RPi3")

    def _send_raw(self, msg: dict) -> bool:
        """Send raw message without lock (internal use)."""
        if not self.socket:
            return False
            
        try:
            data = json.dumps(msg) + '\n'
            self.socket.send(data.encode('utf-8'))
            return True
        except:
            return False

    def send_command(self, command: str, **kwargs) -> Optional[dict]:
        """
        Send command to RPi3 and wait for response.
        Returns response dict or None on failure.
        """
        with self.lock:
            if not self.connected or not self.socket:
                # Start background reconnect if not already running
                if not self.reconnect_thread or not self.reconnect_thread.is_alive():
                    self.lock.release()
                    self.start_background_connect()
                    self.lock.acquire()
                return None
            
            msg = {"command": command, **kwargs}
            
            try:
                # Send kommando
                data = json.dumps(msg) + '\n'
                self.socket.send(data.encode('utf-8'))
                
                # Vent på respons (med timeout)
                self.socket.settimeout(RPI3_COMMAND_TIMEOUT)
                response_data = self.socket.recv(4096).decode('utf-8')
                
                if response_data:
                    response = json.loads(response_data.strip().split('\n')[0])
                    self.last_response_time = time.time()
                    
                    # Oppdater lokal state
                    if 'movement' in response:
                        self.current_movement = response['movement']
                    if 'speed' in response:
                        self.speed = response['speed']
                        
                    return response
                    
            except socket.timeout:
                print("⚠ Command timeout")
                self._handle_disconnect()
            except json.JSONDecodeError as e:
                print(f"⚠ Invalid response: {e}")
            except Exception as e:
                print(f"⚠ Send error: {e}")
                self._handle_disconnect()
                
            return None

    def _handle_disconnect(self):
        """Handle unexpected disconnect."""
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        if self.on_connection_change:
            self.on_connection_change(False)
            
        # Start reconnect i bakgrunnen
        self.start_background_connect()

    def _reconnect_loop(self):
        """Try to reconnect in background."""
        attempts = 0
        
        while self.running and not self.connected:
            attempts += 1
            
            if attempts > RPI3_RECONNECT_ATTEMPTS:
                print(f"⚠ Giving up on RPi3 connection after {attempts-1} attempts")
                print(f"  Will keep trying every 10 seconds...")
                
                # Check if we should stop
                for _ in range(10):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                    
                attempts = 1  # Reset and keep trying
                continue
                
            print(f"🔄 Connecting to RPi3... (attempt {attempts})")
            
            if self.connect(timeout=3.0):
                print("✓ Connected to RPi3!")
                break
            
            # Check if we should stop before waiting
            if not self.running:
                break
                
            time.sleep(RPI3_RECONNECT_DELAY)
            
        self.reconnect_thread = None

    def _receive_loop(self):
        """Background thread for receiving heartbeats and status updates."""
        buffer = ""
        
        while self.running and self.connected:
            try:
                if self.socket:
                    self.socket.settimeout(1.0)
                    data = self.socket.recv(4096).decode('utf-8')
                    
                    if not data:
                        self._handle_disconnect()
                        break
                        
                    buffer += data
                    
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            try:
                                msg = json.loads(line)
                                
                                # Håndter heartbeat
                                if msg.get('type') == 'heartbeat':
                                    self.last_response_time = time.time()
                                    if 'movement' in msg:
                                        self.current_movement = msg['movement']
                                    if 'speed' in msg:
                                        self.speed = msg['speed']
                                        
                                    if self.on_status_update:
                                        self.on_status_update(msg)
                                        
                            except json.JSONDecodeError:
                                pass
                                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self._handle_disconnect()
                break

    # ========== Motor Commands ==========
    
    def move_forward(self, speed: Optional[float] = None) -> bool:
        kwargs = {'speed': speed} if speed is not None else {}
        response = self.send_command('move_forward', **kwargs)
        return response is not None and response.get('status') == 'ok'

    def move_backward(self, speed: Optional[float] = None) -> bool:
        kwargs = {'speed': speed} if speed is not None else {}
        response = self.send_command('move_backward', **kwargs)
        return response is not None and response.get('status') == 'ok'

    def strafe_left(self, speed: Optional[float] = None) -> bool:
        kwargs = {'speed': speed} if speed is not None else {}
        response = self.send_command('strafe_left', **kwargs)
        return response is not None and response.get('status') == 'ok'

    def strafe_right(self, speed: Optional[float] = None) -> bool:
        kwargs = {'speed': speed} if speed is not None else {}
        response = self.send_command('strafe_right', **kwargs)
        return response is not None and response.get('status') == 'ok'

    def rotate_clockwise(self, speed: Optional[float] = None) -> bool:
        kwargs = {'speed': speed} if speed is not None else {}
        response = self.send_command('rotate_clockwise', **kwargs)
        return response is not None and response.get('status') == 'ok'

    def rotate_counterclockwise(self, speed: Optional[float] = None) -> bool:
        kwargs = {'speed': speed} if speed is not None else {}
        response = self.send_command('rotate_counterclockwise', **kwargs)
        return response is not None and response.get('status') == 'ok'

    def stop(self) -> bool:
        response = self.send_command('stop')
        return response is not None and response.get('status') == 'ok'

    def set_speed(self, speed: float) -> bool:
        response = self.send_command('set_speed', speed=speed)
        if response and response.get('status') == 'ok':
            self.speed = speed
            return True
        return False

    def get_status(self) -> Optional[dict]:
        return self.send_command('status')

    def ping(self) -> bool:
        response = self.send_command('ping')
        return response is not None and response.get('status') == 'ok'


class RemoteMotorController:
    """
    Drop-in replacement for local MotorController.
    Uses MotorClient to communicate with RPi3.
    Starts background connection immediately.
    """
    
    def __init__(self, host: str = RPI3_HOST, port: int = RPI3_PORT):
        self.client = MotorClient(host, port)
        self.wheels = self  # For compatibility with existing code
        
        # Start background connection immediately
        self.client.start_background_connect()
        
    def connect(self) -> bool:
        return self.client.connect()
    
    @property
    def connected(self) -> bool:
        return self.client.connected
        
    @property
    def current_movement(self) -> str:
        return self.client.current_movement
        
    @property
    def speed(self) -> float:
        return self.client.speed
        
    def set_speed(self, speed: float):
        self.client.set_speed(speed)
        
    def move_forward(self):
        self.client.move_forward()
        
    def move_backward(self):
        self.client.move_backward()
        
    def strafe_left(self):
        self.client.strafe_left()
        
    def strafe_right(self):
        self.client.strafe_right()
        
    def rotate_clockwise(self):
        self.client.rotate_clockwise()
        
    def rotate_counterclockwise(self):
        self.client.rotate_counterclockwise()
        
    def stop(self):
        self.client.stop()
        
    def cleanup(self):
        self.client.disconnect()


# Test
if __name__ == "__main__":
    import sys
    
    host = sys.argv[1] if len(sys.argv) > 1 else RPI3_HOST
    
    print(f"\n🔌 Testing connection to RPi3 at {host}...")
    
    client = MotorClient(host)
    
    if client.connect():
        print("\n✓ Connected!\n")
        
        # Test ping
        print("Testing ping...")
        if client.ping():
            print("  ✓ Ping OK")
        else:
            print("  ✗ Ping failed")
            
        # Test status
        print("\nGetting status...")
        status = client.get_status()
        if status:
            print(f"  ✓ Status: {status}")
        else:
            print("  ✗ Status failed")
            
        # Test movement
        print("\nTesting forward movement (1 sec)...")
        client.move_forward(0.5)
        time.sleep(1)
        client.stop()
        print("  ✓ Movement test complete")
        
        client.disconnect()
    else:
        print("\n✗ Could not connect")
