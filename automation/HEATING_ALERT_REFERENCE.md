# Heating System Alert Reference

## Document Information
**Version**: 1.0
**Last Updated**: 2026-01-02
**Related Specification**: HEATING_SYSTEM_SPECIFICATION.md Section 3.7 (SR-AL-001, SR-AL-002, SR-AL-003)

---

## Alert ID Format

All heating system alerts follow the format: `HEAT-{CATEGORY}-{NUMBER}`

**Categories**:
- **SF** (Safety): Critical safety alerts related to system protection mechanisms
- **SN** (Sensor): Temperature sensor availability alerts
- **HW** (Hardware): Hardware component connectivity alerts (boiler, pumps, relays)
- **PR** (Performance): System performance and efficiency alerts
- **SY** (System): Control script and service status alerts

---

## Alert Catalog

### HEAT-SF-001: Stale Sensor Reading (Critical)

**Severity**: CRITICAL
**Category**: Safety
**Related Requirement**: SR-SF-007, RISK-013 Failure Mode B
**MQTT Topic**: `heating/{zone_name}/alert/critical`

**Description**:
Temperature sensor has stopped sending updates but retained its last reading, creating risk of uncontrolled heating. This is distinct from sensor going unavailable - the sensor appears "online" but data is frozen.

**Trigger Conditions**:
- No temperature sensor update received for 20 minutes
- Sensor value is not `None` (appears to have valid reading)
- Published directly from Python heating_control.py

**Possible Causes**:
1. **Battery depletion**: Zigbee sensor battery died mid-transmission, firmware froze while maintaining MQTT connection
2. **Zigbee link quality degradation**: Poor signal quality causing sensor to stop transmitting but not disconnect
3. **Sensor firmware crash**: Device firmware hung while maintaining network connection
4. **MQTT broker issue**: Broker stopped receiving updates but retained last message
5. **Network interference**: Sustained RF interference preventing sensor updates

**Recommended Actions**:
1. **IMMEDIATE**: Check Home Assistant → Zigbee2MQTT → Device → Last Seen timestamp
2. Check sensor battery level (should show % in Zigbee2MQTT)
3. Check Zigbee link quality indicator (LQI should be >100)
4. Physically inspect sensor - LED should blink on temperature change
5. Replace sensor battery if >1 year old
6. Move Zigbee coordinator closer if LQI < 100
7. Check for new 2.4GHz interference sources (WiFi routers, microwave ovens)
8. **Resolution**: Heating will auto-resume when sensor sends fresh update

**Impact if Ignored**:
Room may overheat unchecked. Heating continues running based on stale temperature reading. Could result in temperatures exceeding 26°C safety limit.

**Logged As**:
```
WARNING: {zone_name}: SENSOR STALE - No update for X min (threshold: 20 min)
CRITICAL: {zone_name}: [HEAT-SF-001] CRITICAL ALERT published - No sensor update for X minutes - heating disabled
```

---

### HEAT-SF-002: Maximum Runtime Exceeded (Critical)

**Severity**: CRITICAL
**Category**: Safety
**Related Requirement**: SR-SF-008, RISK-013 Failure Mode B
**MQTT Topic**: `heating/{zone_name}/alert/critical`

**Description**:
Zone pump has been running continuously for 6 hours, indicating potential runaway heating scenario. This is a defense-in-depth backup safety mechanism.

**Trigger Conditions**:
- Pump has been ON continuously for ≥6 hours
- Independent of temperature readings
- Published directly from Python heating_control.py

**Possible Causes**:
1. **Stuck sensor reading**: Temperature sensor frozen at low value, see HEAT-SF-001
2. **Extreme cold weather**: Legitimate long runtime during severe outdoor conditions
3. **Insulation failure**: Significant heat loss preventing zone from reaching setpoint
4. **Boiler malfunction**: Boiler not delivering sufficient heat
5. **Pump undersized**: Flow rate insufficient for heating demand
6. **Setpoint unrealistic**: Target temperature set too high for system capacity

