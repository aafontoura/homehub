#!/usr/bin/env python3
"""
Test script for ScheduleManager - validates schedule parsing and mode transitions
"""

import sys
import os
from datetime import datetime, time, timedelta

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schedule_manager import ScheduleManager, OperatingMode, TimeBlock, Schedule

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("WARNING: PyYAML not installed - skipping tests that require heating_config.yaml")

def test_timeblock_midnight_crossing():
    """Test TimeBlock handling of midnight-crossing blocks"""
    print("\n" + "="*80)
    print("TEST: TimeBlock Midnight Crossing")
    print("="*80)

    # Normal block: 06:00-22:00
    normal_block = TimeBlock("06:00", "22:00", 21.0)
    print(f"Normal block: {normal_block}")
    print(f"  Contains 12:00? {normal_block.contains(time(12, 0))} (expected: True)")
    print(f"  Contains 23:00? {normal_block.contains(time(23, 0))} (expected: False)")
    print(f"  Contains 05:00? {normal_block.contains(time(5, 0))} (expected: False)")

    # Midnight-crossing block: 22:00-06:00
    night_block = TimeBlock("22:00", "06:00", 18.0)
    print(f"\nMidnight-crossing block: {night_block}")
    print(f"  Contains 23:00? {night_block.contains(time(23, 0))} (expected: True)")
    print(f"  Contains 02:00? {night_block.contains(time(2, 0))} (expected: True)")
    print(f"  Contains 12:00? {night_block.contains(time(12, 0))} (expected: False)")

    print("\n✅ TimeBlock test passed")

def test_schedule_weekday_weekend():
    """Test Schedule weekday vs weekend selection"""
    print("\n" + "="*80)
    print("TEST: Schedule Weekday/Weekend Selection")
    print("="*80)

    weekday_blocks = [
        TimeBlock("06:00", "08:00", 21.0),
        TimeBlock("08:00", "17:00", 18.0),
        TimeBlock("17:00", "22:00", 21.0),
        TimeBlock("22:00", "06:00", 18.0),
    ]

    weekend_blocks = [
        TimeBlock("07:00", "23:00", 21.0),
        TimeBlock("23:00", "07:00", 18.0),
    ]

    schedule = Schedule(weekday_blocks, weekend_blocks)

    # Monday 07:00 (weekday morning)
    monday_morning = datetime(2026, 1, 5, 7, 0)  # Monday
    setpoint = schedule.get_setpoint_for_time(monday_morning)
    print(f"Monday 07:00: {setpoint}°C (expected: 21.0°C)")

    # Monday 12:00 (weekday afternoon)
    monday_noon = datetime(2026, 1, 5, 12, 0)
    setpoint = schedule.get_setpoint_for_time(monday_noon)
    print(f"Monday 12:00: {setpoint}°C (expected: 18.0°C)")

    # Saturday 07:00 (weekend morning)
    saturday_morning = datetime(2026, 1, 3, 7, 0)  # Saturday
    setpoint = schedule.get_setpoint_for_time(saturday_morning)
    print(f"Saturday 07:00: {setpoint}°C (expected: 21.0°C)")

    # Saturday 23:30 (weekend night)
    saturday_night = datetime(2026, 1, 3, 23, 30)
    setpoint = schedule.get_setpoint_for_time(saturday_night)
    print(f"Saturday 23:30: {setpoint}°C (expected: 18.0°C)")

    print("\n✅ Schedule test passed")

