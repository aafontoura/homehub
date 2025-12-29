"""
PID Controller for Heating System

Proportional-Integral-Derivative controller for smooth temperature regulation.
Prevents oscillations and overshooting compared to simple ON/OFF control.
"""

import time
import logging
from heating_controller_base import HeatingController


class PIDController(HeatingController):
    """
    PID controller for smooth temperature regulation.

    The PID algorithm combines three terms:
    - Proportional (P): Immediate response to current error
    - Integral (I): Corrects persistent error over time
    - Derivative (D): Dampens rapid changes, prevents overshoot
    """

    def __init__(self, name: str, kp: float = 10.0, ki: float = 0.1, kd: float = 5.0,
                 output_limits: tuple = (0, 100)):
        """
        Initialize PID controller.

        Args:
            name: Identifier for this controller (e.g., zone name)
            kp: Proportional gain (default: 10.0)
            ki: Integral gain (default: 0.1)
            kd: Derivative gain (default: 5.0)
            output_limits: Min/max output as percentage (default: 0-100)
        """
        super().__init__(name)

        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits

        # Internal state
        self.setpoint = 20.0  # Default setpoint
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = time.time()

    def calculate_output(self, current_temp: float, setpoint: float) -> float:
        """
        Calculate PID output based on current temperature and setpoint.

        Args:
            current_temp: Current measured temperature in °C
            setpoint: Target temperature in °C

        Returns:
            Control output as percentage (0-100)
        """
        # Update setpoint if changed
        if self.setpoint != setpoint:
            self.setpoint = setpoint

        current_time = time.time()
        dt = current_time - self.last_time

        if dt <= 0.0:
            dt = 0.01  # Prevent division by zero

        # Calculate error (positive = need heating, negative = too hot)
        error = setpoint - current_temp

        # Proportional term (immediate response to current error)
        p_term = self.kp * error

        # Integral term (corrects persistent error over time)
        self.integral += error * dt

        # Anti-windup: clamp integral to prevent runaway accumulation
        max_integral = (self.output_limits[1] - self.output_limits[0]) / (2 * self.ki) if self.ki != 0 else 100
        integral_before_clamp = self.integral
        self.integral = max(-max_integral, min(max_integral, self.integral))
        i_term = self.ki * self.integral

        # Derivative term (dampens rapid changes, prevents overshoot)
        derivative = (error - self.last_error) / dt
        d_term = self.kd * derivative

        # Calculate total output (convert 0-1 range to 0-100 percentage)
        output_raw = p_term + i_term + d_term

        # Clamp output to limits
        output = max(self.output_limits[0], min(self.output_limits[1], output_raw))

        # Log detailed PID calculation
        logging.debug(
            f"PID [{self.name}]: setpoint={setpoint:.2f}°C, current={current_temp:.2f}°C, error={error:.2f}°C | "
            f"P={p_term:.3f} (kp={self.kp}), I={i_term:.3f} (integral={self.integral:.2f}), D={d_term:.3f} | "
            f"Output: {output_raw:.3f} → {output:.3f}% (clamped={output_raw != output})"
        )

        # Warn if integral is being clamped (anti-windup active)
        if integral_before_clamp != self.integral:
            logging.debug(
                f"PID [{self.name}]: Integral anti-windup active "
                f"(clamped from {integral_before_clamp:.2f} to {self.integral:.2f})"
            )

        # Update state
        self.last_error = error
        self.last_time = current_time

        return output

    def reset(self):
        """
        Reset PID controller state.

        Clears integral and derivative terms. Call when:
        - Zone is re-enabled after being disabled
        - System starts up
        - Significant setpoint changes occur
        """
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = time.time()
        logging.debug(f"PID [{self.name}]: Controller reset (integral/derivative cleared)")

    def update_config(self, config: dict):
        """
        Update PID tuning parameters.

        Args:
            config: Dictionary with keys:
                - pid_kp: Proportional gain
                - pid_ki: Integral gain
                - pid_kd: Derivative gain
                - output_limits: (min, max) tuple (optional)
        """
        if 'pid_kp' in config:
            self.kp = config['pid_kp']
        if 'pid_ki' in config:
            self.ki = config['pid_ki']
        if 'pid_kd' in config:
            self.kd = config['pid_kd']
        if 'output_limits' in config:
            self.output_limits = config['output_limits']

        logging.info(
            f"PID [{self.name}]: Config updated - Kp={self.kp}, Ki={self.ki}, Kd={self.kd}, "
            f"Limits={self.output_limits}"
        )
