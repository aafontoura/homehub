# Heating System Specification
**Version**: 1.0
**Date**: 2025-12-27
**System**: Python-based PID Heating Control with Home Assistant Integration

---

## Table of Contents
0. [System Function Overview](#system-function-overview)
1. [Risk Assessment](#risk-assessment)
2. [User-Facing Requirements](#user-facing-requirements)
3. [System Requirements](#system-requirements)
4. [System Design](#system-design)
5. [Traceability Matrix](#traceability-matrix)
6. [Document Revision History](#document-revision-history)

---

# 0. System Function Overview

This heating control system is designed with a clear separation between **primary** and **secondary** functions to ensure reliability, maintainability, and progressive enhancement.

## 0.1 Primary Function
- **Temperature Control**: Control heat based on a setpoint
  - Core responsibility: Maintain zone temperatures at user-defined setpoints
  - Must be simple, reliable, and work independently
  - Forms the foundation of all heating operations

## 0.2 Secondary Functions
Secondary functions enhance the system but are not essential for basic operation. They can be disabled or temporarily unavailable without preventing the primary heating function:

1. **Pump Protection**: Prevents excessive pump cycling to extend hardware lifespan
2. **Window Opening Detection**: Automatically disables heating when windows are detected open
3. **Insulation Performance Metrics**: Provides thermal performance analysis and reporting
4. **Scheduling**: Enables time-based setpoint adjustments for energy optimization

**Design Principle**: The primary function must work reliably even if all secondary functions are disabled or fail. Secondary functions are implemented as optional, modular enhancements that can be independently enabled, disabled, or removed without affecting core temperature control.

---

# 1. Risk Assessment

## 1.1 Risk Evaluation Criteria

**Likelihood Scale** (1-5):
- 1 = Rare (may occur only in exceptional circumstances)
- 2 = Unlikely (could occur at some time)
- 3 = Possible (might occur at some time)
- 4 = Likely (will probably occur in most circumstances)
- 5 = Almost Certain (expected to occur in most circumstances)

**Severity Scale** (1-5):
- 1 = Negligible (minor inconvenience)
- 2 = Minor (some disruption to service)
- 3 = Moderate (significant disruption, repairable damage)
- 4 = Major (property damage, extended service outage)
- 5 = Catastrophic (fire hazard, structural damage, safety risk)

**Risk Rating** = Likelihood × Severity
- 1-6: Low Risk (monitor)
- 7-12: Medium Risk (implement mitigations)
- 13-25: High Risk (requires immediate mitigation)

## 1.2 Identified Risks

#### RISK-001: Overheating Due to Sensor Failure
**Description**: Temperature sensor fails and reports incorrect (lower) temperature, causing system to continuously heat the zone beyond safe limits.

**Likelihood**: 2 (Unlikely - sensors are generally reliable)
**Severity**: 4 (Major - property damage, discomfort, wasted energy)
**Risk Rating**: 8 (Medium)

**Related Requirements**: SR-SF-002, SR-SF-003, UR-SM-001

**Mitigations**:
1. **Implemented**: Maximum temperature limit of 26°C with automatic shutdown (SR-SF-003)
2. **Implemented**: Alert notification when temperature exceeds 26°C for >5 minutes (UR-SM-002)
3. **Implemented**: Heating disabled if sensor becomes unavailable (SR-SF-002, SD-BC-001)
4. **Recommended**: Add redundant temperature sensor per zone for cross-validation
5. **Recommended**: Log temperature trend anomalies (e.g., >3°C increase in 10 minutes)

#### RISK-002: Pump Premature Failure Due to Excessive Cycling
**Description**: Software bug or misconfiguration causes pump to cycle rapidly (on/off every 30 seconds), leading to premature pump motor failure.

**Likelihood**: 2 (Unlikely)
**Severity**: 3 (Moderate - pump replacement cost, temporary heating loss)
**Risk Rating**: 6

**Related Requirements**: SR-SF-004, SR-SF-005, UR-SM-006, UR-EE-003

**Mitigations**:
1. **Implemented**: Minimum ON time of 10 minutes (SR-SF-004, SD-PCP-002)
2. **Implemented**: Minimum OFF time of 10 minutes (SR-SF-005, SD-PCP-003)
3. **Implemented**: Pump cycle count monitoring with alert if >10 cycles/hour (UR-SM-006, SD-PCP-007)
4. **Implemented**: Duty cycle deadband (30% ON threshold, 5% OFF threshold) (SD-PCP-002, SD-PCP-003)
5. **Recommended**: Log all pump state changes with timestamps for forensic analysis
6. **Recommended**: Add configurable maximum cycle rate limit in code

#### RISK-003: Boiler Dry Run (No Flow)
**Description**: Boiler activates when all zone pumps are off, causing boiler to heat without water circulation, potentially damaging boiler heat exchanger.

**Likelihood**: 2 (Unlikely - safety logic prevents this)
**Severity**: 5 (Catastrophic - boiler damage, potential safety hazard)
**Risk Rating**: 10 (Medium)

**Related Requirements**: SR-SF-001

**Mitigations**:
1. **Implemented**: Boiler only activates if at least one pump is ON (SR-SF-001, SD-BC-001)
2. **Implemented**: Boiler deactivates immediately when all pumps turn OFF (SD-BC-002)
3. **Recommended**: Add flow sensor to verify water circulation before boiler activation
4. **Recommended**: Add boiler temperature sensor with overheat protection (independent of zone sensors)
5. **Recommended**: Implement watchdog timer - if boiler is ON for >30 seconds with no pump ON, trigger emergency shutdown

#### RISK-004: Undetected Open Window Causing Energy Waste
**Description**: Window detection algorithm fails to detect open window (e.g., slow air infiltration, sensor placement), causing system to heat while losing heat through open window.

**Likelihood**: 3 (Possible - depends on room layout, window type, sensor placement)
**Severity**: 2 (Minor - energy waste, difficulty reaching setpoint)
**Risk Rating**: 6 (Medium)

**Related Requirements**: UR-EE-001, UR-SM-005

**Mitigations**:
1. **Implemented**: Two-timeframe window detection (1-minute and 2-minute thresholds) (SD-WD-001)
2. **Implemented**: Alert notification if window left open >30 minutes (UR-SM-005)
3. **Implemented**: User can disable window detection if false positives occur (UR-EE-002, SD-WD-005)
4. **Recommended**: Configurable threshold per zone based on room characteristics (SD-WD-001 notes)
5. **Recommended**: Add magnetic door/window sensors for definitive open/close detection
6. **Recommended**: Cross-correlate with outside temperature - larger temp drop expected when colder outside

#### RISK-005: False Window Detection Causing Comfort Loss
**Description**: Window detection incorrectly identifies normal temperature fluctuations as open window, disabling heating unnecessarily and preventing zone from reaching setpoint.

**Likelihood**: 3 (Possible - depends on PID tuning, drafts, external factors)
**Severity**: 2 (Minor - temporary discomfort, user frustration)
**Risk Rating**: 6 (Medium)

**Related Requirements**: UR-EE-002

**Mitigations**:
1. **Implemented**: User can globally disable window detection (UR-EE-002, SD-WD-005)
2. **Implemented**: Window closing detection via temperature stabilization (SD-WD-004)
3. **Implemented**: Two-threshold approach reduces false positives (SD-WD-001)
4. **Recommended**: Configurable thresholds per zone (large vs small rooms)
5. **Recommended**: Require temperature drop to persist for 2 consecutive measurements before triggering
6. **Recommended**: Suppress window detection during first 30 minutes after pump turns ON (expected temp changes)

#### RISK-006: MQTT Broker Failure Causing Loss of Control
**Description**: MQTT broker becomes unavailable, preventing Home Assistant from controlling the heating system and monitoring status.

**Likelihood**: 3 (Possible - MQTT is reliable, but this is a homelab project, the user might stop it for maintenance or shutdown the electricity temporarly)
**Severity**: 4 (Major - loss of remote control, monitoring blind spot, worst case scenario: System stuck on heating mode ON. Causing potential monetary problem for using too much gas/electricity or even due to device damage.)
**Risk Rating**: 6 (Medium)

**Related Requirements**: SR-RL-001, SR-RL-006

**Mitigations**:
1. **Implemented**: Automatic MQTT reconnection in Python client (SR-RL-001, SD-PY-012)
2. **Implemented**: Python control script operates autonomously without MQTT/HA (SD-AR-003)
3. **Implemented**: Heartbeat monitoring to detect Python script failure (SR-RL-006)
4. **Recommended**: MQTT broker monitoring with automatic restart on failure
5. **Recommended**: Retained messages ensure configuration persists across MQTT restarts (SD-MQTT-005)
6. **Recommended**: Fallback to last known setpoints if MQTT unavailable

#### RISK-007: Python Control Script Crash Causing Total Heating Loss
**Description**: Software bug, memory leak, or unhandled exception causes Python control script to crash, stopping all heating control.

**Likelihood**: 2 (Unlikely - tested code with exception handling)
**Severity**: 4 (Major - complete heating system failure in winter)
**Risk Rating**: 8 (Medium)

**Related Requirements**: SR-RL-005, SR-PR-005, UR-SM-007

**Mitigations**:
1. **Implemented**: Systemd service with automatic restart on failure (SR-RL-005, SD-DEP-002)
2. **Implemented**: Comprehensive exception handling in control loop (SD-PY-015)
3. **Implemented**: Heartbeat detection with alert if script offline >5 minutes (UR-SM-007)
4. **Recommended**: Memory usage monitoring with restart if exceeds threshold
5. **Recommended**: Automated testing suite for edge cases (sensor unavailable, rapid setpoint changes, etc.)
6. **Recommended**: Log file rotation to prevent disk space exhaustion
7. **Recommended**: Watchdog timer external to Python script

#### RISK-008: Zone Pump Stuck ON Due to Relay Failure
**Description**: Zone pump relay fails in closed position, causing pump to run continuously even when heating not required, wasting energy and potentially overheating zone.

**Likelihood**: 2 (Unlikely - relay hardware is reliable)
**Severity**: 3 (Moderate - energy waste, overheating, relay replacement cost)
**Risk Rating**: 6 (Medium)

**Related Requirements**: SR-SF-003, UR-SM-004

**Mitigations**:
1. **Implemented**: Maximum temperature limit of 26°C with shutdown (SR-SF-003)
2. **Implemented**: Pump state monitoring via MQTT feedback (UR-SM-004)
3. **Recommended**: Add current sensor to detect pump running vs commanded state
4. **Recommended**: If temperature continues rising when pump commanded OFF, trigger alert
5. **Recommended**: Implement "pump off" verification - if temp still rising 5 min after pump OFF command, assume stuck relay

#### RISK-009: Underheating Due to Insufficient Boiler Capacity
**Description**: Boiler unable to provide enough heat for both zones simultaneously during extreme cold weather, preventing zones from reaching setpoint.

**Likelihood**: 2 (Unlikely - boiler sized for peak demand)
**Severity**: 2 (Minor - temporary discomfort, higher heating costs)
**Risk Rating**: 4 (Low)

**Related Requirements**: UR-SM-003

**Mitigations**:
1. **Implemented**: Alert if temperature remains >2°C below setpoint for >1 hour (UR-SM-003)
2. **Implemented**: Independent zone control allows priority management
3. **Recommended**: Add zone priority setting (e.g., prefer ground floor in extreme cold)
4. **Recommended**: Thermal performance monitoring identifies insufficient capacity (SD-TPM-001)
5. **Recommended**: Log outdoor temperature correlation with heating capacity

#### RISK-010: Configuration File Corruption Causing Startup Failure
**Description**: Configuration file (`heating_config.yaml`) becomes corrupted or contains invalid values, preventing Python script from starting or causing erratic behavior.

**Likelihood**: 2 (Unlikely - YAML is robust, file rarely edited)
**Severity**: 3 (Moderate - heating system offline until fixed)
**Risk Rating**: 6 (Medium)

**Related Requirements**: SR-RL-007

**Mitigations**:
1. **Implemented**: Default values for missing parameters (SR-RL-007, SD-PY-006)
2. **Implemented**: YAML parsing error handling in script startup
3. **Recommended**: Configuration file validation on load (check value ranges, required fields)
4. **Recommended**: Backup configuration file created on each successful startup
5. **Recommended**: Configuration version control (Git repository)
6. **Recommended**: Schema validation using YAML schema definition

#### RISK-011: PID Oscillation Causing Temperature Swings
**Description**: Incorrectly tuned PID parameters cause temperature to oscillate above/below setpoint, creating discomfort and potential equipment stress.

**Likelihood**: 3 (Possible - especially during initial tuning)
**Severity**: 2 (Minor - discomfort, reduced efficiency)
**Risk Rating**: 6 (Medium)

**Related Requirements**: UR-CA-001, UR-CA-002

**Mitigations**:
1. **Implemented**: User-adjustable PID parameters (UR-CA-001, SD-HA-006)
2. **Implemented**: PID tuning guidance in documentation (UR-CA-002, SD-HA-016)
3. **Implemented**: Conservative default PID values (SD-PID-005)
4. **Implemented**: Pump cycling protection dampens rapid oscillations (SD-PCP-001)
5. **Recommended**: Auto-tuning algorithm (Ziegler-Nichols method)
6. **Recommended**: Oscillation detection with alert and recommended parameter adjustments

#### RISK-012: Loss of Mobile Notifications During Critical Failure
**Description**: Mobile app notification system fails, preventing user from receiving alerts about sensor failures, overheating, or system faults.

**Likelihood**: 2 (Unlikely - Home Assistant notification reliable)
**Severity**: 3 (Moderate - delayed response to critical issues)
**Risk Rating**: 6 (Medium)

**Related Requirements**: SR-IN-003, UR-SM-001 through UR-SM-007

**Mitigations**:
1. **Implemented**: Multiple alert types with different tags (SD-HA-011)
2. **Implemented**: Critical alerts use high importance (SD-HA-011)
3. **Recommended**: Redundant notification channels (email, SMS, persistent dashboard notifications)
4. **Recommended**: Daily "system healthy" heartbeat notification to verify notification system works
5. **Recommended**: Local alarm (buzzer/siren) for critical failures

#### RISK-013: Temperature Sensor Connection Loss Due to Battery Depletion or Link Quality Degradation
**Description**: Temperature sensor fails due to battery depletion or poor Zigbee link quality. This risk has two distinct failure modes with vastly different impacts:

**Failure Mode A - Sensor Unavailable** (Graceful Failure):
- Sensor stops transmitting completely
- MQTT payload shows "unavailable" or sensor state becomes `None`
- System correctly detects absence of data (heating_control.py:273)
- Zone heating safely shuts down per SR-SF-002
- User receives alert per UR-SM-001
- **Impact**: Comfort loss only (safe shutdown)
- **Severity**: 2 (Minor)

**Failure Mode B - Stuck Reading** (CRITICAL - Silent Failure):
- Sensor sends final reading before battery completely dies (e.g., 18.0°C)
- Battery depletes mid-transmission or sensor firmware freezes
- Sensor stops sending new updates but MQTT retains last valid reading
- System continues using **stale** temperature reading indefinitely
- **Critical code path** (heating_control.py:273-290):
  - Check `if zone.current_temp is None` → **PASSES** (value is 18.0°C, not None)
  - Controller calculates based on frozen 18.0°C reading
  - If setpoint is 20.0°C → error = +2.0°C → **heating turns ON**
  - Actual room temperature rises to 24°C, 26°C, 28°C...
  - Sensor still reports 18.0°C → heating **continues unchecked**
  - SR-SF-003 max temp limit (26°C) **ineffective** - relies on accurate sensor data
- **Result**: Continuous uncontrolled heating, room overheats, potential property damage
- **Severity**: 4 (Major - overheating risk, property damage, safety concern, monetary loss)

**Likelihood**: 3 (Possible)
- Battery-powered Zigbee sensors typically fail every 1-2 years
- Stuck reading failure mode occurs in ~20% of battery failures based on Zigbee device behavior
- Gradual voltage drop can cause sensor firmware to freeze while maintaining MQTT connection
- No current detection mechanism for stale readings

**Severity**: 4 (Major - Failure Mode B is critical)

**Risk Rating**: **12 (Medium-High)** - Highest unmitigated risk after RISK-003

**Related Requirements**: SR-SF-002 (partial), SR-SF-003 (ineffective for Mode B), UR-SM-001

**Current Mitigations (Partial)**:
1. **Implemented**: Heating disabled if sensor becomes unavailable (`current_temp is None`) - SR-SF-002, heating_control.py:273
   - ✅ **Effective for Failure Mode A** (sensor unavailable)
   - ❌ **Ineffective for Failure Mode B** (stuck reading)
2. **Implemented**: User alert when sensor offline - UR-SM-001
   - ✅ **Effective for Failure Mode A**
   - ❌ **No alert for Failure Mode B** (sensor appears "online" with stale data)

**Critical Gaps - Failure Mode B**:
3. ❌ **NO detection** of stale/stuck sensor readings
4. ❌ **NO timestamp** tracking for sensor updates
5. ❌ **NO watchdog** for sensor update frequency
6. ❌ **NO maximum runtime** limit independent of temperature readings

**Recommended Mitigations**:

**CRITICAL Priority** (Must implement to address Failure Mode B):
7. **Sensor Update Watchdog** (NEW SR-SF-007):
   - Track last update timestamp per sensor
   - If no update for 20 minutes (10x normal interval) → set `current_temp = None`
   - Triggers existing SR-SF-002 safety shutdown
   - Implementation: Add `last_update_time` field to HeatingZone class
8. **Staleness Detection**:
   - Monitor temperature change rate: if temp hasn't changed by >0.05°C in 15 minutes while heating ON → suspicious
   - Cross-validation: check if actual heating is occurring (pump ON, boiler ON, but temp frozen)
   - Alert user: "Sensor may be stuck - verify manually"
9. **Maximum Heating Runtime Safety** (NEW SR-SF-008):
   - Independent watchdog: if pump ON continuously for >2 hours → force shutdown
   - Alert user: "Emergency shutdown - pump runtime exceeded safe limit"
   - Overrides all other logic (defense in depth)
   - Prevents runaway heating even if all sensor checks fail

**HIGH Priority** (Proactive Prevention):
10. **Zigbee Link Quality Monitoring**:
    - Monitor LQI (Link Quality Indicator) from Zigbee2MQTT
    - Alert if LQI < 100 (degrading connection)
    - Track link quality trend over time
11. **Battery Level Monitoring**:
    - Monitor battery percentage from Zigbee2MQTT
    - Alert at 20% threshold (before critical failure)
    - Predictive alert: if battery drops >10% in 1 week → "Replace battery soon"
12. **Weekly Sensor Health Report**:
    - Automated report showing: last update time, battery %, LQI, uptime
    - Identifies sensors approaching failure before they fail
    - Proactive maintenance scheduling

**MEDIUM Priority** (Redundancy & Defense in Depth):
13. **Redundant Temperature Sensor** per critical zone:
    - Second sensor for cross-validation
    - If sensors differ by >2°C → alert and use more conservative reading
    - Cost: ~€30 per zone vs potential property damage
14. **Graceful Degradation**:
    - Use last known temp for 5 minutes before hard shutdown
    - Allows for temporary Zigbee interference recovery
    - Still safer than indefinite stale reading
15. **Sensor Reliability Metrics**:
    - Track uptime percentage, update frequency, failure count in InfluxDB
    - Identify unreliable sensors proactively
    - Trend analysis for predictive maintenance

**Implementation Note**: Mitigation #7 (Sensor Update Watchdog) should be implemented immediately as it addresses the most critical unmitigated failure mode with minimal code changes.

## 1.3 Risk Summary

| Risk ID | Risk Title | Rating | Priority |
|---------|-----------|--------|----------|
| RISK-013 | Sensor Connection Loss (Stuck Reading) | 12 (Medium-High) | **CRITICAL** |
| RISK-003 | Boiler Dry Run | 10 (Medium) | High |
| RISK-002 | Pump Premature Failure | 9 (Medium) | High |
| RISK-001 | Overheating Due to Sensor Failure | 8 (Medium) | High |
| RISK-007 | Python Script Crash | 8 (Medium) | High |
| RISK-004 | Undetected Open Window | 6 (Medium) | Medium |
| RISK-005 | False Window Detection | 6 (Medium) | Medium |
| RISK-006 | MQTT Broker Failure | 6 (Medium) | Medium |
| RISK-008 | Pump Stuck ON | 6 (Medium) | Medium |
| RISK-010 | Configuration Corruption | 6 (Medium) | Medium |
| RISK-011 | PID Oscillation | 6 (Medium) | Medium |
| RISK-012 | Notification Failure | 6 (Medium) | Medium |
| RISK-009 | Insufficient Boiler Capacity | 4 (Low) | Low |

## 1.4 Safety Requirements Coverage

All High and Medium priority risks have been addressed through safety requirements:

| Safety Requirement | Mitigates Risks |
|-------------------|----------------|
| SR-SF-001 | RISK-003 (Boiler Dry Run) |
| SR-SF-002 | RISK-001 (Sensor Failure Overheating), **RISK-013 Failure Mode A only** (Sensor Unavailable) |
| SR-SF-003 | RISK-001 (Overheating), RISK-008 (Pump Stuck ON), **INEFFECTIVE for RISK-013 Failure Mode B** |
| SR-SF-004 | RISK-002 (Pump Cycling) |
| SR-SF-005 | RISK-002 (Pump Cycling) |
| SR-SF-006 | RISK-002 (Manual Override Abuse) |
| **SR-SF-007** (NEW) | **RISK-013 Failure Mode B** (Stuck Reading) - Sensor Update Watchdog |
| **SR-SF-008** (NEW) | **RISK-013 Failure Mode B** (Stuck Reading) - Maximum Runtime Safety |

**CRITICAL GAP IDENTIFIED**:
- SR-SF-002 and SR-SF-003 do NOT mitigate RISK-013 Failure Mode B (stuck sensor readings)
- Current implementation only checks `if current_temp is None` (heating_control.py:273)
- Does NOT detect stale/frozen readings where sensor value is stuck at last reading
- **New safety requirements SR-SF-007 and SR-SF-008 are CRITICAL** to address this gap
- Implementation of sensor update watchdog should be prioritized immediately

Additional recommended mitigations should be considered for defense-in-depth approach.

---

# 2. User-Facing Requirements

## 2.1 Temperature Control

**UR-TC-001**: The system shall allow the user to set target temperatures for each heating zone independently.

**UR-TC-002**: The system shall maintain the temperature in each zone within ±0.5°C of the target temperature under normal operating conditions.

**UR-TC-003**: The user shall be able to enable or disable heating for each zone independently via the dashboard.

**UR-TC-004**: The system shall display current temperature readings for all zones in real-time.

**UR-TC-005**: The user shall be able to view a 24-hour historical temperature graph for each zone.

## 2.2 Energy Efficiency

**UR-EE-001**: The system shall automatically disable heating when an open window is detected in a zone.

**UR-EE-002**: The user shall be able to enable or disable automatic window detection globally for all zones.

**UR-EE-003**: The system shall minimize energy waste by preventing unnecessary pump cycling.

**UR-EE-004**: The user shall be able to view thermal performance metrics (heat loss rate, heat gain rate, insulation quality) for each zone.

## 2.3 System Monitoring

**UR-SM-001**: The user shall be notified when any temperature sensor becomes unavailable.

**UR-SM-002**: The user shall be notified when the temperature in any zone exceeds 26°C for more than 5 minutes.

**UR-SM-003**: The user shall be notified when the temperature in any zone remains more than 2°C below the setpoint for more than 1 hour (when heating is enabled).

**UR-SM-004**: The user shall be able to view the operational status of all hardware components (boiler, pumps, sensors) at a glance.

**UR-SM-005**: The user shall be notified when a window has been left open for more than 30 minutes.

**UR-SM-006**: The user shall be notified if any pump is cycling excessively (>10 cycles/hour).

**UR-SM-007**: The user shall be able to view real-time pump activity and cycling frequency.

## 2.4 Control and Adjustment

**UR-CA-001**: The user shall be able to adjust PID controller parameters (Kp, Ki, Kd) for each zone independently.

**UR-CA-002**: The system shall provide guidance on PID parameter tuning based on observed system behavior.

**UR-CA-003**: Changes to setpoints or settings shall take effect immediately without requiring system restart.

**UR-CA-004**: The system shall respond to manual setpoint changes immediately, bypassing normal pump cycling protection.

**UR-CA-005**: The heating system shall be available as a typical thermostaat control for the user with setpoint, current temperature, mode, schedules. 

**UR-CA-006**: The heating system shall follow schedules defined by the user including time of the day with different setpoints for weekdays and weekends.

**UR-CA-007**: The heating system shall follow mode selected by the user including vacation, off (frozing protection), follow schedule, custom setpoint for X hours. 



## 2.5 Accessibility

**UR-AC-001**: All controls and monitoring shall be accessible via a web-based dashboard on any device.

**UR-AC-002**: The dashboard shall be responsive and usable on mobile phones, tablets, and desktop computers.

**UR-AC-003**: Critical information shall be visible without scrolling on typical mobile phone screens.

**UR-AC-004**: Entity names and labels shall be concise and not truncated on typical screen sizes.

---

# 3. System Requirements

## 3.1 Performance Requirements

**SR-PR-002**: The system shall process temperature updates and adjust heating within 5 seconds of receiving new sensor data.

**SR-PR-003**: The system shall support at least 2 independent heating zones without performance degradation.

**SR-PR-004**: MQTT message delivery shall use QoS 1 (at least once) for all control messages.

**SR-PR-005**: The system shall maintain operation for at least 30 days without manual intervention or restart.

**SR-PR-006**: Historical temperature data shall be retained for at least 24 hours for graphing.

**SR-PR-007**: Thermal performance metrics shall be calculated and published every 60 minutes.

## 3.2 Reliability Requirements

**SR-RL-001**: The system shall automatically reconnect to MQTT broker if connection is lost.

**SR-RL-002**: The system shall gracefully handle unavailable sensors without crashing.

**SR-RL-003**: The system shall continue operating other zones if one zone experiences a sensor failure.

**SR-RL-004**: Configuration changes shall not require Home Assistant restart (except for package additions).

**SR-RL-005**: The control script shall run as a service with automatic restart on failure.

**SR-RL-006**: The system shall publish a heartbeat message every 5 minutes to indicate operational status.

**SR-RL-007**: All configuration shall be stored in YAML files with default values for missing parameters.

## 3.3 Safety Requirements

**SR-SF-001**: The system shall prevent boiler activation if all zone pumps are off.

**SR-SF-002**: The system shall disable heating in a zone if the temperature sensor becomes unavailable.

**SR-SF-003**: The system shall implement a maximum temperature limit of 26°C with automatic shutdown if exceeded.

**SR-SF-004**: Pump minimum ON time shall be at least 10 minutes to prevent premature wear.

**SR-SF-005**: Pump minimum OFF time shall be at least 10 minutes to prevent excessive cycling.

**SR-SF-006**: Manual overrides shall bypass safety limits only for pump cycling protection, not temperature limits.

**SR-SF-007**: The system shall detect stale sensor readings by tracking the last update timestamp for each temperature sensor and shall disable heating in that zone if no sensor update has been received within 20 minutes 

20 minutes is deemed not critical for the heating system to run non-stop in any scenario. 

**SR-SF-008**: If a zone pump has been ON continuously for 6 hours or more, the system shall force the pump OFF, disable heating for that zone, and trigger a critical alert. 

This provides defense-in-depth protection against runaway heating scenarios even if all other safety checks fail.

## 3.4 Integration Requirements

**SR-IN-001**: The system shall integrate with Home Assistant via MQTT protocol.

**SR-IN-002**: The system shall use Zigbee2MQTT for all device communication (sensors, switches, relays).

**SR-IN-003**: The system shall support mobile notifications via Home Assistant mobile app integration.

**SR-IN-004**: All sensor data shall be published to MQTT topics for external monitoring and logging.

**SR-IN-005**: The system shall accept configuration updates via MQTT retained messages.

**SR-IN-006**: Dashboard configuration shall use Home Assistant Lovelace YAML mode.

## 3.5 Data Requirements

**SR-DR-001**: Temperature readings shall be accurate to ±0.1°C.

**SR-DR-002**: PID duty cycle calculations shall use floating-point precision with 3 decimal places.

**SR-DR-003**: Thermal performance calculations shall track at least 20 historical heating/cooling cycles.

**SR-DR-004**: Pump cycle counts shall be tracked per hour and reset at the top of each hour.

**SR-DR-005**: All timestamps shall use UTC with conversion to local time in dashboard display.

## 3.6 Scalability Requirements

**SR-SC-001**: The system architecture shall support addition of new zones without code refactoring.

**SR-SC-002**: MQTT topic structure shall follow a hierarchical naming convention (`heating/{zone}/{metric}`).

**SR-SC-003**: Configuration shall be zone-based, allowing independent tuning parameters per zone.

---

# 4. System Design

## 4.1 Architecture Overview

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
1. **Control**: User faced control (thermostat)
2. **Overview**: Real-time monitoring and control

**SD-HA-014**: The Control view shall contain the following:
1. Header Card
2. Thermostat Control for each zone

**SD-HA-013**: The Overview view shall contain the following card groups (top to bottom):
1. Header card (markdown)
2. Quick Status glance card (5 columns)
3. Zone Controls (2-column horizontal stack)
4. Temperature history graph (24h)
5. Duty cycle history graph (24h)
6. Pump activity history graph (24h)
7. System Health markdown card
8. History Graph that combines temperature, setpoint, pump state, boiler state. 

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

## 5. Traceability Matrix

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

## 6. Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.2 | 2026-01-01 | Claude | Added RISK-013 (Sensor Connection Loss) with critical analysis of stuck reading failure mode; identified gap in current safety requirements; added SR-SF-007 (Sensor Update Watchdog) and SR-SF-008 (Maximum Runtime Safety) to address highest unmitigated risk |
| 1.1 | 2025-12-27 | Claude | Added comprehensive risk assessment with 12 identified risks, likelihood/severity ratings, mitigations, and safety requirements coverage |
| 1.0 | 2025-12-27 | Claude | Initial specification document |

---

**End of Specification**
