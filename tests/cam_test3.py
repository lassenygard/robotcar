import time
import cv2

def test_camera():
    cap = cv2.VideoCapture(0)
    time.sleep(2)

    if not cap.isOpened():
        print("Error: Camera not found or not connected.")
        return

    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame from camera.")
    else:
        cv2.imwrite('test_frame.jpg', frame)

    cap.release()

if __name__ == "__main__":
    test_camera()