**Recommended Actions**:
1. **IMMEDIATE**: Check actual room temperature with independent thermometer
2. Compare to sensor reading - if different by >1°C, replace sensor battery
3. Check outdoor temperature - if <-5°C, this may be legitimate long runtime
4. Inspect windows/doors for gaps or damage
5. Check boiler flame - should be active and stable
6. Verify pump flow rate (listen for water flow sounds)
7. Review setpoint - reduce if >22°C
8. **Resolution**: System will NOT auto-resume - requires manual restart of heating service after root cause addressed

**Impact if Ignored**:
N/A - System automatically forces pump OFF and disables heating for the zone. Manual intervention required.

**Logged As**:
```
CRITICAL: {zone_name}: EMERGENCY SHUTDOWN - Pump runtime X.Xh exceeded 6h limit
CRITICAL: {zone_name}: [HEAT-SF-002] CRITICAL ALERT published - Emergency shutdown: pump runtime X.Xh exceeded 6h limit
```

---

### HEAT-SF-003: Ground Floor Overtemperature (High)

**Severity**: HIGH
**Category**: Safety
**Related Requirement**: SR-SF-003, UR-SM-002, RISK-001
**Home Assistant**: automation `heating_alert_ground_floor_overtemp`

**Description**:
Ground floor temperature has exceeded 26°C safety limit for more than 5 minutes.

**Trigger Conditions**:
- `sensor.living_room_sensor_temperature` > 26°C
- Sustained for >5 minutes

**Possible Causes**:
1. **Controller tuning aggressive**: ON/OFF hysteresis too wide or PID gains too high
2. **External heat source**: Sun exposure through windows, fireplace use, cooking heat
3. **Setpoint too high**: User set target temperature >24°C
4. **Sensor miscalibration**: Sensor reading 2-3°C high
5. **Pump stuck ON**: Relay failure keeping pump running (see RISK-008)

**Recommended Actions**:
1. Check current setpoint in Home Assistant climate entity
2. Reduce setpoint to ≤22°C
3. Check for external heat sources (close curtains, turn off fireplace)
4. If using ON/OFF controller, check hysteresis (should be ≤0.3°C)
5. If using PID controller, reduce Kp gain by 20%
6. Verify pump actually turns OFF when commanded (check `switch.pump_ufh_ground_floor`)
7. Calibrate sensor using independent thermometer
8. Monitor for 1 hour after adjustment

**Impact if Ignored**:
Reduced comfort, increased energy consumption, potential property damage if sustained >30°C (wooden floors, electronics). System should auto-regulate via SR-SF-003 max temp safety.

**Logged As**:
Home Assistant automation logs only (not in Python service logs).

---

### HEAT-SF-004: First Floor Overtemperature (High)

**Severity**: HIGH
**Category**: Safety
**Related Requirement**: SR-SF-003, UR-SM-002, RISK-001
**Home Assistant**: automation `heating_alert_first_floor_overtemp`

**Description**:
First floor temperature has exceeded 26°C safety limit for more than 5 minutes.

**Trigger Conditions**:
- `sensor.first_floor_sensor_temperature` > 26°C
- Sustained for >5 minutes

**Possible Causes**:
1. **Controller tuning aggressive**: ON/OFF hysteresis too wide or PID gains too high
2. **Heat rise from ground floor**: Warm air rising when ground floor heating active
3. **External heat source**: Sun exposure, electric heaters
4. **Setpoint too high**: User set target temperature >23°C
5. **Sensor miscalibration**: Sensor reading 2-3°C high
6. **Insulation**: Better insulated than ground floor, retains heat longer

**Recommended Actions**:
1. Check current setpoint in Home Assistant climate entity
2. Reduce setpoint to ≤21°C (first floor typically warmer)
3. Check ground floor setpoint - if >22°C, reduce it first
4. Check for external heat sources
5. If using ON/OFF controller, reduce hysteresis to 0.15°C
6. If using PID controller, reduce Kp gain by 20%
7. Verify pump actually turns OFF when commanded
8. Consider reducing default setpoint in `heating_config.yaml` to 18°C

**Impact if Ignored**:
Reduced comfort, increased energy consumption. First floor typically has lower heat demand than ground floor.

