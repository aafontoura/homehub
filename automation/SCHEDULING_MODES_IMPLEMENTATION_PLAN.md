# Heating System: Scheduling & Modes Implementation Plan

**Date**: 2025-12-27
**Purpose**: Implementation plan for UR-CA-005, UR-CA-006, UR-CA-007
**Status**: Planning Phase

---

## 1. Executive Summary

This document outlines the plan to extend the existing PID-based heating control system with:
- **Thermostat-like interface** (UR-CA-005)
- **Scheduling system** with weekday/weekend profiles (UR-CA-006)
- **Operating modes** including vacation, off, schedule, and temporary override (UR-CA-007)

These features transform the system from a manual setpoint controller into a fully automated smart thermostat while maintaining the existing PID control, window detection, and thermal monitoring capabilities.

---

## 2. New User Requirements

### UR-CA-005: Thermostat Interface
**Requirement**: The heating system shall be available as a typical thermostat control for the user with setpoint, current temperature, mode, schedules.

**User Impact**: Users can interact with the system like a standard smart thermostat (Nest, Ecobee, etc.) instead of separate controls.

### UR-CA-006: Scheduling
**Requirement**: The heating system shall follow schedules defined by the user including time of the day with different setpoints for weekdays and weekends.

**User Impact**: Set-and-forget operation - temperature automatically adjusts based on time of day and day of week.

### UR-CA-007: Operating Modes
**Requirement**: The heating system shall follow mode selected by the user including vacation, off (freezing protection), follow schedule, custom setpoint for X hours.

**User Impact**: Quick mode changes for common scenarios (going on vacation, manual override, etc.)

---

## 3. System Requirements to Add

### 3.1 Scheduling Requirements

**SR-SC-001**: The system shall support time-based scheduling with configurable setpoints for each time period.

**SR-SC-002**: The system shall support separate schedule profiles for weekdays (Monday-Friday) and weekends (Saturday-Sunday).

**SR-SC-003**: Each schedule shall support at least 4 time periods per day (e.g., morning, day, evening, night).

**SR-SC-004**: Schedule changes shall be evaluated within one minute to determine the active setpoint.

**SR-SC-005**: Schedules shall be stored in Home Assistant input_datetime and input_number helpers for easy user editing.

**SR-SC-006**: The system shall support independent schedules for each heating zone.

**SR-SC-007**: Schedule evaluation shall be timezone-aware and handle daylight saving time transitions.

### 3.2 Operating Mode Requirements

**SR-MD-001**: The system shall support the following operating modes per zone:
- **Off**: Heating disabled, freeze protection active (minimum 5°C)
- **Schedule**: Follow the configured schedule
- **Manual**: Use manually set custom setpoint indefinitely
- **Temporary**: Use custom setpoint for a specified duration, then return to schedule mode
- **Vacation**: Set all zones to energy-saving temperature (e.g., 15°C) until a return date

**SR-MD-002**: Mode transitions shall be immediate (within one control loop cycle = 30 seconds).

**SR-MD-003**: In "Off" mode, the system shall activate heating if temperature falls below 5°C (freeze protection).

**SR-MD-004**: In "Temporary" mode, the system shall automatically revert to "Schedule" mode after the specified duration expires.

**SR-MD-005**: In "Vacation" mode, the system shall automatically return to "Schedule" mode on the specified return date.

**SR-MD-006**: Mode changes shall be logged and published to MQTT for monitoring.

**SR-MD-007**: The current active mode shall be displayed in the dashboard for each zone.

### 3.3 Climate Entity Requirements

**SR-CL-001**: Each heating zone shall be exposed as a Home Assistant Climate entity.

**SR-CL-002**: The Climate entity shall display:
- Current temperature
- Target temperature (from schedule or manual setpoint)
- Current operating mode
- HVAC action (heating/idle)

**SR-CL-003**: The Climate entity shall support changing:
- Target temperature (triggers Manual mode)
- Operating mode (Off/Schedule/Manual)

**SR-CL-004**: Climate entity state changes shall be published to MQTT for Python script consumption.

### 3.4 Integration Requirements

**SR-IN-007**: Schedule and mode configuration shall be stored in Home Assistant helpers (input_select, input_number, input_datetime).

**SR-IN-008**: Schedule and mode state shall be synchronized between Home Assistant and Python control script via MQTT.

