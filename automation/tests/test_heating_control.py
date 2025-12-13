"""
Tests for heating control system
"""

import pytest
import time
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from heating_control import PIDController, HeatingZone


class TestPIDController:
    """Test PID controller functionality"""

    def test_pid_initialization(self):
        """Test PID controller initializes correctly"""
        pid = PIDController(kp=5.0, ki=0.1, kd=1.0, setpoint=20.0)
        assert pid.kp == 5.0
        assert pid.ki == 0.1
        assert pid.kd == 1.0
        assert pid.setpoint == 20.0
        assert pid.integral == 0.0

    def test_pid_proportional_term(self):
        """Test proportional term increases output when below setpoint"""
        pid = PIDController(kp=5.0, ki=0.0, kd=0.0, setpoint=20.0)

        # Temperature below setpoint should give positive output
        output = pid.update(measurement=18.0)
        assert output > 0, "Output should be positive when below setpoint"

        # Larger error should give larger output
        output_large_error = pid.update(measurement=15.0)
        assert output_large_error > output, "Larger error should give larger output"

    def test_pid_zero_error(self):
        """Test PID output when at setpoint"""
        pid = PIDController(kp=5.0, ki=0.0, kd=0.0, setpoint=20.0)
        output = pid.update(measurement=20.0)
        # With no integral or derivative terms, output should be zero
        assert abs(output) < 0.01, "Output should be near zero at setpoint"

    def test_pid_integral_windup_prevention(self):
        """Test that integral term is clamped to prevent windup"""
        pid = PIDController(kp=1.0, ki=1.0, kd=0.0, setpoint=20.0)

        # Simulate sustained error for long time
        for _ in range(100):
            pid.update(measurement=10.0)
            time.sleep(0.01)

        # Integral should be clamped
        assert abs(pid.integral) < 100, "Integral should be limited to prevent windup"

    def test_pid_setpoint_change(self):
        """Test changing setpoint mid-operation"""
        pid = PIDController(kp=5.0, ki=0.1, kd=1.0, setpoint=20.0)

        pid.update(measurement=19.0)
        pid.set_setpoint(22.0)

        assert pid.setpoint == 22.0, "Setpoint should update"
        output = pid.update(measurement=19.0)
        assert output > 0, "Should increase output for new higher setpoint"

    def test_pid_output_limits(self):
        """Test that PID output is clamped to limits"""
        pid = PIDController(kp=10.0, ki=1.0, kd=0.0, setpoint=20.0, output_limits=(0, 1))

        # Very large error should still clamp output
        output = pid.update(measurement=-100.0)
        assert output <= 1.0, "Output should not exceed upper limit"
        assert output >= 0.0, "Output should not go below lower limit"

    def test_pid_reset(self):
        """Test PID reset clears integral and derivative terms"""
        pid = PIDController(kp=5.0, ki=0.1, kd=1.0, setpoint=20.0)

        # Build up some integral
        for _ in range(10):
            pid.update(measurement=18.0)

        initial_integral = pid.integral
        assert initial_integral != 0, "Integral should build up"

        pid.reset()
        assert pid.integral == 0.0, "Integral should be reset"
        assert pid.last_error == 0.0, "Last error should be reset"


