# Heating System Specification
**Version**: 1.0
**Date**: 2025-12-27
**System**: Python-based PID Heating Control with Home Assistant Integration

---

## Table of Contents
1. [User-Facing Requirements](#user-facing-requirements)
2. [System Requirements](#system-requirements)
3. [System Design](#system-design)

---

# 1. User-Facing Requirements

## 1.1 Temperature Control

**UR-TC-001**: The system shall allow the user to set target temperatures for each heating zone independently.

**UR-TC-002**: The system shall maintain the temperature in each zone within ±0.5°C of the target temperature under normal operating conditions.

**UR-TC-003**: The user shall be able to enable or disable heating for each zone independently via the dashboard.

**UR-TC-004**: The system shall display current temperature readings for all zones in real-time.

**UR-TC-005**: The user shall be able to view a 24-hour historical temperature graph for each zone.

## 1.2 Energy Efficiency

**UR-EE-001**: The system shall automatically disable heating when an open window is detected in a zone.

**UR-EE-002**: The user shall be able to enable or disable automatic window detection globally for all zones.

**UR-EE-003**: The system shall minimize energy waste by preventing unnecessary pump cycling.

**UR-EE-004**: The user shall be able to view thermal performance metrics (heat loss rate, heat gain rate, insulation quality) for each zone.

## 1.3 System Monitoring

**UR-SM-001**: The user shall be notified when any temperature sensor becomes unavailable.

**UR-SM-002**: The user shall be notified when the temperature in any zone exceeds 26°C for more than 5 minutes.

**UR-SM-003**: The user shall be notified when the temperature in any zone remains more than 2°C below the setpoint for more than 1 hour (when heating is enabled).

**UR-SM-004**: The user shall be able to view the operational status of all hardware components (boiler, pumps, sensors) at a glance.

**UR-SM-005**: The user shall be notified when a window has been left open for more than 30 minutes.

**UR-SM-006**: The user shall be notified if any pump is cycling excessively (>10 cycles/hour).

**UR-SM-007**: The user shall be able to view real-time pump activity and cycling frequency.

## 1.4 Control and Adjustment

**UR-CA-001**: The user shall be able to adjust PID controller parameters (Kp, Ki, Kd) for each zone independently.

**UR-CA-002**: The system shall provide guidance on PID parameter tuning based on observed system behavior.

**UR-CA-003**: Changes to setpoints or settings shall take effect immediately without requiring system restart.

**UR-CA-004**: The system shall respond to manual setpoint changes immediately, bypassing normal pump cycling protection.

## 1.5 Accessibility

**UR-AC-001**: All controls and monitoring shall be accessible via a web-based dashboard on any device.

**UR-AC-002**: The dashboard shall be responsive and usable on mobile phones, tablets, and desktop computers.

**UR-AC-003**: Critical information shall be visible without scrolling on typical mobile phone screens.

**UR-AC-004**: Entity names and labels shall be concise and not truncated on typical screen sizes.

---

# 2. System Requirements

## 2.1 Performance Requirements

**SR-PR-002**: The system shall process temperature updates and adjust heating within 5 seconds of receiving new sensor data.

**SR-PR-003**: The system shall support at least 2 independent heating zones without performance degradation.

**SR-PR-004**: MQTT message delivery shall use QoS 1 (at least once) for all control messages.

**SR-PR-005**: The system shall maintain operation for at least 30 days without manual intervention or restart.

**SR-PR-006**: Historical temperature data shall be retained for at least 24 hours for graphing.

**SR-PR-007**: Thermal performance metrics shall be calculated and published every 60 minutes.

## 2.2 Reliability Requirements

**SR-RL-001**: The system shall automatically reconnect to MQTT broker if connection is lost.

**SR-RL-002**: The system shall gracefully handle unavailable sensors without crashing.

**SR-RL-003**: The system shall continue operating other zones if one zone experiences a sensor failure.

**SR-RL-004**: Configuration changes shall not require Home Assistant restart (except for package additions).

**SR-RL-005**: The control script shall run as a service with automatic restart on failure.

**SR-RL-006**: The system shall publish a heartbeat message every 5 minutes to indicate operational status.

**SR-RL-007**: All configuration shall be stored in YAML files with default values for missing parameters.

## 2.3 Safety Requirements

**SR-SF-001**: The system shall prevent boiler activation if all zone pumps are off.

**SR-SF-002**: The system shall disable heating in a zone if the temperature sensor becomes unavailable.

**SR-SF-003**: The system shall implement a maximum temperature limit of 26°C with automatic shutdown if exceeded.

**SR-SF-004**: Pump minimum ON time shall be at least 10 minutes to prevent premature wear.

**SR-SF-005**: Pump minimum OFF time shall be at least 10 minutes to prevent excessive cycling.

**SR-SF-006**: Manual overrides shall bypass safety limits only for pump cycling protection, not temperature limits.

## 2.4 Integration Requirements

**SR-IN-001**: The system shall integrate with Home Assistant via MQTT protocol.

**SR-IN-002**: The system shall use Zigbee2MQTT for all device communication (sensors, switches, relays).

**SR-IN-003**: The system shall support mobile notifications via Home Assistant mobile app integration.

**SR-IN-004**: All sensor data shall be published to MQTT topics for external monitoring and logging.

**SR-IN-005**: The system shall accept configuration updates via MQTT retained messages.

**SR-IN-006**: Dashboard configuration shall use Home Assistant Lovelace YAML mode.

## 2.5 Data Requirements

**SR-DR-001**: Temperature readings shall be accurate to ±0.1°C.

**SR-DR-002**: PID duty cycle calculations shall use floating-point precision with 3 decimal places.

**SR-DR-003**: Thermal performance calculations shall track at least 20 historical heating/cooling cycles.

**SR-DR-004**: Pump cycle counts shall be tracked per hour and reset at the top of each hour.

**SR-DR-005**: All timestamps shall use UTC with conversion to local time in dashboard display.

## 2.6 Scalability Requirements

**SR-SC-001**: The system architecture shall support addition of new zones without code refactoring.

**SR-SC-002**: MQTT topic structure shall follow a hierarchical naming convention (`heating/{zone}/{metric}`).

**SR-SC-003**: Configuration shall be zone-based, allowing independent tuning parameters per zone.

---

# 3. System Design

## 3.1 Architecture Overview

**SD-AR-001**: The system shall use a three-layer architecture:
- **Infrastructure Layer**: Docker containers (Home Assistant, MQTT, Zigbee2MQTT)
- **Automation Layer**: Python MQTT client running as systemd service
- **Presentation Layer**: Home Assistant Lovelace dashboard (YAML mode)

**SD-AR-002**: Communication between layers shall use MQTT publish/subscribe pattern.

**SD-AR-003**: The Python automation layer shall be autonomous and continue operating if Home Assistant becomes unavailable.

## 3.2 Component Design

### 3.2.1 PID Controller

**SD-PID-001**: Each zone shall have an independent PID controller instance with separate tuning parameters.

**SD-PID-002**: The PID controller shall implement the following formula:
```
output = Kp * error + Ki * integral + Kd * derivative
```

**SD-PID-003**: The PID controller shall implement integral anti-windup with clamping to prevent integral term saturation.

**SD-PID-004**: The PID controller shall clamp output to range [0.0, 1.0] representing 0-100% duty cycle.

**SD-PID-005**: Default PID parameters shall be:
- Kp = 5.0 (proportional gain)
- Ki = 0.1 (integral gain)
- Kd = 1.0 (derivative gain)

**SD-PID-006**: The PID controller shall reset integral and derivative terms when:
- Heating is disabled for the zone
- Setpoint changes by more than 2°C
- Temperature sensor becomes unavailable

### 3.2.2 Window Detection

**SD-WD-001**: Window detection shall analyze temperature derivatives over two timeframes:
- 1-minute window: threshold 0.3°C/min
- 2-minute window: threshold 0.2°C/min

**SD-WD-002**: A window shall be considered open if EITHER threshold is exceeded.

**SD-WD-003**: Window detection shall maintain a rolling buffer of temperature readings (120 samples = 10 minutes at 5-second intervals).

**SD-WD-004**: Window closing shall be detected when temperature change rate falls below 0.1°C/min for both timeframes.

**SD-WD-005**: Window detection shall be globally enabled/disabled via MQTT message on topic `heating/window_detection/set`.

**SD-WD-006**: When window detection is disabled, all zones shall clear existing "window open" states immediately.

**SD-WD-007**: Window state changes shall be published to MQTT topic `heating/{zone}/window_open` with JSON payload `{"window_open": boolean}`.

### 3.2.3 Pump Cycling Protection

**SD-PCP-001**: Each pump shall track the following states:
- Last ON time
- Last OFF time
- Current state (ON/OFF)
- Cycle count in current hour

**SD-PCP-002**: A pump shall be allowed to turn ON only if:
- PID duty cycle > 30% (ON threshold), AND
- Pump has been OFF for at least 10 minutes, OR
- Manual override is active

**SD-PCP-003**: A pump shall be allowed to turn OFF only if:
- PID duty cycle < 5% (OFF threshold), AND
- Pump has been ON for at least 10 minutes, OR
- Manual override is active

**SD-PCP-004**: Manual override shall be automatically set when:
- User changes setpoint via dashboard
- User toggles zone enable/disable

**SD-PCP-005**: Manual override shall be cleared on the next automatic control loop iteration.

**SD-PCP-006**: Pump cycle count shall be published to MQTT topic `heating/{zone}/pump_cycles` with JSON payload `{"cycles_per_hour": float}`.

**SD-PCP-007**: The system shall log a warning if pump cycling exceeds 6 cycles/hour.

### 3.2.4 Thermal Performance Monitoring

**SD-TPM-001**: The system shall track heating and cooling periods for each zone.

**SD-TPM-002**: A cooling period shall be defined as: pump OFF for at least 15 minutes with valid temperature readings.

**SD-TPM-003**: A heating period shall be defined as: pump ON for at least 15 minutes with valid temperature readings.

**SD-TPM-004**: Heat loss rate (°C/hour) shall be calculated as the average temperature change rate during cooling periods.

**SD-TPM-005**: Heat gain rate (°C/hour) shall be calculated as the average temperature change rate during heating periods.

**SD-TPM-006**: The system shall maintain a rolling buffer of the last 20 heating and 20 cooling periods for statistical accuracy.

**SD-TPM-007**: Insulation quality rating shall be calculated based on heat loss rate:
- Excellent: < 0.3°C/h
- Good: 0.3 - 0.5°C/h
- Fair: 0.5 - 0.8°C/h
- Poor: > 0.8°C/h

**SD-TPM-008**: Thermal metrics shall be published to MQTT topic `heating/{zone}/thermal_metrics` with JSON payload:
```json
{
  "avg_heat_loss_rate": float,
  "avg_heat_gain_rate": float,
  "insulation_rating": string,
  "sample_count_cooling": int,
  "sample_count_heating": int
}
```

### 3.2.5 Boiler Control

**SD-BC-001**: The boiler shall be activated if ANY zone pump is ON.

**SD-BC-002**: The boiler shall be deactivated if ALL zone pumps are OFF.

**SD-BC-003**: Boiler state changes shall be published to MQTT topic `heating/boiler_active` with JSON payload `{"state": boolean}`.

**SD-BC-004**: The boiler control relay shall use MQTT topic `zigbee2mqtt/Boiler Heat Request Switch/set` with payload `{"state": "ON"}` or `{"state": "OFF"}`.

### 3.2.6 MQTT Topic Structure

**SD-MQTT-001**: All MQTT topics shall follow the hierarchical structure: `heating/{zone}/{metric}` or `heating/{metric}` for global settings.

**SD-MQTT-002**: Sensor data topics (published by Python script):
| Topic | Payload | Description |
|-------|---------|-------------|
| `heating/boiler_active` | `{"state": boolean}` | Boiler operational state |
| `heating/{zone}/duty_cycle` | `{"duty": float}` | PID output (0.0-1.0) |
| `heating/{zone}/window_open` | `{"window_open": boolean}` | Window detection state |
| `heating/{zone}/current_temp` | `{"temperature": float}` | Current zone temperature |
| `heating/{zone}/thermal_metrics` | `{...}` | Thermal performance data |
| `heating/{zone}/pump_cycles` | `{"cycles_per_hour": float}` | Pump cycling frequency |

**SD-MQTT-003**: Control topics (subscribed by Python script):
| Topic | Payload | Description |
|-------|---------|-------------|
| `heating/{zone}/setpoint/set` | `{"setpoint": float}` | Target temperature |
| `heating/{zone}/enabled/set` | `{"enabled": boolean}` | Zone enable/disable |
| `heating/{zone}/pid/set` | `{"kp": float, "ki": float, "kd": float}` | PID parameters |
| `heating/window_detection/set` | `{"enabled": boolean}` | Global window detection |
| `heating/mode/set` | `{"mode": string}` | System mode (auto/manual) |

**SD-MQTT-004**: Device control topics (Zigbee2MQTT):
| Topic | Payload | Description |
|-------|---------|-------------|
| `zigbee2mqtt/Boiler Heat Request Switch/set` | `{"state": "ON"/"OFF"}` | Boiler relay control |
| `zigbee2mqtt/Pump UFH Ground Floor/set` | `{"state": "ON"/"OFF"}` | Ground floor pump |
| `zigbee2mqtt/Pump UFH First Floor/set` | `{"state": "ON"/"OFF"}` | First floor pump |

**SD-MQTT-005**: All control messages shall use QoS 1 and retain flag to ensure persistence across restarts.

## 3.3 Data Flow Design

**SD-DF-001**: Temperature sensor update flow:
```
Zigbee2MQTT → MQTT (zigbee2mqtt/{sensor}) → Python Script →
  Update temperature history →
  Run window detection →
  Run PID controller →
  Apply pump cycling protection →
  Update pump/boiler states →
  Publish to MQTT (heating/{zone}/*) →
  Home Assistant sensors
```

**SD-DF-002**: User setpoint change flow:
```
Dashboard → Input Number Helper →
  HA Automation →
  MQTT Publish (heating/{zone}/setpoint/set) →
  Python Script →
  Update PID setpoint →
  Set manual override flag →
  Immediate control loop execution
```

**SD-DF-003**: Window detection enable/disable flow:
```
Dashboard → Input Boolean Helper →
  HA Automation →
  MQTT Publish (heating/window_detection/set) →
  Python Script →
  Update all zones' window_detection_enabled flag →
  Clear existing window open states if disabling
```

## 3.4 Home Assistant Integration Design

### 3.4.1 Package Structure

**SD-HA-001**: All heating system configuration shall be organized in a single package: `packages/heating/`

**SD-HA-002**: The heating package shall contain the following files:
- `mqtt_sensors.yaml` - MQTT sensor definitions
- `helpers.yaml` - Input helpers and MQTT publisher automations
- `template_sensors.yaml` - Friendly status sensors using Jinja2 templates
- `alerts.yaml` - Safety alert automations
- `README.md` - Integration documentation

**SD-HA-003**: Dashboard configuration shall be stored separately in `dashboards/heating.yaml` (YAML mode).

### 3.4.2 Input Helpers

**SD-HA-004**: Setpoint control shall use `input_number` helpers with the following properties:
- Min: 15°C (ground floor) / 15°C (first floor)
- Max: 25°C (ground floor) / 22°C (first floor)
- Step: 0.5°C
- Mode: slider

**SD-HA-005**: Zone enable/disable shall use `input_boolean` helpers.

**SD-HA-006**: PID parameter tuning shall use `input_number` helpers with the following ranges:
- Kp: 0.1 to 10.0, step 0.1
- Ki: 0.0 to 1.0, step 0.01
- Kd: 0.0 to 5.0, step 0.1

**SD-HA-007**: Window detection global enable/disable shall use a single `input_boolean` helper applying to all zones.

### 3.4.3 MQTT Sensors

**SD-HA-008**: All MQTT sensors shall specify:
- Unique ID for entity registry
- Appropriate device class (temperature, running, window, etc.)
- State class (measurement) where applicable
- Unit of measurement
- Value template for JSON parsing

**SD-HA-009**: Binary sensors shall use appropriate device classes:
- `running` for boiler active state
- `window` for window open/closed state

### 3.4.4 Automations

**SD-HA-010**: Each input helper change shall have a corresponding automation that publishes to MQTT with:
- Mode: restart (allows rapid updates)
- QoS: 1 (at least once delivery)
- Retain: true (persists across restarts)

**SD-HA-011**: Alert automations shall use notification service `notify.mobile_app_{device}` with:
- Unique tag per alert type
- Group: "heating" for all heating-related alerts
- Appropriate importance level (normal/high)
- Icon matching the alert type

### 3.4.5 Dashboard Design

**SD-HA-012**: The dashboard shall have two views:
1. **Overview**: Real-time monitoring and control
2. **Advanced**: PID parameter tuning

**SD-HA-013**: The Overview view shall contain the following card groups (top to bottom):
1. Header card (markdown)
2. Quick Status glance card (5 columns)
3. Global Settings entities card
4. Zone Controls (2-column horizontal stack)
5. Thermal Performance (2-column horizontal stack)
6. Temperature history graph (24h)
7. Duty cycle history graph (24h)
8. Pump activity history graph (24h)
9. System Health markdown card

**SD-HA-014**: Entity names in cards shall be concise to prevent truncation:
- Maximum 15 characters for labels
- Use abbreviations: GF (Ground Floor), FF (First Floor)

**SD-HA-015**: History graphs shall use `input_number` setpoints directly (not MQTT sensors) for setpoint display.

**SD-HA-016**: The System Health card shall use inline formatting with pipe separators for compactness.

## 3.5 Python Script Design

### 3.5.1 Class Structure

**SD-PY-001**: The heating control script shall implement the following classes:
- `PIDController`: Implements PID algorithm
- `ThermalPerformanceMonitor`: Tracks heat loss/gain metrics
- `HeatingZone`: Encapsulates zone-specific state and logic
- `HeatingControl`: Main controller inheriting from `AutomationPubSub`

**SD-PY-002**: Each class shall have a dedicated docstring explaining its purpose and key methods.

**SD-PY-003**: The `HeatingZone` class shall encapsulate:
- PID controller instance
- Temperature history buffer (deque)
- Pump state and timing
- Window detection state
- Thermal performance monitor instance
- Zone-specific configuration

### 3.5.2 Configuration Management

**SD-PY-004**: All configuration shall be loaded from `heating_config.yaml` at startup.

**SD-PY-005**: The configuration file shall support the following structure:
```yaml
control_interval_seconds: 30
heartbeat_interval_seconds: 300
report_interval_seconds: 3600
boiler_control_topic: "..."
outside_temperature_topic: "..."

zones:
  zone_name:
    temperature_sensor_topic: "..."
    pump_control_topic: "..."
    default_setpoint: float
    pid_kp: float
    pid_ki: float
    pid_kd: float
    window_detection_threshold_1min: float
    window_detection_threshold_2min: float
    pump_min_on_minutes: int
    pump_min_off_minutes: int
    pump_duty_on_threshold: float
    pump_duty_off_threshold: float
```

**SD-PY-006**: Missing configuration parameters shall use sensible defaults defined in code.

### 3.5.3 Logging Design

**SD-PY-007**: The script shall use Python logging module with the following log levels:
- DEBUG: Detailed control loop execution, sensor updates, calculations
- INFO: State changes (pump ON/OFF, window open/close, thermal reports)
- WARNING: Abnormal conditions (high cycle rate, window detected, limits hit)
- ERROR: Failures (sensor unavailable, MQTT disconnect, invalid config)

**SD-PY-008**: Log messages shall follow the format: `"{zone_name}: {message}"`

**SD-PY-009**: PID calculations shall log: `"PID: setpoint={...}, current={...}, error={...} | P={...}, I={...}, D={...} | Output: {...}"`

**SD-PY-010**: Pump state changes shall log: `"{zone}: Pump cycle #{count} (ON/OFF) | runtime/downtime: {duration} min"`

**SD-PY-011**: Window detection shall log:
- Analysis: `"{zone}: Window detection analysis | 1min: {rate}, 2min: {rate}"`
- Triggered: `"{zone}: WINDOW OPENED! {trigger_reason}"`
- Closed: `"{zone}: WINDOW CLOSED (temperature stabilized)"`

### 3.5.4 Error Handling

**SD-PY-012**: The script shall gracefully handle MQTT disconnections by automatically reconnecting.

**SD-PY-013**: Unavailable sensors shall result in zone-specific degradation (zone stops, others continue).

**SD-PY-014**: Invalid MQTT payloads shall be logged as errors without crashing the script.

**SD-PY-015**: All exceptions in the control loop shall be caught and logged to prevent service termination.

## 3.6 Deployment Design

**SD-DEP-001**: The Python heating control script shall be deployed as a systemd service named `automation-heating.service`.

**SD-DEP-002**: The systemd service shall have the following properties:
- Type: simple
- User: antau
- WorkingDirectory: `/home/antau/personal/thread/homehub/automation/src`
- Restart: always
- RestartSec: 10

**SD-DEP-003**: Environment variables shall be loaded from `.env` file containing:
- `MQTT_BROKER_IP=192.168.1.60`
- `MQTT_USERNAME=...`
- `MQTT_PASSWORD=...`

**SD-DEP-004**: The installation script `install_automation_services.sh` shall:
1. Copy service file to `/etc/systemd/system/`
2. Reload systemd daemon
3. Enable service for auto-start
4. Start the service

**SD-DEP-005**: Logs shall be accessible via `journalctl -u automation-heating.service -f`.

---

## 4. Traceability Matrix

### User Requirements → System Requirements

| User Requirement | System Requirements |
|------------------|-------------------|
| UR-TC-001 | SR-IN-005, SD-HA-004 |
| UR-TC-002 | SR-PR-001, SD-PID-001 |
| UR-TC-003 | SR-IN-005, SD-HA-005 |
| UR-TC-004 | SR-PR-002, SD-MQTT-002 |
| UR-TC-005 | SR-PR-006, SD-HA-015 |
| UR-EE-001 | SR-SF-002, SD-WD-001 |
| UR-EE-002 | SR-IN-005, SD-WD-005 |
| UR-EE-003 | SR-SF-004, SD-PCP-001 |
| UR-EE-004 | SR-PR-007, SD-TPM-001 |
| UR-SM-001 through UR-SM-007 | SR-IN-003, SD-HA-011 |

### System Requirements → Design Elements

| System Requirement | Design Elements |
|--------------------|----------------|
| SR-PR-001 | SD-PY-005 |
| SR-RL-001 | SD-PY-012 |
| SR-SF-001 | SD-BC-001 |
| SR-SF-004 | SD-PCP-002 |
| SR-IN-001 | SD-MQTT-001 through SD-MQTT-005 |
| SR-DR-003 | SD-TPM-006 |

---

## 5. Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-27 | Claude | Initial specification document |

---

**End of Specification**