**SR-IN-009**: The system shall support modifying schedules via the Home Assistant UI without restarting the Python script.

---

## 4. System Design Elements to Add

### 4.1 Schedule Data Structure

**SD-SC-001**: Schedules shall be stored using Home Assistant input helpers:

```yaml
# Weekday Schedule (Ground Floor example)
input_datetime:
  heating_gf_wd_period1_start:
    name: "GF Weekday Period 1 Start"
    has_time: true
    has_date: false
  # ... repeat for period2, period3, period4

input_number:
  heating_gf_wd_period1_temp:
    name: "GF Weekday Period 1 Temp"
    min: 15
    max: 23
    step: 0.5
    unit_of_measurement: "°C"
  # ... repeat for period2, period3, period4

# Weekend Schedule (similar structure)
```

**SD-SC-002**: Schedule structure per zone:
- **4 time periods per day** (configurable start times + setpoints)
- **2 profiles**: Weekday and Weekend
- **Automatic day detection**: Python script determines current day type

**SD-SC-003**: Schedule evaluation logic:
1. Determine current day type (weekday/weekend)
2. Get current time
3. Find the most recent time period that has started
4. Return the setpoint for that period

**Example Schedule**:
```
Weekday:
  06:00 → 21.0°C (morning)
  08:00 → 19.0°C (day - away at work)
  17:00 → 21.5°C (evening - home)
  22:00 → 18.0°C (night - sleeping)

Weekend:
  08:00 → 20.0°C (morning - sleep in)
  09:00 → 21.5°C (day - home)
  22:00 → 18.0°C (night)
```

### 4.2 Operating Mode State Machine

**SD-MD-001**: Operating modes shall be stored in Home Assistant input_select helper:

```yaml
input_select:
  heating_ground_floor_mode:
    name: "Ground Floor Heating Mode"
    options:
      - "off"
      - "schedule"
      - "manual"
      - "temporary"
      - "vacation"
    initial: "schedule"
```

**SD-MD-002**: Mode transition logic:

```
OFF mode:
  - Setpoint = 5°C (freeze protection)
  - Heating enabled ONLY if temp < 5°C
  - Window detection disabled

SCHEDULE mode:
  - Setpoint = current schedule value
  - Full heating control active
  - Window detection active (if globally enabled)

MANUAL mode:
  - Setpoint = input_number.heating_X_setpoint
  - Full heating control active
  - Window detection active (if globally enabled)

TEMPORARY mode:
  - Setpoint = input_number.heating_X_temp_override
  - Duration = input_number.heating_X_temp_duration (hours)
  - Auto-revert to SCHEDULE after duration expires
  - Window detection active (if globally enabled)

VACATION mode:
  - Setpoint = 15°C (energy saving)
  - Return date = input_datetime.heating_vacation_return
  - Auto-revert to SCHEDULE on return date
  - Window detection disabled (expect temperature drop)
```

**SD-MD-003**: Mode state published to MQTT:
```json
{
  "zone": "ground_floor",
  "mode": "schedule",
  "active_setpoint": 21.0,
  "setpoint_source": "weekday_period2"
}
```

### 4.3 Climate Entity Integration

**SD-CL-001**: Use Home Assistant MQTT Climate platform to create thermostat entities:

```yaml
mqtt:
  climate:
    - name: "Heating Ground Floor"
      unique_id: heating_climate_ground_floor
      modes:
        - "off"
        - "heat"
      mode_state_topic: "heating/ground_floor/climate/mode"
      mode_command_topic: "heating/ground_floor/climate/mode/set"
      temperature_state_topic: "heating/ground_floor/climate/setpoint"
      temperature_command_topic: "heating/ground_floor/climate/setpoint/set"
      current_temperature_topic: "heating/ground_floor/current_temp"
      temp_step: 0.5
      min_temp: 5
      max_temp: 26
      action_topic: "heating/ground_floor/climate/action"
```

**SD-CL-002**: Climate entity shall display in dashboard using `thermostat` card:

```yaml
- type: thermostat
  entity: climate.heating_ground_floor
  features:
    - type: climate-hvac-modes
```

### 4.4 Python Script Modifications

**SD-PY-020**: Add `ScheduleManager` class to evaluate schedules:

