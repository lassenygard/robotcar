"""
Flask web server for robot control interface - RPi5 (Master)
Handles video feed (dual cameras), LIDAR streaming, and autonomous navigation.
Motor commands are sent to RPi3 over the network.
"""

from flask import Flask, Response, render_template
from flask_socketio import SocketIO, emit
import threading
import cv2
import time
import math
import numpy as np

# Import vision module
try:
    from src.visionmapping.vision_combined import start_detection, ObjectDetector
    VISION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Vision module not available - {e}")
    VISION_AVAILABLE = False
    
    class ObjectDetector:
        def __init__(self):
            self.detected_objects = set()

# Try to import LIDAR
try:
    from src.visionmapping.lidar_mapping import LidarScanner, GridMap
    LIDAR_AVAILABLE = True
except ImportError:
    LIDAR_AVAILABLE = False
    print("Warning: LIDAR module not available")

# Try to import config
try:
    from config import (
        WEB_HOST, WEB_PORT, 
        DEFAULT_SAFE_DISTANCE, DEFAULT_LIDAR_OFFSET,
        CAMERA_FRONT, CAMERA_REAR, CAMERA_RESOLUTION
    )
except ImportError:
    WEB_HOST = '0.0.0.0'
    WEB_PORT = 5000
    DEFAULT_SAFE_DISTANCE = 500
    DEFAULT_LIDAR_OFFSET = -105
    CAMERA_FRONT = 0
    CAMERA_REAR = 1
    CAMERA_RESOLUTION = (640, 480)


