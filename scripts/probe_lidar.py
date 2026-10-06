"""Bounded serial-only LiDAR diagnostic; never imports or controls wheel GPIO.

Stop robotcar@lidar before using this tool, and restart it afterwards. The
LiDAR's own spinning motor is enabled by DTR. FORCE_SCAN is diagnostic only;
it does not replace a successful health check in the production reader.
Raw captures may reveal the room layout: keep them outside the public repo.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robotcar.lidar import decode_packet


DESCRIPTOR = bytes.fromhex('a55a0500004081')
COMMANDS = {'info': 0x50, 'health': 0x52, 'scan': 0x20, 'force-scan': 0x21}
PORT = '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0'


def summarize(data, command):
    result = {'bytes': len(data), 'command': command}
    if command == 'info':
        marker = bytes.fromhex('a55a1400000004')
        index = data.find(marker)
        if index >= 0 and len(data) >= index + 27:
            payload = data[index + 7:index + 27]
            result.update(model=payload[0], firmware=f'{payload[2]}.{payload[1]}', hardware=payload[3])
        return result
    if command == 'health':
        index = data.find(bytes.fromhex('a55a0300000006'))
        if index >= 0 and len(data) >= index + 10:
            payload = data[index + 7:index + 10]
            result.update(health_status=payload[0], health_error=int.from_bytes(payload[1:], 'little'))
        return result

    index = data.find(DESCRIPTOR)
    result['scan_descriptor'] = index >= 0
    if index < 0:
        return result  # Noise is never reported as an identified scan stream.
    buffer = memoryview(data)[index + len(DESCRIPTOR):]
    qualities = Counter()
    distances = []
    packets = bad = starts = usable_revolutions = revolution_points = 0
    have_start = False
    while len(buffer) >= 5:
        packet = decode_packet(buffer[:5])
        if packet is None:
            bad += 1
            buffer = buffer[1:]
            continue
        buffer = buffer[5:]
        new, quality, angle, distance = packet
        packets += 1
        qualities[quality] += 1
        if new:
            starts += 1
            if have_start and revolution_points >= 60:
                usable_revolutions += 1
            have_start, revolution_points = True, 0
        if quality and .12 <= distance <= 8:
            distances.append(distance)
            revolution_points += 1
    result.update(packets=packets, rejected_bytes=bad, revolution_starts=starts,
                  complete_revolutions_with_60_returns=usable_revolutions,
                  valid_returns=len(distances), qualities=dict(qualities),
                  distance_min_m=min(distances, default=None),
                  distance_max_m=max(distances, default=None))
    return result


def probe(args):
    import serial
    capture = bytearray()
    device = None
    output_fd = None
    try:
        if args.save_raw:
            # Refuse overwrites and make private at creation, irrespective of umask.
            output_fd = os.open(args.save_raw, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        device = serial.Serial(args.port, args.baud, timeout=.1, write_timeout=1,
                               exclusive=True, dsrdtr=False, rtscts=False)
        device.dtr = False
        device.rts = True
        time.sleep(args.settle)
        device.reset_input_buffer()
        device.write(bytes([0xa5, COMMANDS[args.command]]))
        device.flush()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            capture.extend(device.read(4096))
    finally:
        try:
            if device is not None:
                try:
                    device.write(bytes.fromhex('a525'))
                    device.flush()
                    device.dtr = True
                finally:
                    device.close()
        finally:
            if output_fd is not None:
                with os.fdopen(output_fd, 'wb') as output:
                    output.write(capture)
                    output.flush()
                    os.fsync(output.fileno())
    return summarize(capture, args.command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=PORT)
    parser.add_argument('--baud', type=int, choices=(115200, 256000, 460800), default=115200)
    parser.add_argument('--command', choices=COMMANDS, default='health')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--settle', type=float, default=2)
    parser.add_argument('--save-raw', type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60 or not 0 <= args.settle <= 10:
        parser.error('seconds must be in (0, 60] and settle in [0, 10]')

    def terminate(*_):
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        print(json.dumps(probe(args), indent=2))
    except (OSError, ValueError) as error:
        print(json.dumps({'error': str(error)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