```python
class ScheduleManager:
    def __init__(self, zone_name):
        self.zone = zone_name
        self.weekday_schedule = []  # [(time, setpoint), ...]
        self.weekend_schedule = []

    def update_schedule(self, schedule_data):
        """Update schedule from MQTT message"""
        pass

    def get_current_setpoint(self):
        """Return setpoint for current day/time"""
        is_weekend = datetime.now().weekday() >= 5
        schedule = self.weekend_schedule if is_weekend else self.weekday_schedule
        current_time = datetime.now().time()

        # Find most recent period that has started
        active_setpoint = schedule[0][1]  # Default to first period
        for period_time, setpoint in schedule:
            if current_time >= period_time:
                active_setpoint = setpoint

        return active_setpoint
```

**SD-PY-021**: Add `ModeManager` class to handle mode transitions:

```python
class ModeManager:
    def __init__(self, zone_name):
        self.zone = zone_name
        self.current_mode = "schedule"
        self.manual_setpoint = 20.0
        self.temp_override_setpoint = 20.0
        self.temp_override_expiry = None
        self.vacation_return_date = None

    def set_mode(self, mode):
        """Change operating mode"""
        logging.info(f"{self.zone}: Mode changed to {mode}")
        self.current_mode = mode

    def get_active_setpoint(self, schedule_manager):
        """Return active setpoint based on current mode"""
        if self.current_mode == "off":
            return 5.0  # Freeze protection
        elif self.current_mode == "schedule":
            return schedule_manager.get_current_setpoint()
        elif self.current_mode == "manual":
            return self.manual_setpoint
        elif self.current_mode == "temporary":
            if datetime.now() > self.temp_override_expiry:
                self.set_mode("schedule")
                return schedule_manager.get_current_setpoint()
            return self.temp_override_setpoint
        elif self.current_mode == "vacation":
            if datetime.now().date() >= self.vacation_return_date:
                self.set_mode("schedule")
                return schedule_manager.get_current_setpoint()
            return 15.0  # Energy saving temp

    def is_heating_allowed(self):
        """Check if heating is allowed in current mode"""
        return self.current_mode != "off"  # Off mode uses freeze protection
```

**SD-PY-022**: Integrate mode and schedule into `HeatingZone` class:

```python
class HeatingZone:
    def __init__(self, name, config):
        # ... existing init ...
        self.schedule_manager = ScheduleManager(name)
        self.mode_manager = ModeManager(name)

    def update_control(self):
        """Main control loop - called every 30 seconds"""
        # Get active setpoint based on current mode
        target_setpoint = self.mode_manager.get_active_setpoint(self.schedule_manager)

        # Check if heating is allowed
        if not self.mode_manager.is_heating_allowed():
            # Off mode - only heat if below freeze protection threshold
            if self.current_temp < 5.0:
                target_setpoint = 5.0
            else:
                self.disable_heating()
                return

        # ... existing PID logic using target_setpoint ...
```

**SD-PY-023**: Add MQTT subscriptions for schedule and mode updates:

```python
def _setup_subscriptions(self):
    """Subscribe to all necessary MQTT topics"""
    topics = [
        # Existing topics...
        f"heating/{self.name}/schedule/weekday/set",
        f"heating/{self.name}/schedule/weekend/set",
        f"heating/{self.name}/mode/set",
        f"heating/{self.name}/temp_override/set",
        "heating/vacation/set"
    ]
    self._subscribe_to_topics(topics)
```

### 4.5 MQTT Topic Structure

**SD-MQTT-006**: New MQTT topics for scheduling and modes:

**Schedule Configuration** (Home Assistant → Python):
```
heating/{zone}/schedule/weekday/set
  Payload: {
    "period1": {"time": "06:00", "temp": 21.0},
    "period2": {"time": "08:00", "temp": 19.0},
    "period3": {"time": "17:00", "temp": 21.5},
    "period4": {"time": "22:00", "temp": 18.0}
  }

heating/{zone}/schedule/weekend/set
  Payload: {similar structure}
```

**Mode Control** (Home Assistant → Python):
```
heating/{zone}/mode/set
  Payload: {"mode": "schedule|manual|temporary|vacation|off"}

heating/{zone}/temp_override/set
  Payload: {"temp": 22.0, "duration_hours": 3}

heating/vacation/set
  Payload: {"return_date": "2025-12-31"}
```

**Mode Status** (Python → Home Assistant):
```
heating/{zone}/mode/status
  Payload: {
    "mode": "schedule",
    "active_setpoint": 21.0,
    "setpoint_source": "weekday_period2",
    "next_change": "17:00"
  }
```

