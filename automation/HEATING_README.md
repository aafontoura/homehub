# Python Heating Control System

Advanced PID-based heating control with window detection, weather compensation, and energy optimization.

## Overview

This Python automation replaces Home Assistant's `generic_thermostat` with a sophisticated control system featuring:

1. **PID Control** - Smooth temperature regulation without oscillations
2. **Window Detection** - Automatic heating shutdown when windows open
3. **Weather Compensation** - Adjusts indoor setpoint based on outdoor temperature
4. **Energy Optimization** - Pre-heats during cheap EPEX Spot energy periods
5. **Safety Watchdog** - MQTT heartbeat for Shelly relay failsafe

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Zigbee Temperature Sensors                                   │
│  • zigbee2mqtt/living_room_sensor                            │
│  • zigbee2mqtt/first_floor_sensor                            │
└────────────────────┬────────────────────────────────────────┘
                     │ MQTT
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ heating_control.py (Python MQTT Automation)                  │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ PID Controller                                       │    │
│  │  • Smooth temperature control                        │    │
│  │  • Anti-windup integral clamping                     │    │
│  │  • Derivative dampening                              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Window Detection                                     │    │
│  │  • Temperature derivative analysis                   │    │
│  │  • Multi-timeframe validation (1min, 2min)           │    │
│  │  • Auto heating shutdown on window open              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Weather Compensation                                 │    │
│  │  • Heating curve: Indoor = f(Outdoor)                │    │
│  │  • Reduces setpoint on mild days                     │    │
│  │  • Increases setpoint on cold days                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Energy Optimization                                  │    │
│  │  • Integrates EPEX Spot prices from HA               │    │
│  │  • Pre-heats +1°C during cheap periods               │    │
│  │  • Reduces energy cost                               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Safety Watchdog                                      │    │
│  │  • MQTT heartbeat every 5 minutes                    │    │
│  │  • Resets Shelly auto-off timer                      │    │
│  │  • Boiler turns off if HA crashes                    │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────┬────────────────────────────────────────┘
                     │ MQTT
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Hardware Relays (via MQTT)                                   │
│  • switch.pump_ground_floor                                  │
│  • switch.pump_first_floor                                   │
│  • switch.boiler_heat_request_switch                         │
└─────────────────────────────────────────────────────────────┘
```

## Files

```
homehub/automation/
├── src/
│   ├── heating_control.py       # Main control system
│   ├── heating_config.yaml      # Configuration
│   ├── homehub_mqtt.py          # Base MQTT class (existing)
│   └── energycalculation.py     # Energy price analysis (existing)
├── services/
│   └── automation-heating.service  # Systemd service
├── tests/
│   └── test_heating_control.py  # Pytest tests
└── HEATING_README.md            # This file
```

## Installation

### 1. Configure Shelly Relay Watchdog

First, set up the Shelly auto-off script as described in the main README. The Python system sends MQTT heartbeats to `boiler_heat_request/heartbeat` every 5 minutes.

### 2. Update Configuration

Edit [heating_config.yaml](src/heating_config.yaml) to match your setup:

```yaml
zones:
  ground_floor:
    temperature_sensor_topic: "zigbee2mqtt/YOUR_SENSOR"
    pump_control_topic: "homeassistant/switch/YOUR_PUMP/set"
    default_setpoint: 20.0
    # ... PID tuning parameters
```

### 3. Install Dependencies

Dependencies are already in [requirements.txt](requirements.txt):
- `paho-mqtt` - MQTT client
- `pandas` - Energy price analysis
- `PyYAML` - Configuration files

### 4. Deploy Service

```bash
# Copy service file
sudo cp services/automation-heating.service /etc/systemd/system/

# Or use the install script
sudo ./install/install_automation_services.sh

# Enable and start
sudo systemctl enable automation-heating.service
sudo systemctl start automation-heating.service

# Check status
sudo systemctl status automation-heating.service

