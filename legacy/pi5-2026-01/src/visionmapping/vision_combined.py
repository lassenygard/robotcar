"""
Combined script for object detection and vision processing, including Hailo interface and tracking.
Uses frames provided by the web server's camera manager instead of opening its own camera.
"""

import threading
import cv2
import queue
import numpy as np
from typing import List
import os
import sys
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Try to import config for paths
try:
    from config import HEF_PATH, LABELS_PATH, DETECTION_THRESHOLD
except ImportError:
    # Fallback to defaults relative to this file
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    HEF_PATH = os.path.join(_project_root, 'yolov5m_wo_spp_60p.hef')
    LABELS_PATH = os.path.join(_project_root, 'coco.txt')
    DETECTION_THRESHOLD = 0.5

# Try to import dependencies
try:
    from supervision import Detections, ByteTrack, RoundBoxAnnotator, LabelAnnotator
    SUPERVISION_AVAILABLE = True
except ImportError:
    SUPERVISION_AVAILABLE = False
    print("Warning: Supervision not available")

try:
    from utils import HailoAsyncInference
    HAILO_AVAILABLE = True
except ImportError:
    HAILO_AVAILABLE = False
    print("Warning: Hailo utils not available")


# ObjectDetector Class
class ObjectDetector:
    """Object detector that tracks unique detected objects."""
    
    def __init__(self):
        self.detected_objects = set()

    def update_detected_objects(self, objects):
        """Update the set of detected objects."""
        self.detected_objects.update(objects)

    def get_detected_objects(self):
        """Return the current set of detected objects."""
        return list(self.detected_objects)


# Vision Functions
def preprocess_frame(frame: np.ndarray, model_h: int, model_w: int) -> np.ndarray:
    """Preprocess the frame to match the model's input size."""
    return cv2.resize(frame, (model_w, model_h))


def extract_detections(hailo_output: List[np.ndarray], h: int, w: int, threshold: float = 0.5) -> dict:
    """Extract detections from the Hailo output."""
    xyxy, confidence, class_id = [], [], []

    for i, detections in enumerate(hailo_output):
        if len(detections) == 0:
            continue
        for detection in detections:
            bbox, score = detection[:4], detection[4]
            if score < threshold:
                continue
            bbox = [bbox[1] * w, bbox[0] * h, bbox[3] * w, bbox[2] * h]
            xyxy.append(bbox)
            confidence.append(score)
            class_id.append(i)

    return {
        "xyxy": np.array(xyxy),
        "confidence": np.array(confidence),
        "class_id": np.array(class_id),
        "num_detections": len(xyxy),
    }


def postprocess_detections(
    frame: np.ndarray,
    detections: dict,
    class_names: List[str],
    tracker,
    box_annotator,
    label_annotator,
    detected_objects: set,
) -> tuple:
    """Annotate the frame with detected objects."""
    if detections["xyxy"].size == 0:
        return frame, []

    sv_detections = Detections(
        xyxy=detections["xyxy"],
        confidence=detections["confidence"],
        class_id=detections["class_id"],
    )
    sv_detections = tracker.update_with_detections(sv_detections)

    labels = [
        f"#{tracker_id} {class_names[class_id]}"
        for class_id, tracker_id in zip(sv_detections.class_id, sv_detections.tracker_id)
    ]

    new_objects = set(labels) - detected_objects
    detected_objects.update(new_objects)

    annotated_frame = box_annotator.annotate(
        scene=frame.copy(), detections=sv_detections
    )
    annotated_labeled_frame = label_annotator.annotate(
        scene=annotated_frame, detections=sv_detections, labels=labels
    )
    return annotated_labeled_frame, list(new_objects)


