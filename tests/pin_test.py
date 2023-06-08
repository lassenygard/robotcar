from gpiozero import Motor, OutputDevice
from time import sleep

# Define Motor objects for each motor, including the GPIO pins for forward and backward
motors = {
    "Motor1": Motor(forward=24, backward=27),
    "Motor2": Motor(forward=6, backward=22),
    "Motor3": Motor(forward=23, backward=16),
    "Motor4": Motor(forward=13, backward=18),
}

# Define OutputDevice for each motor's enable pin
enables = {
    "Motor1": OutputDevice(5, initial_value=True),
    "Motor2": OutputDevice(17, initial_value=True),
    "Motor3": OutputDevice(12, initial_value=True),
    "Motor4": OutputDevice(25, initial_value=True),
}

# Loop through each motor and perform actions
for loop_number, (motor_name, motor) in enumerate(motors.items(), start=1):
    # Enable the motor
    enables[motor_name].on()

    print(f"{loop_number} - Motor {motor_name} forward")
    motor.forward()
    sleep(1)

    print(f"{loop_number} - Motor {motor_name} backward")
    motor.backward()
    sleep(1)

    print(f"{loop_number} - Motor {motor_name} stopped")
    motor.stop()

    # Disable the motor
    enables[motor_name].off()

# gpiozero cleanup is automatic when the script ends