# View logs
journalctl -u automation-heating.service -f
```

## Configuration Guide

### PID Tuning

The PID controller has three parameters:

- **kp (Proportional)**: How aggressively to respond to current error
  - Too high: Oscillations, overshooting
  - Too low: Slow response, never reaches setpoint
  - Recommended: 3.0 - 7.0

- **ki (Integral)**: How much to account for accumulated error
  - Too high: Overshooting, instability
  - Too low: Steady-state error (never quite reaches setpoint)
  - Recommended: 0.05 - 0.2

- **kd (Derivative)**: How much to dampen based on rate of change
  - Too high: Sensitive to noise, jittery
  - Too low: Overshooting, oscillations
  - Recommended: 0.5 - 2.0

**Tuning Process:**

1. Start with conservative values: `kp=3.0, ki=0.05, kd=0.5`
2. Monitor temperature response over 24 hours
3. Adjust based on observed behavior:

| Problem | Solution |
|---------|----------|
| Temperature oscillates | Reduce kp, increase kd |
| Too slow to reach setpoint | Increase kp, increase ki |
| Overshoots setpoint | Reduce kp, increase kd |
| Never quite reaches setpoint | Increase ki |

### Weather Compensation

The heating curve formula:
```
indoor_setpoint = default_setpoint - curve_factor × (outdoor_temp - reference_temp)
```

**Example with curve_factor=0.1, reference=10°C, default=20°C:**

| Outdoor Temp | Indoor Setpoint | Effect |
|--------------|-----------------|--------|
| -10°C | 22°C | Very cold → heat more |
| 0°C | 21°C | Cold → heat a bit more |
| 10°C | 20°C | Mild → normal heating |
| 15°C | 19.5°C | Warm → reduce heating |
| 20°C | 19°C | Very warm → minimal |

**Tuning:**
- Start with `curve_factor=0.1` (moderate)
- Increase to 0.2 for more aggressive compensation
- Decrease to 0.05 for subtle compensation

### Window Detection

Temperature drop thresholds:

| Threshold | Interpretation |
|-----------|----------------|
| 0.2°C/min | Slow drop (draft, not necessarily window) |
| 0.3°C/min | Moderate drop (likely window) |
| 0.5°C/min | Fast drop (definitely window) |

**Tuning based on room characteristics:**
- Large rooms with high ceilings: Higher threshold (0.4-0.5°C/min)
- Small well-insulated rooms: Lower threshold (0.2-0.3°C/min)
- Drafty rooms: Higher threshold to avoid false positives

### Energy Optimization

Configure EPEX Spot integration in Home Assistant:

1. Set up EPEX Spot sensor (e.g., via custom integration)
2. Configure topic in `heating_config.yaml`:
   ```yaml
   energy_price_topic: "homeassistant/sensor/epex_spot_prices/state"
   ```
3. System automatically boosts setpoint by 1°C during cheapest 30% of hours

## Testing

### Run Unit Tests

```bash
cd homehub/automation
pytest tests/test_heating_control.py -v
```

### Test Individual Components

**PID Controller:**
```python
from heating_control import PIDController

pid = PIDController(kp=5.0, ki=0.1, kd=1.0, setpoint=20.0)
output = pid.update(measurement=18.0)
print(f"PID output: {output}")  # Should be positive
```

**Window Detection:**
```python
from heating_control import HeatingZone

config = {
    'default_setpoint': 20.0,
    'pid_kp': 5.0, 'pid_ki': 0.1, 'pid_kd': 1.0,
    'window_detection_threshold_1min': 0.3,
    'history_length': 120
}
zone = HeatingZone("test", config)

# Simulate rapid drop
for i in range(30):
    zone.update_temperature(20.0 - i * 0.02)
    time.sleep(0.1)

print(f"Window open: {zone.detect_window_open()}")  # Should be True
```

## Monitoring

### Check System Status

```bash
# Service status
systemctl status automation-heating.service

# Recent logs
journalctl -u automation-heating.service -n 100

# Follow logs in real-time
journalctl -u automation-heating.service -f
```

### MQTT Monitoring

```bash
# Monitor all heating topics
mosquitto_sub -h 192.168.1.60 -t 'heating/#' -v

# Monitor temperature sensors
mosquitto_sub -h 192.168.1.60 -t 'zigbee2mqtt/living_room_sensor' -v

# Monitor heartbeat
mosquitto_sub -h 192.168.1.60 -t 'boiler_heat_request/heartbeat' -v
```

### Key Metrics to Watch

**Log messages to look for:**

```
# Normal operation
INFO - ground_floor: Pump ON (duty: 65%, temp: 19.2°C)
INFO - Boiler ON - heartbeat started
DEBUG - Heartbeat sent

# Window detection
WARNING - ground_floor: Window opening detected! Rate: 0.45°C/min
INFO - ground_floor: Pump OFF (window open)

# Energy optimization
INFO - Cheap energy period activated (price: 0.05 ≤ 0.08)

# Weather compensation
DEBUG - ground_floor temperature: 19.5°C
DEBUG - Outside temperature: 5.0°C
```

## Troubleshooting

### Heating Not Responding

**Check:**
```bash
# Is service running?
systemctl status automation-heating.service

# Recent errors?
journalctl -u automation-heating.service -p err -n 50

# Is MQTT connected?
mosquitto_sub -h 192.168.1.60 -t 'heating/#' -v
```

**Common causes:**
- MQTT broker down
- Incorrect topic names in config
- Temperature sensors not publishing

### Temperature Oscillating

**Symptoms:**
- Temperature swings ±1°C around setpoint
- Pump turns on/off frequently

**Solution:**
Reduce PID proportional gain:
```yaml
pid_kp: 3.0  # Reduce from 5.0
pid_kd: 1.5  # Increase damping
```

### Window Detection False Positives

**Symptoms:**
- Heating stops when window is closed
- "Window detected" logs during normal operation

**Solution:**
Increase detection threshold:
```yaml
window_detection_threshold_1min: 0.4  # Increase from 0.3
window_detection_threshold_2min: 0.3  # Increase from 0.2
```

### Never Reaches Setpoint

**Symptoms:**
- Temperature stays 0.5-1°C below setpoint
- Pump runs continuously

**Solution:**
Increase integral gain:
```yaml
pid_ki: 0.15  # Increase from 0.1
```

Or check if weather compensation is too aggressive:
```yaml
weather_compensation_curve: 0.05  # Reduce from 0.1
```

### Heartbeat Not Working

**Check Shelly script:**
```bash
# MQTT heartbeat being sent?
mosquitto_sub -h 192.168.1.60 -t 'boiler_heat_request/heartbeat' -v

