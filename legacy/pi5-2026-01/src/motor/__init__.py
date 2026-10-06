"""
Motor control module.
Supports both local GPIO and remote (RPi3) motor control.
"""

from .motor_controller import MotorControlManager

__all__ = ['MotorControlManager']