class TestHeatingZone:
    """Test heating zone functionality"""

    def test_zone_initialization(self):
        """Test heating zone initializes correctly"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'history_length': 120
        }
        zone = HeatingZone("test_zone", config)

        assert zone.name == "test_zone"
        assert zone.setpoint == 20.0
        assert zone.current_temp is None
        assert zone.window_open is False

    def test_temperature_update(self):
        """Test temperature updates are recorded in history"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'history_length': 120
        }
        zone = HeatingZone("test_zone", config)

        zone.update_temperature(19.5)
        assert zone.current_temp == 19.5
        assert len(zone.temp_history) == 1
        assert zone.temp_history[0]['temp'] == 19.5

    def test_window_detection_no_history(self):
        """Test window detection with insufficient history"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'history_length': 120,
            'window_detection_threshold_1min': 0.3,
            'window_detection_threshold_2min': 0.2
        }
        zone = HeatingZone("test_zone", config)

        # With no history, should not detect window
        assert zone.detect_window_open() is False

    def test_window_detection_rapid_drop(self):
        """Test window detection with rapid temperature drop"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'history_length': 120,
            'window_detection_threshold_1min': 0.3,
            'window_detection_threshold_2min': 0.2
        }
        zone = HeatingZone("test_zone", config)

        # Simulate rapid temperature drop (window opening)
        base_time = time.time()
        for i in range(30):
            # Drop 0.5°C per minute = 0.0083°C per second
            temp = 20.0 - (i * 0.5 / 60)
            zone.temp_history.append({
                'temp': temp,
                'time': base_time + i * 2  # Every 2 seconds
            })

        # Should detect window opening
        assert zone.detect_window_open() is True
        assert zone.window_open is True

    def test_window_detection_slow_drop(self):
        """Test window detection with slow temperature drop (no window)"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'history_length': 120,
            'window_detection_threshold_1min': 0.3,
            'window_detection_threshold_2min': 0.2
        }
        zone = HeatingZone("test_zone", config)

        # Simulate slow temperature drop (normal cooling)
        base_time = time.time()
        for i in range(30):
            # Drop 0.1°C per minute = slow cooling
            temp = 20.0 - (i * 0.1 / 60)
            zone.temp_history.append({
                'temp': temp,
                'time': base_time + i * 2
            })

        # Should NOT detect window opening
        assert zone.detect_window_open() is False

    def test_weather_compensation_cold_outside(self):
        """Test weather compensation increases setpoint when cold outside"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'weather_compensation_curve': 0.1,
            'reference_outside_temp': 10.0,
            'min_setpoint': 18.0,
            'max_setpoint': 23.0
        }
        zone = HeatingZone("test_zone", config)

        # Outside is 0°C (cold)
        compensated = zone.calculate_weather_compensated_setpoint(outside_temp=0.0)
        # Should be: 20 - 0.1 * (0 - 10) = 20 + 1 = 21°C
        assert compensated == pytest.approx(21.0, abs=0.01)

    def test_weather_compensation_warm_outside(self):
        """Test weather compensation decreases setpoint when warm outside"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'weather_compensation_curve': 0.1,
            'reference_outside_temp': 10.0,
            'min_setpoint': 18.0,
            'max_setpoint': 23.0
        }
        zone = HeatingZone("test_zone", config)

        # Outside is 20°C (warm)
        compensated = zone.calculate_weather_compensated_setpoint(outside_temp=20.0)
        # Should be: 20 - 0.1 * (20 - 10) = 20 - 1 = 19°C
        assert compensated == pytest.approx(19.0, abs=0.01)

    def test_weather_compensation_clamping(self):
        """Test weather compensation respects min/max limits"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'weather_compensation_curve': 0.5,
            'reference_outside_temp': 10.0,
            'min_setpoint': 18.0,
            'max_setpoint': 22.0
        }
        zone = HeatingZone("test_zone", config)

        # Very cold outside would calculate 25°C, but should clamp to max
        compensated_cold = zone.calculate_weather_compensated_setpoint(outside_temp=-10.0)
        assert compensated_cold <= 22.0, "Should clamp to max setpoint"

        # Very warm outside would calculate 15°C, but should clamp to min
        compensated_warm = zone.calculate_weather_compensated_setpoint(outside_temp=30.0)
        assert compensated_warm >= 18.0, "Should clamp to min setpoint"

    def test_control_output_below_setpoint(self):
        """Test control output increases when below setpoint"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.1,
            'pid_kd': 1.0,
            'history_length': 120
        }
        zone = HeatingZone("test_zone", config)

        zone.current_temp = 18.0
        output = zone.calculate_control_output()

        assert output > 0.0, "Output should be positive when below setpoint"

    def test_control_output_at_setpoint(self):
        """Test control output is low when at setpoint"""
        config = {
            'default_setpoint': 20.0,
            'pid_kp': 5.0,
            'pid_ki': 0.0,  # No integral term
            'pid_kd': 0.0,  # No derivative term
            'history_length': 120
        }
        zone = HeatingZone("test_zone", config)

        zone.current_temp = 20.0
        output = zone.calculate_control_output()

        assert output < 0.1, "Output should be near zero at setpoint"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
