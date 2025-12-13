#!/usr/bin/env python3
"""
Heating Control System - PID-based heating controller with monitoring
Features:
- PID temperature control
- Window opening detection via temperature patterns
- Thermal performance monitoring (insulation quality metrics)
- Heat delivery tracking (boiler efficiency)
- MQTT heartbeat watchdog for Shelly relay safety
"""

import time
import logging
import threading
from collections import deque
from datetime import datetime, timedelta
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from homehub_mqtt import AutomationPubSub


class PIDController:
    """
    PID controller for smooth temperature regulation.
    Prevents oscillations and overshooting compared to bang-bang control.
    """
    def __init__(self, kp, ki, kd, setpoint, output_limits=(0, 1)):
        self.kp = kp  # Proportional gain
        self.ki = ki  # Integral gain
        self.kd = kd  # Derivative gain
        self.setpoint = setpoint
        self.output_limits = output_limits

        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = time.time()

    def update(self, measurement):
        """
        Calculate PID output based on current measurement.

        Returns:
            float: Control output (0.0 to 1.0)
        """
        current_time = time.time()
        dt = current_time - self.last_time

        if dt <= 0.0:
            dt = 0.01  # Prevent division by zero

        # Calculate error
        error = self.setpoint - measurement

        # Proportional term
        p_term = self.kp * error

        # Integral term (with anti-windup)
        self.integral += error * dt
        # Anti-windup: clamp integral
        max_integral = (self.output_limits[1] - self.output_limits[0]) / (2 * self.ki) if self.ki != 0 else 100
        self.integral = max(-max_integral, min(max_integral, self.integral))
        i_term = self.ki * self.integral

        # Derivative term
        derivative = (error - self.last_error) / dt
        d_term = self.kd * derivative

        # Calculate total output
        output = p_term + i_term + d_term

        # Clamp output to limits
        output = max(self.output_limits[0], min(self.output_limits[1], output))

        # Update state
        self.last_error = error
        self.last_time = current_time

        return output

    def set_setpoint(self, setpoint):
        """Update the target setpoint"""
        self.setpoint = setpoint

    def reset(self):
        """Reset integral and derivative terms"""
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = time.time()