**Logged As**:
Home Assistant automation logs only.

---

### HEAT-SN-001: Ground Floor Sensor Unavailable (High)

**Severity**: HIGH
**Category**: Sensor
**Related Requirement**: SR-SF-002, UR-SM-001, RISK-013 Failure Mode A
**Home Assistant**: automation `heating_alert_ground_floor_sensor_unavailable`

**Description**:
Ground floor temperature sensor (Living Room Sensor) has become unavailable and is not reporting temperature data.

**Trigger Conditions**:
- `sensor.living_room_sensor_temperature` state = `unavailable`
- Sustained for >5 minutes

**Possible Causes**:
1. **Battery depleted**: Zigbee sensor battery fully drained
2. **Zigbee network issue**: Coordinator offline, mesh network disrupted
3. **Sensor hardware failure**: Device malfunction or damage
4. **Physical obstruction**: Sensor moved or fell, lost line-of-sight to coordinator
5. **Firmware crash**: Sensor requires power cycle

**Recommended Actions**:
1. **IMMEDIATE**: Ground floor heating will auto-disable per SR-SF-002 (safe shutdown)
2. Check Zigbee2MQTT dashboard - is sensor showing as offline?
3. Replace sensor battery (typically CR2032 or AA)
4. Power cycle sensor (remove/reinsert battery)
5. Check Zigbee coordinator status in Docker: `docker logs zigbee2mqtt -f`
6. If multiple sensors offline, check coordinator USB stick connection
7. Re-pair sensor to Zigbee2MQTT if persistently offline
8. **Resolution**: Heating will auto-resume when sensor returns online

**Impact if Ignored**:
Ground floor heating disabled until sensor restored. No safety risk - system fails safe.

**Logged As**:
Home Assistant automation logs. Python service logs will show `current_temp is None` and disable heating.

---

### HEAT-SN-002: First Floor Sensor Unavailable (High)

**Severity**: HIGH
**Category**: Sensor
**Related Requirement**: SR-SF-002, UR-SM-001, RISK-013 Failure Mode A
**Home Assistant**: automation `heating_alert_first_floor_sensor_unavailable`

**Description**:
First floor temperature sensor has become unavailable and is not reporting temperature data.

**Trigger Conditions**:
- `sensor.first_floor_sensor_temperature` state = `unavailable`
- Sustained for >5 minutes

**Possible Causes**:
1. **Battery depleted**: Zigbee sensor battery fully drained
2. **Zigbee network issue**: Coordinator offline, mesh network disrupted
3. **Sensor hardware failure**: Device malfunction or damage
4. **Physical distance**: First floor sensor may be at edge of Zigbee range
5. **Interference**: 2.4GHz WiFi or other devices blocking signal

**Recommended Actions**:
1. **IMMEDIATE**: First floor heating will auto-disable per SR-SF-002 (safe shutdown)
2. Check Zigbee2MQTT dashboard - is sensor showing as offline?
3. Replace sensor battery
4. Check Zigbee link quality (LQI) - should be >100
5. Add Zigbee router device if LQI consistently low
6. Power cycle sensor
7. Re-pair sensor if needed
8. **Resolution**: Heating will auto-resume when sensor returns online

**Impact if Ignored**:
First floor heating disabled until sensor restored. No safety risk - system fails safe.

**Logged As**:
Home Assistant automation logs. Python service logs will show `current_temp is None` and disable heating.

---

### HEAT-HW-001: Boiler Relay Offline (Critical)

**Severity**: CRITICAL
**Category**: Hardware
**Related Requirement**: SR-SF-001, RISK-007
**Home Assistant**: automation `heating_alert_boiler_relay_offline`

**Description**:
Shelly boiler relay is unavailable. Python heating control cannot activate boiler, disabling all heating zones.

**Trigger Conditions**:
- `switch.boiler_heat_request_switch` state = `unavailable`
- Sustained for >5 minutes

**Possible Causes**:
1. **Shelly device offline**: Power loss, WiFi disconnection, device failure
2. **Network issue**: Home Assistant cannot reach Shelly on network
3. **Shelly firmware crash**: Device requires reboot
4. **MQTT broker issue**: Broker not relaying Shelly messages
5. **Power supply failure**: Shelly not receiving power

