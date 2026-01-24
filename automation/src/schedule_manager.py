#!/usr/bin/env python3
"""
Schedule Manager - Weekly schedule and operating mode management

Handles time-based setpoint calculations and operating mode state.
"""

import logging
import json
import os
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional, Dict, List


class OperatingMode(Enum):
    """Operating modes for heating zones"""
    AUTO = "auto"  # Follow weekly schedule
    COMFORT = "comfort"  # Schedule with positive offset (e.g., +1°C)
    MANUAL = "manual"  # Custom setpoint, no schedule
    AWAY = "away"  # Schedule with offset (e.g., -3°C)
    VACATION = "vacation"  # Freeze protection (e.g., 10°C)
    OFF = "off"  # Heating disabled
    BOOST = "boost"  # Temporary override with timer


class TimeBlock:
    """Represents a scheduled time block with setpoint"""

    def __init__(self, start: str, end: str, setpoint: float):
        """
        Initialize time block.

        Args:
            start: Start time as "HH:MM" (24-hour format)
            end: End time as "HH:MM" (24-hour format)
            setpoint: Target temperature in °C
        """
        self.start_time = datetime.strptime(start, "%H:%M").time()
        self.end_time = datetime.strptime(end, "%H:%M").time()
        self.setpoint = setpoint

    def contains(self, check_time: time) -> bool:
        """
        Check if time falls within this block.

        Handles blocks that cross midnight (e.g., 22:00-06:00).

        Args:
            check_time: Time to check

        Returns:
            bool: True if time is within block
        """
        if self.start_time <= self.end_time:
            # Normal case: block within same day
            result = self.start_time <= check_time < self.end_time
            logging.debug(
                f"    TimeBlock check: {check_time.strftime('%H:%M')} in "
                f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} "
                f"(setpoint: {self.setpoint}°C) = {result}"
            )
            return result
        else:
            # Block crosses midnight (e.g., 22:00-06:00)
            result = check_time >= self.start_time or check_time < self.end_time
            logging.debug(
                f"    TimeBlock check (midnight-crossing): {check_time.strftime('%H:%M')} in "
                f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} "
                f"(setpoint: {self.setpoint}°C) = {result}"
            )
            return result

    def __repr__(self):
        return f"TimeBlock({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}: {self.setpoint}°C)"


class Schedule:
    """Weekly schedule for a heating zone"""

    def __init__(self, weekday_blocks: List[TimeBlock], weekend_blocks: List[TimeBlock]):
        """
        Initialize schedule.

        Args:
            weekday_blocks: Time blocks for Monday-Friday
            weekend_blocks: Time blocks for Saturday-Sunday
        """
        self.weekday_blocks = weekday_blocks
        self.weekend_blocks = weekend_blocks

    def get_setpoint_for_time(self, dt: datetime) -> Optional[float]:
        """
        Get scheduled setpoint for given datetime.

        Args:
            dt: Datetime to check

        Returns:
            float: Scheduled setpoint in °C, or None if no block matches
        """
        # Determine weekday vs weekend
        is_weekend = dt.weekday() >= 5  # Saturday=5, Sunday=6

        blocks = self.weekend_blocks if is_weekend else self.weekday_blocks
        current_time = dt.time()

        logging.debug(
            f"  Schedule lookup: {dt.strftime('%A %H:%M')} "
            f"(weekday={dt.weekday()}, is_weekend={is_weekend}, checking {len(blocks)} blocks)"
        )

        # Find matching time block
        for block in blocks:
            if block.contains(current_time):
                logging.debug(f"  ✓ Found matching block → setpoint={block.setpoint}°C")
                return block.setpoint

        # No matching block found
        logging.warning(
            f"No schedule block found for {dt.strftime('%A %H:%M')} | "
            f"Available blocks: {blocks}"
        )
        return None