class ThermalPerformanceMonitor:
    """
    Monitors thermal performance to assess insulation quality.

    Metrics tracked:
    - Heat loss rate (°C/hour when not heating)
    - Temperature recovery rate (°C/hour when heating)
    - Heating efficiency (temp rise per hour of boiler runtime)
    - Outdoor correlation (how much outdoor temp affects indoor)
    """
    def __init__(self, zone_name):
        self.zone_name = zone_name

        # Measurement periods
        self.cooling_periods = deque(maxlen=20)  # Last 20 cooling cycles
        self.heating_periods = deque(maxlen=20)  # Last 20 heating cycles

        # Current measurement
        self.current_period_start = None
        self.current_period_start_temp = None
        self.current_period_heating = False

    def start_heating_period(self, temperature, outside_temp):
        """Mark start of a heating period"""
        self.current_period_start = time.time()
        self.current_period_start_temp = temperature
        self.current_period_outside_temp = outside_temp
        self.current_period_heating = True

    def start_cooling_period(self, temperature, outside_temp):
        """Mark start of a cooling period (heating off)"""
        self.current_period_start = time.time()
        self.current_period_start_temp = temperature
        self.current_period_outside_temp = outside_temp
        self.current_period_heating = False

    def end_period(self, temperature, outside_temp):
        """End current measurement period and calculate metrics"""
        if self.current_period_start is None:
            return

        duration_hours = (time.time() - self.current_period_start) / 3600
        if duration_hours < 0.25:  # Ignore periods < 15 minutes
            return

        temp_change = temperature - self.current_period_start_temp
        rate_per_hour = temp_change / duration_hours
        temp_delta_outside = (self.current_period_start_temp + temperature) / 2 - outside_temp

        period_data = {
            'timestamp': time.time(),
            'duration_hours': duration_hours,
            'temp_change': temp_change,
            'rate_per_hour': rate_per_hour,
            'outside_temp': outside_temp,
            'temp_delta_outside': temp_delta_outside,
            'start_temp': self.current_period_start_temp,
            'end_temp': temperature
        }

        if self.current_period_heating:
            self.heating_periods.append(period_data)
            logging.info(f"{self.zone_name} Heating cycle: {temp_change:+.2f}°C in {duration_hours:.1f}h "
                        f"({rate_per_hour:+.2f}°C/h), outside: {outside_temp:.1f}°C")
        else:
            self.cooling_periods.append(period_data)
            logging.info(f"{self.zone_name} Cooling cycle: {temp_change:+.2f}°C in {duration_hours:.1f}h "
                        f"({rate_per_hour:+.2f}°C/h), outside: {outside_temp:.1f}°C")

        # Reset for next period
        self.current_period_start = None

    def get_insulation_metrics(self):
        """
        Calculate insulation quality metrics.

        Returns:
            dict: Thermal performance metrics
        """
        if not self.cooling_periods:
            return None

        # Average heat loss rate (cooling)
        avg_heat_loss = sum(p['rate_per_hour'] for p in self.cooling_periods) / len(self.cooling_periods)

        # Correlation with outside temperature
        if len(self.cooling_periods) > 5:
            # Calculate how heat loss varies with temperature delta
            losses = [(p['rate_per_hour'], p['temp_delta_outside']) for p in self.cooling_periods]
            # Simple correlation: more delta = more loss (negative rate)
            avg_loss_per_delta = sum(abs(loss) / delta if delta > 0 else 0
                                    for loss, delta in losses) / len(losses)
        else:
            avg_loss_per_delta = None

        # Average heating recovery rate
        if self.heating_periods:
            avg_heat_gain = sum(p['rate_per_hour'] for p in self.heating_periods) / len(self.heating_periods)
        else:
            avg_heat_gain = None

        return {
            'avg_heat_loss_rate': avg_heat_loss,  # °C/hour when not heating
            'avg_heat_gain_rate': avg_heat_gain,  # °C/hour when heating
            'heat_loss_per_delta': avg_loss_per_delta,  # Heat loss per °C difference with outside
            'sample_count_cooling': len(self.cooling_periods),
            'sample_count_heating': len(self.heating_periods)
        }

    def get_insulation_rating(self):
        """
        Get a simple insulation quality rating.

        Returns:
            str: Rating (Excellent/Good/Fair/Poor/Unknown)
        """
        metrics = self.get_insulation_metrics()
        if not metrics or metrics['avg_heat_loss_rate'] is None:
            return "Unknown (insufficient data)"

        # Typical heat loss rates for different insulation qualities:
        # Excellent: -0.3°C/h or better (10°C delta)
        # Good: -0.3 to -0.5°C/h
        # Fair: -0.5 to -0.8°C/h
        # Poor: worse than -0.8°C/h

        loss_rate = abs(metrics['avg_heat_loss_rate'])

        if loss_rate < 0.3:
            return "Excellent"
        elif loss_rate < 0.5:
            return "Good"
        elif loss_rate < 0.8:
            return "Fair"
        else:
            return "Poor"


