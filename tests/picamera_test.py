import picamera

with picamera.PiCamera() as camera:
    camera.resolution = (1024, 768)
    camera.start_preview()
    # Camera warm-up time
    import time
    time.sleep(2)
    camera.capture('test_image.jpg')
