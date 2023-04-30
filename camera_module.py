#camera_module.py

import io
import time
import threading
from picamera import PiCamera
from picamera.array import PiRGBArray
from flask import Flask, Response

class PiCameraModule:
    def __init__(self, resolution=(640, 480), framerate=30):
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.framerate = framerate
        self.raw_capture = PiRGBArray(self.camera, size=resolution)
        self.streaming = False
        self.stream_thread = None
        time.sleep(0.1)

    def capture_image(self, output_format="rgb", as_array=False):
        self.raw_capture.truncate(0)
        self.camera.capture(self.raw_capture, format=output_format, use_video_port=True)
        if as_array:
            return self.raw_capture.array
        else:
            return self.raw_capture.getvalue()

    def start_streaming(self):
        self.streaming = True
        self.stream_thread = threading.Thread(target=self.stream)
        self.stream_thread.start()

    def stop_streaming(self):
        self.streaming = False
        self.stream_thread.join()

    def stream(self):
        def gen():
            while self.streaming:
                frame = self.capture_image(output_format="jpeg", as_array=True)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame.tobytes() + b'\r\n')
        app = Flask(__name__)

        @app.route('/video_feed')
        def video_feed():
            return Response(gen(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')
        app.run(host='0.0.0.0', port=8000, threaded=True)

    def cleanup(self):
        if self.streaming:
            self.stop_streaming()
        self.camera.close()
