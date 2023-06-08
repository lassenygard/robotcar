#!/usr/bin/python3
import time
import curses
from RpiMotorLib import RpiMotorLib

# Define GPIO pins connected to the ULN2003 driver board
gpio_pins = (4, 14, 26, 20)  # in1, in2, in3, in4

# Define the stepper motor
stepper_motor = RpiMotorLib.BYJMotor("MyMotorOne", "28BYJ")

# Sleep duration between steps
step_sleep = 0.002

# Initialize curses
stdscr = curses.initscr()
curses.cbreak()
stdscr.keypad(1)
stdscr.nodelay(1)  # makes getch() non-blocking

# Initialize direction
direction = None

# Try-except block to handle motor rotation and keyboard interrupt
try:
    while True:
        c = stdscr.getch()
        
        # Arrow right: clockwise
        if c == curses.KEY_LEFT:
            direction = False  # False for clockwise
            stdscr.addstr(0, 0, 'Clockwise     ')
            
        # Arrow left: counter-clockwise
        elif c == curses.KEY_RIGHT:
            direction = True  # True for counter-clockwise
            stdscr.addstr(0, 0, 'Counter-clockwise')

        # 'q' key: quit
        elif c == ord('q'):
            break

        # No key pressed
        elif c == -1:
            direction = None

        # Rotate the motor
        if direction is not None:
            stepper_motor.motor_run(gpio_pins, step_sleep, 1, direction, False, "half", .05)
        else:
            stepper_motor.motor_stop()

except KeyboardInterrupt:
    stepper_motor.motor_stop()
    curses.nocbreak()
    stdscr.keypad(0)
    curses.echo()
    curses.endwin()
    exit(1)

# Clean up GPIO pins before exiting
stepper_motor.motor_stop()
curses.nocbreak()
stdscr.keypad(0)
curses.echo()
curses.endwin()
exit(0)
