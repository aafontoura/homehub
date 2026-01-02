"""
Heating Zone Module

Represents a single heating zone (floor) with its own temperature control
and pump management.
"""

import logging
import time
from pid_controller import PIDController
from onoff_controller import OnOffController


class HeatingZone:
    """
    Represents a single heating zone (floor) with its own control logic.

    Features:
    - Temperature-based control via pluggable controller (PID, ON/OFF, etc.)
    - Pump state management
    - Simple and direct control without protection overhead
    """

    def __init__(self, name, config):
        self.name = name
        self.config = config

        # Temperature state
        self.current_temp = None
        self.outside_temp = None
        self.setpoint = config['default_setpoint']

        # Create controller based on config
        controller_type = config.get('controller_type', 'pid').lower()

        if controller_type == 'onoff':
            # ON/OFF controller with hysteresis
            hysteresis = config.get('hysteresis', 0.5)
            self.controller = OnOffController(name=self.name, hysteresis=hysteresis)
            logging.info(f"{self.name}: Using ON/OFF controller (hysteresis={hysteresis}°C)")
        else:
            # PID controller (default)
            self.controller = PIDController(
                name=self.name,
                kp=config.get('pid_kp', 5.0),
                ki=config.get('pid_ki', 0.1),
                kd=config.get('pid_kd', 1.0)
            )
            logging.info(f"{self.name}: Using PID controller (Kp={config.get('pid_kp', 5.0)}, "
                        f"Ki={config.get('pid_ki', 0.1)}, Kd={config.get('pid_kd', 1.0)})")

        # Pump state
        self.pump_state = False
        self.pump_duty_cycle = 0.0  # 0.0 to 1.0

        # SR-SF-007: Sensor update watchdog (RISK-013 Failure Mode B mitigation)
        self.last_temp_update_time = None  # Track last sensor update timestamp
        self.sensor_timeout_minutes = 20   # 20 minutes per SR-SF-007

        # SR-SF-008: Maximum runtime safety (RISK-013 Failure Mode B mitigation)
        self.pump_on_start_time = None     # When pump last turned ON
        self.max_runtime_hours = 6         # 6 hours per SR-SF-008

    def calculate_control_output(self):
        """
        Calculate pump control output using configured controller.

        Returns:
            float: Duty cycle (0.0 to 1.0)
        """
        if self.current_temp is None:
            return 0.0

        # Get controller output (returns 0-100%)
        output = self.controller.calculate_output(self.current_temp, self.setpoint) / 100.0

        return output

    def update_temperature(self, new_temp):
        """
        Update the current temperature reading and record timestamp (SR-SF-007).

        Args:
            new_temp: Current measured temperature in °C
        """
        self.current_temp = new_temp
        self.last_temp_update_time = time.time()  # Record update time for staleness detection

    def update_setpoint(self, new_setpoint):
        """
        Update the target setpoint temperature.

        Args:
            new_setpoint: New target temperature in °C
        """
        if new_setpoint != self.setpoint:
            logging.info(f"{self.name}: Setpoint changed {self.setpoint:.1f}°C → {new_setpoint:.1f}°C")
            self.setpoint = new_setpoint
            # Reset controller state when setpoint changes significantly
            if abs(new_setpoint - self.setpoint) > 1.0:
                self.controller.reset()
                logging.debug(f"{self.name}: Controller reset due to significant setpoint change")

    def set_pump_state(self, new_state):
        """
        Update pump state and track runtime (SR-SF-008).

        Args:
            new_state: True for ON, False for OFF
        """
        if new_state != self.pump_state:
            # Track pump ON time for SR-SF-008 maximum runtime safety
            if new_state:
                # Pump turning ON - record start time
                self.pump_on_start_time = time.time()
                logging.info(
                    f"{self.name}: Pump ON | "
                    f"Temp: {self.current_temp:.1f}°C, Setpoint: {self.setpoint:.1f}°C"
                )
            else:
                # Pump turning OFF - clear start time
                if self.pump_on_start_time is not None:
                    runtime_hours = (time.time() - self.pump_on_start_time) / 3600
                    logging.info(
                        f"{self.name}: Pump OFF (runtime: {runtime_hours:.2f}h) | "
                        f"Temp: {self.current_temp}°C, Setpoint: {self.setpoint:.1f}°C"
                    )
                else:
                    logging.info(
                        f"{self.name}: Pump OFF | "
                        f"Temp: {self.current_temp}°C, Setpoint: {self.setpoint:.1f}°C"
                    )
                self.pump_on_start_time = None

        self.pump_state = new_state

    def is_sensor_stale(self):
        """
        Check if sensor reading is stale (SR-SF-007).

        Returns:
            bool: True if no sensor update received within timeout period
        """
        if self.last_temp_update_time is None:
            return True  # Never received any update

        elapsed_minutes = (time.time() - self.last_temp_update_time) / 60
        return elapsed_minutes > self.sensor_timeout_minutes

    def is_runtime_exceeded(self):
        """
        Check if pump has been ON continuously for too long (SR-SF-008).

        Returns:
            bool: True if pump runtime exceeds maximum safe duration
        """
        if not self.pump_state or self.pump_on_start_time is None:
            return False  # Pump is OFF or no start time recorded

        elapsed_hours = (time.time() - self.pump_on_start_time) / 3600
        return elapsed_hours >= self.max_runtime_hours
