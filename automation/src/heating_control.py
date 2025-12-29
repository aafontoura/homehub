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

        # Boiler state
        self.boiler_active = False
        self.boiler_on_time = None

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

        # Heating mode control
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

            # Manual setpoint overrides
            if '/setpoint/set' in topic:
                zone_name = topic.split('/')[1]
                if zone_name in self.zones:
                    setpoint = float(payload) if isinstance(payload, (int, float)) else float(payload.get('setpoint', 20))
                    zone = self.zones[zone_name]
                    zone.update_setpoint(setpoint)
                    logging.info(f"Manual setpoint for {zone_name}: {setpoint}°C")
                return

            # Heating mode
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
        """Handle heating mode changes (auto, off, manual)"""
        logging.info(f"Heating mode changed to: {mode}")
        # Implementation depends on requirements
        pass

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
        Main control loop - runs periodically (default: every 30 seconds).

        For each zone:
        1. Check for window openings (rapid temp drop detection)
        2. Calculate PID control output (duty cycle 0-100%)
        3. Convert duty to pump ON/OFF with deadband (prevents cycling)
        4. Apply pump protection (minimum ON/OFF times)
        5. Publish pump state to MQTT

        Then control boiler based on any zone being active.
        """
        try:
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

                # Validate zone has temperature data before processing
                if zone.current_temp is None:
                    logging.debug(f"│ ⚠️  NO TEMPERATURE DATA - Skipping control")
                    logging.debug(f"└" + "─" * 78)
                    # Still publish climate state (will show current state even without temp)
                    self._publish_climate_state(zone_name)
                    zone_status_summary.append(f"{zone_name}: NO DATA")
                    continue

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

                # Apply pump state change if needed
                if pump_changing:
                    self._set_pump_state(zone_name, desired_state)
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

            # Control boiler based on zone activity (DEBUG level)
            logging.debug("")
            logging.debug("─" * 80)
            if any_zone_active:
                logging.debug(f"🔥 BOILER: ON  │  Active zones: {', '.join(zones_requesting_heat)}")
            else:
                logging.debug(f"⚫ BOILER: OFF │  No zones requesting heat")

            self._set_boiler_state(any_zone_active)

            # Single INFO-level summary
            boiler_status = "ON" if any_zone_active else "OFF"
            logging.info(f"Control Loop: Boiler {boiler_status} | {' | '.join(zone_status_summary)}")

            loop_duration = time.time() - loop_start
            logging.debug(f"====== CONTROL LOOP END (duration: {loop_duration:.2f}s) ======\n")

        except Exception as e:
            logging.error(f"Error in control loop: {e}", exc_info=True)
        finally:
            # Schedule next run
            logging.debug(f'Scheduling next control loop iteration in {self.control_interval}')
            self.control_timer = threading.Timer(self.control_interval, self._run_control_loop)
            self.control_timer.daemon = True
            self.control_timer.start()

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
        if active == self.boiler_active:
            # No state change - log current state periodically
            if active and self.boiler_on_time:
                runtime = (time.time() - self.boiler_on_time) / 60
                logging.debug(f"Boiler remains ON (runtime: {runtime:.1f} min)")
            return

        self.boiler_active = active

        # Publish boiler state to Shelly relay
        # Config has base topic, append /set for commands
        boiler_topic = self.config['boiler_control_topic'] + '/set'
        payload = {"state": "ON" if active else "OFF"}
        logging.debug(f"Publishing boiler state to MQTT | Topic: {boiler_topic} | Payload: {payload}")
        self.client.publish(boiler_topic, json.dumps(payload), qos=1, retain=True)

        # Publish heating_active state for Home Assistant integration
        self.client.publish("heating/boiler_active", json.dumps({"state": active}), qos=1, retain=True)

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
            self.boiler_on_time = None
            logging.info(
                f"BOILER OFF | "
                f"Heartbeat stopped | "
                f"Total runtime: {runtime:.1f} min | "
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
            self.client.publish(
                f"heating/{zone_name}/current_temp",
                str(zone.current_temp),
                qos=1,
                retain=True
            )

        # Publish target temperature (setpoint)
        self.client.publish(
            f"heating/{zone_name}/climate/setpoint",
            str(zone.setpoint),
            qos=1,
            retain=True
        )

        # Publish HVAC mode
        # For Part 1, mode is always "heat" - the input_boolean controls actual heating
        # Mode changes via climate card are handled by HA automations → input_boolean
        self.client.publish(
            f"heating/{zone_name}/climate/mode",
            "heat",
            qos=1,
            retain=True
        )

        # Publish HVAC action (heating/idle based on pump state)
        action = "heating" if zone.pump_state else "idle"
        self.client.publish(
            f"heating/{zone_name}/climate/action",
            action,
            qos=1,
            retain=True
        )


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