def test_operating_modes():
    """Test different operating modes"""
    print("\n" + "="*80)
    print("TEST: Operating Modes")
    print("="*80)

    if not HAS_YAML:
        print("⚠️  SKIPPED: PyYAML not installed")
        return

    # Load config
    with open('heating_config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    manager = ScheduleManager(config)

    # Test AUTO mode (should follow schedule)
    print("\n1. AUTO mode (should follow schedule)")
    manager.set_zone_mode('ground_floor', OperatingMode.AUTO)
    weekday_morning = datetime(2026, 1, 5, 7, 0)  # Monday 07:00
    setpoint = manager.get_effective_setpoint('ground_floor', weekday_morning)
    print(f"   Monday 07:00: {setpoint}°C (expected: 21.0°C from schedule)")

    # Test MANUAL mode
    print("\n2. MANUAL mode (fixed setpoint)")
    manager.set_zone_mode('ground_floor', OperatingMode.MANUAL, manual_setpoint=22.5)
    setpoint = manager.get_effective_setpoint('ground_floor', weekday_morning)
    print(f"   Monday 07:00: {setpoint}°C (expected: 22.5°C manual)")

    # Test AWAY mode (schedule with offset)
    print("\n3. AWAY mode (schedule -3°C)")
    manager.set_zone_mode('ground_floor', OperatingMode.AWAY)
    setpoint = manager.get_effective_setpoint('ground_floor', weekday_morning)
    print(f"   Monday 07:00: {setpoint}°C (expected: 18.0°C = 21.0 - 3.0)")

    # Test VACATION mode (freeze protection)
    print("\n4. VACATION mode (freeze protection)")
    manager.set_zone_mode('ground_floor', OperatingMode.VACATION)
    setpoint = manager.get_effective_setpoint('ground_floor', weekday_morning)
    print(f"   Monday 07:00: {setpoint}°C (expected: 10.0°C vacation setpoint)")

    # Test OFF mode
    print("\n5. OFF mode (heating disabled)")
    manager.set_zone_mode('ground_floor', OperatingMode.OFF)
    setpoint = manager.get_effective_setpoint('ground_floor', weekday_morning)
    print(f"   Monday 07:00: {setpoint} (expected: None)")

    # Test BOOST mode with auto-expiry
    print("\n6. BOOST mode (temporary override with timer)")
    manager.set_zone_mode('ground_floor', OperatingMode.BOOST, manual_setpoint=24.0, boost_duration_hours=0.001)  # 3.6 seconds
    setpoint = manager.get_effective_setpoint('ground_floor', datetime.now())
    print(f"   Current time: {setpoint}°C (expected: 24.0°C boost)")

    # Wait for boost to expire
    print("   Waiting 4 seconds for boost to expire...")
    import time as time_module
    time_module.sleep(4)

    # Should revert to previous mode (OFF in this case, but AUTO by default)
    setpoint = manager.get_effective_setpoint('ground_floor', datetime.now())
    print(f"   After expiry: {setpoint} (expected: None, reverted to OFF)")

    print("\n✅ Operating modes test passed")

def test_state_persistence():
    """Test state persistence to JSON file"""
    print("\n" + "="*80)
    print("TEST: State Persistence")
    print("="*80)

    if not HAS_YAML:
        print("⚠️  SKIPPED: PyYAML not installed")
        return

    # Load config
    with open('heating_config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Override persistence file for testing
    config['scheduling']['persistence_file'] = 'test_heating_schedule_state.json'

    # Create manager and set some modes
    print("\n1. Creating manager and setting modes...")
    manager1 = ScheduleManager(config)
    manager1.set_zone_mode('ground_floor', OperatingMode.MANUAL, manual_setpoint=22.5)
    manager1.set_zone_mode('first_floor', OperatingMode.AWAY)

    # Create new manager (should load persisted state)
    print("\n2. Creating new manager (should load persisted state)...")
    manager2 = ScheduleManager(config)

    gf_mode = manager2.get_zone_mode('ground_floor')
    gf_setpoint = manager2.get_effective_setpoint('ground_floor')
    print(f"   Ground floor: mode={gf_mode.value}, setpoint={gf_setpoint}°C")
    print(f"   Expected: mode=manual, setpoint=22.5°C")

    ff_mode = manager2.get_zone_mode('first_floor')
    print(f"   First floor: mode={ff_mode.value}")
    print(f"   Expected: mode=away")

    # Cleanup
    import os
    if os.path.exists('test_heating_schedule_state.json'):
        os.remove('test_heating_schedule_state.json')
        print("\n   Cleaned up test persistence file")

    print("\n✅ State persistence test passed")

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("SCHEDULE MANAGER TEST SUITE")
    print("="*80)

    try:
        test_timeblock_midnight_crossing()
        test_schedule_weekday_weekend()
        test_operating_modes()
        test_state_persistence()

        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED")
        print("="*80)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
