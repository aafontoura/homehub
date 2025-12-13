
```markdown
# Task: Home Assistant Heating Control System

## Overview
Create a Home Assistant configuration for a 2-floor heating system with per-floor temperature control, safety watchdogs, and relay failsafe logic.

## Hardware Setup
- **Boiler:** ATAG a244ec (controlled via on/off relay, replacing Honeywell BDR91)
- **Boiler relay:** Shelly 1 gen4 - entity: `switch.boiler_heat_request_switch`
- **Ground floor pump:** Wilo Yonos via smart relay - entity: `switch.pump_ground_floor`
- **First floor pump:** Wilo Yonos via smart relay - entity: `switch.pump_first_floor`
- **Temperature sensors:** Zigbee sensors already in HA
  - Ground floor: `sensor.living_room_sensor_temperature`
  - First floor: `sensor.temperature_first_floor`

## Requirements

### 1. Climate Control
- Use `generic_thermostat` platform for each floor
- Default setpoints: ground floor 20°C, first floor 19°C
- Hysteresis: 0.3°C cold tolerance, 0.3°C hot tolerance
- Minimum cycle time: 5 minutes

### 2. Coordination Logic
- Boiler fires when ANY floor calls for heat
- Only the calling floor's pump runs
- Post-circulation: pumps run 3 minutes after boiler stops

### 3. Safety Watchdog (Critical)
- Shelly auto-off is set to 10 minutes on the device. A local script is necessary
- HA must send heartbeat (turn_on command) every 5 minutes while heating is active
- If HA crashes, relay auto-turns off after 10 min

### 4. Monitoring & Alerts
- Alert if boiler runs continuously > 2 hours
- Alert if any temperature sensor goes unavailable
- Alert if any room exceeds 26°C
- Alert if any room stays below setpoint - 2°C for > 1 hour

### 5. Dashboard
- Simple thermostat cards for each floor
- Status indicators for boiler and pumps
- Sensor health overview

## Deliverables
Create the following files:

1. `my-ha/packages/heating/climate.yaml` - Generic thermostat definitions
2. `my-ha/packages/heating/automations.yaml` - All automations (coordination, heartbeat, safety)
3. `my-ha/packages/heating/alerts.yaml` - Notification automations for safety alerts
4. `my-ha/packages/heating/dashboard.yaml` - Lovelace dashboard card configuration
5. `my-ha/packages/heating/helpers.yaml` - Input booleans and any helper entities needed

## Notes
- Use packages structure for organization
- Notify via `notify.mobile_app_antonio` for alerts
- Add comments explaining each automation's purpose
- Use YAML anchors where it reduces repetition
- Prefer `mode: restart` for automations that should reset on retrigger
```

