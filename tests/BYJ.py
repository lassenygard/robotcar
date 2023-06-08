#!/usr/bin/env python3
""" test example file for module:rpiMotorlib.py 
file: RpiMotorLib.py class BYJMotor
"""

import time 
import RPi.GPIO as GPIO

# Next 3 lines for development local library testing import
# Comment out in production release and change RpiMotorLib.BYJMotor to BYJMotor
#import sys
#sys.path.insert(0, '/home/pi/Documents/tech/RpiMotorLib/RpiMotorLib')
#from RpiMotorLib import BYJMotor

# Production installed library import 
from RpiMotorLib import RpiMotorLib

"""
# Needed for testing motor stop 
# To Test motor stop put push button to VCC on GPIO 17 
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
"""

# Declare an named instance of class pass your custom name and type of motor
mymotortest = RpiMotorLib.BYJMotor("MyMotorOne", "28BYJ")

def main():
    """main function loop"""
    
    # ====== tests for motor 28BYJ48 ====
    
    # Needed for testing motor stop
    # GPIO.add_event_detect(17, GPIO.RISING, callback=button_callback)
    
    # Connect GPIO to [IN1 , IN2 , IN3 ,IN4] on Motor PCB
    GpioPins = [4, 14, 26, 20]
    
    # Arguments  for motor run function
    # (GPIOPins, stepdelay, steps, clockwise, verbose, steptype, initdelay)
    
    time.sleep(0.1)
    input("Press <Enter> to go CCW")
    mymotortest.motor_run(GpioPins,.001,90, True, True,"half", .05) # Clockwise (right)
    time.sleep(1)
    input("Press <Enter> to go CW")
    mymotortest.motor_run(GpioPins,.001,180, False, True,"half", .05) # Counterclockwise (left)
    time.sleep(1)
    input("Press <Enter> to go to initial position")
    mymotortest.motor_run(GpioPins,.001,90, True, True,"half", .05) # Back to initial position
    time.sleep(1)
  
"""
# needed for testing motor stop 
def button_callback(channel): 
    print("Test file: Stopping motor")
    mymotortest.motor_stop()   
"""

# ===================MAIN===============================

if __name__ == '__main__':
   
    print("START")
    main()
    GPIO.cleanup() # Optional 
    exit()
    
    
# =====================END===============================
