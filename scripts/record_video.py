"""Record an authenticated Robotcar camera to a private MP4, without moving it.

Frame durations follow reception times, so a slow stream is not sped up.
The JSON sidecar preserves source sequence numbers and reception intervals.
Requires ffmpeg; all other dependencies are in the Python standard library.
"""
import argparse
import http.cookiejar
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request


def record(args):
    if urllib.parse.urlsplit(args.url).scheme != 'https':
        raise ValueError('Use HTTPS when sending login credentials.')
    output = args.output.resolve()
    report = output.with_suffix('.json')
    if output.suffix != '.mp4' or output.exists() or report.exists():
        raise ValueError('Choose a new .mp4 filename; existing recordings are never overwritten.')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 120:
        raise ValueError('Recording duration must be between 0 and 120 seconds.')
    os.umask(0o077)
    output.parent.mkdir(parents=True, exist_ok=True)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    config = dict(line.split('=', 1) for line in args.credentials.read_text().splitlines() if '=' in line)
    login = urllib.parse.urlencode({key: config[key] for key in ('username', 'password')}).encode()
    with opener.open(args.url.rstrip('/') + '/login', data=login, timeout=5) as response:
        if response.status != 200 or not any(c.name == 'robotcar_session' for c in jar):
            raise ValueError('Login failed.')
    frames = []
    started_utc = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with tempfile.TemporaryDirectory(prefix='robotcar-video-') as temporary:
        folder = Path(temporary)
        with opener.open(args.url.rstrip('/') + '/video/' + args.camera, timeout=3) as stream:
            if stream.headers.get_content_type() != 'multipart/x-mixed-replace':
                raise ValueError('Camera did not return a video stream.')
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                # Locate the next boundary, allowing the CRLF after each JPEG.
                for _ in range(4):
                    line = stream.readline(2048)
                    if line.strip() == b'--frame':
                        break
                    if not line or line.strip():
                        raise ValueError('Invalid or ended video stream.')
                else:
                    raise ValueError('Missing frame boundary.')
                headers = {}
                for _ in range(16):
                    line = stream.readline(2048)
                    if line == b'\r\n':
                        break
                    key, value = line.decode('ascii').split(':', 1)
                    headers[key.lower()] = value.strip()
                else:
                    raise ValueError('Too many frame headers.')
                length = int(headers['content-length'])
                seq = int(headers['x-frame-sequence'])
                stamp = float(headers['x-frame-monotonic'])
                if not 4 <= length <= 2_000_000 or not math.isfinite(stamp) or seq < 1:
                    raise ValueError('Invalid frame metadata.')
                if frames and (seq <= frames[-1]['sequence'] or stamp <= frames[-1]['source_monotonic']):
                    raise ValueError('Repeated or out-of-order camera frame.')
                jpeg = stream.read(length)
                if len(jpeg) != length or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                    raise ValueError('Incomplete camera frame.')
                received = time.monotonic()
                name = f'frame-{len(frames):06d}.jpg'
                (folder / name).write_bytes(jpeg)
                frames.append(dict(file=name, sequence=seq, source_monotonic=stamp, received=received))
                if len(frames) == 1 and args.ready_file:
                    with args.ready_file.open('x') as ready:
                        json.dump(dict(camera=args.camera, received_monotonic=received,
                                       sequence=seq), ready)
        if len(frames) < 2:
            raise ValueError('Not enough frames to make a recording.')
        intervals = [b['received']-a['received'] for a, b in zip(frames, frames[1:])]
        lines = []
        for frame, duration in zip(frames, intervals + [intervals[-1]]):
            lines.extend([f"file '{frame['file']}'", f'duration {duration:.6f}'])
        lines.append(f"file '{frames[-1]['file']}'")
        (folder / 'frames.txt').write_text('\n'.join(lines) + '\n')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-f', 'concat',
                        '-safe', '1', '-i', 'frames.txt', '-fps_mode', 'vfr', '-c:v', 'libx264',
                        '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', '-metadata', 'title=' + args.label, str(output)],
                       cwd=folder, check=True, timeout=90)
    first = frames[0]['received']
    summary = dict(label=args.label, camera=args.camera, started_utc=started_utc,
                   frames=len(frames), reception_span_s=frames[-1]['received']-first,
                   longest_frame_gap_s=max(intervals), recorder_controls_motors=False,
                   timing='Frame durations follow reception times; no slow motion or speed-up.',
                   samples=[dict(sequence=f['sequence'], source_monotonic=f['source_monotonic'],
                                 received_s=round(f['received']-first, 6)) for f in frames])
    report.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: value for key, value in summary.items() if key != 'samples'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://robotcar.nygardene.no')
    parser.add_argument('--credentials', type=Path, default=Path.home()/'.ssh/robotcar-web-login.conf')
    parser.add_argument('--camera', choices=('front', 'rear'), default='front')
    parser.add_argument('--seconds', type=float, default=8)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ready-file', type=Path, help='Create this private marker after the first valid frame.')
    record(parser.parse_args())
