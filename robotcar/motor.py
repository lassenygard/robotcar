"""Pi 4 motor service. No camera, mapping, or Internet work runs here.

Only this process owns the GPIO pins. A separate watchdog thread expires leases
and enforces a continuous-motion limit that repeated commands cannot extend.
"""
import hmac
import json
import math
import os
import signal
import socket
import socketserver
import threading
import time

from .common import secret

# BCM numbering recovered from the installed motor_controller/config.py.
PINS = {'front_left': (24, 27, 5), 'front_right': (6, 22, 17),
        'rear_left': (23, 16, 12), 'rear_right': (18, 13, 25)}


class GPIOWheels:
    def __init__(self):
        from gpiozero import Motor
        self.motors = {}
        self.signs = json.loads(os.environ.get('MOTOR_SIGNS', '{}'))
        self.swap_sides = os.environ.get('MOTOR_SWAP_SIDES') == '1'
        try:
            for name, pins in PINS.items():
                self.motors[name] = Motor(*pins[:2], enable=pins[2])
            self.apply(0, 0)
        except Exception:
            self.close()
            raise  # Never silently simulate physical hardware.

    def apply(self, left, right):
        if self.swap_sides:
            left, right = right, left
        for name, motor in self.motors.items():
            speed = (left if name.endswith('left') else right) * self.signs.get(name, 1)
            if speed > 0:
                motor.forward(speed)
            elif speed < 0:
                motor.backward(-speed)
            else:
                motor.stop()

    def close(self):
        self.apply(0, 0)
        for motor in self.motors.values():
            motor.close()


class MotorGuard:
    def __init__(self, wheels, clock=time.monotonic, max_run=2.5, max_speed=.35,
                 autonomy=False, cooldown=1.0):
        self.wheels, self.clock = wheels, clock
        self.max_run = min(float(max_run), 2.5)
        self.max_speed = min(float(max_speed), .5)
        self.autonomy, self.cooldown = autonomy, cooldown
        self.lock = threading.RLock()
        self.left = self.right = 0.0
        self.started = None
        self.deadline = 0.0
        self.stopped_at = -100.0
        self.owner = None
        self.armed = False
        self.reason = 'startup_disarmed'
        self.last_seq = -1
        self.wheels.apply(0, 0)

    def stop(self, reason='stopped', disarm=True):
        with self.lock:
            self.wheels.apply(0, 0)
            if self.left or self.right:
                self.stopped_at = self.clock()
            self.left = self.right = 0.0
            self.started = None
            self.reason = reason
            if disarm:
                self.armed = False
                self.owner = None

    def tick(self):
        with self.lock:
            now = self.clock()
            if self.started is not None:
                if now - self.started >= self.max_run:
                    self.stop('continuous_limit')
                elif now >= self.deadline:
                    self.stop('lease_expired')

    def handle(self, message, owner):
        with self.lock:
            self.tick()
            action = message.get('action')
            if action == 'stop':
                self.stop('operator_stop')
            elif action == 'arm':
                if self.owner not in (None, owner):
                    raise ValueError('another operator owns the motors')
                if self.clock() - self.stopped_at < self.cooldown:
                    raise ValueError('cooldown: wheels must remain stopped for one second')
                if self.started is not None:
                    raise ValueError('stop before rearming')
                self.armed, self.owner, self.last_seq = True, owner, -1
                self.reason = 'armed'
            elif action == 'drive':
                if not self.armed or self.owner != owner:
                    raise ValueError('motors are disarmed; explicitly rearm after stopping')
                if message.get('mode', 'manual') != 'manual' and not self.autonomy:
                    raise ValueError('autonomy is disabled until supervised commissioning')
                left, right = float(message['left']), float(message['right'])
                ttl = float(message.get('ttl', .3))
                seq = message.get('seq')
                if not all(math.isfinite(x) for x in [left, right, ttl]):
                    raise ValueError('non-finite motion')
                if type(seq) is not int or seq <= self.last_seq:
                    raise ValueError('old or invalid command sequence')
                if not 0 < ttl <= .4 or max(abs(left), abs(right)) > self.max_speed:
                    raise ValueError('speed or lease exceeds commissioning limit')
                self.last_seq = seq
                if left == right == 0:
                    self.stop('zero_command')
                else:
                    if self.started is None:
                        self.started = self.clock()
                    self.deadline = self.clock() + ttl
                    self.wheels.apply(left, right)
                    self.left, self.right, self.reason = left, right, 'driving'
            elif action != 'status':
                raise ValueError('unknown motor action')
            return self.status()

    def status(self):
        with self.lock:
            return dict(armed=self.armed, left=self.left, right=self.right,
                        reason=self.reason, max_run_s=self.max_run,
                        max_speed=self.max_speed, autonomy_enabled=self.autonomy,
                        remaining_s=max(0, self.max_run - (self.clock() - self.started))
                        if self.started is not None else self.max_run)


class MotorServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    token = secret()
    wheels = GPIOWheels()
    guard = MotorGuard(wheels, autonomy=os.environ.get('AUTONOMY_ENABLED') == '1')
    closed = threading.Event()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            owner = object()
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.request.settimeout(2)
            try:
                while not closed.is_set():
                    line = self.rfile.readline(2049)
                    if not line or len(line) > 2048:
                        break
                    try:
                        msg = json.loads(line)
                        if not isinstance(msg, dict) or not hmac.compare_digest(str(msg.get('token', '')), token):
                            break
                        reply = {'ok': True, **guard.handle(msg, owner)}
                    except (ValueError, KeyError, TypeError) as exc:
                        if guard.owner == owner:
                            guard.stop('invalid_command')
                        reply = {'ok': False, 'error': str(exc), **guard.status()}
                    self.wfile.write((json.dumps(reply) + '\n').encode())
            except (OSError, TimeoutError):
                pass
            finally:
                if guard.owner == owner:
                    guard.stop('connection_lost')

    def watchdog():
        while not closed.wait(.01):
            guard.tick()

    threading.Thread(target=watchdog, daemon=True).start()
    def shutdown(*_):
        guard.stop('service_shutdown')
        closed.set()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        with MotorServer((os.environ.get('MOTOR_BIND', '0.0.0.0'), 5001), Handler) as server:
            print('Motor GPIO ready; disarmed; continuous limit 2.5s', flush=True)
            server.serve_forever(poll_interval=.1)
    finally:
        guard.stop('service_shutdown')
        closed.set()
        wheels.close()


if __name__ == '__main__':
    main()
