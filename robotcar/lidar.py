"""Bounded RPLIDAR A1 reader with packet resynchronisation and stale-state reporting.

Protocol: SLAMTEC LR001 v2.2. One process exclusively owns the UART. Units in
published scans are radians/metres in a right-handed body frame (x forward).
"""
import math
import os
import signal
import struct
import time
import uuid
from .common import RUN, atomic_json


def decode_packet(data):
    if len(data) != 5 or (data[0] & 1) == ((data[0] >> 1) & 1) or not data[1] & 1:
        return None
    angle = ((data[1] >> 1) | (data[2] << 7)) / 64.0
    if angle >= 360:
        return None
    return bool(data[0] & 1), data[0] >> 2, angle, ((data[3] | data[4] << 8) / 4000.0)


class RPLidar:
    def __init__(self, port, baud=115200):
        import serial
        self.serial = serial.Serial(port, baud, timeout=.1, write_timeout=.5, exclusive=True)

    def read_exact(self, size, timeout=2):
        data = bytearray()
        end = time.monotonic() + timeout
        while len(data) < size and time.monotonic() < end:
            data.extend(self.serial.read(size-len(data)))
        if len(data) != size:
            raise TimeoutError(f'RPLiDAR returned {len(data)}/{size} bytes')
        return bytes(data)

    def command(self, value):
        self.serial.write(bytes([0xA5, value]))

    def start(self):
        self.serial.dtr = False
        self.command(0x25)
        time.sleep(.15)
        self.serial.reset_input_buffer()
        self.command(0x52)
        descriptor = self.read_exact(7)
        if descriptor != b'\xa5\x5a\x03\x00\x00\x00\x06':
            raise ValueError('Invalid RPLiDAR health response')
        health = self.read_exact(3)
        if health[0] == 2:
            raise RuntimeError(f'RPLiDAR hardware error {int.from_bytes(health[1:], "little")}')
        self.command(0x20)
        if self.read_exact(7) != b'\xa5\x5a\x05\x00\x00\x40\x81':
            raise ValueError('Invalid RPLiDAR scan descriptor')

    def scans(self):
        buffer, scan = bytearray(), []
        last = time.monotonic()
        while True:
            buffer.extend(self.serial.read(max(1, min(self.serial.in_waiting, 4096))))
            if time.monotonic() - last > 2:
                raise TimeoutError('No complete LiDAR revolution for two seconds')
            while len(buffer) >= 5:
                packet = decode_packet(buffer[:5])
                if packet is None:
                    del buffer[0]
                    continue
                del buffer[:5]
                new, quality, angle, distance = packet
                if new:
                    if len(scan) >= 60:
                        last = time.monotonic()
                        yield scan
                    scan = []
                if quality and .12 <= distance <= 8:
                    scan.append((angle, distance, quality))

    def close(self):
        try:
            self.command(0x25)
            self.serial.dtr = True
        finally:
            self.serial.close()


def main():
    remote = os.environ.get('LIDAR_REMOTE_URL')
    if remote:
        import asyncio
        from .lidarfeed import collect
        asyncio.run(collect(remote))
        return
    port = os.environ.get('LIDAR_PORT', '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0')
    offset = float(os.environ.get('LIDAR_OFFSET_DEG', '-105'))
    count = 0
    source_id = uuid.uuid4().hex
    def terminate(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    while True:
        device = None
        try:
            device = RPLidar(port, int(os.environ.get('LIDAR_BAUD', '115200')))
            device.start()
            previous = time.monotonic()
            for scan in device.scans():
                now = time.monotonic()
                count += 1
                points = [[round(math.atan2(math.sin(-math.radians(a+offset)), math.cos(-math.radians(a+offset))), 5),
                           round(d, 4), q] for a, d, q in scan]
                atomic_json(RUN / 'lidar.json', dict(seq=count, source_id=source_id, monotonic=now, time=time.time(),
                    hz=round(1/max(.001, now-previous), 2), points=points, error=None))
                previous = now
        except Exception as exc:
            atomic_json(RUN / 'lidar.json', dict(seq=count, source_id=source_id, monotonic=time.monotonic(), time=time.time(),
                hz=0, points=[], error=str(exc)))
        finally:
            if device:
                device.close()
        time.sleep(3)


if __name__ == '__main__':
    main()
