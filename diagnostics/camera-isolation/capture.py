"""One camera per process; no robot modules, AI, web server or motor access."""
import argparse
import json
import os
from pathlib import Path
import socket
import time

SENSORS = {'front': ('imx219', (1640, 1232)), 'rear': ('imx708', (2304, 1296))}


def notify(message):
    address = os.environ.get('NOTIFY_SOCKET')
    if address:
        if address.startswith('@'):
            address = '\0' + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), address)


def write_status(path, value):
    temporary = path.with_suffix('.next')
    temporary.write_text(json.dumps(value, allow_nan=False) + '\n')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('camera', choices=SENSORS)
    name = parser.parse_args().camera
    run = Path('/run/robotcar-camera-test')
    saved = Path('/var/lib/robotcar-camera-test')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    model, size = SENSORS[name]
    state = dict(camera=name, model=model, boot_id=boot, frames=0, first_frame=None,
                 last_frame=None, longest_gap_s=0., fps=0., duration_s=0., error=None,
                 test='minimal capture, fixed 20 fps, no JPEG/AI/network')
    path = run / (name + '.json')
    write_status(path, state)
    camera = None
    try:
        from picamera2 import Picamera2
        found = [c for c in Picamera2.global_camera_info() if c['Model'].startswith(model)]
        if len(found) != 1:
            raise RuntimeError(f'Expected one {model}; detected {len(found)}')
        camera = Picamera2(found[0]['Num'])
        camera.configure(camera.create_video_configuration(
            main={'size': (640, 480), 'format': 'RGB888'},
            sensor={'output_size': size, 'bit_depth': 10},
            controls={'FrameRate': 20}, buffer_count=3, queue=False))
        camera.start()
        published = logged = window_start = time.monotonic()
        window_count = 0
        qualified = False
        while True:
            frame = camera.capture_array()
            now = time.monotonic()
            if frame.shape != (480, 640, 3):
                raise ValueError(f'Unexpected image shape: {frame.shape}')
            if state['last_frame'] is not None:
                state['longest_gap_s'] = max(state['longest_gap_s'], now-state['last_frame'])
            else:
                state['first_frame'] = now
                notify('READY=1')
            state['frames'] += 1
            state['last_frame'] = now
            state['duration_s'] = now-state['first_frame']
            window_count += 1
            if now-published >= 1:
                state['fps'] = round(window_count/(now-window_start), 2)
                write_status(path, state)
                notify('WATCHDOG=1')
                window_count = 0
                published = window_start = now
            if now-logged >= 30:
                print(json.dumps(state), flush=True)
                logged = now
            if not qualified and state['duration_s'] >= 600:
                state['ten_minute_observation'] = True
                write_status(saved / (boot+'-'+name+'.json'), state)
                print('TEN_MINUTE_OBSERVATION ' + json.dumps(state), flush=True)
                qualified = True
    except BaseException as exc:
        state['error'] = f'{type(exc).__name__}: {exc}'
        write_status(path, state)
        write_status(saved / (boot+'-'+name+'-failed.json'), state)
        print(json.dumps(state), flush=True)
        raise
    finally:
        if camera is not None:
            camera.close()


if __name__ == '__main__':
    main()
