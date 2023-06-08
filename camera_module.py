import io
import time
import threading
from picamera2 import Picamera2
from libcamera import controls, Transform
from flask import Flask, Response

class PiCameraModule:
    def __init__(self, resolution=(800, 600), framerate=30, transform=Transform(hflip=1)):
        self.camera = Picamera2()
        self.camera.start(show_preview=True)
 #       self.camera.set_controls({"AfMode": controls.AfModeEnum.Continuous})
 #       self.camera.set_controls({"transform": Transform(hflip=1, vflip=1)})
        self.streaming = False
        self.stream_thread = None
        import atexit
        atexit.register(self.cleanup)
        time.sleep(0.1)

    def capture_image(self, output_format="jpeg", as_array=False):
        # This part may require changes as it's not clear how picamera2 handles image capture
         return self.camera.capture_array("main")
        
    def start_streaming(self):
        if self.stream_thread is None or not self.stream_thread.is_alive():
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
                frame = self.capture_image()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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