### 4.6 Dashboard Updates

**SD-DASH-001**: Add Climate card to main dashboard:

```yaml
# Replace current zone control cards with:
- type: thermostat
  entity: climate.heating_ground_floor
  features:
    - type: climate-hvac-modes
  show_current_as_primary: true
```

**SD-DASH-002**: Add Schedule Configuration tab:

```yaml
- title: Schedules
  path: schedules
  cards:
    # Weekday Schedule Card
    - type: entities
      title: "Ground Floor - Weekday Schedule"
      entities:
        - input_datetime.heating_gf_wd_period1_start
        - input_number.heating_gf_wd_period1_temp
        - input_datetime.heating_gf_wd_period2_start
        - input_number.heating_gf_wd_period2_temp
        # ... periods 3 & 4

    # Weekend Schedule Card
    - type: entities
      title: "Ground Floor - Weekend Schedule"
      entities:
        # ... similar structure
```

**SD-DASH-003**: Add Mode Control card:

```yaml
- type: entities
  title: "Heating Modes"
  entities:
    - input_select.heating_ground_floor_mode
    - input_number.heating_ground_floor_temp_override
    - input_number.heating_ground_floor_temp_duration
    - input_datetime.heating_vacation_return
```

---

## 5. Implementation Phases

### Phase 1: Schedule Infrastructure (2-3 hours)
1. Create input helpers for schedule storage (weekday/weekend, 4 periods per zone)
2. Create Home Assistant automations to publish schedule changes to MQTT
3. Add `ScheduleManager` class to Python script
4. Test schedule evaluation logic with various day/time scenarios

**Deliverables**:
- `packages/heating/schedules.yaml` - Input helpers and automations
- Updated `heating_control.py` with `ScheduleManager`
- Unit tests for schedule evaluation

### Phase 2: Mode Management (2-3 hours)
1. Create input_select helpers for mode selection
2. Add input helpers for temporary override and vacation settings
3. Implement `ModeManager` class in Python script
4. Add mode transition logic and MQTT subscriptions
5. Test all mode transitions and edge cases

**Deliverables**:
- `packages/heating/modes.yaml` - Mode helpers and automations
- Updated `heating_control.py` with `ModeManager`
- Unit tests for mode transitions

### Phase 3: Climate Entity Integration (1-2 hours)
1. Create MQTT Climate entities for each zone
2. Update Python script to publish climate state
3. Test climate entity state synchronization
4. Verify climate entity control (setpoint, mode changes)

**Deliverables**:
- `packages/heating/climate.yaml` - MQTT Climate entities
- Updated Python script with climate state publishing

### Phase 4: Dashboard Updates (1-2 hours)
1. Replace basic controls with thermostat cards
2. Create Schedule configuration tab
3. Create Mode control section
4. Update system health to show current mode
5. Test UI on mobile and desktop

**Deliverables**:
- Updated `dashboards/heating.yaml`
- Screenshots of new UI

### Phase 5: Testing & Documentation (2-3 hours)
1. End-to-end testing of all modes
2. Schedule transition testing (day changes, DST)
3. Update specification document with new SR/SD elements
4. Create user guide for scheduling
5. Update risk assessment

**Deliverables**:
- Test report
- Updated `HEATING_SYSTEM_SPECIFICATION.md`
- `SCHEDULING_USER_GUIDE.md`

**Total Estimated Time**: 8-13 hours

---

## 6. Risk Assessment

### RISK-013: Schedule Malfunction Causing Discomfort
**Description**: Schedule evaluation bug causes incorrect setpoint to be applied, resulting in over/underheating.

**Likelihood**: 3 (Possible - scheduling logic is complex)
**Severity**: 2 (Minor - temporary discomfort, user can switch to manual mode)
**Risk Rating**: 6 (Low)

**Related Requirements**: SR-SC-004, SR-SC-007

**Mitigations**:
1. **Implemented**: Manual mode allows bypassing schedule if issues occur (SR-MD-001)
2. **Implemented**: Current active setpoint displayed in dashboard for verification (SD-MD-003)
3. **Recommended**: Log every schedule evaluation with timestamp and selected period
4. **Recommended**: Publish "next schedule change" time to dashboard for user awareness
5. **Recommended**: Unit tests covering edge cases (midnight rollover, DST transitions)

