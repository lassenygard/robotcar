# camera_module.py

import io
import time
import threading
import cv2
import numpy as np
from flask import Flask, Response

class PiCameraModule:
    def __init__(self, resolution=(640, 480), framerate=30):
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        self.camera.set(cv2.CAP_PROP_FPS, framerate)
        self.streaming = False
        self.stream_thread = None
        import atexit
        atexit.register(self.cleanup)
        time.sleep(0.1)

    def capture_image(self, output_format="rgb", as_array=False):
        ret, frame = self.camera.read()
        if output_format == "rgb":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if as_array:
            return frame
        else:
            ret, buffer = cv2.imencode(".jpg", frame)
            return io.BytesIO(buffer)

    def start_streaming(self):
        self.streaming = True
        self.stream_thread = threading.Thread(target=self.stream)
        self.stream_thread.start()

    def stop_streaming(self):
        self.streaming = False
        if self.stream_thread is not None:
            self.stream_thread.join()

    def stream(self):
        def gen():
            while self.streaming:
                frame = self.capture_image(output_format="bgr", as_array=True)
                ret, jpeg = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        app = Flask(__name__)

        @app.route('/video_feed')
        def video_feed():
            return Response(gen(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')
        app.run(host='0.0.0.0', port=8000, threaded=True)

    def cleanup(self):
        if self.streaming:
            self.stop_streaming()
        self.camera.release()
