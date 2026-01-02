# Phase 2: Redundant Sensor Support Implementation Plan

**Status:** Planned (Not Yet Implemented)
**Priority:** MEDIUM (RISK-013 Mitigation #13)
**Estimated Effort:** Week 2-3
**Target Version:** 2.0

## Overview

Add secondary temperature sensor support per heating zone with cross-validation logic and automatic fallback to conservative readings when sensors disagree. This implements RISK-013 mitigation #13 for defense-in-depth sensor redundancy.

## Business Value

- **Reliability**: Heating continues even if one sensor fails
- **Safety**: Automatic detection of sensor disagreement prevents erroneous heating decisions
- **Maintenance**: Proactive alerts when sensors disagree indicate calibration issues or failure
- **Cost**: ~€30 per zone for secondary sensor vs potential property damage from sensor failure

## Configuration Changes

### 1. Update `heating_config.yaml`

Add optional secondary sensor configuration per zone:

```yaml
zones:
  ground_floor:
    # Existing configuration
    temperature_sensor_topic: "zigbee2mqtt/Living Room Sensor"

    # NEW - Optional secondary sensor
    temperature_sensor_secondary_topic: "zigbee2mqtt/Living Room Sensor 2"

    # NEW - Alert threshold (optional, default 2.0°C)
    sensor_disagreement_threshold: 2.0

    # ... rest of existing configuration
    pump_control_topic: "zigbee2mqtt/Pump UFH Ground Floor"
    default_setpoint: 20.0
    min_setpoint: 18.0
    max_setpoint: 23.0
    controller_type: "onoff"
    hysteresis: 0.2

  first_floor:
    temperature_sensor_topic: "zigbee2mqtt/First Floor Sensor"
    temperature_sensor_secondary_topic: "zigbee2mqtt/First Floor Sensor 2"
    sensor_disagreement_threshold: 2.0
    # ... rest of configuration
```

**Backward Compatibility:** Zones without `temperature_sensor_secondary_topic` continue working exactly as before with single sensor.

---

## Code Changes

### 2. Update `heating_zone.py`

**Location:** `homehub/automation/src/heating_zone.py`

#### Add New Fields to `__init__()`:

```python
class HeatingZone:
    def __init__(self, name, config):
        # ... existing initialization

        # Secondary sensor support (SR-SF-009)
        self.current_temp_secondary = None  # Secondary sensor temperature
        self.last_temp_secondary_update_time = None  # Timestamp for staleness detection
        self.has_secondary_sensor = 'temperature_sensor_secondary_topic' in config
        self.sensor_disagreement_threshold = config.get('sensor_disagreement_threshold', 2.0)

        if self.has_secondary_sensor:
            logging.info(
                f"{self.name}: Redundant sensor configured | "
                f"Secondary: {config['temperature_sensor_secondary_topic']} | "
                f"Disagreement threshold: {self.sensor_disagreement_threshold}°C"
            )
```

#### Add New Methods:

```python
def update_temperature_secondary(self, new_temp):
    """
    Update secondary sensor temperature reading and record timestamp.

    Args:
        new_temp: Current measured temperature from secondary sensor in °C
    """
    self.current_temp_secondary = new_temp
    self.last_temp_secondary_update_time = time.time()

def get_validated_temperature(self):
    """
    Get validated temperature using cross-validation logic (SR-SF-009).

    Returns:
        float: Validated temperature in °C (or None if no sensors available)

    Cross-validation logic:
    1. Both sensors available and agree (within threshold): return average
    2. Sensors disagree (>threshold): return lower value (conservative, safer for heating)
    3. Only primary available: return primary
    4. Only secondary available: return secondary (fallback)
    5. Neither available: return None
    """
    primary_available = self.current_temp is not None
    secondary_available = self.current_temp_secondary is not None and self.has_secondary_sensor

    # Case 5: Neither sensor available
    if not primary_available and not secondary_available:
        return None

    # Case 3: Only primary available
    if primary_available and not secondary_available:
        return self.current_temp

    # Case 4: Only secondary available (fallback)
    if secondary_available and not primary_available:
        logging.warning(
            f"{self.name}: Using SECONDARY sensor only (primary unavailable) | "
            f"Temp: {self.current_temp_secondary:.1f}°C"
        )
        return self.current_temp_secondary

    # Case 1 & 2: Both sensors available - check disagreement
    temp_diff = abs(self.current_temp - self.current_temp_secondary)

    if temp_diff <= self.sensor_disagreement_threshold:
        # Case 1: Sensors agree - use average for best accuracy
        avg_temp = (self.current_temp + self.current_temp_secondary) / 2.0
        logging.debug(
            f"{self.name}: Sensors agree | "
            f"Primary: {self.current_temp:.1f}°C, "
            f"Secondary: {self.current_temp_secondary:.1f}°C, "
            f"Average: {avg_temp:.1f}°C"
        )
        return avg_temp
    else:
        # Case 2: Sensors disagree - use lower value (conservative)
        conservative_temp = min(self.current_temp, self.current_temp_secondary)
        logging.warning(
            f"{self.name}: SENSOR DISAGREEMENT | "
            f"Primary: {self.current_temp:.1f}°C, "
            f"Secondary: {self.current_temp_secondary:.1f}°C, "
            f"Diff: {temp_diff:.1f}°C (threshold: {self.sensor_disagreement_threshold}°C) | "
            f"Using conservative: {conservative_temp:.1f}°C"
        )
        # Note: Disagreement alert is published by heating_control.py
        return conservative_temp

def are_all_sensors_stale(self):
    """
    Check if ALL configured sensors are stale (SR-SF-007 with redundancy).

    Returns:
        bool: True only if all sensors are stale, False if any sensor is fresh

    Logic:
    - If only primary configured: check primary staleness
    - If secondary configured: BOTH must be stale to return True
    - This allows heating to continue if either sensor is working
    """
    primary_stale = self.is_sensor_stale()  # Uses existing SR-SF-007 logic

    if not self.has_secondary_sensor:
        return primary_stale  # Single sensor mode

    # Check secondary staleness
    if self.last_temp_secondary_update_time is None:
        secondary_stale = True  # Never received update
    else:
        elapsed_minutes = (time.time() - self.last_temp_secondary_update_time) / 60
        secondary_stale = elapsed_minutes > self.sensor_timeout_minutes

    # Both must be stale to trigger shutdown
    both_stale = primary_stale and secondary_stale

    if both_stale:
        logging.warning(
            f"{self.name}: ALL SENSORS STALE | "
            f"Primary and secondary both exceeded {self.sensor_timeout_minutes} min timeout"
        )
    elif primary_stale and not secondary_stale:
        logging.info(
            f"{self.name}: Primary sensor stale, but secondary sensor active - "
            f"heating continues using secondary"
        )
    elif secondary_stale and not primary_stale:
        logging.info(
            f"{self.name}: Secondary sensor stale, but primary sensor active - "
            f"heating continues using primary"
        )

    return both_stale
```

#### Modify Existing Methods:

**Update `calculate_control_output()`:**

```python
def calculate_control_output(self):
    """
    Calculate pump control output using configured controller.

    Returns:
        float: Duty cycle (0.0 to 1.0)
    """
    # Get validated temperature (cross-validation logic)
    validated_temp = self.get_validated_temperature()

    if validated_temp is None:
        return 0.0  # No temperature data available

    # Get controller output (returns 0-100%)
    output = self.controller.calculate_output(validated_temp, self.setpoint) / 100.0

    return output
```

---

### 3. Update `heating_control.py`

**Location:** `homehub/automation/src/heating_control.py`

#### Modify `_setup_subscriptions()`:

```python
def _setup_subscriptions(self):
    """Subscribe to all necessary MQTT topics"""
    topics = []

    # Temperature sensors (primary and secondary)
    if self.config and 'zones' in self.config:
        for zone_name, zone_config in self.config['zones'].items():
            # Primary sensor
            sensor_topic = zone_config['temperature_sensor_topic']
            topics.append(sensor_topic)
            logging.info(f"Subscribing to {zone_name} primary sensor: {sensor_topic}")

            # Secondary sensor (if configured)
            if 'temperature_sensor_secondary_topic' in zone_config:
                secondary_topic = zone_config['temperature_sensor_secondary_topic']
                topics.append(secondary_topic)
                logging.info(f"Subscribing to {zone_name} secondary sensor: {secondary_topic}")

    # ... rest of existing subscription logic
```

#### Modify `handle_message()`:

```python
def handle_message(self, topic, payload):
    """Handle incoming MQTT messages"""
    try:
        logging.debug(f"Received message on {topic}: {payload}")

        # Temperature sensor updates (primary and secondary)
        for zone_name, zone in self.zones.items():
            # Primary sensor
            if topic == zone.config['temperature_sensor_topic']:
                temp = self._extract_temperature(payload)
                if temp is not None:
                    zone.update_temperature(temp)
                    logging.debug(f"{zone_name} primary temperature: {temp}°C")
                else:
                    logging.warning(f"Invalid temperature payload for {zone_name} primary: {payload}")
                return

            # Secondary sensor (if configured)
            if zone.has_secondary_sensor and topic == zone.config.get('temperature_sensor_secondary_topic'):
                temp = self._extract_temperature(payload)
                if temp is not None:
                    zone.update_temperature_secondary(temp)
                    logging.debug(f"{zone_name} secondary temperature: {temp}°C")
                else:
                    logging.warning(f"Invalid temperature payload for {zone_name} secondary: {payload}")
                return

        # ... rest of existing message handling
```

#### Add New Method `_check_sensor_disagreement()`:

```python
def _check_sensor_disagreement(self, zone_name):
    """
    Check for sensor disagreement and publish alert if needed (HEAT-MN-004).

    Args:
        zone_name: Name of the zone to check

    Publishes:
        MQTT alert to heating/monitor/{zone}/alert/sensor_disagreement if sensors disagree
    """
    zone = self.zones[zone_name]

    # Only check if secondary sensor is configured and both have readings
    if not zone.has_secondary_sensor:
        return

    if zone.current_temp is None or zone.current_temp_secondary is None:
        return  # Can't compare if either is missing

    temp_diff = abs(zone.current_temp - zone.current_temp_secondary)

    if temp_diff > zone.sensor_disagreement_threshold:
        alert_payload = {
            'alert_id': 'HEAT-MN-004',
            'zone': zone_name,
            'primary_temp': round(zone.current_temp, 1),
            'secondary_temp': round(zone.current_temp_secondary, 1),
            'difference': round(temp_diff, 1),
            'threshold': zone.sensor_disagreement_threshold,
            'conservative_temp': round(min(zone.current_temp, zone.current_temp_secondary), 1),
            'message': (
                f"{zone_name} sensors disagree: "
                f"Primary {zone.current_temp:.1f}°C vs Secondary {zone.current_temp_secondary:.1f}°C "
                f"(diff: {temp_diff:.1f}°C, threshold: {zone.sensor_disagreement_threshold}°C). "
                f"Using conservative: {min(zone.current_temp, zone.current_temp_secondary):.1f}°C"
            ),
            'timestamp': time.time()
        }

        self.client.publish(
            f"heating/monitor/{zone_name}/alert/sensor_disagreement",
            json.dumps(alert_payload),
            qos=1,
            retain=False
        )

        logging.warning(
            f"[HEAT-MN-004] {zone_name}: SENSOR DISAGREEMENT - "
            f"Primary {zone.current_temp:.1f}°C vs Secondary {zone.current_temp_secondary:.1f}°C "
            f"(diff: {temp_diff:.1f}°C)"
        )
```

#### Modify `_run_control_loop_logic()`:

```python
def _run_control_loop_logic(self):
    """Core control loop logic - calculates and applies heating control."""
    loop_start = time.time()

    # ... existing loop start logging

    for zone_name, zone in self.zones.items():
        logging.debug("")
        logging.debug(f"┌─ {zone_name.upper().replace('_', ' ')} " + "─" * (70 - len(zone_name)))

        # Check sensor disagreement (HEAT-MN-004)
        self._check_sensor_disagreement(zone_name)

        # SR-SF-007: Check for stale sensor readings (now checks ALL sensors)
        if zone.last_temp_update_time is not None and zone.are_all_sensors_stale():
            logging.warning(
                f"{zone_name}: ALL SENSORS STALE - No updates within "
                f"{zone.sensor_timeout_minutes} min threshold"
            )
            # Set validated temp to None to trigger SR-SF-002 shutdown
            zone.current_temp = None
            zone.current_temp_secondary = None
            self._publish_critical_alert(zone_name, "stale_sensor",
                "All configured sensors stale - heating disabled",
                "HEAT-SF-001")

        # Get validated temperature for control decisions
        validated_temp = zone.get_validated_temperature()

        # SR-SF-002: Validate zone has temperature data before processing
        if validated_temp is None:
            logging.debug(f"│ ⚠️  NO TEMPERATURE DATA - Skipping control")
            logging.debug(f"└" + "─" * 78)
            self._publish_climate_state(zone_name)
            zone_status_summary.append(f"{zone_name}: NO DATA")
            continue

        # Calculate temperature error using validated temperature
        temp_error = zone.setpoint - validated_temp

        # Enhanced logging for dual-sensor zones
        if zone.has_secondary_sensor and zone.current_temp is not None and zone.current_temp_secondary is not None:
            logging.debug(
                f"│ 🌡️  Primary: {zone.current_temp:5.1f}°C  |  "
                f"Secondary: {zone.current_temp_secondary:5.1f}°C  |  "
                f"Validated: {validated_temp:5.1f}°C"
            )

        logging.debug(
            f"│ 🎯 Target: {zone.setpoint:5.1f}°C  │  Error: {temp_error:+5.1f}°C"
        )

        # ... rest of existing control loop logic
```

---

### 4. Update `heating_monitor.py`

**Location:** `homehub/automation/src/heating_monitor.py`

#### Extend Sensor Tracking:

```python
def __init__(self, broker_ip, config_file='heating_config.yaml', mqtt_username=None, mqtt_password=None):
    super().__init__(broker_ip, "heating_monitor", username=mqtt_username, password=mqtt_password)

    # ... existing initialization

    # Extract sensor topics from config (primary and secondary)
    self.zone_sensors = {}  # {zone_name: primary_topic}
    self.zone_sensors_secondary = {}  # {zone_name: secondary_topic}

    for zone_name, zone_config in self.config['zones'].items():
        # Primary sensor
        sensor_topic = zone_config.get('temperature_sensor_topic')
        if sensor_topic:
            self.zone_sensors[zone_name] = sensor_topic
            logging.info(f"Monitoring primary sensor for {zone_name}: {sensor_topic}")

        # Secondary sensor (if configured)
        secondary_topic = zone_config.get('temperature_sensor_secondary_topic')
        if secondary_topic:
            self.zone_sensors_secondary[zone_name] = secondary_topic
            logging.info(f"Monitoring secondary sensor for {zone_name}: {secondary_topic}")

    # Subscribe to all sensors (primary and secondary)
    all_sensor_topics = list(self.zone_sensors.values()) + list(self.zone_sensors_secondary.values())
    self._subscribe_to_topics(all_sensor_topics)
    logging.info(f"Subscribed to {len(all_sensor_topics)} sensor topics ({len(self.zone_sensors)} primary, {len(self.zone_sensors_secondary)} secondary)")
```

#### Update Message Processing:

```python
def _process_zigbee_message(self, topic, payload):
    """Process Zigbee2MQTT sensor messages to track health."""
    # Check if this is a primary or secondary sensor
    is_primary = topic in self.zone_sensors.values()
    is_secondary = topic in self.zone_sensors_secondary.values()

    if not is_primary and not is_secondary:
        return  # Not a heating sensor

    # ... existing payload parsing

    # Determine which zone and sensor type
    zone_name = None
    sensor_type = None

    if is_primary:
        for zname, ztopic in self.zone_sensors.items():
            if ztopic == topic:
                zone_name = zname
                sensor_type = "primary"
                break
    elif is_secondary:
        for zname, ztopic in self.zone_sensors_secondary.items():
            if ztopic == topic:
                zone_name = zname
                sensor_type = "secondary"
                break

    # ... existing sensor tracking and health publishing

    # Publish with sensor type suffix
    if sensor_type == "secondary":
        self.client.publish(
            f"heating/monitor/{zone_name}/sensor_health_secondary",
            json.dumps(metrics),
            qos=1,
            retain=True
        )
    else:
        # Primary sensor (existing logic)
        self.client.publish(
            f"heating/monitor/{zone_name}/sensor_health",
            json.dumps(metrics),
            qos=1,
            retain=True
        )
```

---

### 5. Create Alert Documentation

**Update:** `homehub/automation/HEATING_ALERT_REFERENCE.md`

Add new section after HEAT-MN-003:

```markdown
### HEAT-MN-004: Sensor Disagreement (High)

**Severity**: HIGH
**Category**: Monitoring
**Related Requirement**: SR-SF-009, RISK-013 mitigation #13
**MQTT Topic**: `heating/monitor/{zone_name}/alert/sensor_disagreement`

**Description**:
Primary and secondary temperature sensors for the same zone differ by more than the configured disagreement threshold (default 2°C). This indicates potential sensor failure, calibration drift, or poor sensor placement.

**Trigger Conditions**:
- Both primary and secondary sensors configured for zone
- Both sensors reporting valid temperatures
- Absolute difference exceeds `sensor_disagreement_threshold` (default 2.0°C)
- Published by heating_control.py control loop

**Possible Causes**:
1. **One sensor failing or stuck**: One sensor reports frozen/incorrect reading
2. **Calibration drift**: Sensors no longer calibrated to same reference
3. **Poor sensor placement**: Sensors in different microclimates within zone
4. **Environmental factors**: One sensor receiving direct sunlight, draft, or near heat source
5. **Sensor quality difference**: Different sensor models with different accuracy
6. **Zigbee interference**: One sensor experiencing poor link quality affecting readings

**Recommended Actions**:
1. **IMMEDIATE**: Check both sensor readings in Zigbee2MQTT dashboard
2. Compare recent history (last 1 hour) to identify if one sensor is stuck
3. Check sensor battery levels - low battery can cause erratic readings
4. Check link quality (LQI) for both sensors - poor connection causes issues
5. Verify physical sensor placement:
   - Should be in same thermal zone
   - Not near windows, doors, vents, or heat sources
   - Similar height above floor
   - Not in direct sunlight
6. If one sensor clearly stuck: replace or recalibrate failing sensor
7. If both sensors drifting: recalibrate both or replace
8. **NOTE**: System automatically uses **lower temperature** (conservative) for safety

**System Behavior During Alert**:
- Heating **continues** operating (not a safety shutdown)
- System uses **more conservative** (lower) temperature reading
- Prevents overheating if one sensor reports artificially high temperature
- Allows early detection before complete sensor failure

**Impact if Ignored**:
May indicate impending sensor failure. If ignored:
- Risk of inaccurate temperature control
- Potential sensor failure leading to HEAT-SF-001 (stale sensor)
- May mask calibration issues affecting comfort
- Could indicate poor sensor placement reducing system efficiency

**Logged As**:
```
WARNING: [HEAT-MN-004] {zone_name}: SENSOR DISAGREEMENT - Primary X.X°C vs Secondary Y.Y°C (diff: Z.Z°C)
```

**Alert Payload Example**:
```json
{
  "alert_id": "HEAT-MN-004",
  "zone": "ground_floor",
  "primary_temp": 20.5,
  "secondary_temp": 22.8,
  "difference": 2.3,
  "threshold": 2.0,
  "conservative_temp": 20.5,
  "message": "ground_floor sensors disagree: Primary 20.5°C vs Secondary 22.8°C (diff: 2.3°C, threshold: 2.0°C). Using conservative: 20.5°C",
  "timestamp": 1735842234.567
}
```
```

---

### 6. Update System Specification

**Update:** `homehub/automation/HEATING_SYSTEM_SPECIFICATION.md`

#### Add New Safety Requirement (Section 3.3):

```markdown
**SR-SF-009**: When redundant temperature sensors are configured for a zone, the system shall:
1. Use the average temperature when sensors agree (within configured threshold, default 2.0°C)
2. Use the most conservative (lower) temperature reading when sensors disagree by more than the threshold
3. Continue heating operation if either sensor is available (both must be stale to trigger SR-SF-007 shutdown)
4. Publish HEAT-MN-004 alert when sensor disagreement exceeds threshold

This provides defense-in-depth protection against single sensor failures and stuck readings.
```

#### Update Zone Design Section (Section 3.2.1):

```markdown
### 3.2.1 Heating Zone Design

**SD-ZN-001**: Each heating zone shall support optional redundant temperature sensing with the following configuration:
- `temperature_sensor_topic`: Primary temperature sensor (required)
- `temperature_sensor_secondary_topic`: Secondary temperature sensor (optional)
- `sensor_disagreement_threshold`: Alert threshold in °C (optional, default 2.0)

**SD-ZN-002**: When redundant sensors are configured:
- Both sensors shall be monitored for health (battery, LQI, staleness)
- Cross-validation logic per SR-SF-009 shall be applied
- Disagreement alerts (HEAT-MN-004) shall be published when threshold exceeded
- System shall continue operation if either sensor is available

**SD-ZN-003**: Backward compatibility shall be maintained - zones without secondary sensors operate with single-sensor logic.
```

#### Update RISK-013 Mitigation Status:

```markdown
**MEDIUM Priority** (Redundancy & Defense in Depth):
13. **Redundant Temperature Sensor** per critical zone: ✅ **IMPLEMENTED** (Phase 2)
    - Second sensor for cross-validation
    - If sensors differ by >2°C → alert (HEAT-MN-004) and use more conservative reading
    - Cost: ~€30 per zone vs potential property damage
    - Status: Optional per zone via `temperature_sensor_secondary_topic` configuration
```

#### Update Alert Requirements (Section 3.7):

```markdown
**SR-AL-003**: The system shall include the following monitoring alert types:
- HEAT-MN-001: Battery low warning (battery < 20%)
- HEAT-MN-002: Link quality degraded (LQI < 100)
- HEAT-MN-003: Sensor not reporting (no update for 30 minutes)
- **HEAT-MN-004: Sensor disagreement (redundant sensors differ by >threshold)** ← NEW
```

#### Update MQTT Topics (Section 3.2.7):

```markdown
| `heating/monitor/{zone}/sensor_health_secondary` | `{"battery": float, "linkquality": int, ...}` | Secondary sensor health metrics (monitoring service) |
| `heating/monitor/{zone}/alert/sensor_disagreement` | `{"alert_id": "HEAT-MN-004", ...}` | Sensor disagreement alert (HEAT-MN-004) |
```

#### Update Revision History:

```markdown
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 2.0 | TBD | Claude | **Phase 2 - Redundant Sensor Support**: Added SR-SF-009 for redundant sensor cross-validation; added SD-ZN-001, SD-ZN-002, SD-ZN-003 for zone design with secondary sensors; added HEAT-MN-004 alert for sensor disagreement; updated RISK-013 mitigation #13 status to IMPLEMENTED; extended heating_monitor.py to track both primary and secondary sensor health |
```

---

## Testing Plan

### 1. Configuration Validation Tests

**Test 1.1: Single Sensor (Backward Compatibility)**
- Config: Zone with only `temperature_sensor_topic`
- Expected: System operates exactly as before, no secondary sensor logic triggered
- Verify: `zone.has_secondary_sensor == False`, no secondary health metrics published

**Test 1.2: Dual Sensor Configuration**
- Config: Zone with both primary and secondary sensor topics
- Expected: Both sensors subscribed, health metrics published for both
- Verify: Both sensors appear in logs, separate health topics published

**Test 1.3: Invalid Secondary Topic**
- Config: Secondary topic pointing to non-existent device
- Expected: System continues with primary sensor only, logs warning
- Verify: No crash, heating operates normally with primary

### 2. Cross-Validation Logic Tests

**Test 2.1: Sensors Agree (Average)**
- Setup: Primary = 20.0°C, Secondary = 20.2°C, threshold = 2.0°C
- Expected: Validated temp = 20.1°C (average)
- Verify: No disagreement alert, controller uses 20.1°C

**Test 2.2: Sensors Disagree (Conservative)**
- Setup: Primary = 20.0°C, Secondary = 23.0°C, threshold = 2.0°C
- Expected: Validated temp = 20.0°C (lower/conservative)
- Verify: HEAT-MN-004 alert published, warning logged

**Test 2.3: Only Primary Available**
- Setup: Primary = 20.0°C, Secondary = None
- Expected: Validated temp = 20.0°C (fallback to primary)
- Verify: No alert, normal operation

**Test 2.4: Only Secondary Available**
- Setup: Primary = None, Secondary = 20.0°C
- Expected: Validated temp = 20.0°C (fallback to secondary)
- Verify: Warning logged about using secondary only

**Test 2.5: Neither Sensor Available**
- Setup: Primary = None, Secondary = None
- Expected: Validated temp = None
- Verify: SR-SF-002 shutdown triggered, heating disabled

### 3. Staleness Detection Tests

**Test 3.1: Primary Stale, Secondary Active**
- Setup: Primary no update for 25 min, Secondary updating normally
- Expected: Heating continues using secondary sensor
- Verify: No SR-SF-007 shutdown, heating active

**Test 3.2: Secondary Stale, Primary Active**
- Setup: Secondary no update for 25 min, Primary updating normally
- Expected: Heating continues using primary sensor
- Verify: No SR-SF-007 shutdown, heating active

**Test 3.3: Both Sensors Stale**
- Setup: Both sensors no update for 25 min
- Expected: SR-SF-007 triggers, heating disabled
- Verify: HEAT-SF-001 alert published, all temps set to None

### 4. Monitoring Integration Tests

**Test 4.1: Health Metrics for Both Sensors**
- Verify: Two separate MQTT topics published
  - `heating/monitor/{zone}/sensor_health` (primary)
  - `heating/monitor/{zone}/sensor_health_secondary` (secondary)
- Check: Both contain battery, LQI, last_seen, temperature

**Test 4.2: Battery Alerts for Both Sensors**
- Setup: Secondary sensor battery drops to 15%
- Expected: HEAT-MN-001 alert published for secondary sensor
- Verify: Alert clearly indicates which sensor (primary vs secondary)

**Test 4.3: Disagreement Alert Payload**
- Setup: Trigger sensor disagreement
- Verify: Alert payload contains:
  - `alert_id: "HEAT-MN-004"`
  - `primary_temp`, `secondary_temp`, `difference`, `threshold`
  - `conservative_temp` (the value actually being used)
  - Human-readable `message`

### 5. Edge Case Tests

**Test 5.1: Rapid Sensor Fluctuation**
- Setup: Sensors alternate between agreeing/disagreeing every control loop
- Expected: Alert published each time disagreement occurs (no debouncing)
- Verify: System remains stable, no oscillation

**Test 5.2: Extreme Disagreement**
- Setup: Primary = 15.0°C, Secondary = 30.0°C (15°C difference)
- Expected: Uses 15.0°C (conservative), HEAT-MN-004 alert
- Verify: No crash, clear logging of issue

**Test 5.3: Threshold Customization**
- Config: `sensor_disagreement_threshold: 1.0`
- Setup: Sensors differ by 1.5°C
- Expected: Alert triggered (exceeds 1.0°C threshold)
- Verify: Custom threshold respected

---

## Implementation Checklist

- [ ] Update `heating_zone.py` with secondary sensor fields and methods
- [ ] Modify `heating_control.py` for secondary sensor subscription and disagreement checking
- [ ] Extend `heating_monitor.py` to track both primary and secondary sensor health
- [ ] Update `heating_config.yaml` with example secondary sensor configuration
- [ ] Add HEAT-MN-004 alert documentation to `HEATING_ALERT_REFERENCE.md`
- [ ] Update `HEATING_SYSTEM_SPECIFICATION.md` with SR-SF-009 and related requirements
- [ ] Create unit tests for cross-validation logic
- [ ] Create integration tests for staleness detection with redundant sensors
- [ ] Test backward compatibility with single-sensor zones
- [ ] Update Home Assistant dashboard to display both sensor readings
- [ ] Create automation in Home Assistant to handle HEAT-MN-004 alerts
- [ ] Document sensor placement guidelines for redundant sensors
- [ ] Update installation documentation with redundant sensor setup instructions

---

## Success Criteria

✅ **Backward Compatibility**: Existing single-sensor zones work unchanged
✅ **Redundancy**: System continues heating if either sensor is available
✅ **Safety**: Conservative (lower) temperature used when sensors disagree
✅ **Alerting**: HEAT-MN-004 alert triggers when disagreement exceeds threshold
✅ **Monitoring**: Both sensors monitored for battery/LQI health independently
✅ **Logging**: Clear, informative logs show both sensor values and validation decisions
✅ **Configuration**: Simple, intuitive configuration per zone
✅ **Testing**: All test cases pass, edge cases handled gracefully

---

## Future Enhancements (Post-Phase 2)

1. **Sensor Weighting**: Allow configuration of sensor confidence weights (e.g., trust primary 60%, secondary 40%)
2. **Disagreement Hysteresis**: Add time-based filtering to prevent alert spam on borderline disagreements
3. **Historical Trend Analysis**: Track sensor disagreement patterns over time to predict failures
4. **Auto-Calibration**: Automatically adjust for consistent sensor bias (e.g., secondary always reads 0.3°C higher)
5. **Three-Sensor Support**: Extend to 3 sensors with voting logic for maximum reliability
6. **Graceful Degradation Modes**: Different control strategies based on sensor availability (1 vs 2 sensors)

---

## References

- HEATING_SYSTEM_SPECIFICATION.md - System requirements and design
- HEATING_ALERT_REFERENCE.md - Alert catalog and troubleshooting
- HEATING_PROJECT_PLAN.md - Overall project roadmap
- RISK-013 Analysis - Stuck sensor reading failure mode analysis
