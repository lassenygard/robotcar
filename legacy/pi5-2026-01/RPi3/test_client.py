#!/usr/bin/env python3
"""
Test-klient for RPi3 Motor Controller Service.
Kjør dette fra en annen maskin for å teste tilkoblingen.

Bruk: python test_client.py <rpi3-ip> [port]
"""

import socket
import json
import sys
import time


def send_command(sock, command: str, **kwargs) -> dict:
    """Send a command and receive response."""
    msg = {"command": command, **kwargs}
    sock.send((json.dumps(msg) + '\n').encode('utf-8'))
    
    response = sock.recv(4096).decode('utf-8')
    return json.loads(response.strip())


def main():
    if len(sys.argv) < 2:
        print("Bruk: python test_client.py <rpi3-ip> [port]")
        print("Eksempel: python test_client.py 192.168.1.100")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5001
    
    print(f"\n🔌 Kobler til RPi3 Motor Controller på {host}:{port}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        print("✓ Tilkoblet!\n")
        
        # Test ping
        print("1. Test PING...")
        response = send_command(sock, "ping")
        print(f"   Response: {response}\n")
        
        # Test status
        print("2. Test STATUS...")
        response = send_command(sock, "status")
        print(f"   Response: {response}\n")
        
        # Test hastighet
        print("3. Test SET_SPEED (75%)...")
        response = send_command(sock, "set_speed", speed=0.75)
        print(f"   Response: {response}\n")
        
        # Test bevegelse
        print("4. Test MOVE_FORWARD (1 sekund)...")
        response = send_command(sock, "move_forward")
        print(f"   Response: {response}")
        time.sleep(1)
        
        print("5. Test STOP...")
        response = send_command(sock, "stop")
        print(f"   Response: {response}\n")
        
        # Test rotasjon
        print("6. Test ROTATE_CLOCKWISE (0.5 sekund)...")
        response = send_command(sock, "rotate_clockwise", speed=0.5)
        print(f"   Response: {response}")
        time.sleep(0.5)
        
        print("7. Test STOP...")
        response = send_command(sock, "stop")
        print(f"   Response: {response}\n")
        
        # Final status
        print("8. Final STATUS...")
        response = send_command(sock, "status")
        print(f"   Response: {response}\n")
        
        print("✅ Alle tester fullført!")
        
    except socket.timeout:
        print("✗ Timeout - kunne ikke koble til")
        sys.exit(1)
    except ConnectionRefusedError:
        print("✗ Tilkobling avvist - sjekk at motor_service.py kjører på RPi3")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Feil: {e}")
        sys.exit(1)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