class HeatingZone:
    """
    Represents a single heating zone (floor) with its own control logic.
    """
    def __init__(self, name, config):
        self.name = name
        self.config = config

        # Temperature state
        self.current_temp = None
        self.outside_temp = None
        self.setpoint = config['default_setpoint']

        # Temperature history for pattern detection
        self.temp_history = deque(maxlen=config.get('history_length', 120))  # 10 min at 5sec

        # Window detection state
        self.window_open = False
        self.window_open_time = None

        # PID controller
        self.pid = PIDController(
            kp=config.get('pid_kp', 5.0),
            ki=config.get('pid_ki', 0.1),
            kd=config.get('pid_kd', 1.0),
            setpoint=self.setpoint
        )

        # Pump state
        self.pump_state = False
        self.pump_duty_cycle = 0.0  # 0.0 to 1.0
        self.pump_on_time = None  # Track when pump turned on
        self.pump_off_time = None  # Track when pump turned off

        # Pump cycling protection
        self.pump_last_on_time = None
        self.pump_last_off_time = None
        self.pump_manual_override = False  # True if last change was manual
        self.pump_cycle_count = 0  # Cycles in current hour
        self.pump_cycle_hour_start = time.time()

        # Pump protection thresholds from config
        self.pump_min_on_minutes = config.get('pump_min_on_minutes', 10)
        self.pump_min_off_minutes = config.get('pump_min_off_minutes', 10)
        self.pump_duty_on_threshold = config.get('pump_duty_on_threshold', 0.30)
        self.pump_duty_off_threshold = config.get('pump_duty_off_threshold', 0.05)

        # Thermal performance monitoring
        self.thermal_monitor = ThermalPerformanceMonitor(name)

    def update_temperature(self, temp):
        """Update current temperature and add to history"""
        self.current_temp = temp
        self.temp_history.append({
            'temp': temp,
            'time': time.time()
        })

    def detect_window_open(self):
        """
        Detect window opening via rapid temperature drop.

        Algorithm:
        - Calculate temperature derivative over last 1-2 minutes
        - If drop rate exceeds threshold (e.g., 0.3°C/min), window is open
        - Use multiple timeframes to reduce false positives
        """
        if len(self.temp_history) < 20:
            return False

        # Check short-term drop (1 minute)
        recent_1min = self._get_temp_range(seconds=60)
        if len(recent_1min) < 2:
            return False

        temp_drop_1min = recent_1min[0]['temp'] - recent_1min[-1]['temp']
        time_diff_1min = recent_1min[-1]['time'] - recent_1min[0]['time']
        rate_1min = (temp_drop_1min / time_diff_1min) * 60  # Convert to °C/min

        # Check medium-term drop (2 minutes)
        recent_2min = self._get_temp_range(seconds=120)
        if len(recent_2min) < 2:
            return False

        temp_drop_2min = recent_2min[0]['temp'] - recent_2min[-1]['temp']
        time_diff_2min = recent_2min[-1]['time'] - recent_2min[0]['time']
        rate_2min = (temp_drop_2min / time_diff_2min) * 60

        # Window detected if:
        # - Short-term drop > 0.3°C/min OR
        # - Medium-term drop > 0.2°C/min
        threshold_1min = self.config.get('window_detection_threshold_1min', 0.3)
        threshold_2min = self.config.get('window_detection_threshold_2min', 0.2)

        if rate_1min > threshold_1min or rate_2min > threshold_2min:
            if not self.window_open:
                logging.warning(f"{self.name}: Window opening detected! "
                              f"Rate: {rate_1min:.2f}°C/min (1min), {rate_2min:.2f}°C/min (2min)")
                self.window_open = True
                self.window_open_time = time.time()
            return True

        # Window closing detection: temperature stabilizes
        if self.window_open:
            if abs(rate_1min) < 0.1 and abs(rate_2min) < 0.1:
                logging.info(f"{self.name}: Window appears to be closed (temperature stabilized)")
                self.window_open = False
                self.window_open_time = None

        return self.window_open

    def _get_temp_range(self, seconds):
        """Get temperature readings from last N seconds"""
        if not self.temp_history:
            return []

        cutoff_time = time.time() - seconds
        return [entry for entry in self.temp_history if entry['time'] >= cutoff_time]

    def calculate_control_output(self):
        """
        Calculate pump control output using PID controller.

        Returns:
            float: Duty cycle (0.0 to 1.0)
        """
        if self.current_temp is None:
            return 0.0

        # Get PID output
        output = self.pid.update(self.current_temp)

        return output

    def set_pump_state(self, new_state, manual=False):
        """
        Update pump state and track thermal performance.

        Args:
            new_state: True for ON, False for OFF
            manual: True if this is a manual override (bypass protection)
        """
        # Detect state changes for thermal monitoring
        if new_state != self.pump_state:
            current_time = time.time()

            if new_state:
                # Pump turning ON - end cooling period, start heating
                if self.current_temp and self.outside_temp:
                    self.thermal_monitor.end_period(self.current_temp, self.outside_temp)
                    self.thermal_monitor.start_heating_period(self.current_temp, self.outside_temp)
                self.pump_on_time = current_time
                self.pump_last_on_time = current_time
                self.pump_cycle_count += 1
                logging.info(f"{self.name}: Pump cycle #{self.pump_cycle_count} (ON)" +
                           (" [MANUAL OVERRIDE]" if manual else ""))
            else:
                # Pump turning OFF - end heating period, start cooling
                if self.current_temp and self.outside_temp:
                    self.thermal_monitor.end_period(self.current_temp, self.outside_temp)
                    self.thermal_monitor.start_cooling_period(self.current_temp, self.outside_temp)
                self.pump_off_time = current_time
                self.pump_last_off_time = current_time
                logging.info(f"{self.name}: Pump OFF (runtime: {(current_time - self.pump_on_time) / 60:.1f} min)" +
                           (" [MANUAL OVERRIDE]" if manual else ""))
                self.pump_on_time = None

            # Track if this was a manual override
            self.pump_manual_override = manual

            # Reset hourly cycle counter
            hours_elapsed = (current_time - self.pump_cycle_hour_start) / 3600
            if hours_elapsed >= 1.0:
                cycles_per_hour = self.pump_cycle_count / hours_elapsed
                logging.info(f"{self.name}: Pump cycles last hour: {self.pump_cycle_count} ({cycles_per_hour:.1f}/h)")
                if cycles_per_hour > 6:
                    logging.warning(f"{self.name}: High pump cycle rate: {cycles_per_hour:.1f} cycles/hour!")
                self.pump_cycle_count = 0
                self.pump_cycle_hour_start = current_time

        self.pump_state = new_state

    def can_change_pump_state(self, desired_state):
        """
        Check if pump state can be changed based on minimum runtime protection.

        Args:
            desired_state: Desired pump state (True=ON, False=OFF)

        Returns:
            tuple: (can_change: bool, reason: str)
        """
        # Manual overrides always allowed
        if self.pump_manual_override:
            return (True, "Manual override - protection bypassed")

        current_time = time.time()

        if desired_state and not self.pump_state:
            # Want to turn ON, currently OFF
            if self.pump_last_off_time is None:
                return (True, "First startup")

            off_duration_minutes = (current_time - self.pump_last_off_time) / 60
            if off_duration_minutes < self.pump_min_off_minutes:
                remaining = self.pump_min_off_minutes - off_duration_minutes
                return (False, f"Pump must stay OFF for {self.pump_min_off_minutes} min (off {off_duration_minutes:.1f} min, need {remaining:.1f} more)")
            return (True, f"Pump has been OFF for {off_duration_minutes:.1f} min")

        elif not desired_state and self.pump_state:
            # Want to turn OFF, currently ON
            if self.pump_last_on_time is None:
                return (True, "Initial state")

            on_duration_minutes = (current_time - self.pump_last_on_time) / 60
            if on_duration_minutes < self.pump_min_on_minutes:
                remaining = self.pump_min_on_minutes - on_duration_minutes
                return (False, f"Pump must stay ON for {self.pump_min_on_minutes} min (on {on_duration_minutes:.1f} min, need {remaining:.1f} more)")
            return (True, f"Pump has been ON for {on_duration_minutes:.1f} min")

        return (True, "No state change")