### RISK-014: Mode Transition Failure Leaving System in Wrong State
**Description**: Mode change command fails to process, leaving system in unintended mode (e.g., stuck in vacation mode after returning).

**Likelihood**: 2 (Unlikely - MQTT is reliable)
**Severity**: 3 (Moderate - discomfort, energy waste until noticed)
**Risk Rating**: 6 (Low)

**Related Requirements**: SR-MD-002, SR-MD-006

**Mitigations**:
1. **Implemented**: Mode changes logged and published to MQTT for monitoring (SR-MD-006)
2. **Implemented**: Current mode displayed in dashboard (SR-MD-007)
3. **Implemented**: Automatic mode reversion (temporary → schedule, vacation → schedule)
4. **Recommended**: Mode state persisted to disk and restored on Python script restart
5. **Recommended**: Alert if mode hasn't changed in >7 days (possible stuck state)

### RISK-015: Freeze Protection Failure in Off Mode
**Description**: In "Off" mode, freeze protection logic fails, allowing pipes to freeze and burst.

**Likelihood**: 2 (Unlikely - simple threshold logic)
**Severity**: 5 (Catastrophic - property damage, pipe burst)
**Risk Rating**: 10 (Medium)

**Related Requirements**: SR-MD-003, SR-SF-002

**Mitigations**:
1. **Implemented**: Freeze protection activates at 5°C in Off mode (SR-MD-003)
2. **Implemented**: Heating disabled if sensor unavailable (SR-SF-002 - prevents false freeze activation)
3. **Recommended**: Alert notification if temperature drops below 7°C in Off mode
4. **Recommended**: Weekly reminder notification if system in Off mode for >7 days
5. **Recommended**: Freeze protection temperature configurable (default 5°C, range 3-8°C)

### RISK-016: Timezone/DST Issues Causing Schedule Misalignment
**Description**: Daylight saving time transition or timezone misconfiguration causes schedule to activate at wrong times.

**Likelihood**: 3 (Possible - DST transitions happen twice per year)
**Severity**: 2 (Minor - temporary discomfort, self-corrects after 1 hour)
**Risk Rating**: 6 (Low)

**Related Requirements**: SR-SC-007

**Mitigations**:
1. **Implemented**: Timezone-aware schedule evaluation (SR-SC-007)
2. **Recommended**: Use Home Assistant's internal timezone configuration
3. **Recommended**: Log warning during DST transition days
4. **Recommended**: Display current system time and timezone in dashboard
5. **Recommended**: Notification 1 week before DST transition to verify schedules

### RISK-017: Temporary Override Expiry Not Reverting to Schedule
**Description**: Temporary mode timer fails to expire, preventing automatic return to schedule mode.

**Likelihood**: 2 (Unlikely - simple time comparison)
**Severity**: 2 (Minor - user can manually switch back to schedule mode)
**Risk Rating**: 4 (Low)

**Related Requirements**: SR-MD-004

**Mitigations**:
1. **Implemented**: Automatic reversion to schedule mode on expiry (SR-MD-004)
2. **Implemented**: Mode transitions logged (SR-MD-006)
3. **Recommended**: Display countdown timer in dashboard ("Temporary mode expires in 2h 15m")
4. **Recommended**: Notification when temporary mode expires
5. **Recommended**: Maximum temporary override duration (e.g., 24 hours)

### RISK-018: Vacation Mode Not Deactivating on Return Date
**Description**: Vacation mode fails to deactivate on return date, leaving home cold upon arrival.

**Likelihood**: 2 (Unlikely - date comparison is simple)
**Severity**: 3 (Moderate - significant discomfort arriving to cold home)
**Risk Rating**: 6 (Low)

**Related Requirements**: SR-MD-005

**Mitigations**:
1. **Implemented**: Automatic return to schedule mode on return date (SR-MD-005)
2. **Implemented**: Mode status visible in dashboard (SR-MD-007)
3. **Recommended**: Pre-heat option: activate schedule mode 2 hours before return time
4. **Recommended**: Notification on return date when vacation mode deactivates
5. **Recommended**: Mobile app notification if still in vacation mode 2 hours after return date

---

## 7. Traceability Matrix Updates

### User Requirements → System Requirements