class DualCameraManager:
    """Manages front and rear cameras."""
    
    def __init__(self):
        self.front_camera = None
        self.rear_camera = None
        self.active_camera = 'front'
        self.frame_lock = threading.Lock()
        self.current_frame = None
        self._running = False
        self._capture_thread = None
        
        # Try to initialize cameras
        self._init_cameras()
        
    def _init_cameras(self):
        """Initialize cameras."""
        try:
            # Try PiCamera2 first (for Raspberry Pi)
            from picamera2 import Picamera2
            
            self.front_camera = Picamera2(camera_num=CAMERA_FRONT)
            self.front_camera.configure(
                self.front_camera.create_preview_configuration(
                    main={"format": "RGB888", "size": CAMERA_RESOLUTION}
                )
            )
            print(f"✓ Front camera initialized (PiCamera {CAMERA_FRONT})")
            
            try:
                self.rear_camera = Picamera2(camera_num=CAMERA_REAR)
                self.rear_camera.configure(
                    self.rear_camera.create_preview_configuration(
                        main={"format": "RGB888", "size": CAMERA_RESOLUTION}
                    )
                )
                print(f"✓ Rear camera initialized (PiCamera {CAMERA_REAR})")
            except Exception as e:
                print(f"⚠ Rear camera not available: {e}")
                
        except ImportError:
            # Fallback to OpenCV (USB cameras or simulation)
            print("PiCamera2 not available, trying OpenCV...")
            
            self.front_camera = cv2.VideoCapture(CAMERA_FRONT)
            if self.front_camera.isOpened():
                self.front_camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
                self.front_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
                print(f"✓ Front camera initialized (OpenCV {CAMERA_FRONT})")
            else:
                self.front_camera = None
                print("⚠ Front camera not available")
                
            self.rear_camera = cv2.VideoCapture(CAMERA_REAR)
            if self.rear_camera.isOpened():
                self.rear_camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
                self.rear_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
                print(f"✓ Rear camera initialized (OpenCV {CAMERA_REAR})")
            else:
                self.rear_camera = None
                print("⚠ Rear camera not available")
        except Exception as e:
            print(f"⚠ Camera initialization failed: {e}")
    
    def start(self):
        """Start camera capture."""
        self._running = True
        
        # Start PiCamera if available
        if self.front_camera and hasattr(self.front_camera, 'start'):
            try:
                self.front_camera.start()
                print("✓ Front camera started")
            except Exception as e:
                print(f"✗ Front camera start failed: {e}")
                self.front_camera = None
                
        if self.rear_camera and hasattr(self.rear_camera, 'start'):
            try:
                self.rear_camera.start()
                print("✓ Rear camera started")
            except Exception as e:
                print(f"✗ Rear camera start failed: {e}")
                self.rear_camera = None
            
        # Give cameras time to warm up
        time.sleep(1)
        
        # Test capture
        if self.front_camera:
            try:
                test_frame = self.front_camera.capture_array()
                print(f"✓ Front camera test capture OK: {test_frame.shape}")
                # Store initial frame
                with self.frame_lock:
                    self.current_frame = test_frame
            except Exception as e:
                print(f"✗ Front camera test capture failed: {e}")
        
        # Start background capture thread for AI detection
        self._capture_thread = threading.Thread(target=self._background_capture, daemon=True)
        self._capture_thread.start()
        print("✓ Background capture started")
    
    def _background_capture(self):
        """Continuously capture frames in background for AI detection."""
        while self._running:
            try:
                frame = self.get_frame()
                if frame is not None:
                    with self.frame_lock:
                        self.current_frame = frame
                time.sleep(0.05)  # ~20 fps background capture
            except Exception as e:
                print(f"Background capture error: {e}")
                time.sleep(0.5)
            
    def stop(self):
        """Stop camera capture."""
        self._running = False
        
        if self.front_camera:
            if hasattr(self.front_camera, 'stop'):
                self.front_camera.stop()
            elif hasattr(self.front_camera, 'release'):
                self.front_camera.release()
                
        if self.rear_camera:
            if hasattr(self.rear_camera, 'stop'):
                self.rear_camera.stop()
            elif hasattr(self.rear_camera, 'release'):
                self.rear_camera.release()
                
    def switch_camera(self, camera: str):
        """Switch between front and rear camera."""
        if camera in ['front', 'rear']:
            self.active_camera = camera
            return True
        return False
        
    def get_frame(self):
        """Get current frame from active camera."""
        camera = self.front_camera if self.active_camera == 'front' else self.rear_camera
        
        if camera is None:
            return self._generate_placeholder()
            
        try:
            if hasattr(camera, 'capture_array'):
                # PiCamera2
                frame = camera.capture_array()
                if frame is not None and frame.size > 0:
                    return frame
            else:
                # OpenCV
                ret, frame = camera.read()
                if ret and frame is not None:
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception as e:
            print(f"Camera capture error ({self.active_camera}): {e}")
            
        return self._generate_placeholder()
        
    def _generate_placeholder(self):
        """Generate placeholder frame when no camera is available."""
        frame = np.zeros((CAMERA_RESOLUTION[1], CAMERA_RESOLUTION[0], 3), dtype=np.uint8)
        text = f"No {self.active_camera.upper()} Camera"
        cv2.putText(frame, text, (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
        return frame


class AutonomousNavigator:
    """Handles autonomous navigation logic."""
    
    STATES = ['IDLE', 'FIND_WALL', 'FOLLOW_WALL', 'HANDLE_OBSTACLE', 'EXPLORING', 'MAPPING']
    
    def __init__(self, motor_controller, lidar_scanner=None):
        self.motor = motor_controller
        self.lidar = lidar_scanner
        self.state = 'IDLE'
        self.mode = None
        self.safe_distance = DEFAULT_SAFE_DISTANCE
        self.lidar_offset = DEFAULT_LIDAR_OFFSET
        self.obstacle_count = 0
        self.distance_traveled = 0.0
        self.position = {'x': 0, 'y': 0, 'theta': 0}
        self._running = False
        self._thread = None
        self._last_position_time = time.time()
        
    def set_params(self, safe_distance=None, lidar_offset=None):
        if safe_distance is not None:
            self.safe_distance = safe_distance
        if lidar_offset is not None:
            self.lidar_offset = lidar_offset
            
    def adjust_angle(self, angle):
        return (angle + self.lidar_offset) % 360
    
    def check_obstacles(self, scan_data, angle_range=(-30, 30)):
        obstacles = []
        for angle, distance in scan_data:
            adjusted = self.adjust_angle(angle)
            if adjusted > 180:
                adjusted -= 360
            if angle_range[0] <= adjusted <= angle_range[1] and distance < self.safe_distance:
                obstacles.append((adjusted, distance))
        return obstacles
    
    def get_scan_data(self):
        if self.lidar:
            raw_data = self.lidar.get_scan_data()
            return [(angle, distance) for (_, angle, distance) in raw_data]
        return []
    
    def start(self, mode):
        if self._running:
            self.stop()
            
        self.mode = mode
        self._running = True
        self.state = 'FIND_WALL' if mode == 'wall_follow' else 'EXPLORING'
        self._thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        self._running = False
        self.state = 'IDLE'
        self.mode = None
        self.motor.execute_command('stop')
        if self._thread:
            self._thread.join(timeout=1.0)
            
    def _navigation_loop(self):
        while self._running:
            try:
                scan_data = self.get_scan_data()
                
                if self.mode == 'explore':
                    self._explore_step(scan_data)
                elif self.mode == 'wall_follow':
                    self._wall_follow_step(scan_data)
                elif self.mode == 'map_room':
                    self._map_room_step(scan_data)
                    
                self._update_position()
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Navigation error: {e}")
                self.motor.execute_command('stop')
                time.sleep(0.5)
                
    def _explore_step(self, scan_data):
        obstacles = self.check_obstacles(scan_data)
        
        if obstacles:
            self.state = 'HANDLE_OBSTACLE'
            self.obstacle_count += 1
            self.motor.execute_command('stop')
            time.sleep(0.2)
            
            left_clear = not self.check_obstacles(scan_data, (-90, -30))
            right_clear = not self.check_obstacles(scan_data, (30, 90))
            
            if left_clear:
                self.motor.execute_command('rotate_counterclockwise')
                time.sleep(0.5)
            elif right_clear:
                self.motor.execute_command('rotate_clockwise')
                time.sleep(0.5)
            else:
                self.motor.execute_command('move_backward')
                time.sleep(0.5)
                self.motor.execute_command('rotate_clockwise')
                time.sleep(1.0)
                
            self.motor.execute_command('stop')
        else:
            self.state = 'EXPLORING'
            self.motor.execute_command('move_forward')
            
    def _wall_follow_step(self, scan_data):
        front_obstacles = self.check_obstacles(scan_data, (-30, 30))
        right_obstacles = self.check_obstacles(scan_data, (60, 120))
        
        if self.state == 'FIND_WALL':
            if front_obstacles:
                self.state = 'FOLLOW_WALL'
                self.motor.execute_command('stop')
                self.motor.execute_command('rotate_counterclockwise')
                time.sleep(0.5)
                self.motor.execute_command('stop')
            else:
                self.motor.execute_command('move_forward')
                
        elif self.state == 'FOLLOW_WALL':
            if front_obstacles:
                self.obstacle_count += 1
                self.motor.execute_command('stop')
                self.motor.execute_command('rotate_counterclockwise')
                time.sleep(0.4)
                self.motor.execute_command('stop')
            elif not right_obstacles:
                self.motor.execute_command('rotate_clockwise')
                time.sleep(0.3)
                self.motor.execute_command('move_forward')
                time.sleep(0.3)
            else:
                self.motor.execute_command('move_forward')
                
    def _map_room_step(self, scan_data):
        self._wall_follow_step(scan_data)
        self.state = 'MAPPING'
        
    def _update_position(self):
        now = time.time()
        dt = now - self._last_position_time
        self._last_position_time = now
        
        movement = self.motor.wheels.current_movement
        
        if movement == 'forward':
            speed = 0.2
            self.position['x'] += math.cos(self.position['theta']) * speed * dt
            self.position['y'] += math.sin(self.position['theta']) * speed * dt
            self.distance_traveled += speed * dt
        elif movement == 'rotate_cw':
            self.position['theta'] -= 0.5 * dt
        elif movement == 'rotate_ccw':
            self.position['theta'] += 0.5 * dt
            
    def get_status(self):
        return {
            'state': self.state,
            'mode': self.mode,
            'obstacles': self.obstacle_count,
            'distance': self.distance_traveled,
            'position': self.position
        }


class WebServer:
    def __init__(self, robot_controller):
        self.robot_controller = robot_controller
        self.app = Flask(__name__, template_folder="templates", static_folder="static")
        self.app.config['SECRET_KEY'] = 'LEGACY_NOT_FOR_DEPLOYMENT'
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        # Camera manager
        self.camera_manager = DualCameraManager()
        
        # Frame for AI detection
        self.frame_lock = threading.Lock()
        self.global_frame = [None]
        
        # Initialize LIDAR if available
        self.lidar_scanner = None
        self.grid_map = None
        if LIDAR_AVAILABLE:
            try:
                self.lidar_scanner = LidarScanner()
                self.grid_map = GridMap(grid_size=100, resolution=0.05)
                print("✓ LIDAR initialized")
            except Exception as e:
                print(f"⚠ Failed to initialize LIDAR: {e}")
                
        # Initialize navigator
        self.navigator = AutonomousNavigator(
            robot_controller.motor_controller,
            self.lidar_scanner
        )
        
        self.is_auto_mode = False
        self._running = False
        
        self._setup_routes()
        self._setup_socketio_events()

    def _setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template('index.html')

        @self.app.route('/video_feed')
        def stream_video_feed():
            return Response(
                self._video_feed_generator(),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
            
        @self.app.route('/video_feed/<camera>')
        def stream_camera_feed(camera):
            return Response(
                self._video_feed_generator(camera),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )

    def _setup_socketio_events(self):
        @self.socketio.on('connect')
        def handle_connect():
            print("Client connected")
            
            # Send initial state
            motor_status = self.robot_controller.motor_controller.get_status()
            emit('motor_status', motor_status)
            emit('log', {'message': 'Connected to robot', 'type': 'success'})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            print("Client disconnected")

        @self.socketio.on('get_objects')
        def handle_get_objects():
            detected_objects = list(self.robot_controller.object_detector.detected_objects)
            emit('objects', detected_objects)

        @self.socketio.on('get_state')
        def handle_get_state():
            emit('mode', 'auto' if self.is_auto_mode else 'manual')
            emit('nav_status', self.navigator.get_status())
            emit('position', self.navigator.position)
            emit('motor_status', self.robot_controller.motor_controller.get_status())

        @self.socketio.on('command')
        def handle_command(data):
            if isinstance(data, dict):
                command = data.get('command', 'stop')
                speed = data.get('speed', 0.5)
            else:
                command = data
                speed = 0.5
                
            if not self.is_auto_mode or command == 'stop':
                success = self.robot_controller.motor_controller.execute_command(command, speed)
                
                if success:
                    emit('log', {'message': f'Executed: {command}', 'type': 'info'})
                else:
                    emit('log', {'message': f'Failed: {command}', 'type': 'error'})

        @self.socketio.on('mode')
        def handle_mode(mode):
            self.is_auto_mode = (mode == 'auto')
            
            if not self.is_auto_mode:
                self.navigator.stop()
            
            self.socketio.emit('mode', mode)
            emit('log', {'message': f'Mode: {mode.upper()}', 'type': 'success'})

        @self.socketio.on('set_speed')
        def handle_set_speed(speed):
            self.robot_controller.motor_controller.wheels.set_speed(speed)
            
        @self.socketio.on('switch_camera')
        def handle_switch_camera(camera):
            if self.camera_manager.switch_camera(camera):
                emit('log', {'message': f'Switched to {camera} camera', 'type': 'info'})
            else:
                emit('log', {'message': f'Invalid camera: {camera}', 'type': 'error'})
            
        @self.socketio.on('nav_mode')
        def handle_nav_mode(data):
            mode = data.get('mode')
            safe_distance = data.get('safe_distance', DEFAULT_SAFE_DISTANCE)
            lidar_offset = data.get('lidar_offset', DEFAULT_LIDAR_OFFSET)
            
            self.navigator.set_params(safe_distance, lidar_offset)
            
            if self.is_auto_mode and mode:
                self.navigator.start(mode)
                emit('log', {'message': f'Navigation started: {mode}', 'type': 'success'})
            
        @self.socketio.on('set_params')
        def handle_set_params(data):
            self.navigator.set_params(
                data.get('safe_distance'),
                data.get('lidar_offset')
            )
            emit('log', {'message': 'Parameters updated', 'type': 'info'})
            
        @self.socketio.on('clear_map')
        def handle_clear_map():
            if self.grid_map:
                self.grid_map.reset_map()
            emit('log', {'message': 'Map cleared', 'type': 'info'})

    def _video_feed_generator(self, camera=None):
        """Generate video frames for streaming."""
        print(f"Video feed started (camera={camera or 'default'})")
        
        if camera:
            self.camera_manager.switch_camera(camera)
        
        frame_count = 0
        error_count = 0
        
        while True:
            try:
                # Get frame from camera manager (also used by AI)
                frame = self.camera_manager.get_frame()
                
                if frame is None:
                    error_count += 1
                    if error_count <= 3:
                        print(f"Video feed: got None frame")
                    time.sleep(0.1)
                    continue
                
                # Convert to JPEG (PiCamera2 gives RGB, imencode expects BGR)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_bytes = buffer.tobytes()
                
                frame_count += 1
                if frame_count == 1:
                    print(f"Video feed: first frame sent, shape={frame.shape}")
                
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                time.sleep(0.033)  # ~30 fps
                
            except GeneratorExit:
                print(f"Video feed ended (sent {frame_count} frames)")
                break
            except Exception as e:
                error_count += 1
                if error_count <= 5:
                    print(f"Video feed error #{error_count}: {e}")
                time.sleep(0.1)

    def _lidar_stream_loop(self):
        """Stream LIDAR data to clients."""
        last_time = time.time()
        scan_count = 0
        
        while self._running:
            try:
                if self.lidar_scanner:
                    scan_data = self.lidar_scanner.get_scan_data()
                    
                    scan_count += 1
                    now = time.time()
                    if now - last_time >= 1.0:
                        scan_rate = scan_count
                        scan_count = 0
                        last_time = now
                    else:
                        scan_rate = scan_count / max(0.1, now - last_time)
                    
                    points = [
                        {'angle': angle, 'distance': distance}
                        for (_, angle, distance) in scan_data
                        if distance > 0
                    ]
                    
                    if self.grid_map:
                        robot_pos = (
                            self.navigator.position['x'],
                            self.navigator.position['y'],
                            self.navigator.position['theta']
                        )
                        self.grid_map.update_map(scan_data, robot_pos)
                    
                    self.socketio.emit('lidar_data', {
                        'points': points,
                        'scan_rate': round(scan_rate, 1)
                    })
                    
                self.socketio.emit('nav_status', self.navigator.get_status())
                self.socketio.emit('position', self.navigator.position)
                self.socketio.emit('motor_status', self.robot_controller.motor_controller.get_status())
                    
                time.sleep(0.1)
                
            except Exception as e:
                print(f"LIDAR stream error: {e}")
                time.sleep(1)

    def start_detection_thread(self):
        """Start AI detection thread."""
        if VISION_AVAILABLE:
            # Pass camera manager's frame and lock to AI detection
            self._detection_thread = threading.Thread(
                target=self._detection_wrapper,
                daemon=True
            )
            self._detection_thread.start()
            print("✓ AI detection started")
        else:
            print("⚠ AI detection not available")
    
    def _detection_wrapper(self):
        """Wrapper that provides frames from camera manager to AI detection."""
        # Create a simple wrapper that maps camera_manager.current_frame to global_frame
        class FrameProxy:
            def __init__(self, camera_manager):
                self.camera_manager = camera_manager
            
            def __getitem__(self, idx):
                return self.camera_manager.current_frame
            
            def __setitem__(self, idx, value):
                self.camera_manager.current_frame = value
        
        frame_proxy = FrameProxy(self.camera_manager)
        start_detection(
            frame_proxy,
            self.camera_manager.frame_lock,
            self.robot_controller.object_detector
        )

    def _status_broadcast_loop(self):
        """Broadcast motor and navigation status to clients."""
        while self._running:
            try:
                # Always send motor status
                self.socketio.emit('motor_status', 
                    self.robot_controller.motor_controller.get_status())
                
                # Always send navigation status
                self.socketio.emit('nav_status', self.navigator.get_status())
                self.socketio.emit('position', self.navigator.position)
                
                time.sleep(0.5)  # 2 Hz status updates
                
            except Exception as e:
                print(f"Status broadcast error: {e}")
                time.sleep(1)

    def start_status_thread(self):
        """Start status broadcast thread."""
        self._status_thread = threading.Thread(target=self._status_broadcast_loop, daemon=True)
        self._status_thread.start()
        print("✓ Status broadcast started")

    def start_lidar_thread(self):
        """Start LIDAR streaming thread."""
        if self.lidar_scanner:
            self.lidar_scanner.start_scanning()
            self._lidar_thread = threading.Thread(target=self._lidar_stream_loop, daemon=True)
            self._lidar_thread.start()
            print("✓ LIDAR streaming started")

    def run(self):
        """Start the web server."""
        self._running = True
        
        # Start cameras FIRST
        print("Starting cameras...")
        self.camera_manager.start()
        print("Cameras ready")
        
        # Start detection, LIDAR, and status broadcast
        self.start_detection_thread()
        self.start_lidar_thread()
        self.start_status_thread()
        
        print("\n" + "="*50)
        print("   🤖 RPi5 ROBOT CONTROL SERVER")
        print("="*50)
        print(f"   Web UI: http://0.0.0.0:{WEB_PORT}")
        print(f"   Motors: {'Remote (RPi3)' if self.robot_controller.motor_controller.is_remote else 'Local'}")
        print(f"   LIDAR:  {'Available' if LIDAR_AVAILABLE else 'Not available'}")
        print(f"   Vision: {'Available' if VISION_AVAILABLE else 'Not available'}")
        print("="*50 + "\n")
        
        self.socketio.run(self.app, host=WEB_HOST, port=WEB_PORT, debug=False)

    def stop(self):
        """Stop the web server."""
        print("Stopping web server...")
        self._running = False
        
        self.navigator.stop()
        self.camera_manager.stop()
        
        if self.lidar_scanner:
            self.lidar_scanner.stop()