class ModeManager:
    """Manages operating mode state for a heating zone"""

    def __init__(
        self,
        zone_name: str,
        default_mode: OperatingMode = OperatingMode.AUTO,
        persistence_file: Optional[str] = None
    ):
        """
        Initialize mode manager.

        Args:
            zone_name: Name of the zone
            default_mode: Initial operating mode
            persistence_file: Path to JSON file for state persistence
        """
        self.zone_name = zone_name
        self.current_mode = default_mode
        self.manual_setpoint: Optional[float] = None
        self.boost_expires_at: Optional[datetime] = None
        self.previous_mode: Optional[OperatingMode] = None
        self.persistence_file = persistence_file

        # Load persisted state if available
        if persistence_file:
            self.load_state()

    def get_effective_setpoint(
        self,
        schedule: Schedule,
        current_time: datetime,
        comfort_offset: float,
        away_offset: float,
        vacation_setpoint: float
    ) -> Optional[float]:
        """
        Calculate effective setpoint based on current mode.

        Args:
            schedule: Zone schedule
            current_time: Current datetime
            comfort_offset: Temperature offset for Comfort mode (e.g., +1.0)
            away_offset: Temperature offset for Away mode (e.g., -3.0)
            vacation_setpoint: Freeze protection setpoint (e.g., 10.0)

        Returns:
            float: Effective setpoint in °C, or None for OFF mode
        """
        # Check if Boost mode has expired
        if self.current_mode == OperatingMode.BOOST:
            if self.boost_expires_at and current_time >= self.boost_expires_at:
                # Boost expired - revert to previous mode
                logging.info(
                    f"{self.zone_name}: Boost mode expired | "
                    f"Reverting to {self.previous_mode.value if self.previous_mode else 'auto'}"
                )
                # self.current_mode = self.previous_mode or OperatingMode.AUTO
                # there is a bug here that the mode is not set to the correct previous mode
                self.current_mode = OperatingMode.AUTO # For now, always revert to AUTO after boost. 
                self.boost_expires_at = None
                self.manual_setpoint = None
                self.persist_state()

        # Calculate setpoint based on mode
        if self.current_mode == OperatingMode.OFF:
            return None  # Heating disabled

        elif self.current_mode == OperatingMode.MANUAL:
            return self.manual_setpoint

        elif self.current_mode == OperatingMode.BOOST:
            return self.manual_setpoint

        elif self.current_mode == OperatingMode.VACATION:
            return vacation_setpoint

        elif self.current_mode == OperatingMode.COMFORT:
            # Get scheduled setpoint and apply positive offset
            scheduled_setpoint = schedule.get_setpoint_for_time(current_time)
            if scheduled_setpoint is not None:
                return scheduled_setpoint + comfort_offset
            return None

        elif self.current_mode == OperatingMode.AWAY:
            # Get scheduled setpoint and apply negative offset
            scheduled_setpoint = schedule.get_setpoint_for_time(current_time)
            if scheduled_setpoint is not None:
                return scheduled_setpoint + away_offset
            return None

        elif self.current_mode == OperatingMode.AUTO:
            # Follow schedule
            return schedule.get_setpoint_for_time(current_time)

        else:
            logging.error(f"{self.zone_name}: Unknown operating mode: {self.current_mode}")
            return None

    def set_mode(
        self,
        mode: OperatingMode,
        manual_setpoint: Optional[float] = None,
        boost_duration_hours: Optional[float] = None
    ):
        """
        Change operating mode.

        Args:
            mode: New operating mode
            manual_setpoint: Setpoint for Manual/Boost modes
            boost_duration_hours: Duration for Boost mode
        """
        # Store previous mode for Boost revert
        if mode == OperatingMode.BOOST:
            self.previous_mode = self.current_mode
            self.boost_expires_at = datetime.now() + timedelta(hours=boost_duration_hours or 2)
            self.manual_setpoint = manual_setpoint
            logging.info(
                f"{self.zone_name}: Boost mode activated | "
                f"Setpoint: {manual_setpoint}°C, "
                f"Expires: {self.boost_expires_at.strftime('%H:%M')}"
            )
        elif mode == OperatingMode.MANUAL:
            self.manual_setpoint = manual_setpoint
            self.boost_expires_at = None
            self.previous_mode = None
            logging.info(f"{self.zone_name}: Manual mode | Setpoint: {manual_setpoint}°C")
        else:
            self.manual_setpoint = None
            self.boost_expires_at = None
            self.previous_mode = None
            logging.info(f"{self.zone_name}: Mode changed to {mode.value}")

        self.current_mode = mode
        self.persist_state()

    def persist_state(self):
        """Save current state to JSON file"""
        if not self.persistence_file:
            return

        # Load existing data
        if os.path.exists(self.persistence_file):
            try:
                with open(self.persistence_file, 'r') as f:
                    data = json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load persistence file: {e}, creating new")
                data = {}
        else:
            data = {}

        # Update this zone's state
        data[self.zone_name] = {
            'mode': self.current_mode.value,
            'manual_setpoint': self.manual_setpoint,
            'boost_expires_at': self.boost_expires_at.isoformat() if self.boost_expires_at else None,
            'previous_mode': self.previous_mode.value if self.previous_mode else None,
            'last_updated': datetime.now().isoformat()
        }

        # Save to file
        try:
            with open(self.persistence_file, 'w') as f:
                json.dump(data, f, indent=2)
            logging.debug(f"{self.zone_name}: State persisted to {self.persistence_file}")
        except Exception as e:
            logging.error(f"{self.zone_name}: Failed to persist state: {e}")

    def load_state(self):
        """Load state from JSON file"""
        if not self.persistence_file or not os.path.exists(self.persistence_file):
            logging.info(f"{self.zone_name}: No persisted state found, using defaults")
            return

        try:
            with open(self.persistence_file, 'r') as f:
                data = json.load(f)

            zone_data = data.get(self.zone_name)
            if not zone_data:
                logging.info(f"{self.zone_name}: No state for this zone in persistence file")
                return

            # Restore state
            self.current_mode = OperatingMode(zone_data['mode'])
            self.manual_setpoint = zone_data.get('manual_setpoint')
            self.previous_mode = OperatingMode(zone_data['previous_mode']) if zone_data.get('previous_mode') else None

            if zone_data.get('boost_expires_at'):
                self.boost_expires_at = datetime.fromisoformat(zone_data['boost_expires_at'])

            logging.info(
                f"{self.zone_name}: State loaded from persistence | "
                f"Mode: {self.current_mode.value}, "
                f"Setpoint: {self.manual_setpoint}, "
                f"Boost expires: {self.boost_expires_at}"
            )

        except Exception as e:
            logging.error(f"{self.zone_name}: Failed to load persisted state: {e}")