| User Requirement | System Requirements |
|------------------|---------------------|
| UR-CA-005 (Thermostat Interface) | SR-CL-001, SR-CL-002, SR-CL-003, SR-CL-004 |
| UR-CA-006 (Scheduling) | SR-SC-001, SR-SC-002, SR-SC-003, SR-SC-004, SR-SC-005, SR-SC-006, SR-SC-007 |
| UR-CA-007 (Operating Modes) | SR-MD-001, SR-MD-002, SR-MD-003, SR-MD-004, SR-MD-005, SR-MD-006, SR-MD-007 |

### System Requirements → Design Elements

| System Requirement | Design Elements |
|--------------------|----------------|
| SR-SC-001 | SD-SC-001, SD-SC-002, SD-SC-003 |
| SR-SC-004 | SD-PY-020 |
| SR-MD-001 | SD-MD-001, SD-MD-002 |
| SR-MD-002 | SD-PY-021 |
| SR-CL-001 | SD-CL-001 |
| SR-CL-002 | SD-CL-001, SD-PY-022 |
| SR-IN-007 | SD-SC-001, SD-MD-001 |
| SR-IN-008 | SD-MQTT-006, SD-PY-023 |

---

## 8. Testing Strategy

### 8.1 Unit Tests

**Schedule Manager Tests**:
- Test weekday schedule evaluation (Monday-Friday)
- Test weekend schedule evaluation (Saturday-Sunday)
- Test midnight rollover (23:59 → 00:00)
- Test schedule with gaps between periods
- Test schedule update from MQTT

**Mode Manager Tests**:
- Test each mode transition (off ↔ schedule ↔ manual ↔ temporary ↔ vacation)
- Test temporary mode expiry
- Test vacation mode return date
- Test freeze protection activation in off mode
- Test setpoint calculation for each mode

### 8.2 Integration Tests

**End-to-End Scenarios**:
1. **Morning Weekday**: Verify schedule changes from night → morning setpoint at 06:00
2. **Weekend Day Transition**: Verify Friday evening → Saturday morning uses weekend schedule
3. **Manual Override**: User sets manual setpoint, verify mode switches to manual
4. **Temporary Override**: Set 3-hour override, verify auto-revert to schedule after 3 hours
5. **Vacation Mode**: Enable vacation, verify 15°C setpoint, set return date, verify auto-revert
6. **Freeze Protection**: Set mode to off, lower temp below 5°C, verify heating activates
7. **DST Transition**: Simulate clock change, verify schedule still activates at correct local time

### 8.3 User Acceptance Tests

**Usability Tests**:
- User can create a weekly schedule in <5 minutes
- User can enable vacation mode with return date in <1 minute
- User can set temporary override in <30 seconds
- Climate card displays current/target temps clearly on mobile
- Mode changes reflect in UI within 30 seconds

---

## 9. Migration Path

### 9.1 Existing System Compatibility

**Current State**:
- Users manually control setpoints via `input_number` helpers
- `input_boolean` toggles enable/disable heating per zone
- No scheduling or automated mode changes

**Migration Strategy**:
1. **Default to Manual Mode**: On first deployment, set all zones to "manual" mode using current setpoint values
2. **Preserve Existing Controls**: Keep existing input_number setpoint helpers (now used in manual mode)
3. **Gradual Adoption**: Users can continue using manual controls, enable scheduling when ready
4. **Documentation**: Provide migration guide showing how to:
   - Configure first schedule
   - Switch from manual to schedule mode
   - Use temporary override for one-off changes

### 9.2 Backward Compatibility

**Maintain Existing Features**:
- PID control parameters (Kp, Ki, Kd) remain adjustable
- Window detection still functions (disabled in off/vacation modes)
- Pump cycling protection remains active
- Thermal performance monitoring continues
- All existing dashboard metrics preserved

**No Breaking Changes**:
- Python script remains compatible with current MQTT topics
- Existing automations continue to work
- Dashboard can be updated incrementally (keep old cards during transition)

---

## 10. Documentation Updates Required

### 10.1 Specification Document Updates

**Add to Section 2 (System Requirements)**:
- 2.7 Scheduling Requirements (SR-SC-*)
- 2.8 Operating Mode Requirements (SR-MD-*)
- 2.9 Climate Entity Requirements (SR-CL-*)
- Update 2.4 Integration Requirements (add SR-IN-007, SR-IN-008)

