cp /srv/dev-disk-by-label-media/home/antonio/homehub/automation/*.service /etc/systemd/system


systemctl enable automation-heating.service
systemctl start automation-heating.service