class ScheduleManager:
    """Manages schedules and modes for all heating zones"""

    def __init__(self, config: dict):
        """
        Initialize schedule manager.

        Args:
            config: Heating configuration dict (from heating_config.yaml)
        """
        self.config = config
        self.schedules: Dict[str, Schedule] = {}
        self.mode_managers: Dict[str, ModeManager] = {}

        # Global scheduling settings
        scheduling_config = config.get('scheduling', {})
        self.enabled = scheduling_config.get('enabled', True)
        self.persistence_file = scheduling_config.get('persistence_file', 'heating_schedule_state.json')
        self.default_boost_duration_hours = scheduling_config.get('boost_default_duration_hours', 2.0)
        self.comfort_offset = scheduling_config.get('comfort_offset_celsius', 1.0)
        self.away_offset = scheduling_config.get('away_offset_celsius', -3.0)
        self.vacation_setpoint = scheduling_config.get('vacation_setpoint', 10.0)

        # Load schedules for each zone
        self._load_schedules()

        logging.info("ScheduleManager initialized")
        logging.info(f"Scheduling enabled: {self.enabled}")
        logging.info(f"Comfort offset: {self.comfort_offset}°C")
        logging.info(f"Away offset: {self.away_offset}°C")
        logging.info(f"Vacation setpoint: {self.vacation_setpoint}°C")
        logging.info(f"Loaded schedules for {len(self.schedules)} zones")

    def _load_schedules(self):
        """Load schedules from configuration"""
        for zone_name, zone_config in self.config.get('zones', {}).items():
            schedule_config = zone_config.get('schedule')
            if not schedule_config:
                logging.warning(f"{zone_name}: No schedule configuration found")
                # Create mode manager anyway (for Manual/Off modes)
                self.mode_managers[zone_name] = ModeManager(
                    zone_name=zone_name,
                    default_mode=OperatingMode.MANUAL,  # Default to manual if no schedule
                    persistence_file=self.persistence_file
                )
                continue

            # Parse weekday blocks
            weekday_blocks = [
                TimeBlock(block['start'], block['end'], block['setpoint'])
                for block in schedule_config.get('weekdays', [])
            ]

            # Parse weekend blocks
            weekend_blocks = [
                TimeBlock(block['start'], block['end'], block['setpoint'])
                for block in schedule_config.get('weekends', [])
            ]

            # Create schedule
            self.schedules[zone_name] = Schedule(weekday_blocks, weekend_blocks)

            # Create mode manager
            self.mode_managers[zone_name] = ModeManager(
                zone_name=zone_name,
                default_mode=OperatingMode.AUTO,
                persistence_file=self.persistence_file
            )

            logging.info(
                f"{zone_name}: Schedule loaded | "
                f"Weekday blocks: {len(weekday_blocks)}, "
                f"Weekend blocks: {len(weekend_blocks)}"
            )
            logging.debug(f"{zone_name}: Weekday blocks: {weekday_blocks}")
            logging.debug(f"{zone_name}: Weekend blocks: {weekend_blocks}")

    def get_effective_setpoint(self, zone_name: str, current_time: Optional[datetime] = None) -> Optional[float]:
        """
        Get effective setpoint for a zone considering schedule and mode.

        Args:
            zone_name: Name of the zone
            current_time: Current datetime (defaults to now)

        Returns:
            float: Effective setpoint in °C, or None if heating disabled
        """
        if not self.enabled:
            logging.debug(f"{zone_name}: Scheduling disabled globally")
            return None

        if zone_name not in self.mode_managers:
            logging.warning(f"{zone_name}: No mode manager configured")
            return None

        current_time = current_time or datetime.now()
        mode_manager = self.mode_managers[zone_name]

        # If no schedule, only Manual/Off modes make sense
        if zone_name not in self.schedules:
            if mode_manager.current_mode == OperatingMode.MANUAL:
                return mode_manager.manual_setpoint
            elif mode_manager.current_mode == OperatingMode.BOOST:
                return mode_manager.manual_setpoint
            elif mode_manager.current_mode == OperatingMode.VACATION:
                return self.vacation_setpoint
            else:
                logging.warning(f"{zone_name}: No schedule, mode {mode_manager.current_mode.value} not applicable")
                return None

        schedule = self.schedules[zone_name]

        setpoint = mode_manager.get_effective_setpoint(
            schedule=schedule,
            current_time=current_time,
            comfort_offset=self.comfort_offset,
            away_offset=self.away_offset,
            vacation_setpoint=self.vacation_setpoint
        )

        logging.debug(
            f"{zone_name}: Effective setpoint calculation → "
            f"mode={mode_manager.current_mode.value}, setpoint={setpoint}°C"
        )

        return setpoint

    def set_zone_mode(
        self,
        zone_name: str,
        mode: OperatingMode,
        manual_setpoint: Optional[float] = None,
        boost_duration_hours: Optional[float] = None
    ):
        """
        Change operating mode for a zone.

        Args:
            zone_name: Name of the zone
            mode: New operating mode
            manual_setpoint: Setpoint for Manual/Boost modes
            boost_duration_hours: Duration for Boost mode (defaults to config value)
        """
        if zone_name not in self.mode_managers:
            logging.error(f"{zone_name}: No mode manager found")
            return

        mode_manager = self.mode_managers[zone_name]
        mode_manager.set_mode(
            mode=mode,
            manual_setpoint=manual_setpoint,
            boost_duration_hours=boost_duration_hours or self.default_boost_duration_hours
        )

    def get_zone_mode(self, zone_name: str) -> Optional[OperatingMode]:
        """Get current operating mode for a zone"""
        if zone_name not in self.mode_managers:
            return None
        return self.mode_managers[zone_name].current_mode

    def get_zone_state(self, zone_name: str) -> dict:
        """
        Get complete state for a zone (for MQTT publishing).

        Returns:
            dict: Zone state including mode, setpoint, schedule info
        """
        if zone_name not in self.mode_managers:
            return {}

        mode_manager = self.mode_managers[zone_name]
        current_time = datetime.now()
        effective_setpoint = self.get_effective_setpoint(zone_name, current_time)

        state = {
            'mode': mode_manager.current_mode.value,
            'effective_setpoint': effective_setpoint,
            'manual_setpoint': mode_manager.manual_setpoint,
            'boost_expires_at': mode_manager.boost_expires_at.isoformat() if mode_manager.boost_expires_at else None,
            'previous_mode': mode_manager.previous_mode.value if mode_manager.previous_mode else None,
            'schedule_active': mode_manager.current_mode in [OperatingMode.AUTO, OperatingMode.COMFORT, OperatingMode.AWAY]
        }

        return state
