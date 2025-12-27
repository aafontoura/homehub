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

        # Calculate error (positive = need heating, negative = too hot)
        error = self.setpoint - measurement

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

        # Calculate total output
        output_raw = p_term + i_term + d_term

        # Clamp output to limits (0.0 = no heat, 1.0 = max heat)
        output = max(self.output_limits[0], min(self.output_limits[1], output_raw))

        # Log detailed PID calculation
        logging.debug(
            f"PID: setpoint={self.setpoint:.2f}°C, current={measurement:.2f}°C, error={error:.2f}°C | "
            f"P={p_term:.3f} (kp={self.kp}), I={i_term:.3f} (integral={self.integral:.2f}), D={d_term:.3f} | "
            f"Output: {output_raw:.3f} → {output:.3f} (clamped={output_raw != output})"
        )

        # Warn if integral is being clamped (anti-windup active)
        if integral_before_clamp != self.integral:
            logging.debug(f"PID: Integral anti-windup active (clamped from {integral_before_clamp:.2f} to {self.integral:.2f})")

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
        logging.debug(
            f"{self.zone_name}: Thermal monitor - HEATING period started | "
            f"Indoor: {temperature:.2f}°C, Outdoor: {outside_temp:.2f}°C, Delta: {temperature - outside_temp:.2f}°C"
        )

    def start_cooling_period(self, temperature, outside_temp):
        """Mark start of a cooling period (heating off)"""
        self.current_period_start = time.time()
        self.current_period_start_temp = temperature
        self.current_period_outside_temp = outside_temp
        self.current_period_heating = False
        logging.debug(
            f"{self.zone_name}: Thermal monitor - COOLING period started | "
            f"Indoor: {temperature:.2f}°C, Outdoor: {outside_temp:.2f}°C, Delta: {temperature - outside_temp:.2f}°C"
        )

    def end_period(self, temperature, outside_temp):
        """End current measurement period and calculate metrics"""
        if self.current_period_start is None:
            logging.debug(f"{self.zone_name}: Thermal monitor - No active period to end")
            return

        duration_hours = (time.time() - self.current_period_start) / 3600
        duration_minutes = duration_hours * 60

        if duration_hours < 0.25:  # Ignore periods < 15 minutes
            logging.debug(
                f"{self.zone_name}: Thermal monitor - Period too short to analyze "
                f"({duration_minutes:.0f} min < 15 min minimum)"
            )
            return

        temp_change = temperature - self.current_period_start_temp
        rate_per_hour = temp_change / duration_hours
        avg_indoor_temp = (self.current_period_start_temp + temperature) / 2
        temp_delta_outside = avg_indoor_temp - outside_temp

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

        period_type = "HEATING" if self.current_period_heating else "COOLING"

        if self.current_period_heating:
            self.heating_periods.append(period_data)
            logging.info(
                f"{self.zone_name}: {period_type} cycle complete | "
                f"Duration: {duration_hours:.1f}h ({duration_minutes:.0f} min) | "
                f"Temp: {self.current_period_start_temp:.2f}°C → {temperature:.2f}°C ({temp_change:+.2f}°C) | "
                f"Rate: {rate_per_hour:+.2f}°C/h | "
                f"Outside: {outside_temp:.1f}°C (Δ{temp_delta_outside:+.1f}°C from avg indoor)"
            )
        else:
            self.cooling_periods.append(period_data)
            logging.info(
                f"{self.zone_name}: {period_type} cycle complete | "
                f"Duration: {duration_hours:.1f}h ({duration_minutes:.0f} min) | "
                f"Temp: {self.current_period_start_temp:.2f}°C → {temperature:.2f}°C ({temp_change:+.2f}°C) | "
                f"Heat loss rate: {rate_per_hour:+.2f}°C/h | "
                f"Outside: {outside_temp:.1f}°C (Δ{temp_delta_outside:+.1f}°C from avg indoor)"
            )

        # Reset for next period
        self.current_period_start = None

    def get_insulation_metrics(self):
        """
        Calculate insulation quality metrics.

        Analyzes historical heating/cooling cycles to determine:
        - How fast the house loses heat when heating is OFF
        - How fast the house gains heat when heating is ON
        - How outdoor temperature affects indoor heat loss

        Returns:
            dict: Thermal performance metrics
        """
        if not self.cooling_periods:
            logging.debug(f"{self.zone_name}: Thermal metrics - No cooling data available yet")
            return None

        # Average heat loss rate (cooling) - negative value indicates temperature dropping
        avg_heat_loss = sum(p['rate_per_hour'] for p in self.cooling_periods) / len(self.cooling_periods)

        # Correlation with outside temperature
        if len(self.cooling_periods) > 5:
            # Calculate how heat loss varies with temperature delta
            # Better insulation = less dependency on outdoor temp
            losses = [(p['rate_per_hour'], p['temp_delta_outside']) for p in self.cooling_periods]
            # Simple correlation: more delta = more loss (negative rate)
            avg_loss_per_delta = sum(abs(loss) / delta if delta > 0 else 0
                                    for loss, delta in losses) / len(losses)
            logging.debug(
                f"{self.zone_name}: Thermal metrics - Heat loss correlation: "
                f"{avg_loss_per_delta:.4f}°C/h per °C outdoor delta (based on {len(self.cooling_periods)} samples)"
            )
        else:
            avg_loss_per_delta = None
            logging.debug(
                f"{self.zone_name}: Thermal metrics - Need more cooling samples for correlation "
                f"({len(self.cooling_periods)}/6 samples)"
            )

        # Average heating recovery rate
        if self.heating_periods:
            avg_heat_gain = sum(p['rate_per_hour'] for p in self.heating_periods) / len(self.heating_periods)
            logging.debug(
                f"{self.zone_name}: Thermal metrics - Avg heat gain: {avg_heat_gain:+.2f}°C/h "
                f"(based on {len(self.heating_periods)} heating cycles)"
            )
        else:
            avg_heat_gain = None
            logging.debug(f"{self.zone_name}: Thermal metrics - No heating data available yet")

        metrics = {
            'avg_heat_loss_rate': avg_heat_loss,  # °C/hour when not heating
            'avg_heat_gain_rate': avg_heat_gain,  # °C/hour when heating
            'heat_loss_per_delta': avg_loss_per_delta,  # Heat loss per °C difference with outside
            'sample_count_cooling': len(self.cooling_periods),
            'sample_count_heating': len(self.heating_periods)
        }

        logging.debug(
            f"{self.zone_name}: Thermal metrics summary | "
            f"Heat loss: {avg_heat_loss:+.2f}°C/h (cooling) | "
            f"Heat gain: {avg_heat_gain:+.2f}°C/h (heating) | " if avg_heat_gain else ""
            f"Samples: {len(self.cooling_periods)} cool, {len(self.heating_periods)} heat"
        )

        return metrics

    def get_insulation_rating(self):
        """
        Get a simple insulation quality rating based on heat loss rate.

        Rating benchmarks (typical values for 10-15°C indoor/outdoor delta):
        - Excellent: < 0.3°C/h loss (well-insulated modern home)
        - Good: 0.3-0.5°C/h (decent insulation)
        - Fair: 0.5-0.8°C/h (average/older home)
        - Poor: > 0.8°C/h (poor insulation, drafty)

        Returns:
            str: Rating (Excellent/Good/Fair/Poor/Unknown)
        """
        metrics = self.get_insulation_metrics()
        if not metrics or metrics['avg_heat_loss_rate'] is None:
            return "Unknown (insufficient data)"

        # Heat loss rate is negative (temperature dropping), so take absolute value
        loss_rate = abs(metrics['avg_heat_loss_rate'])

        if loss_rate < 0.3:
            rating = "Excellent"
        elif loss_rate < 0.5:
            rating = "Good"
        elif loss_rate < 0.8:
            rating = "Fair"
        else:
            rating = "Poor"

        logging.debug(
            f"{self.zone_name}: Insulation rating - {rating} "
            f"(heat loss: {loss_rate:.2f}°C/h based on {metrics['sample_count_cooling']} samples)"
        )

        return rating


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
        self.window_detection_enabled = config.get('window_detection_enabled', True)  # Default: enabled

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
        # Check if window detection is enabled
        if not self.window_detection_enabled:
            # If window detection is disabled, reset window state if it was open
            if self.window_open:
                logging.info(f"{self.name}: Window detection DISABLED - clearing window open state")
                self.window_open = False
                self.window_open_time = None
            return False

        if len(self.temp_history) < 20:
            logging.debug(f"{self.name}: Window detection skipped (insufficient history: {len(self.temp_history)}/20)")
            return False

        # Check short-term drop (1 minute)
        recent_1min = self._get_temp_range(seconds=60)
        if len(recent_1min) < 2:
            logging.debug(f"{self.name}: Window detection skipped (insufficient 1min data: {len(recent_1min)}/2)")
            return False

        temp_drop_1min = recent_1min[0]['temp'] - recent_1min[-1]['temp']
        time_diff_1min = recent_1min[-1]['time'] - recent_1min[0]['time']
        rate_1min = (temp_drop_1min / time_diff_1min) * 60  # Convert to °C/min

        # Check medium-term drop (2 minutes)
        recent_2min = self._get_temp_range(seconds=120)
        if len(recent_2min) < 2:
            logging.debug(f"{self.name}: Window detection skipped (insufficient 2min data: {len(recent_2min)}/2)")
            return False

        temp_drop_2min = recent_2min[0]['temp'] - recent_2min[-1]['temp']
        time_diff_2min = recent_2min[-1]['time'] - recent_2min[0]['time']
        rate_2min = (temp_drop_2min / time_diff_2min) * 60

        # Get thresholds
        threshold_1min = self.config.get('window_detection_threshold_1min', 0.3)
        threshold_2min = self.config.get('window_detection_threshold_2min', 0.2)

        # Log temperature change rates for debugging
        temp_start_1min = recent_1min[0]['temp']
        temp_end_1min = recent_1min[-1]['temp']
        temp_start_2min = recent_2min[0]['temp']
        temp_end_2min = recent_2min[-1]['temp']

        logging.debug(
            f"{self.name}: Window detection analysis | "
            f"1min: {temp_start_1min:.2f}°C → {temp_end_1min:.2f}°C = {rate_1min:+.3f}°C/min (threshold: {threshold_1min:.2f}) | "
            f"2min: {temp_start_2min:.2f}°C → {temp_end_2min:.2f}°C = {rate_2min:+.3f}°C/min (threshold: {threshold_2min:.2f})"
        )

        # Window detected if rapid temperature drop exceeds thresholds
        # Positive rate = temperature dropping (potential window opening)
        if rate_1min > threshold_1min or rate_2min > threshold_2min:
            if not self.window_open:
                trigger_reason = []
                if rate_1min > threshold_1min:
                    trigger_reason.append(f"1min drop: {rate_1min:.2f}°C/min > {threshold_1min:.2f}")
                if rate_2min > threshold_2min:
                    trigger_reason.append(f"2min drop: {rate_2min:.2f}°C/min > {threshold_2min:.2f}")

                logging.warning(
                    f"{self.name}: WINDOW OPENED! {' AND '.join(trigger_reason)} | "
                    f"Temp drop: {temp_start_1min:.2f}°C → {temp_end_1min:.2f}°C in 1min"
                )
                self.window_open = True
                self.window_open_time = time.time()
            return True

        # Window closing detection: temperature stabilizes (near-zero change rate)
        if self.window_open:
            stabilization_threshold = 0.1  # °C/min
            if abs(rate_1min) < stabilization_threshold and abs(rate_2min) < stabilization_threshold:
                open_duration = time.time() - (self.window_open_time or time.time())
                logging.info(
                    f"{self.name}: WINDOW CLOSED (temperature stabilized) | "
                    f"Open for: {open_duration/60:.1f} min | "
                    f"Rates: 1min={rate_1min:+.3f}°C/min, 2min={rate_2min:+.3f}°C/min (both < {stabilization_threshold})"
                )
                self.window_open = False
                self.window_open_time = None
            else:
                logging.debug(
                    f"{self.name}: Window still open (temp not stabilized: 1min={rate_1min:+.3f}, 2min={rate_2min:+.3f}°C/min)"
                )

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
        # Detect state changes for thermal monitoring and cycle tracking
        if new_state != self.pump_state:
            current_time = time.time()

            if new_state:
                # Pump turning ON - end cooling period, start heating
                if self.current_temp and self.outside_temp:
                    self.thermal_monitor.end_period(self.current_temp, self.outside_temp)
                    self.thermal_monitor.start_heating_period(self.current_temp, self.outside_temp)

                # Calculate how long pump was OFF
                off_duration = (current_time - self.pump_last_off_time) / 60 if self.pump_last_off_time else 0

                self.pump_on_time = current_time
                self.pump_last_on_time = current_time
                self.pump_cycle_count += 1

                logging.info(
                    f"{self.name}: PUMP ON (Cycle #{self.pump_cycle_count}) | "
                    f"Was OFF for: {off_duration:.1f} min | "
                    f"Temp: {self.current_temp:.1f}°C → target: {self.setpoint:.1f}°C" +
                    (" | [MANUAL OVERRIDE]" if manual else "")
                )
            else:
                # Pump turning OFF - end heating period, start cooling
                if self.current_temp and self.outside_temp:
                    self.thermal_monitor.end_period(self.current_temp, self.outside_temp)
                    self.thermal_monitor.start_cooling_period(self.current_temp, self.outside_temp)

                # Calculate how long pump was ON
                on_duration = (current_time - self.pump_on_time) / 60 if self.pump_on_time else 0

                self.pump_off_time = current_time
                self.pump_last_off_time = current_time

                logging.info(
                    f"{self.name}: PUMP OFF (End of cycle #{self.pump_cycle_count}) | "
                    f"Runtime: {on_duration:.1f} min | "
                    f"Temp: {self.current_temp:.1f}°C (target: {self.setpoint:.1f}°C)" +
                    (" | [MANUAL OVERRIDE]" if manual else "")
                )
                self.pump_on_time = None

            # Track if this was a manual override
            self.pump_manual_override = manual

            # Report hourly cycle statistics
            hours_elapsed = (current_time - self.pump_cycle_hour_start) / 3600
            if hours_elapsed >= 1.0:
                cycles_per_hour = self.pump_cycle_count / hours_elapsed
                max_healthy_cycles = 6  # From pump protection design

                logging.info(
                    f"{self.name}: Hourly pump cycle report | "
                    f"Cycles: {self.pump_cycle_count} in {hours_elapsed:.1f}h = {cycles_per_hour:.1f} cycles/hour | "
                    f"Health: {'✓ GOOD' if cycles_per_hour <= max_healthy_cycles else '⚠ HIGH'} (target ≤{max_healthy_cycles}/h)"
                )

                if cycles_per_hour > max_healthy_cycles:
                    logging.warning(
                        f"{self.name}: EXCESSIVE PUMP CYCLING DETECTED! {cycles_per_hour:.1f} cycles/hour > {max_healthy_cycles}/hour | "
                        f"This may reduce pump lifespan. Consider adjusting PID parameters or deadband thresholds."
                    )

                # Reset counter for next hour
                self.pump_cycle_count = 0
                self.pump_cycle_hour_start = current_time
        else:
            # No state change - pump staying in same state
            logging.debug(f"{self.name}: Pump state unchanged (remains {'ON' if new_state else 'OFF'})")

        self.pump_state = new_state

    def can_change_pump_state(self, desired_state):
        """
        Check if pump state can be changed based on minimum runtime protection.

        Pump protection prevents excessive cycling by enforcing:
        - Minimum ON time (default 10 min) - protects pump motor from frequent starts
        - Minimum OFF time (default 10 min) - allows system to stabilize

        Args:
            desired_state: Desired pump state (True=ON, False=OFF)

        Returns:
            tuple: (can_change: bool, reason: str)
        """
        # Manual overrides always allowed
        # if self.pump_manual_override:
        #     return (True, "Manual override - protection bypassed")

        current_time = time.time()

        if desired_state and not self.pump_state:
            # Request: Turn pump ON (currently OFF)
            if self.pump_last_off_time is None:
                logging.info(f"{self.name}: Pump protection - First startup, allowing pump ON")
                return (True, "First startup")

            off_duration_minutes = (current_time - self.pump_last_off_time) / 60
            if off_duration_minutes < self.pump_min_off_minutes:
                remaining = self.pump_min_off_minutes - off_duration_minutes
                logging.debug(
                    f"{self.name}: Pump protection BLOCKING ON request | "
                    f"Min OFF time: {self.pump_min_off_minutes} min | "
                    f"Currently OFF for: {off_duration_minutes:.1f} min | "
                    f"Need to wait: {remaining:.1f} min more"
                )
                return (False, f"Pump must stay OFF for {self.pump_min_off_minutes} min (off {off_duration_minutes:.1f} min, need {remaining:.1f} more)")

            logging.debug(
                f"{self.name}: Pump protection ALLOWING ON request | "
                f"OFF duration: {off_duration_minutes:.1f} min >= {self.pump_min_off_minutes} min"
            )
            return (True, f"Pump has been OFF for {off_duration_minutes:.1f} min")

        elif not desired_state and self.pump_state:
            # Request: Turn pump OFF (currently ON)
            if self.pump_last_on_time is None:
                logging.info(f"{self.name}: Pump protection - Initial state, allowing pump OFF")
                return (True, "Initial state")

            on_duration_minutes = (current_time - self.pump_last_on_time) / 60
            if on_duration_minutes < self.pump_min_on_minutes:
                remaining = self.pump_min_on_minutes - on_duration_minutes
                logging.debug(
                    f"{self.name}: Pump protection BLOCKING OFF request | "
                    f"Min ON time: {self.pump_min_on_minutes} min | "
                    f"Currently ON for: {on_duration_minutes:.1f} min | "
                    f"Need to wait: {remaining:.1f} min more"
                )
                return (False, f"Pump must stay ON for {self.pump_min_on_minutes} min (on {on_duration_minutes:.1f} min, need {remaining:.1f} more)")

            logging.debug(
                f"{self.name}: Pump protection ALLOWING OFF request | "
                f"ON duration: {on_duration_minutes:.1f} min >= {self.pump_min_on_minutes} min"
            )
            return (True, f"Pump has been ON for {on_duration_minutes:.1f} min")

        # No state change requested (already in desired state)
        logging.debug(f"{self.name}: Pump protection - No state change needed (desired={desired_state}, current={self.pump_state})")
        return (True, "No state change")


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

        # Window detection enable/disable (global)
        topics.append("heating/window_detection/set")

        self._subscribe_to_topics(topics)

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

            # Window detection enable/disable (global - applies to all zones)
            if topic == "heating/window_detection/set":
                enabled = payload.get('enabled', True) if isinstance(payload, dict) else bool(payload)
                for zone_name, zone in self.zones.items():
                    zone.window_detection_enabled = enabled
                logging.info(f"Window detection globally {'ENABLED' if enabled else 'DISABLED'} for all zones")
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
            logging.debug(f"====== CONTROL LOOP START (interval: {self.control_interval}s) ======")

            # Update each zone
            any_zone_active = False
            zones_requesting_heat = []

            for zone_name, zone in self.zones.items():
                logging.debug(f"--- Processing zone: {zone_name} ---")

                # Check for window opening (auto-safety feature)
                window_open = zone.detect_window_open()

                if window_open:
                    # Window open - turn off heating for this zone for safety/efficiency
                    if zone.pump_state:
                        self._set_pump_state(zone_name, False)
                        logging.warning(f"{zone_name}: Pump forced OFF due to open window (safety)")
                    else:
                        logging.debug(f"{zone_name}: Heating disabled (window open, pump already OFF)")
                    continue

                
                # Calculate PID control output (0.0 = no heat, 1.0 = max heat)
                duty_cycle = zone.calculate_control_output()
                zone.pump_duty_cycle = duty_cycle
                logging.debug(f"{zone_name}: PID duty cycle: {duty_cycle:.1%} | Temp: {zone.current_temp}°C → Setpoint: {zone.setpoint}°C")

                # Determine desired pump state using deadband hysteresis
                # ON threshold: 30% prevents pump from turning on for tiny heating needs
                # OFF threshold: 5% prevents pump from turning off when barely maintaining temp
                # Deadband prevents rapid cycling between 5-30%
                desired_state = None
                current_state = "ON" if zone.pump_state else "OFF"

                if duty_cycle > zone.pump_duty_on_threshold:
                    # PID requesting significant heat - want pump ON
                    if not zone.pump_state:
                        desired_state = True
                        logging.debug(
                            f"{zone_name}: Requesting pump ON | "
                            f"Duty: {duty_cycle:.1%} > ON threshold {zone.pump_duty_on_threshold:.1%} | "
                            f"Temp: {zone.current_temp:.2f}°C → {zone.setpoint:.2f}°C (error: {zone.setpoint - zone.current_temp:+.2f}°C)"
                        )
                    else:
                        logging.debug(
                            f"{zone_name}: Pump staying ON | "
                            f"Duty: {duty_cycle:.1%} > OFF threshold {zone.pump_duty_off_threshold:.1%}"
                        )

                elif duty_cycle < zone.pump_duty_off_threshold:
                    # PID requesting minimal/no heat - want pump OFF
                    if zone.pump_state:
                        desired_state = False
                        logging.debug(
                            f"{zone_name}: Requesting pump OFF | "
                            f"Duty: {duty_cycle:.1%} < OFF threshold {zone.pump_duty_off_threshold:.1%} | "
                            f"Temp: {zone.current_temp:.2f}°C (close to setpoint {zone.setpoint:.2f}°C)"
                        )
                    else:
                        logging.debug(
                            f"{zone_name}: Pump staying OFF | "
                            f"Duty: {duty_cycle:.1%} < OFF threshold {zone.pump_duty_off_threshold:.1%}"
                        )
                else:
                    # Duty cycle in deadband (5-30%) - maintain current state to prevent cycling
                    logging.debug(
                            f"{zone_name}: In DEADBAND (pump stays {current_state}) | "
                            f"Duty: {duty_cycle:.1%} between OFF ({zone.pump_duty_off_threshold:.1%}) "
                            f"and ON ({zone.pump_duty_on_threshold:.1%}) thresholds"
                        )

                # Apply pump protection (minimum runtime limits)
                if desired_state is not None:
                    can_change, reason = zone.can_change_pump_state(desired_state)

                    if can_change:
                        self._set_pump_state(zone_name, desired_state)
                        action = "ON" if desired_state else "OFF"
                        logging.info(
                            f"{zone_name}: Pump {action} | "
                            f"Duty: {duty_cycle:.1%} | "
                            f"Temp: {zone.current_temp:.1f}°C → {zone.setpoint:.1f}°C | "
                            f"{reason}"
                        )
                    else:
                        # Pump protection blocking the state change
                        action = "ON" if desired_state else "OFF"
                        logging.info(
                            f"{zone_name}: Pump {action} request BLOCKED by protection | "
                            f"{reason}"
                        )

                # Track if zone is requesting heat (for boiler control)
                # Zone is "active" if pump is ON or duty cycle wants it ON
                if zone.pump_state or duty_cycle > zone.pump_duty_on_threshold:
                    any_zone_active = True
                    zones_requesting_heat.append(zone_name)

            # Control boiler based on zone activity
            if any_zone_active:
                logging.debug(f"Zones requesting heat: {', '.join(zones_requesting_heat)}")
            else:
                logging.debug("No zones requesting heat")

            self._set_boiler_state(any_zone_active)

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
        pump_topic = zone.config['pump_control_topic']
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
        boiler_topic = self.config['boiler_control_topic']
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
    broker_ip = os.environ.get('MQTT_BROKER_IP', '192.168.1.60')

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
        if heating.report_timer:
            heating.report_timer.cancel()


if __name__ == '__main__':
    main()
