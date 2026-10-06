"""Hailo inference worker. A native driver crash cannot stop motor or video services."""
import os
import time
import cv2
import numpy as np
from .common import RUN, atomic_json


def main():
    from picamera2.devices import Hailo
    cv2.setNumThreads(1)
    model = os.environ.get('HAILO_MODEL', '/home/pi/robotcarClaude/yolov5m_wo_spp_60p.hef')
    labels = (os.environ.get('HAILO_LABELS', '/home/pi/robotcarClaude/coco.txt'))
    with open(labels) as stream:
        names = stream.read().splitlines()
    detector = Hailo(model)
    height, width, _ = detector.get_input_shape()
    previous = None
    while True:
        start = time.monotonic()
        try:
            path = RUN / 'front.jpg'
            stamp = path.stat().st_mtime_ns
            if stamp == previous or time.time() - path.stat().st_mtime > 1:
                time.sleep(.03)
                continue
            previous = stamp
            frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            rgb = cv2.cvtColor(cv2.resize(frame, (width, height)), cv2.COLOR_BGR2RGB)
            result = detector.run(rgb)
            if isinstance(result, dict):
                result = next(iter(result.values()))
            objects = []
            for class_id, detections in enumerate(result):
                for detection in detections:
                    y1, x1, y2, x2, score = [float(v) for v in detection[:5]]
                    if score >= .40:
                        objects.append(dict(label=names[class_id], confidence=round(score, 3),
                                            box=[x1, y1, x2, y2]))
            atomic_json(RUN / 'vision.json', dict(time=time.time(), monotonic=time.monotonic(),
                frame_stamp=stamp, objects=objects, inference_ms=round((time.monotonic()-start)*1000, 1),
                error=None, model=os.path.basename(model)))
        except Exception as exc:
            atomic_json(RUN / 'vision.json', dict(time=time.time(), monotonic=time.monotonic(),
                objects=[], error=str(exc)))
            time.sleep(1)
        time.sleep(max(0, .125 - (time.monotonic()-start)))


if __name__ == '__main__':
    main()
