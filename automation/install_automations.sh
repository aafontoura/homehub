cp *.service /etc/systemd/system

systemctl enable automation-ventilation.service
systemctl restart automation-ventilation.service
systemctl enable logger-ventilation.service
systemctl restart logger-ventilation.service
systemctl enable storage-light.service
systemctl restart storage-light.service
systemctl enable automation-bed-ledstrip.service
systemctl restart automation-bed-ledstrip.service