**Add to Section 3 (System Design)**:
- 3.8 Schedule Management (SD-SC-*)
- 3.9 Mode Management (SD-MD-*)
- 3.10 Climate Entity Integration (SD-CL-*)
- 3.11 Dashboard Updates (SD-DASH-*)
- Update 3.4 MQTT Topics (add SD-MQTT-006)
- Update 3.3 Python Script (add SD-PY-020, SD-PY-021, SD-PY-022, SD-PY-023)

**Update Section 4 (Risk Assessment)**:
- Add RISK-013 through RISK-018
- Update risk summary table

**Update Section 5 (Traceability Matrix)**:
- Add UR-CA-005/006/007 mappings
- Add new SR-* and SD-* mappings

**Update Document Version**: 1.2 → 1.3

### 10.2 New User Documentation

**Create**: `SCHEDULING_USER_GUIDE.md`
- How to create your first schedule
- Understanding weekday vs weekend profiles
- Using operating modes
- Best practices for energy efficiency
- Troubleshooting common issues

**Create**: `MODE_REFERENCE.md`
- Detailed explanation of each mode
- When to use each mode
- Mode priority and override behavior
- Examples and use cases

### 10.3 Developer Documentation

**Update**: `heating_control.py` docstrings
- Document new classes (ScheduleManager, ModeManager)
- Document MQTT topic structure
- Document configuration format

**Create**: `SCHEDULING_ARCHITECTURE.md`
- System architecture diagrams
- Data flow for schedule evaluation
- Mode state machine diagram
- MQTT topic reference

---

## 11. Success Criteria

### 11.1 Functional Requirements Met
- ✅ Users can configure schedules via Home Assistant UI
- ✅ Schedules automatically adjust setpoints based on time and day
- ✅ All 5 operating modes function correctly
- ✅ Temporary overrides auto-revert after expiry
- ✅ Vacation mode auto-reverts on return date
- ✅ Freeze protection works in off mode
- ✅ Climate entities display and control correctly

### 11.2 Non-Functional Requirements Met
- ✅ Mode changes take effect within 30 seconds
- ✅ Schedule evaluation completes in <100ms
- ✅ System remains stable for 7+ days continuous operation
- ✅ Dashboard remains responsive on mobile devices
- ✅ All existing features continue working

### 11.3 Quality Metrics
- ✅ Unit test coverage >80% for new code
- ✅ Zero critical bugs in end-to-end testing
- ✅ User acceptance testing completed successfully
- ✅ Documentation reviewed and approved
- ✅ Risk assessment complete with mitigations identified

---

## 12. Open Questions & Decisions Needed

### 12.1 Schedule Granularity
**Question**: Should we support 4, 6, or 8 time periods per day?
**Options**:
- 4 periods (morning, day, evening, night) - simpler, covers most use cases
- 6 periods - more flexibility
- 8 periods - maximum flexibility but complex UI

**Recommendation**: Start with 4 periods, make extensible for future enhancement

### 12.2 Vacation Mode Scope
**Question**: Should vacation mode be global (all zones) or per-zone?
**Options**:
- Global - simpler, most common use case (whole house on vacation)
- Per-zone - more flexible but complex

**Recommendation**: Global vacation mode, can enhance to per-zone in future if needed

### 12.3 Temporary Override Default Duration
**Question**: What should be the default duration for temporary overrides?
**Options**:
- 1 hour - short, safe default
- 3 hours - typical "until I get home" duration
- 8 hours - full day/night override

**Recommendation**: 3 hours default, user-configurable from 1-24 hours

### 12.4 Climate Entity HVAC Modes
**Question**: Should we expose all our modes as HVAC modes, or simplify?
**Options**:
- Simple: off, heat (our modes hidden, controlled via input_select)
- Complex: off, heat, auto (map to our modes)

**Recommendation**: Simple approach - use standard HVAC modes, control our modes via separate input_select for clarity

### 12.5 Schedule Storage Format
**Question**: Store schedules in Home Assistant helpers or configuration file?
**Options**:
- Helpers (input_datetime, input_number) - user-editable via UI
- YAML config file - version controlled, but requires restart to change

**Recommendation**: Helpers for ease of use, optionally add YAML import/export feature

---

## 13. Next Steps

1. **Review this plan** with stakeholders/user
2. **Decide on open questions** (section 12)
3. **Begin Phase 1** (Schedule Infrastructure)
4. **Incremental deployment**: Test each phase before proceeding
5. **Update specification document** as implementation progresses

---

**End of Implementation Plan**
