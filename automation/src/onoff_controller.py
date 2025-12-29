"""
ON/OFF Controller for Heating System

Simple hysteresis-based controller (also known as bang-bang control).
More predictable and easier to understand than PID, suitable for systems
with slow thermal response.
"""

import logging
from heating_controller_base import HeatingController


class OnOffController(HeatingController):
    """
    Simple ON/OFF controller with hysteresis.

    Uses a dead-band (hysteresis) to prevent rapid switching:
    - Turns ON when: temp < setpoint - hysteresis
    - Turns OFF when: temp > setpoint
    - Stays in current state within the dead-band

    Example with setpoint=20°C, hysteresis=0.5°C:
    - Heating turns ON at 19.5°C
    - Heating stays ON until 20.0°C
    - Heating turns OFF at 20.0°C
    - Dead-band: 19.5°C - 20.0°C (no state change)
    """

    def __init__(self, name: str, hysteresis: float = 0.5):
        """
        Initialize ON/OFF controller.

        Args:
            name: Identifier for this controller (e.g., zone name)
            hysteresis: Temperature dead-band in °C (default: 0.5°C)
                       Prevents rapid on/off cycling
        """
        super().__init__(name)
        self.hysteresis = hysteresis
        self.is_heating = False  # Track current heating state

    def calculate_output(self, current_temp: float, setpoint: float) -> float:
        """
        Calculate ON/OFF output based on temperature and hysteresis.

        Args:
            current_temp: Current measured temperature in °C
            setpoint: Target temperature in °C

        Returns:
            Control output as percentage:
            - 0: Heating OFF
            - 100: Heating ON (full power)
        """
        # Calculate thresholds
        turn_on_threshold = setpoint - self.hysteresis
        turn_off_threshold = setpoint

        previous_state = self.is_heating

        # Hysteresis logic
        if current_temp < turn_on_threshold:
            # Temperature too low - turn on heating
            self.is_heating = True
        elif current_temp > turn_off_threshold:
            # Temperature reached setpoint - turn off heating
            self.is_heating = False
        # else: within dead-band, maintain current state

        # Log state changes
        if self.is_heating != previous_state:
            logging.info(
                f"ON/OFF [{self.name}]: State changed {previous_state} → {self.is_heating} | "
                f"Temp: {current_temp:.2f}°C, Setpoint: {setpoint:.2f}°C, "
                f"Thresholds: ON<{turn_on_threshold:.2f}°C, OFF>{turn_off_threshold:.2f}°C"
            )
        else:
            logging.debug(
                f"ON/OFF [{self.name}]: State={self.is_heating} | "
                f"Temp: {current_temp:.2f}°C, Setpoint: {setpoint:.2f}°C, "
                f"Error: {setpoint - current_temp:.2f}°C"
            )

        # Return 100% for ON, 0% for OFF
        return 100.0 if self.is_heating else 0.0

    def reset(self):
        """
        Reset controller state.

        Turns off heating and clears internal state.
        Call when zone is re-enabled or system starts up.
        """
        self.is_heating = False
        logging.debug(f"ON/OFF [{self.name}]: Controller reset (heating OFF)")

    def update_config(self, config: dict):
        """
        Update controller configuration.

        Args:
            config: Dictionary with keys:
                - hysteresis: Temperature dead-band in °C
        """
        if 'hysteresis' in config:
            old_hysteresis = self.hysteresis
            self.hysteresis = config['hysteresis']
            logging.info(
                f"ON/OFF [{self.name}]: Hysteresis updated {old_hysteresis:.2f}°C → {self.hysteresis:.2f}°C"
            )
