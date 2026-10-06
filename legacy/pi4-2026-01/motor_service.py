"""
Motor Controller Service - RPi3
TCP-server som mottar motorkommandoer fra RPi5 (master).
"""

import socket
import json
import threading
import time
import signal
import sys
from typing import Optional

from config import HOST, PORT, SOCKET_TIMEOUT, HEARTBEAT_INTERVAL, LOG_LEVEL
from motor_controller import MecanumWheels


class MotorService:
    """
    TCP-server som mottar motorkommandoer over nettverket.
    Kommuniserer med RPi5 (master) via JSON-meldinger.
    """
    
    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.wheels = MecanumWheels()
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.clients = []
        self.lock = threading.Lock()
        
        # Kommando-mapping
        self.commands = {
            'move_forward': self.wheels.move_forward,
            'move_backward': self.wheels.move_backward,
            'strafe_left': self.wheels.strafe_left,
            'strafe_right': self.wheels.strafe_right,
            'rotate_clockwise': self.wheels.rotate_clockwise,
            'rotate_counterclockwise': self.wheels.rotate_counterclockwise,
            'diagonal_forward_left': self.wheels.diagonal_forward_left,
            'diagonal_forward_right': self.wheels.diagonal_forward_right,
            'diagonal_backward_left': self.wheels.diagonal_backward_left,
            'diagonal_backward_right': self.wheels.diagonal_backward_right,
            'stop': self.wheels.stop,
        }
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\n⚡ Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)

    def _log(self, message: str, level: str = 'INFO'):
        """Simple logging."""
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] [{level}] {message}")

    def start(self):
        """Start the motor service."""
        self.running = True
        
        # Opprett TCP socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)  # For å kunne stoppe gracefully
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            self._log(f"Motor Service started on {self.host}:{self.port}", 'INFO')
            self._print_banner()
            
            # Start heartbeat thread hvis aktivert
            if HEARTBEAT_INTERVAL > 0:
                heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                heartbeat_thread.start()
            
            # Hovedloop - aksepter tilkoblinger
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    self._log(f"Client connected: {address[0]}:{address[1]}", 'INFO')
                    
                    # Start client handler thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue  # Tillater sjekk av self.running
                except Exception as e:
                    if self.running:
                        self._log(f"Accept error: {e}", 'ERROR')
                        
        except Exception as e:
            self._log(f"Server error: {e}", 'ERROR')
        finally:
            self.stop()

    def _print_banner(self):
        """Print startup banner."""
        print("\n" + "="*50)
        print("   🤖 RPi3 MOTOR CONTROLLER SERVICE")
        print("="*50)
        print(f"   Host: {self.host}")
        print(f"   Port: {self.port}")
        print(f"   GPIO: {'Available' if self.wheels.motors else 'Simulation'}")
        print("="*50)
        print("   Waiting for connections...")
        print("   Press Ctrl+C to stop\n")

    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle a single client connection."""
        client_socket.settimeout(SOCKET_TIMEOUT)
        
        with self.lock:
            self.clients.append(client_socket)
        
        buffer = ""
        
        try:
            while self.running:
                try:
                    data = client_socket.recv(4096).decode('utf-8')
                    if not data:
                        break  # Client disconnected
                    
                    buffer += data
                    
                    # Prosesser komplette JSON-meldinger (newline-separert)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            response = self._process_command(line.strip())
                            client_socket.send((json.dumps(response) + '\n').encode('utf-8'))
                            
                except socket.timeout:
                    continue
                except json.JSONDecodeError as e:
                    self._log(f"JSON error: {e}", 'WARNING')
                    response = {"status": "error", "message": f"Invalid JSON: {e}"}
                    client_socket.send((json.dumps(response) + '\n').encode('utf-8'))
                    
        except Exception as e:
            self._log(f"Client error ({address[0]}): {e}", 'ERROR')
        finally:
            with self.lock:
                if client_socket in self.clients:
                    self.clients.remove(client_socket)
            client_socket.close()
            self._log(f"Client disconnected: {address[0]}:{address[1]}", 'INFO')
            
            # Stopp motorene når klient kobler fra (sikkerhet)
            self.wheels.stop()

    def _process_command(self, data: str) -> dict:
        """Process a command and return response."""
        try:
            msg = json.loads(data)
            command = msg.get('command', '').lower()
            
            # Håndter spesialkommandoer
            if command == 'status':
                return {
                    "status": "ok",
                    **self.wheels.get_status()
                }
            
            if command == 'set_speed':
                speed = msg.get('speed', 0.5)
                self.wheels.set_speed(float(speed))
                return {
                    "status": "ok",
                    "speed": self.wheels.speed
                }
            
            if command == 'ping':
                return {
                    "status": "ok",
                    "message": "pong",
                    "timestamp": time.time()
                }
            
            # Håndter bevegelseskommandoer
            if command in self.commands:
                # Sett hastighet hvis oppgitt
                if 'speed' in msg:
                    self.wheels.set_speed(float(msg['speed']))
                
                # Utfør kommando
                self.commands[command]()
                
                self._log(f"Command: {command} (speed: {self.wheels.speed:.0%})", 'INFO')
                
                return {
                    "status": "ok",
                    "command": command,
                    "movement": self.wheels.current_movement,
                    "speed": self.wheels.speed
                }
            
            # Ukjent kommando
            self._log(f"Unknown command: {command}", 'WARNING')
            return {
                "status": "error",
                "message": f"Unknown command: {command}",
                "available": list(self.commands.keys()) + ['status', 'set_speed', 'ping']
            }
            
        except Exception as e:
            self._log(f"Command processing error: {e}", 'ERROR')
            return {
                "status": "error",
                "message": str(e)
            }

    def _heartbeat_loop(self):
        """Send periodic heartbeat to connected clients."""
        while self.running:
            time.sleep(HEARTBEAT_INTERVAL)
            
            heartbeat = json.dumps({
                "type": "heartbeat",
                "timestamp": time.time(),
                **self.wheels.get_status()
            }) + '\n'
            
            with self.lock:
                for client in self.clients[:]:  # Copy list to avoid modification during iteration
                    try:
                        client.send(heartbeat.encode('utf-8'))
                    except:
                        pass  # Client will be cleaned up in handler

    def stop(self):
        """Stop the motor service."""
        self._log("Stopping service...", 'INFO')
        self.running = False
        
        # Stopp motorene
        self.wheels.stop()
        self.wheels.cleanup()
        
        # Lukk alle klient-tilkoblinger
        with self.lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients.clear()
        
        # Lukk server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self._log("Service stopped", 'INFO')


def main():
    """Main entry point."""
    print("\n🚀 Starting RPi3 Motor Controller Service...\n")
    
    service = MotorService()
    
    try:
        service.start()
    except KeyboardInterrupt:
        print("\n")
    finally:
        service.stop()


if __name__ == "__main__":
    main()
