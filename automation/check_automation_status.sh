echo automation-ventilation.service:
systemctl status automation-ventilation.service | grep Active
echo logger-ventilation.service:
systemctl status logger-ventilation.service | grep Active
echo status storage-light.service:
systemctl status storage-light.service | grep Active
echo automation-bed-ledstrip.service:
systemctl status automation-bed-ledstrip.service | grep Active
