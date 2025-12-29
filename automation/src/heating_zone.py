"""
Heating Zone Module

Represents a single heating zone (floor) with its own temperature control
and pump management.
"""

import logging
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
        Update the current temperature reading.

        Args:
            new_temp: Current measured temperature in °C
        """
        self.current_temp = new_temp

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
        Update pump state.

        Args:
            new_state: True for ON, False for OFF
        """
        if new_state != self.pump_state:
            logging.info(
                f"{self.name}: Pump {'ON' if new_state else 'OFF'} | "
                f"Temp: {self.current_temp:.1f}°C, Setpoint: {self.setpoint:.1f}°C"
            )

        self.pump_state = new_state
