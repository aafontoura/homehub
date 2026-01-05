# Known Issues - Heating Control System

This document tracks known issues and bugs in the heating control system.

---

## Issue #1: Pump Not Shutdown When Temperature Sensor Becomes Unavailable

**Status**: Open
**Severity**: Medium
**Reported**: 2026-01-04

### Description
When a temperature sensor becomes unavailable (stale data), the zone's pump is not automatically shut down. The boiler is correctly shut down if no zones are requesting heat, but individual zone pumps remain in their previous state.

### Expected Behavior
When a temperature sensor goes stale/unavailable:
1. The zone pump should be turned OFF
2. The boiler should be turned OFF if no other zones are requesting heat
3. The system should log a warning about the stale sensor

### Actual Behavior
- ✅ Boiler is shut down correctly
- ❌ Zone pumps remain in their previous state (ON or OFF)
- The control loop skips the zone with "NO TEMPERATURE DATA" but doesn't force the pump OFF

### Affected Code
[heating_control.py:402-411](heating_control.py:402-411) - Control loop skips zones without temperature data but doesn't set pump state to OFF:

```python
# SR-SF-002: Validate zone has temperature data before processing
if zone.current_temp is None:
    logging.debug(f"│ ⚠️  NO TEMPERATURE DATA - Skipping control")
    logging.debug(f"└" + "─" * 78)
    # Still publish climate state (will show current state even without temp)
    self._publish_climate_state(zone_name)
    # Publish schedule state
    self._publish_schedule_state(zone_name)
    zone_status_summary.append(f"{zone_name}: NO DATA")
    continue  # ← Does not force pump OFF before skipping
```

### Proposed Fix
Before skipping a zone with no temperature data, force the pump to OFF state:

```python
if zone.current_temp is None:
    logging.debug(f"│ ⚠️  NO TEMPERATURE DATA - Forcing pump OFF")
    self._set_pump_state(zone_name, False)
    logging.debug(f"└" + "─" * 78)
    self._publish_climate_state(zone_name)
    self._publish_schedule_state(zone_name)
    zone_status_summary.append(f"{zone_name}: NO DATA")
    continue
```

### Related Requirements
- SR-SF-002: Temperature sensor validation
- SR-RB-001: Fail-safe operation (system must fail to safe state)

---

## Issue #2: No Mobile Notification for Stale Temperature Sensor

**Status**: Open
**Severity**: Low
**Reported**: 2026-01-04

### Description
When a temperature sensor becomes stale/unavailable, no notification is sent to the user's mobile device via Home Assistant mobile app.

### Expected Behavior
When a temperature sensor has not reported data for more than X minutes:
1. Send a push notification to the user's mobile device
2. Include which zone is affected
3. Include timestamp of last valid reading (if available)

### Actual Behavior
- The system logs "NO TEMPERATURE DATA" warnings
- No notification is sent to mobile devices

### Proposed Implementation

#### Option 1: MQTT Alert Topic
Publish alerts to a dedicated MQTT topic that Home Assistant automation can monitor:

```python
# In control loop when sensor is stale
if zone.current_temp is None:
    self.client.publish(
        f"heating/{zone_name}/alerts/sensor_stale",
        json.dumps({
            "zone": zone_name,
            "timestamp": datetime.now().isoformat(),
            "last_reading": zone.last_temp_update.isoformat() if zone.last_temp_update else None
        }),
        qos=1,
        retain=True
    )
```

Then in Home Assistant `automations.yaml`:

```yaml
- alias: "Heating Sensor Stale Alert"
  trigger:
    - platform: mqtt
      topic: "heating/+/alerts/sensor_stale"
  action:
    - service: notify.mobile_app
      data:
        title: "Heating Sensor Issue"
        message: >
          Temperature sensor for {{ trigger.topic.split('/')[1] }} is stale.
          Last update: {{ trigger.payload_json.last_reading }}
        data:
          tag: heating_sensor_stale
          importance: high
          notification_icon: mdi:thermometer-alert
```

#### Option 2: Home Assistant Binary Sensor
Create binary sensors in Home Assistant that track sensor availability, then use standard HA notification automations.

In `packages/heating/scheduling.yaml`:

```yaml
binary_sensor:
  - platform: mqtt
    name: "Ground Floor Temperature Sensor Status"
    state_topic: "zigbee2mqtt/Living Room Sensor"
    payload_on: "online"
    payload_off: "offline"
    device_class: connectivity
    availability_topic: "zigbee2mqtt/bridge/state"
```

### Related Requirements
- SR-MON-002: System health monitoring
- User experience: Proactive notification of issues

---

## Issue Tracking

### How to Report Issues
1. Add new issue to this document with descriptive title
2. Include severity: Critical, High, Medium, Low
3. Describe expected vs actual behavior
4. Include affected code references with line numbers
5. Propose fix if possible

### Severity Definitions
- **Critical**: System unsafe or completely non-functional
- **High**: Major functionality broken, workaround difficult
- **Medium**: Important functionality impaired, workaround available
- **Low**: Minor inconvenience, cosmetic issue, or feature request

---

**Last Updated**: 2026-01-04