**Recommended Actions**:
1. **IMMEDIATE**: ALL heating zones disabled - system cannot activate boiler
2. Check Shelly device status lights (should show WiFi and power)
3. Ping Shelly IP address from Home Assistant host
4. Check Shelly web UI directly (http://<shelly_ip>)
5. Power cycle Shelly device
6. Check MQTT broker status: `docker logs mosquitto -f`
7. Verify Shelly configured for MQTT mode (not HTTP)
8. Check Home Assistant Shelly integration status
9. **Resolution**: Heating will resume when Shelly relay returns online

**Impact if Ignored**:
Complete heating system failure. Boiler cannot be activated. Property at risk of freezing in winter.

**Logged As**:
Home Assistant automation logs. Python service logs will show boiler command failures.

---

### HEAT-HW-002: Ground Floor Pump Offline (High)

**Severity**: HIGH
**Category**: Hardware
**Related Requirement**: SR-RL-003
**Home Assistant**: automation `heating_alert_pump_ground_floor_offline`

**Description**:
Ground floor pump relay is unavailable. Ground floor heating not possible, but first floor can continue operating.

**Trigger Conditions**:
- `switch.pump_ufh_ground_floor` state = `unavailable`
- Sustained for >5 minutes

**Possible Causes**:
1. **Shelly/relay offline**: Power loss, WiFi disconnection
2. **Network issue**: Home Assistant cannot reach relay
3. **Device firmware crash**: Relay requires reboot
4. **Wiring fault**: Relay lost power supply

**Recommended Actions**:
1. **IMMEDIATE**: Ground floor heating disabled, first floor continues
2. Check pump relay device status (LED indicators)
3. Ping relay IP address
4. Access relay web UI directly
5. Power cycle relay device
6. Check 24V power supply to relay
7. Verify relay MQTT configuration
8. **Resolution**: Ground floor heating resumes when relay returns online

**Impact if Ignored**:
Ground floor heating disabled. First floor heating unaffected per SR-RL-003 zone independence.

**Logged As**:
Home Assistant automation logs. Python service logs will show pump command failures for ground floor.

---

### HEAT-HW-003: First Floor Pump Offline (High)

**Severity**: HIGH
**Category**: Hardware
**Related Requirement**: SR-RL-003
**Home Assistant**: automation `heating_alert_pump_first_floor_offline`

**Description**:
First floor pump relay is unavailable. First floor heating not possible, but ground floor can continue operating.

**Trigger Conditions**:
- `switch.pump_ufh_first_floor` state = `unavailable`
- Sustained for >5 minutes

**Possible Causes**:
1. **Shelly/relay offline**: Power loss, WiFi disconnection
2. **Network issue**: Home Assistant cannot reach relay
3. **Device firmware crash**: Relay requires reboot
4. **Wiring fault**: Relay lost power supply

**Recommended Actions**:
1. **IMMEDIATE**: First floor heating disabled, ground floor continues
2. Check pump relay device status (LED indicators)
3. Ping relay IP address
4. Access relay web UI directly
5. Power cycle relay device
6. Check 24V power supply to relay
7. Verify relay MQTT configuration
8. **Resolution**: First floor heating resumes when relay returns online

**Impact if Ignored**:
First floor heating disabled. Ground floor heating unaffected per SR-RL-003 zone independence.

**Logged As**:
Home Assistant automation logs. Python service logs will show pump command failures for first floor.

---

### HEAT-PR-001: Ground Floor Undertemperature (Medium)

**Severity**: MEDIUM
**Category**: Performance
**Related Requirement**: UR-SM-003
**Home Assistant**: automation `heating_alert_ground_floor_undertemp`

**Description**:
Ground floor temperature has remained 2°C or more below setpoint for over 1 hour despite heating being enabled.

**Trigger Conditions**:
- `sensor.living_room_sensor_temperature` < (setpoint - 2°C)
- Sustained for >1 hour
- `input_boolean.heating_ground_floor_enabled` = ON

**Possible Causes**:
1. **Python service crashed**: heating_control.py not running
2. **Boiler failure**: Boiler not responding to heat requests
3. **Pump failure**: Pump not circulating water despite relay ON
4. **Extreme cold**: Outdoor temperature extremely low (< -10°C)
5. **Insulation failure**: Significant heat loss from windows/doors
6. **Controller tuning conservative**: Gains too low, slow response
7. **Air in system**: Hydronic system needs bleeding

**Recommended Actions**:
1. Check Python service status: `journalctl -u automation-heating.service -n 50`
2. Verify boiler flame is active and steady
3. Listen to pump - should hear water flow
4. Check outdoor temperature - if <-5°C, may need 2+ hours to reach setpoint
5. Inspect windows/doors for drafts
6. Check radiator/underfloor manifold valves are open
7. Bleed air from hydronic system if recently serviced
8. If using PID, increase Kp gain by 20%
9. Consider increasing setpoint temporarily

**Impact if Ignored**:
Reduced comfort. Not a safety issue - just indicates system struggling to maintain temperature.

**Logged As**:
Home Assistant automation logs only.

---

### HEAT-PR-002: First Floor Undertemperature (Medium)

**Severity**: MEDIUM
**Category**: Performance
**Related Requirement**: UR-SM-003
**Home Assistant**: automation `heating_alert_first_floor_undertemp`

**Description**:
First floor temperature has remained 2°C or more below setpoint for over 1 hour despite heating being enabled.

**Trigger Conditions**:
- `sensor.first_floor_sensor_temperature` < (setpoint - 2°C)
- Sustained for >1 hour
- `input_boolean.heating_first_floor_enabled` = ON

**Possible Causes**:
1. **Python service crashed**: heating_control.py not running
2. **Boiler failure**: Boiler not responding
3. **Pump failure**: First floor pump not circulating
4. **Extreme cold**: Outdoor temperature very low
5. **Insulation failure**: Heat loss through roof/walls
6. **Flow rate insufficient**: First floor manifold valve partially closed
7. **Ground floor priority**: If ground floor demanding heat, first floor may wait

**Recommended Actions**:
1. Check Python service status: `journalctl -u automation-heating.service -n 50`
2. Verify boiler flame active
3. Listen to first floor pump - should hear flow
4. Check first floor manifold valves are fully open
5. Verify both zones can run simultaneously (SR-SF-001 allows multi-zone)
6. Check outdoor temperature
7. Inspect attic/roof insulation
8. Bleed air from first floor radiators/manifold
9. If using PID, increase Kp gain by 20%

**Impact if Ignored**:
Reduced comfort. Not a safety issue.

**Logged As**:
Home Assistant automation logs only.

---

### HEAT-PR-003: Ground Floor Excessive Pump Cycling (Medium)

**Severity**: MEDIUM
**Category**: Performance
**Related Requirement**: SR-SF-004, SR-SF-005, UR-SM-006, RISK-002
**Home Assistant**: automation `heating_alert_ground_floor_excessive_cycling`

**Description**:
Ground floor pump is cycling ON/OFF more than 10 times per hour, indicating pump protection mechanisms may be failing.

**Trigger Conditions**:
- `sensor.heating_ground_floor_pump_cycles` > 10
- Sustained for >10 minutes

**Possible Causes**:
1. **Min ON/OFF times not enforced**: SR-SF-004/005 protection bypassed
2. **Controller oscillation**: PID tuning unstable, or ON/OFF hysteresis too narrow
3. **Temperature sensor noise**: Sensor fluctuating rapidly
4. **Setpoint hunting**: User changing setpoint frequently
5. **Window open/close cycles**: Rapid temperature changes
6. **Manual override abuse**: User toggling pump manually

**Recommended Actions**:
1. **IMMEDIATE**: Review Python service logs for pump protection bypasses
2. Check pump cycle count sensor: verify it's accurately counting
3. If using PID controller:
   - Increase Kd (derivative) gain by 50% to dampen oscillations
   - Reduce Ki (integral) gain by 30%
4. If using ON/OFF controller:
   - Increase hysteresis from 0.2°C to 0.3°C or 0.5°C
5. Verify SR-SF-004 (min ON time 10 min) is active in code
6. Verify SR-SF-006 (manual override limits) is active
7. Check sensor for rapid fluctuations (>0.2°C/min)
8. Stop manual overrides - let controller stabilize

**Impact if Ignored**:
Premature pump failure (RISK-002). Pumps designed for <6 cycles/hour. Excessive cycling causes bearing wear and reduces lifespan from 10 years to 2-3 years.

**Logged As**:
Home Assistant automation logs. Python service should log pump state changes.

---

### HEAT-PR-004: First Floor Excessive Pump Cycling (Medium)

**Severity**: MEDIUM
**Category**: Performance
**Related Requirement**: SR-SF-004, SR-SF-005, UR-SM-006, RISK-002
**Home Assistant**: automation `heating_alert_first_floor_excessive_cycling`

**Description**:
First floor pump is cycling ON/OFF more than 10 times per hour, indicating pump protection mechanisms may be failing.

**Trigger Conditions**:
- `sensor.heating_first_floor_pump_cycles` > 10
- Sustained for >10 minutes

**Possible Causes**:
1. **Min ON/OFF times not enforced**: SR-SF-004/005 protection bypassed
2. **Controller oscillation**: PID tuning unstable, or ON/OFF hysteresis too narrow
3. **Temperature sensor noise**: Sensor fluctuating rapidly
4. **Heat rise from ground floor**: Ground floor heating causing first floor overshoot
5. **Setpoint too close to ambient**: Only 0.5°C difference, small changes cause cycling
6. **Manual override abuse**: User toggling pump manually

**Recommended Actions**:
1. **IMMEDIATE**: Review Python service logs for pump protection bypasses
2. Check pump cycle count sensor accuracy
3. If using PID controller:
   - Increase Kd (derivative) gain by 50%
   - Reduce Ki (integral) gain by 30%
4. If using ON/OFF controller:
   - Increase hysteresis to 0.3°C or higher
5. Reduce ground floor setpoint if it's >22°C (heat rises)
6. Verify min ON/OFF times are enforced in code
7. Check sensor stability
8. Stop manual overrides

**Impact if Ignored**:
Premature pump failure (RISK-002). Pump lifespan reduced significantly.

**Logged As**:
Home Assistant automation logs. Python service should log pump state changes.

---

### HEAT-PR-005: Window Left Open (Low)

**Severity**: LOW
**Category**: Performance
**Related Requirement**: UR-SM-005, RISK-004
**Home Assistant**: automation `heating_alert_window_left_open`

**Description**:
Window has been detected open for more than 30 minutes, wasting energy heating outside air.

**Trigger Conditions**:
- `binary_sensor.heating_ground_floor_window_open` = true for >30 min, OR
- `binary_sensor.heating_first_floor_window_open` = true for >30 min

**Possible Causes**:
1. **User forgot window open**: Intentional ventilation, forgot to close
2. **False detection**: Temperature drop detection algorithm triggered incorrectly
3. **Door left open**: Heat loss similar to window open
4. **External temperature drop**: Sudden outdoor cold front
5. **Sensor malfunction**: Temperature sensor reporting inaccurate rapid drop

**Recommended Actions**:
1. Check if window actually open (visual inspection)
2. Close window if open
3. If window closed, check temperature sensor for accuracy
4. Review window detection algorithm thresholds (typically >1.5°C drop in 5 minutes)
5. If false positives frequent, increase detection threshold to 2°C
6. Note: Heating remains active but efficiency reduced

**Impact if Ignored**:
Increased energy consumption (10-30% depending on window size and outdoor temp). Not a safety issue. Heating continues operating.

**Logged As**:
Home Assistant automation logs only.

---

### HEAT-SY-001: Python Service Offline (Critical)

**Severity**: CRITICAL
**Category**: System
**Related Requirement**: SR-RL-005, SR-RL-006, UR-SM-007, RISK-007
**Home Assistant**: automation `heating_alert_python_service_offline`

**Description**:
The heating_control.py Python service has not published updates to MQTT for over 5 minutes. All heating control is offline.

**Trigger Conditions**:
- `binary_sensor.heating_boiler_active` not updated for >5 minutes
- Additional 5 minute delay for confirmation

**Possible Causes**:
1. **Service crashed**: Python exception, segfault, OOM killer
2. **MQTT connection lost**: Broker offline or network issue
3. **Host system issue**: Raspberry Pi frozen, out of memory, SD card failure
4. **Infinite loop**: Code hung in blocking operation
5. **Configuration error**: Recent config change caused startup failure

**Recommended Actions**:
1. **IMMEDIATE**: Check service status: `systemctl status automation-heating.service`
2. View recent logs: `journalctl -u automation-heating.service -n 100`
3. Check for Python exceptions in logs
4. Verify MQTT broker running: `docker ps | grep mosquitto`
5. Test MQTT connection: `mosquitto_sub -h 192.168.1.60 -t '#' -v`
6. Check system resources: `free -h`, `df -h`
7. Restart service: `sudo systemctl restart automation-heating.service`
8. If restart fails, check config: `cd /path/to/automation && python3 heating_control.py` (test mode)
9. Review recent config changes in `heating_config.yaml`

**Impact if Ignored**:
COMPLETE HEATING SYSTEM FAILURE. No automatic temperature control. Boiler will not activate. Property at risk of freezing in winter. Immediate action required.

**Logged As**:
Home Assistant automation logs. Systemd logs via journalctl.

---

## Alert Severity Levels

| Level | Description | Response Time | Examples |
|-------|-------------|---------------|----------|
| **CRITICAL** | Safety risk or complete system failure | Immediate (within 1 hour) | HEAT-SF-001, HEAT-SF-002, HEAT-HW-001, HEAT-SY-001 |
| **HIGH** | Significant functionality loss | Within 24 hours | HEAT-SF-003, HEAT-SF-004, HEAT-SN-001, HEAT-SN-002, HEAT-HW-002, HEAT-HW-003 |
| **MEDIUM** | Performance degradation | Within 1 week | HEAT-PR-001, HEAT-PR-002, HEAT-PR-003, HEAT-PR-004 |
| **LOW** | Informational, efficiency impact | When convenient | HEAT-PR-005 |

---

## Troubleshooting Quick Reference

### Python Service Issues
```bash
# Check service status
systemctl status automation-heating.service

# View live logs
journalctl -u automation-heating.service -f

# View last 50 lines
journalctl -u automation-heating.service -n 50

# Restart service
sudo systemctl restart automation-heating.service

# View errors only
journalctl -u automation-heating.service -p err
```

### MQTT Debugging
```bash
# Subscribe to all heating topics
mosquitto_sub -h 192.168.1.60 -t 'heating/#' -v

# Subscribe to critical alerts
mosquitto_sub -h 192.168.1.60 -t 'heating/+/alert/critical' -v

# Check broker status
docker logs mosquitto --tail 50
```

### Zigbee Sensor Debugging
```bash
# View Zigbee2MQTT logs
docker logs zigbee2mqtt --tail 100 -f

# Check specific device
# Navigate to: Home Assistant → Zigbee2MQTT → Devices → {sensor_name}
# Look for: Last Seen, Battery %, Link Quality (LQI)
```

### Hardware Relay Debugging
```bash
# Ping Shelly device
ping <shelly_ip>

# Check Shelly web UI
# Navigate to: http://<shelly_ip>

# Check Shelly MQTT messages
mosquitto_sub -h 192.168.1.60 -t 'shellies/#' -v
```

---

## Related Documentation

- **System Specification**: `/homehub/automation/HEATING_SYSTEM_SPECIFICATION.md`
- **Project Plan**: `/homehub/automation/HEATING_PROJECT_PLAN.md`
- **Configuration**: `/homehub/automation/src/heating_config.yaml`
- **Alert Automations**: `/my-ha/packages/heating/alerts.yaml`
- **Dashboard**: `/my-ha/dashboards/heating.yaml`

---

**End of Alert Reference**
