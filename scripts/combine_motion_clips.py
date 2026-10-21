"""Compile verified motion clips at normal speed, shortening only the pauses.

The source MP4s, ready markers and motion logs must share each basename.
This edits private video files only; it never connects to or moves the robot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def combine(clips, output):
    os.umask(0o077)
    output = output.resolve()
    report = output.with_suffix('.json')
    if output.suffix != '.mp4' or output.exists() or report.exists():
        raise ValueError('Choose a new MP4 filename.')
    output.parent.mkdir(parents=True, exist_ok=True)
    segments = []
    with tempfile.TemporaryDirectory(prefix='robotcar-compilation-') as temporary:
        folder = Path(temporary)
        for index, clip in enumerate(clips):
            clip = clip.resolve()
            ready = json.loads(clip.with_suffix('.ready.json').read_text())
            motion = json.loads(clip.with_suffix('.motion.json').read_text())
            events = motion['events']
            drive = next(e for e in events if e['event'] == 'send' and e.get('action') == 'drive')
            stopped = next(e for e in events if e['event'] == 'stopped')
            motor = stopped['motor']
            if motor['armed'] or motor['left'] or motor['right']:
                raise ValueError('The source must have a confirmed motor stop.')
            start = max(0, drive['monotonic']-ready['received_monotonic']-.5)
            end = stopped['monotonic']-ready['received_monotonic']+1
            duration = float(subprocess.check_output(['ffprobe', '-v', 'error',
                '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(clip)]))
            if not start < end <= duration:
                raise ValueError('The requested motion interval is not fully recorded.')
            name = f'{index:03d}.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n',
                '-ss', str(start), '-i', str(clip), '-t', str(end-start), '-an',
                '-fps_mode', 'vfr', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                '-pix_fmt', 'yuv420p', str(folder/name)], check=True, timeout=60)
            segments.append(dict(source=str(clip), source_sha256=hashlib.sha256(clip.read_bytes()).hexdigest(),
                                 start_s=start, end_s=end, direction=motion['direction'], file=name))
        (folder/'clips.txt').write_text(''.join(f"file '{s['file']}'\n" for s in segments))
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-f', 'concat',
            '-safe', '1', '-i', str(folder/'clips.txt'), '-vf', 'fps=25',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-metadata', 'title=Trinnvis rotasjon – kjøring i sanntid, forkortede pauser',
            '-metadata', 'comment=Edited compilation; pauses between recorded steps shortened. Motion plays at normal speed.',
            str(output)], check=True, timeout=60)
    report.write_text(json.dumps(dict(edited_compilation_not_continuous_capture=True,
        playback_speed=1, output_fps=25, segments=segments), indent=2)+'\n')
    print(json.dumps(dict(output=str(output), segments=len(segments), report=str(report))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clips', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    combine(args.clips, args.output)
