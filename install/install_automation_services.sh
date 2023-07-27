cp /srv/dev-disk-by-label-media/home/antonio/homehub/automation/*.service /etc/systemd/system

systemctl enable automation-ventilation.service
systemctl start automation-ventilation.service
systemctl enable logger-ventilation.service
systemctl start logger-ventilation.service
systemctl enable storage-light.service
systemctl start storage-light.service