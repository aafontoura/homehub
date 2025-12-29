"""
Heating Controller Base Class

Abstract base class for different heating control algorithms.
Provides a common interface for PID, ON/OFF, and future controller types.
"""

from abc import ABC, abstractmethod


class HeatingController(ABC):
    """
    Abstract base class for heating controllers.

    Defines the interface that all heating controllers must implement.
    Controllers calculate heating output based on current temperature and setpoint.
    """

    def __init__(self, name: str):
        """
        Initialize the heating controller.

        Args:
            name: Identifier for this controller instance (e.g., zone name)
        """
        self.name = name

    @abstractmethod
    def calculate_output(self, current_temp: float, setpoint: float) -> float:
        """
        Calculate the heating control output.

        Args:
            current_temp: Current measured temperature in °C
            setpoint: Target temperature in °C

        Returns:
            Control output as a percentage (0-100)
            - 0: No heating required
            - 100: Maximum heating required
            - Values in between: Proportional heating
        """
        pass

    @abstractmethod
    def reset(self):
        """
        Reset the controller state.

        Called when:
        - System starts up
        - Zone is re-enabled after being disabled
        - Significant configuration changes occur

        Should clear any accumulated state (e.g., PID integral term).
        """
        pass

    @abstractmethod
    def update_config(self, config: dict):
        """
        Update controller configuration parameters.

        Args:
            config: Dictionary of configuration parameters specific to this controller
                   (e.g., PID gains, hysteresis values, etc.)
        """
        pass

    def __repr__(self):
        """String representation of the controller."""
        return f"{self.__class__.__name__}(name='{self.name}')"