class HeatingControl(AutomationPubSub):
    """
    Main heating control system managing multiple zones.
    """
    def __init__(self, broker_ip, config_file='heating_config.yaml'):
        super().__init__(broker_ip, "heating_control")

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

        # Performance reporting
        self.report_interval = self.config.get('report_interval_seconds', 3600)  # 1 hour
        self.report_timer = None

        # Subscribe to MQTT topics
        self._setup_subscriptions()

        # Start control loop
        self._start_control_loop()

        # Start performance reporting
        self._start_performance_reporting()

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

    def handle_message(self, topic, payload):
        """Handle incoming MQTT messages"""
        try:
            # Temperature sensor updates
            for zone_name, zone in self.zones.items():
                if topic == zone.config['temperature_sensor_topic']:
                    temp = self._extract_temperature(payload)
                    if temp is not None:
                        zone.update_temperature(temp)
                        logging.debug(f"{zone_name} temperature: {temp}°C")
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
                    zone.setpoint = setpoint
                    zone.pid.set_setpoint(setpoint)
                    # Mark as manual override - bypasses pump protection on next cycle
                    zone.pump_manual_override = True
                    logging.info(f"Manual setpoint for {zone_name}: {setpoint}°C [Manual override enabled]")
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
        """Start the main control loop"""
        self._run_control_loop()

    def _run_control_loop(self):
        """Main control loop - runs periodically"""
        try:
            # Update each zone
            any_zone_active = False

            for zone_name, zone in self.zones.items():
                # Check for window opening
                window_open = zone.detect_window_open()

                if window_open:
                    # Window open - turn off heating for this zone
                    if zone.pump_state:
                        self._set_pump_state(zone_name, False)
                        logging.info(f"{zone_name}: Pump OFF (window open)")
                    continue

                # Calculate control output
                duty_cycle = zone.calculate_control_output()
                zone.pump_duty_cycle = duty_cycle

                # Convert duty cycle to on/off with wider deadband and protection
                # ON threshold: 30% (configurable), OFF threshold: 5% (configurable)
                desired_state = None

                if duty_cycle > zone.pump_duty_on_threshold:
                    # Want to turn ON
                    if not zone.pump_state:
                        desired_state = True
                elif duty_cycle < zone.pump_duty_off_threshold:
                    # Want to turn OFF
                    if zone.pump_state:
                        desired_state = False

                # Check if state change is allowed (minimum runtime protection)
                if desired_state is not None:
                    can_change, reason = zone.can_change_pump_state(desired_state)

                    if can_change:
                        self._set_pump_state(zone_name, desired_state)
                        action = "ON" if desired_state else "OFF"
                        logging.info(f"{zone_name}: Pump {action} (duty: {duty_cycle:.1%}, temp: {zone.current_temp:.1f}°C, setpoint: {zone.setpoint:.1f}°C) - {reason}")
                    else:
                        # Protection preventing change
                        logging.debug(f"{zone_name}: Pump state change blocked - {reason}")

                # Track if zone is active (regardless of protection blocking)
                if zone.pump_state or duty_cycle > zone.pump_duty_on_threshold:
                    any_zone_active = True

            # Control boiler (on if ANY zone is active)
            self._set_boiler_state(any_zone_active)

        except Exception as e:
            logging.error(f"Error in control loop: {e}", exc_info=True)
        finally:
            # Schedule next run
            self.control_timer = threading.Timer(self.control_interval, self._run_control_loop)
            self.control_timer.daemon = True
            self.control_timer.start()

    def _set_pump_state(self, zone_name, state):
        """Set pump state for a zone"""
        zone = self.zones[zone_name]
        zone.set_pump_state(state)

        # Publish to MQTT
        pump_topic = zone.config['pump_control_topic']
        payload = {"state": "ON" if state else "OFF"}
        self.client.publish(pump_topic, json.dumps(payload), qos=1, retain=True)

    def _set_boiler_state(self, active):
        """Set boiler state and manage heartbeat"""
        if active == self.boiler_active:
            return  # No change

        self.boiler_active = active

        # Publish boiler state
        boiler_topic = self.config['boiler_control_topic']
        payload = {"state": "ON" if active else "OFF"}
        self.client.publish(boiler_topic, json.dumps(payload), qos=1, retain=True)

        # Publish heating_active state (for HA)
        self.client.publish("heating/boiler_active", json.dumps({"state": active}), qos=1, retain=True)

        # Manage heartbeat timer
        if active:
            self._start_heartbeat()
            self.boiler_on_time = time.time()
            logging.info("Boiler ON - heartbeat started")
        else:
            self._stop_heartbeat()
            self.boiler_on_time = None
            logging.info("Boiler OFF - heartbeat stopped")

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

    def _start_performance_reporting(self):
        """Start periodic performance reporting"""
        self._report_performance()

    def _report_performance(self):
        """Generate and publish thermal performance reports"""
        try:
            for zone_name, zone in self.zones.items():
                metrics = zone.thermal_monitor.get_insulation_metrics()
                rating = zone.thermal_monitor.get_insulation_rating()

                if metrics:
                    # Log performance metrics
                    logging.info(f"\n{'='*60}\n"
                               f"Thermal Performance Report - {zone_name}\n"
                               f"{'='*60}\n"
                               f"Insulation Rating: {rating}\n"
                               f"Heat Loss Rate: {metrics['avg_heat_loss_rate']:.3f} °C/hour\n"
                               f"Heat Gain Rate: {metrics['avg_heat_gain_rate']:.3f} °C/hour\n"
                               f"Heat Loss per °C Delta: {metrics['heat_loss_per_delta']:.4f} °C/h per °C\n"
                               f"Samples (cooling/heating): {metrics['sample_count_cooling']}/{metrics['sample_count_heating']}\n"
                               f"{'='*60}")

                    # Publish to MQTT for HA dashboard
                    report_topic = f"heating/{zone_name}/performance"
                    report_payload = {
                        'insulation_rating': rating,
                        'heat_loss_rate': round(metrics['avg_heat_loss_rate'], 3),
                        'heat_gain_rate': round(metrics['avg_heat_gain_rate'], 3) if metrics['avg_heat_gain_rate'] else None,
                        'heat_loss_per_delta': round(metrics['heat_loss_per_delta'], 4) if metrics['heat_loss_per_delta'] else None,
                        'timestamp': datetime.now().isoformat()
                    }
                    self.client.publish(report_topic, json.dumps(report_payload), qos=1, retain=True)

        except Exception as e:
            logging.error(f"Error in performance reporting: {e}", exc_info=True)
        finally:
            # Schedule next report
            self.report_timer = threading.Timer(self.report_interval, self._report_performance)
            self.report_timer.daemon = True
            self.report_timer.start()


def main():
    """Main entry point"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('heating_control.log')
        ]
    )

    # Get MQTT broker IP from environment or use default
    broker_ip = os.environ.get('MQTT_BROKER_IP', '192.168.1.60')

    # Create heating control instance
    logging.info("Starting heating control system...")
    heating = HeatingControl(broker_ip)

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
        if heating.report_timer:
            heating.report_timer.cancel()


if __name__ == '__main__':
    main()
