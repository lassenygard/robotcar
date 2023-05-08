import cv2

def test_camera():
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Camera not found or not connected.")
        return

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Error: Could not read frame from camera.")
            break

        cv2.imshow("Camera Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_camera()