def start_detection(
    global_frame,
    frame_lock,
    object_detector: ObjectDetector,
    hef_path: str = None,
    labels_path: str = None,
    score_thresh: float = None
):
    """
    Run the detection process.
    
    Uses frames from global_frame (populated by the camera manager) instead of
    opening its own camera. This avoids camera conflicts.
    """
    # Use config values or defaults
    hef_path = hef_path or HEF_PATH
    labels_path = labels_path or LABELS_PATH
    score_thresh = score_thresh or DETECTION_THRESHOLD
    
    # Check if required components are available
    if not HAILO_AVAILABLE:
        print("⚠ Hailo not available - AI detection disabled")
        return
        
    if not SUPERVISION_AVAILABLE:
        print("⚠ Supervision not available - AI detection disabled")
        return
    
    # Check if HEF file exists
    if not os.path.exists(hef_path):
        print(f"⚠ HEF file not found: {hef_path}")
        print("  AI detection disabled - copy yolov5m_wo_spp_60p.hef to project root")
        return
        
    # Check if labels file exists
    if not os.path.exists(labels_path):
        print(f"⚠ Labels file not found: {labels_path}")
        print("  AI detection disabled - copy coco.txt to project root")
        return
    
    print(f"Loading Hailo model from: {hef_path}")
    
    retries = 3
    input_queue = queue.Queue()
    output_queue = queue.Queue()
    hailo_inference = None

    while retries > 0:
        try:
            hailo_inference = HailoAsyncInference(
                hef_path=hef_path,
                input_queue=input_queue,
                output_queue=output_queue
            )
            print("✓ Hailo inference initialized")
            break
        except Exception as e:
            retries -= 1
            print(f"Hailo initialization failed. Retries left: {retries}. Error: {e}")
            time.sleep(2)
    
    if hailo_inference is None:
        print("⚠ Failed to initialize Hailo after retries - AI detection disabled")
        return

    model_h, model_w, _ = hailo_inference.get_input_shape()

    box_annotator = RoundBoxAnnotator()
    label_annotator = LabelAnnotator()
    tracker = ByteTrack()

    with open(labels_path, "r", encoding="utf-8") as f:
        class_names = f.read().splitlines()

    # Start inference thread
    threading.Thread(target=hailo_inference.run, daemon=True).start()

    try:
        print("✓ AI detection process started (using shared camera frames)")
        detected_objects = object_detector.detected_objects
        
        # Wait for first frame from camera manager
        print("  Waiting for camera frames...")
        wait_count = 0
        while wait_count < 50:  # Wait up to 5 seconds
            with frame_lock:
                if global_frame[0] is not None:
                    break
            time.sleep(0.1)
            wait_count += 1
        
        if global_frame[0] is None:
            print("⚠ No camera frames available - AI detection stopping")
            return
            
        print("  Camera frames available, starting detection loop")
        
        while True:
            # Get frame from shared global_frame (populated by camera manager)
            with frame_lock:
                if global_frame[0] is None:
                    time.sleep(0.1)
                    continue
                frame = global_frame[0].copy()
            
            # Get frame dimensions
            h, w = frame.shape[:2]
            
            # Preprocess and run inference
            preprocessed_frame = preprocess_frame(frame, model_h, model_w)
            input_queue.put([preprocessed_frame])

            try:
                _, results = output_queue.get(timeout=1.0)
            except queue.Empty:
                continue
                
            if len(results) == 1:
                results = results[0]

            detections = extract_detections(results, h, w, score_thresh)

            # Update global frame with annotations
            with frame_lock:
                annotated_frame, new_objects = postprocess_detections(
                    frame, detections, class_names, tracker, 
                    box_annotator, label_annotator, detected_objects
                )
                global_frame[0] = annotated_frame
                
                if new_objects:
                    object_detector.update_detected_objects(new_objects)
                    print("New Objects Detected:", new_objects)

            # Small delay to not overwhelm the system
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("Stopping detection process.")
    except Exception as e:
        print(f"Detection error: {e}")
    finally:
        if hailo_inference:
            hailo_inference.stop()
