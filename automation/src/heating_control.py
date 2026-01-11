#!/usr/bin/env python3
"""
Heating Control System - Multi-zone heating controller with MQTT integration

Features:
- Pluggable controller architecture (PID or ON/OFF)
- Multi-zone temperature control
- Pump protection (minimum on/off times, cycle limits)
- MQTT heartbeat watchdog for Shelly relay safety
- Home Assistant Climate entity integration
"""

import time
import logging
import threading
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from homehub_mqtt import AutomationPubSub
from heating_zone import HeatingZone
from pid_controller import PIDController
from onoff_controller import OnOffController
from schedule_manager import ScheduleManager, OperatingMode


class HeatingControl(AutomationPubSub):
    """
    Main heating control system managing multiple zones.
    """
    def __init__(self, broker_ip, config_file='heating_config.yaml', mqtt_username=None, mqtt_password=None):
        super().__init__(broker_ip, "heating_control", username=mqtt_username, password=mqtt_password)

        # Load configuration
        self.config = self.read_config(config_file)
        if not self.config:
            raise RuntimeError(f"Failed to load config from {config_file}")

        # Initialize heating zones
        self.zones = {}
        for zone_name, zone_config in self.config['zones'].items():
            self.zones[zone_name] = HeatingZone(zone_name, zone_config)
            logging.info(f"Initialized zone: {zone_name}")

        # Initialize schedule manager
        self.schedule_manager = ScheduleManager(self.config)
        logging.info("ScheduleManager initialized")

        # Boiler state
        self.boiler_active = False
        self.boiler_on_time = None
        self.total_boiler_runtime = 0.0  # Total runtime in minutes (cumulative)

        # Outside temperature
        self.outside_temp = None

        # Heartbeat watchdog
        self.heartbeat_interval = self.config.get('heartbeat_interval_seconds', 300)  # 5 min
        self.heartbeat_timer = None

        # Control loop
        self.control_interval = self.config.get('control_interval_seconds', 30)  # 30 sec
        self.control_timer = None

        # Subscribe to MQTT topics
        self._setup_subscriptions()

        # Start control loop
        self._start_control_loop()

    def _setup_subscriptions(self):
        """Subscribe to all necessary MQTT topics"""
        topics = []

        # Temperature sensors
        if self.config and 'zones' in self.config:
            for zone_name, zone_config in self.config['zones'].items():
                sensor_topic = zone_config['temperature_sensor_topic']
                topics.append(sensor_topic)
                logging.info(f"Subscribing to {zone_name} sensor: {sensor_topic}")

        # Outside temperature
        if self.config and 'outside_temperature_topic' in self.config:
            topics.append(self.config['outside_temperature_topic'])

        # Manual setpoint overrides
        for zone_name in self.zones.keys():
            topics.append(f"heating/{zone_name}/setpoint/set")

        # Operating mode control (per-zone)
        for zone_name in self.zones.keys():
            topics.append(f"heating/{zone_name}/mode/set")

        # Climate preset mode control (per-zone)
        for zone_name in self.zones.keys():
            topics.append(f"heating/{zone_name}/climate/preset/set")

        # Legacy global mode control (deprecated, kept for backwards compatibility)
        topics.append("heating/mode/set")

        self._subscribe_to_topics(topics)

    def _on_connection_established(self):
        """
        Called after MQTT connection and subscriptions are complete.
        Requests initial state from all devices to ensure complete data before control starts.
        """
        self._request_initial_states()

    def _request_initial_states(self):
        """
        Request current state from all Zigbee2MQTT devices on startup.
        Ensures system has complete data before first control loop executes.

        Uses Zigbee2MQTT '/get' endpoint pattern to query device state.
        Responses arrive on normal device topics and are handled by handle_message().
        """

        logging.info("Requesting initial device states from Zigbee2MQTT...")

        # Request temperature from all zone sensors
        for zone in self.zones.values():
            sensor_topic = zone.config['temperature_sensor_topic']
            device_name = sensor_topic.replace('zigbee2mqtt/', '')
            get_topic = f"zigbee2mqtt/{device_name}/get"

            self.client.publish(get_topic, '{"temperature": ""}', qos=1)
            logging.debug(f"Requested state: {get_topic}")

        # Request outside temperature
        if self.config and 'outside_temperature_topic' in self.config:
            outdoor_topic = self.config['outside_temperature_topic']
            device_name = outdoor_topic.replace('zigbee2mqtt/', '')
            get_topic = f"zigbee2mqtt/{device_name}/get"

            self.client.publish(get_topic, '{"temperature": ""}', qos=1)
            logging.debug(f"Requested state: {get_topic}")

        # Request pump states
        for zone in self.zones.values():
            pump_topic = zone.config['pump_control_topic']
            device_name = pump_topic.replace('zigbee2mqtt/', '')
            get_topic = f"zigbee2mqtt/{device_name}/get"

            self.client.publish(get_topic, '{"state": ""}', qos=1)
            logging.debug(f"Requested state: {get_topic}")

        # Request boiler state
        if self.config and 'boiler_control_topic' in self.config:
            boiler_topic = self.config['boiler_control_topic']
            device_name = boiler_topic.replace('zigbee2mqtt/', '')
            get_topic = f"zigbee2mqtt/{device_name}/get"

            self.client.publish(get_topic, '{"state": ""}', qos=1)
            logging.debug(f"Requested state: {get_topic}")

        logging.info("Initial state requests sent (awaiting responses...)")

    def handle_message(self, topic, payload):
        """Handle incoming MQTT messages"""
        try:
            logging.debug(f"Received message on {topic}: {payload}")
            # Temperature sensor updates
            for zone_name, zone in self.zones.items():
                if topic == zone.config['temperature_sensor_topic']:
                    temp = self._extract_temperature(payload)
                    if temp is not None:
                        zone.update_temperature(temp)
                        logging.debug(f"{zone_name} temperature: {temp}°C")
                    else:
                        logging.warning(f"Invalid temperature payload for {zone_name}: {payload}")
                    return

            # Outside temperature
            if self.config and topic == self.config.get('outside_temperature_topic'):
                temp = self._extract_temperature(payload)
                if temp is not None:
                    self.outside_temp = temp
                    # Update all zones
                    for zone in self.zones.values():
                        zone.outside_temp = temp
                    logging.debug(f"Outside temperature: {temp}°C")
                return

            # Manual setpoint overrides (DEPRECATED - use mode=manual instead)
            if '/setpoint/set' in topic:
                zone_name = topic.split('/')[1]
                if zone_name in self.zones:
                    setpoint = float(payload) if isinstance(payload, (int, float)) else float(payload.get('setpoint', 20))
                    # Set mode to MANUAL with the specified setpoint
                    self.schedule_manager.set_zone_mode(
                        zone_name=zone_name,
                        mode=OperatingMode.MANUAL,
                        manual_setpoint=setpoint
                    )
                    logging.info(f"Manual setpoint for {zone_name}: {setpoint}°C (mode set to MANUAL)")
                    self._publish_schedule_state(zone_name)
                return

            # Per-zone operating mode control
            if '/mode/set' in topic and topic != "heating/mode/set":
                zone_name = topic.split('/')[1]
                if zone_name in self.zones:
                    self._handle_zone_mode_change(zone_name, payload)
                    self._publish_schedule_state(zone_name)
                return

            # Climate preset mode control (new standard method)
            if '/climate/preset/set' in topic:
                zone_name = topic.split('/')[1]
                if zone_name in self.zones:
                    self._handle_preset_change(zone_name, payload)
                    self._publish_schedule_state(zone_name)
                    self._publish_climate_preset(zone_name)
                return

            # Legacy global mode control (deprecated)
            if topic == "heating/mode/set":
                mode = payload if isinstance(payload, str) else payload.get('mode', 'auto')
                self._handle_mode_change(mode)
                return

        except Exception as e:
            logging.error(f"Error handling message from {topic}: {e}", exc_info=True)

    def _extract_temperature(self, payload):
        """Extract temperature value from various payload formats"""
        if isinstance(payload, (int, float)):
            return float(payload)
        elif isinstance(payload, dict):
            # Zigbee2MQTT format
            if 'temperature' in payload:
                return float(payload['temperature'])
            # Home Assistant format
            elif 'state' in payload:
                try:
                    return float(payload['state'])
                except (ValueError, TypeError):
                    return None
        return None

    def _handle_mode_change(self, mode):
        """
        Handle legacy global heating mode changes (deprecated).

        This method is kept for backwards compatibility but should be replaced
        with per-zone mode control using heating/{zone_name}/mode/set topics.
        """
        logging.warning(f"Legacy global mode change to '{mode}' (deprecated - use per-zone mode control)")
        # Apply mode to all zones
        for zone_name in self.zones.keys():
            try:
                operating_mode = OperatingMode(mode.lower())
                self.schedule_manager.set_zone_mode(zone_name, operating_mode)
                self._publish_schedule_state(zone_name)
            except ValueError:
                logging.error(f"Invalid operating mode: {mode}")

    def _handle_zone_mode_change(self, zone_name: str, payload):
        """
        Handle per-zone operating mode changes.

        Payload format:
            {"mode": "auto|manual|away|vacation|off|boost", "setpoint": 21.0, "duration_hours": 2.0}

        Or simple string:
            "auto", "manual", "away", etc.
        """
        try:
            # Parse payload
            if isinstance(payload, str):
                mode_str = payload.lower()
                manual_setpoint = None
                boost_duration = None
            elif isinstance(payload, dict):
                mode_str = payload.get('mode', 'auto').lower()
                manual_setpoint = payload.get('setpoint')
                boost_duration = payload.get('duration_hours')
            else:
                logging.error(f"{zone_name}: Invalid mode payload format: {payload}")
                return

            # Convert to OperatingMode enum
            try:
                mode = OperatingMode(mode_str)
            except ValueError:
                logging.error(f"{zone_name}: Invalid operating mode: {mode_str}")
                return

            # Set the mode
            self.schedule_manager.set_zone_mode(
                zone_name=zone_name,
                mode=mode,
                manual_setpoint=manual_setpoint,
                boost_duration_hours=boost_duration
            )

            logging.info(f"{zone_name}: Mode changed to {mode.value}" +
                        (f" (setpoint: {manual_setpoint}°C)" if manual_setpoint else "") +
                        (f" (duration: {boost_duration}h)" if boost_duration else ""))

        except Exception as e:
            logging.error(f"{zone_name}: Error handling mode change: {e}", exc_info=True)

    def _handle_preset_change(self, zone_name: str, payload):
        """
        Handle climate preset mode changes (new standard method).

        Preset mapping:
            "none" -> No specific mode (stays in current mode)
            "home" -> AUTO (follow schedule)
            "comfort" -> COMFORT (schedule + offset)
            "away" -> AWAY (schedule - 3°C)
            "eco" -> VACATION (10°C freeze protection)
            "boost" -> BOOST (temporary override with timer)

        Payload: string preset name (e.g., "home", "comfort", "boost")
        """
        try:
            # Parse payload
            if isinstance(payload, str):
                preset_str = payload.lower()
            else:
                logging.error(f"{zone_name}: Invalid preset payload format: {payload}")
                return

            # Map preset to OperatingMode
            preset_to_mode = {
                "none": None,  # No change
                "home": OperatingMode.AUTO,
                "comfort": OperatingMode.COMFORT,
                "away": OperatingMode.AWAY,
                "eco": OperatingMode.VACATION,
                "boost": OperatingMode.BOOST,
            }

            if preset_str not in preset_to_mode:
                logging.error(f"{zone_name}: Unknown preset: {preset_str}")
                return

            mode = preset_to_mode[preset_str]
            if mode is None:
                logging.info(f"{zone_name}: Preset 'none' - no mode change")
                return

            # Handle boost mode specially - needs setpoint and expiry
            if mode == OperatingMode.BOOST:
                # Get default boost setpoint from current schedule + comfort offset
                current_setpoint = self.schedule_manager.get_effective_setpoint(zone_name)
                boost_setpoint = (current_setpoint or 21.0) + 2.0  # Boost = current + 2°C

                # Use default duration (2h)
                boost_duration = self.config.get('scheduling', {}).get('boost_default_duration_hours', 2.0) if self.config else 2.0

                self.schedule_manager.set_zone_mode(
                    zone_name=zone_name,
                    mode=mode,
                    manual_setpoint=boost_setpoint,
                    boost_duration_hours=boost_duration
                )

                logging.info(f"{zone_name}: Preset changed to {preset_str} " +
                            f"(boost setpoint: {boost_setpoint}°C, duration: {boost_duration}h)")
            else:
                # Other presets don't need setpoint/duration
                self.schedule_manager.set_zone_mode(
                    zone_name=zone_name,
                    mode=mode
                )

                logging.info(f"{zone_name}: Preset changed to {preset_str} (mode: {mode.value})")

        except Exception as e:
            logging.error(f"{zone_name}: Error handling preset change: {e}", exc_info=True)

    def _publish_schedule_state(self, zone_name: str):
        """
        Publish current schedule/mode state for a zone to MQTT.

        Published to: heating/{zone_name}/schedule/state

        Payload includes:
        - mode: Current operating mode
        - effective_setpoint: Calculated setpoint considering mode and schedule
        - manual_setpoint: Manual setpoint (if in Manual/Boost mode)
        - boost_expires_at: Boost expiry timestamp (if in Boost mode)
        - schedule_active: Whether schedule is currently being followed
        """
        try:
            state = self.schedule_manager.get_zone_state(zone_name)
            topic = f"heating/{zone_name}/schedule/state"
            self.client.publish(topic, json.dumps(state), qos=1, retain=True)
            logging.debug(f"{zone_name}: Published schedule state: {state}")
        except Exception as e:
            logging.error(f"{zone_name}: Error publishing schedule state: {e}", exc_info=True)

    def _start_control_loop(self):
        """Start the main control loop after initialization delay"""
        # Delay first run to allow initial state requests to complete
        initialization_delay = 5  # 5 seconds for devices to respond

        logging.info(f"Delaying first control loop by {initialization_delay}s for initialization...")
        self.control_timer = threading.Timer(initialization_delay, self._run_control_loop)
        self.control_timer.daemon = True
        self.control_timer.start()

    def _run_control_loop(self):
        """
        Main control loop wrapper - runs the control logic and schedules next iteration.
        """
        try:
            self._run_control_loop_logic()
        except Exception as e:
            logging.error(f"Error in control loop: {e}", exc_info=True)
        finally:
            # Schedule next run
            logging.debug(f'Scheduling next control loop iteration in {self.control_interval}')
            self.control_timer = threading.Timer(self.control_interval, self._run_control_loop)
            self.control_timer.daemon = True
            self.control_timer.start()

    def _run_control_loop_logic(self):
        """
        Core control loop logic - calculates and applies heating control.

        For each zone:
        1. Calculate controller output (duty cycle 0-100%)
        2. Determine pump state (ON if duty > 0%)
        3. Publish pump state to MQTT

        Then control boiler based on any zone being active.

        This method contains only the control logic without scheduling,
        so it can be called both for initial sync and regular loops.
        """
        loop_start = time.time()

        # Clear visual separator for new control loop (DEBUG level)
        logging.debug("")
        logging.debug("=" * 80)
        logging.debug(f"CONTROL LOOP | Interval: {self.control_interval}s")
        logging.debug("=" * 80)

        # Update each zone
        any_zone_active = False
        zones_requesting_heat = []
        zone_status_summary = []

        for zone_name, zone in self.zones.items():
            logging.debug("")
            logging.debug(f"┌─ {zone_name.upper().replace('_', ' ')} " + "─" * (70 - len(zone_name)))

            # SR-SF-007: Check for stale sensor readings (RISK-013 Failure Mode B)
            # Only check if we've received at least one update (ignore on startup)
            if zone.last_temp_update_time is not None and zone.is_sensor_stale():
                elapsed_minutes = (time.time() - zone.last_temp_update_time) / 60 if zone.last_temp_update_time else float('inf')
                logging.warning(
                    f"{zone_name}: SENSOR STALE - No update for {elapsed_minutes:.1f} min "
                    f"(threshold: {zone.sensor_timeout_minutes} min)"
                )
                zone.current_temp = None  # Treat as unavailable, triggers SR-SF-002 shutdown below
                self._publish_critical_alert(zone_name, "stale_sensor",
                    f"No sensor update for {elapsed_minutes:.0f} minutes - heating disabled",
                    "HEAT-SF-001")

            # SR-SF-008: Check for maximum runtime exceeded (RISK-013 Failure Mode B)
            if zone.is_runtime_exceeded():
                runtime_hours = (time.time() - zone.pump_on_start_time) / 3600
                logging.critical(
                    f"{zone_name}: EMERGENCY SHUTDOWN - Pump runtime {runtime_hours:.1f}h "
                    f"exceeded {zone.max_runtime_hours}h limit"
                )
                # Force pump OFF
                self._set_pump_state(zone_name, False)
                zone.current_temp = None  # Disable zone until manual intervention
                self._publish_critical_alert(zone_name, "runtime_exceeded",
                    f"Emergency shutdown: pump runtime {runtime_hours:.1f}h exceeded {zone.max_runtime_hours}h limit",
                    "HEAT-SF-002")
                logging.debug(f"└" + "─" * 78)
                zone_status_summary.append(f"{zone_name}: EMERGENCY STOP")
                continue

            # SR-SF-002: Validate zone has temperature data before processing
            if zone.current_temp is None:
                logging.debug(f"│ ⚠️  NO TEMPERATURE DATA - Skipping control")
                logging.debug(f"└" + "─" * 78)
                # Still publish climate state (will show current state even without temp)
                self._publish_climate_state(zone_name)
                # Publish schedule state
                self._publish_schedule_state(zone_name)
                zone_status_summary.append(f"{zone_name}: NO DATA")
                continue

            # SR-SCH-001: Get effective setpoint from ScheduleManager
            # This considers current operating mode and schedule
            effective_setpoint = self.schedule_manager.get_effective_setpoint(zone_name)

            # SR-SCH-002: Handle OFF mode (heating disabled)
            if effective_setpoint is None:
                mode = self.schedule_manager.get_zone_mode(zone_name)
                logging.debug(f"│ 🛑 Heating disabled (mode: {mode.value if mode else 'unknown'})")
                # Force pump OFF
                self._set_pump_state(zone_name, False)
                logging.debug(f"└" + "─" * 78)
                # Publish states
                self._publish_climate_state(zone_name)
                self._publish_schedule_state(zone_name)
                zone_status_summary.append(f"{zone_name}: OFF")
                continue

            # Update zone setpoint (for controller and MQTT publishing)
            zone.update_setpoint(effective_setpoint)

            # Log schedule information
            mode = self.schedule_manager.get_zone_mode(zone_name)
            logging.debug(f"│ 📅 Schedule | Mode: {mode.value if mode else 'unknown'} | Setpoint: {effective_setpoint}°C")

            # Calculate temperature error
            temp_error = zone.setpoint - zone.current_temp
            error_symbol = "🔥" if temp_error > 0 else "❄️" if temp_error < 0 else "✓"

            # Calculate control output (0.0 = no heat, 1.0 = max heat)
            duty_cycle = zone.calculate_control_output()
            zone.pump_duty_cycle = duty_cycle

            # Determine pump state
            desired_state = duty_cycle > 0.0
            pump_changing = desired_state != zone.pump_state
            pump_symbol = "🟢" if desired_state else "⚫"
            change_indicator = " [CHANGING]" if pump_changing else ""

            # Log zone status (DEBUG level)
            logging.debug(f"│ 🌡️  Temp: {zone.current_temp:5.1f}°C  →  Target: {zone.setpoint:5.1f}°C  │  Error: {temp_error:+5.1f}°C {error_symbol}")
            logging.debug(f"│ 🎛️  Controller Output: {duty_cycle:6.1%}  │  Pump: {pump_symbol} {'ON ' if desired_state else 'OFF'}{change_indicator}")

            # Always publish pump state to ensure device stays in sync
            self._set_pump_state(zone_name, desired_state)
            if pump_changing:
                logging.debug(f"│ 🔄 Pump state changed: {'OFF → ON' if desired_state else 'ON → OFF'}")

            logging.debug(f"└" + "─" * 78)

            # Track if zone is requesting heat (for boiler control)
            if zone.pump_state:
                any_zone_active = True
                zones_requesting_heat.append(zone_name)
                zone_status_summary.append(f"{zone_name}: ON ({duty_cycle:.0%})")
            else:
                zone_status_summary.append(f"{zone_name}: OFF")

            # Publish climate state for thermostat interface (Part 1)
            self._publish_climate_state(zone_name)
            self._publish_climate_preset(zone_name)

            # Publish schedule state (SR-SCH-005: MQTT control interface)
            self._publish_schedule_state(zone_name)

            # Publish metrics for historical analysis and InfluxDB
            self._publish_zone_metrics(zone_name, temp_error, duty_cycle)

        # Control boiler based on zone activity (DEBUG level)
        logging.debug("")
        logging.debug("─" * 80)
        if any_zone_active:
            logging.debug(f"🔥 BOILER: ON  │  Active zones: {', '.join(zones_requesting_heat)}")
        else:
            logging.debug(f"⚫ BOILER: OFF │  No zones requesting heat")

        self._set_boiler_state(any_zone_active)

        # Publish system-wide metrics
        self._publish_system_metrics(any_zone_active, len(zones_requesting_heat))

        # Single INFO-level summary
        boiler_status = "ON" if any_zone_active else "OFF"
        logging.info(f"Control Loop: Boiler {boiler_status} | {' | '.join(zone_status_summary)}")

        loop_duration = time.time() - loop_start
        logging.debug(f"====== CONTROL LOOP END (duration: {loop_duration:.2f}s) ======\n")

    def _set_pump_state(self, zone_name, state):
        """Set pump state for a zone and publish to MQTT"""
        zone = self.zones[zone_name]
        zone.set_pump_state(state)

        # Publish to MQTT for physical pump control
        # Config has base topic, append /set for commands
        pump_topic = zone.config['pump_control_topic'] + '/set'
        payload = {"state": "ON" if state else "OFF"}
        self.client.publish(pump_topic, json.dumps(payload), qos=1, retain=True)

        logging.debug(
            f"{zone_name}: Published pump state to MQTT | "
            f"Topic: {pump_topic} | "
            f"Payload: {payload}"
        )

    def _set_boiler_state(self, active):
        """Set boiler state and manage heartbeat watchdog"""
        if not self.config:
            return

        state_changing = active != self.boiler_active

        # Always publish boiler state to ensure device stays in sync
        boiler_topic = self.config['boiler_control_topic'] + '/set'
        payload = {"state": "ON" if active else "OFF"}
        logging.debug(f"Publishing boiler state to MQTT | Topic: {boiler_topic} | Payload: {payload}")
        self.client.publish(boiler_topic, json.dumps(payload), qos=1, retain=True)

        # Publish heating_active state for Home Assistant integration
        self.client.publish("heating/boiler_active", json.dumps({"state": active}), qos=1, retain=True)

        # Only update heartbeat and logging on state changes
        if state_changing:
            self.boiler_active = active

            # Manage heartbeat watchdog timer (safety mechanism for Shelly relay)
            if active:
                self._start_heartbeat()
                self.boiler_on_time = time.time()
                logging.info(
                    f"BOILER ON | "
                    f"Heartbeat started (interval: {self.heartbeat_interval}s) | "
                    f"MQTT: {boiler_topic} → {payload}"
                )
            else:
                self._stop_heartbeat()
                runtime = (time.time() - self.boiler_on_time) / 60 if self.boiler_on_time else 0
                self.total_boiler_runtime += runtime  # Accumulate total runtime
                self.boiler_on_time = None
                logging.info(
                    f"BOILER OFF | "
                    f"Heartbeat stopped | "
                    f"Session runtime: {runtime:.1f} min | "
                    f"Total runtime: {self.total_boiler_runtime:.1f} min | "
                    f"MQTT: {boiler_topic} → {payload}"
                )

    def _start_heartbeat(self):
        """Start heartbeat timer for Shelly watchdog"""
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

        self._send_heartbeat()

    def _send_heartbeat(self):
        """Send heartbeat ping to Shelly watchdog"""
        if not self.boiler_active:
            return

        # Send heartbeat
        heartbeat_topic = self.config.get('heartbeat_topic', 'boiler_heat_request/heartbeat')
        self.client.publish(heartbeat_topic, "ping", qos=0, retain=False)
        logging.debug("Heartbeat sent")

        # Schedule next heartbeat
        self.heartbeat_timer = threading.Timer(self.heartbeat_interval, self._send_heartbeat)
        self.heartbeat_timer.daemon = True
        self.heartbeat_timer.start()

    def _stop_heartbeat(self):
        """Stop heartbeat timer"""
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None

    def _publish_climate_state(self, zone_name):
        """
        Publish climate entity state to MQTT for Home Assistant thermostat interface.

        Publishes:
        - Current temperature
        - Target setpoint
        - HVAC mode (heat/off based on enabled state)
        - HVAC action (heating/idle based on pump state)
        """
        zone = self.zones[zone_name]

        # Publish current temperature
        if zone.current_temp is not None:
            logging.debug(f"Publishing heating/{zone_name}/current_temp: {zone.current_temp}°C")
            self.client.publish(
                f"heating/{zone_name}/current_temp",
                str(zone.current_temp),
                qos=1,
                retain=True
            )

        # Publish target temperature (setpoint from schedule manager)
        # Get effective setpoint from schedule manager to ensure it reflects current mode/schedule
        effective_setpoint = self.schedule_manager.get_effective_setpoint(zone_name)
        if effective_setpoint is not None:
            logging.debug(f"Publishing heating/{zone_name}/climate/setpoint: {effective_setpoint}°C")
            self.client.publish(
                f"heating/{zone_name}/climate/setpoint",
                str(effective_setpoint),
                qos=1,
                retain=True
            )

        # Publish HVAC mode
        # For Part 1, mode is always "heat" - the input_boolean controls actual heating
        # Mode changes via climate card are handled by HA automations → input_boolean
        logging.debug(f"Publishing heating/{zone_name}/climate/mode: heat")
        self.client.publish(
            f"heating/{zone_name}/climate/mode",
            "heat",
            qos=1,
            retain=True
        )

        # Publish HVAC action (heating/idle based on pump state)
        action = "heating" if zone.pump_state else "idle"
        logging.debug(f"Publishing heating/{zone_name}/climate/action: {action}")
        self.client.publish(
            f"heating/{zone_name}/climate/action",
            action,
            qos=1,
            retain=True
        )

    def _publish_climate_preset(self, zone_name):
        """
        Publish current preset mode to MQTT for climate entity.

        Maps OperatingMode to climate preset:
            AUTO -> "home"
            COMFORT -> "comfort"
            AWAY -> "away"
            VACATION -> "eco"
            BOOST -> "boost"
            MANUAL -> "none"
            OFF -> "none"
        """
        # Get current operating mode
        current_mode = self.schedule_manager.get_zone_mode(zone_name)
        if current_mode is None:
            return

        # Map OperatingMode to preset
        mode_to_preset = {
            OperatingMode.AUTO: "home",
            OperatingMode.COMFORT: "comfort",
            OperatingMode.AWAY: "away",
            OperatingMode.VACATION: "eco",
            OperatingMode.BOOST: "boost",
            OperatingMode.MANUAL: "none",
            OperatingMode.OFF: "none",
        }

        preset = mode_to_preset.get(current_mode, "none")

        # Publish preset state
        logging.debug(f"Publishing heating/{zone_name}/climate/preset: {preset} (mode: {current_mode.value})")
        self.client.publish(
            f"heating/{zone_name}/climate/preset",
            preset,
            qos=1,
            retain=True
        )

        logging.debug(f"{zone_name}: Published climate preset: {preset} (mode: {current_mode.value})")

    def _publish_zone_metrics(self, zone_name, temp_error, duty_cycle):
        """
        Publish zone metrics for historical analysis and InfluxDB.

        Args:
            zone_name: Name of the zone
            temp_error: Temperature error (setpoint - current_temp) in °C
            duty_cycle: Controller output duty cycle (0.0 to 1.0)
        """
        zone = self.zones[zone_name]

        metrics = {
            "setpoint": round(zone.setpoint, 2),
            "temp_error": round(temp_error, 2),
            "duty_cycle": round(duty_cycle * 100, 1),  # Convert to percentage
            "controller_output": round(duty_cycle * 100, 1),  # Same as duty_cycle for Phase 1
            "pump_active": zone.pump_state
        }

        self.client.publish(
            f"heating/{zone_name}/metrics",
            json.dumps(metrics),
            qos=1,
            retain=True
        )

        logging.debug(
            f"{zone_name}: Published metrics | "
            f"Setpoint: {metrics['setpoint']}°C, "
            f"Error: {metrics['temp_error']:+.2f}°C, "
            f"Duty: {metrics['duty_cycle']:.1f}%, "
            f"Pump: {'ON' if metrics['pump_active'] else 'OFF'}"
        )

    def _publish_system_metrics(self, boiler_active, active_zones_count):
        """
        Publish system-wide metrics for historical analysis and InfluxDB.

        Args:
            boiler_active: Whether boiler is currently active
            active_zones_count: Number of zones requesting heat
        """
        metrics = {
            "boiler_active": boiler_active,
            "boiler_runtime_minutes": round(self.total_boiler_runtime, 1),
            "active_zones_count": active_zones_count
        }

        self.client.publish(
            "heating/system/metrics",
            json.dumps(metrics),
            qos=1,
            retain=True
        )

        logging.debug(
            f"System: Published metrics | "
            f"Boiler: {'ON' if boiler_active else 'OFF'}, "
            f"Active zones: {active_zones_count}, "
            f"Total runtime: {metrics['boiler_runtime_minutes']:.1f} min"
        )

    def _publish_critical_alert(self, zone_name, alert_type, message, alert_id):
        """
        Publish critical safety alert to MQTT (SR-SF-007, SR-SF-008, SR-AL-001).

        Args:
            zone_name: Name of the zone triggering the alert
            alert_type: Type of alert ("stale_sensor" or "runtime_exceeded")
            message: Human-readable alert message
            alert_id: Unique alert identifier per SR-AL-001 (e.g., "HEAT-SF-001")
        """
        alert_payload = {
            "alert_id": alert_id,
            "zone": zone_name,
            "alert_type": alert_type,
            "message": message,
            "timestamp": time.time()
        }

        self.client.publish(
            f"heating/{zone_name}/alert/critical",
            json.dumps(alert_payload),
            qos=1,
            retain=False  # Don't retain alerts
        )

        logging.critical(f"{zone_name}: [{alert_id}] CRITICAL ALERT published - {message}")


def main():
    """Main entry point"""
    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError as e:
        logging.warning(f"Could not load .env file: {e}")
        pass  # python-dotenv not installed, use system environment only
    except Exception as e:
        logging.warning(f"Could not load .env file: {e}")

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('heating_control.log')
        ]
    )

    # Get MQTT broker IP from environment or use default
    broker_ip = os.environ.get('MQTT_BROKER_IP', '192.168.1.10')

    # Get MQTT credentials from environment (optional)
    mqtt_username = os.environ.get('MQTT_USERNAME')
    mqtt_password = os.environ.get('MQTT_PASSWORD')

    if mqtt_username and mqtt_password:
        logging.info(f"MQTT authentication configured for user: {mqtt_username}")
    else:
        logging.info("MQTT authentication not configured (anonymous access)")

    # Create heating control instance
    logging.info("Starting heating control system...")
    heating = HeatingControl(broker_ip, mqtt_username=mqtt_username, mqtt_password=mqtt_password)

    # Connect to MQTT
    heating.connect()

    logging.info("Heating control system running")

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down heating control system")
        if heating.heartbeat_timer:
            heating.heartbeat_timer.cancel()
        if heating.control_timer:
            heating.control_timer.cancel()


if __name__ == '__main__':
    main()