# Should see "ping" every 5 minutes when heating active
```

**Check Shelly logs:**
- Access Shelly web interface
- Scripts → View console
- Should see "Timer reset" messages

## Migration from Home Assistant YAML

If you're currently using the Home Assistant `generic_thermostat` setup from [my_ha/packages/heating/](../my_ha/packages/heating/), here's how to migrate:

### Step 1: Run Both in Parallel (Testing)

1. Keep HA automations running
2. Deploy Python heating control
3. Configure Python to **monitor only** (don't control pumps yet):
   ```yaml
   # Temporarily use test topics
   pump_control_topic: "heating/test/pump_ground_floor"
   ```
4. Compare behavior over 24-48 hours

### Step 2: Switch Control to Python

1. Disable HA climate entities:
   ```yaml
   # Comment out in my_ha/packages/heating/climate.yaml
   # climate:
   #   - platform: generic_thermostat
   #     ...
   ```
2. Update Python config to use real pump topics:
   ```yaml
   pump_control_topic: "homeassistant/switch/pump_ground_floor/set"
   ```
3. Restart Python service
4. Monitor closely for first 24 hours

### Step 3: Keep HA Safety Alerts

**Recommended:** Keep Home Assistant alert automations from [my_ha/packages/heating/alerts.yaml](../my_ha/packages/heating/alerts.yaml):
- Sensor unavailable alerts
- Overtemperature alerts
- Hardware offline detection

These provide redundancy if the Python service crashes.

## Advanced Features

### Custom Heating Schedules

Add time-based setpoint adjustments:

```python
# In heating_control.py, add to HeatingZone.calculate_control_output():
from datetime import datetime

now = datetime.now()
if 6 <= now.hour < 8:
    # Morning boost
    self.setpoint += 1.0
elif 22 <= now.hour or now.hour < 6:
    # Night reduction
    self.setpoint -= 2.0
```

### Occupancy Detection

Integrate with presence sensors:

```python
# Subscribe to occupancy topic
topics.append("zigbee2mqtt/motion_sensor/occupancy")

# In handle_message():
if 'motion_sensor' in topic and payload.get('occupancy') == False:
    # No occupancy for 2 hours → reduce setpoint
    zone.setpoint -= 2.0
```

### Multi-Border Room Zones

Add radiator valve control per room:

```yaml
zones:
  living_room:
    temperature_sensor_topic: "zigbee2mqtt/living_room_sensor"
    pump_control_topic: "homeassistant/switch/pump_ground_floor/set"
    valve_control_topic: "zigbee2mqtt/living_room_valve/set"
    # Individual room PID
```

## Performance Considerations

### CPU Usage

- Control loop runs every 30 seconds (configurable)
- PID calculations are lightweight (<1ms per zone)
- Expected CPU usage: <1% on Raspberry Pi 4

### Memory Usage

- Temperature history: ~14KB per zone (120 samples × 2 floats)
- Total expected RAM: ~50MB

### MQTT Traffic

- Temperature updates: ~2 messages/min per sensor
- Control updates: ~2 messages/min per pump
- Heartbeat: 1 message/5min
- Total: ~10-15 messages/min

## Comparison: Python vs Home Assistant YAML

| Feature | Python | HA YAML |
|---------|--------|---------|
| **Control Algorithm** | PID (smooth) | Bang-bang (on/off) |
| **Window Detection** | Yes (pattern analysis) | No |
| **Weather Compensation** | Yes (heating curves) | No |
| **Energy Optimization** | Yes (EPEX integration) | Manual |
| **Testing** | Pytest unit tests | Manual only |
| **Debugging** | Python logging + IDE | HA traces only |
| **Complexity** | Higher (requires Python knowledge) | Lower (YAML config) |
| **Performance** | Better (optimized control) | Good (simpler) |
| **Customization** | Full (code-based) | Limited (templates) |

## Contributing

Improvements welcome! Key areas:

1. **Adaptive PID tuning** - Auto-tune based on system response
2. **Machine learning** - Predict optimal preheat times
3. **Multi-room zones** - Per-radiator valve control
4. **Better energy optimization** - Day-ahead planning
5. **Occupancy learning** - Detect patterns and adjust schedules

## License

MIT License - Part of the homehub automation infrastructure.

## References

- Base MQTT automation: [homehub_mqtt.py](src/homehub_mqtt.py)
- Energy calculation: [energycalculation.py](src/energycalculation.py)
- Similar automation: [ventilation_control.py](src/ventilation_control.py)
- Installation: [install_automation_services.sh](../install/install_automation_services.sh)
