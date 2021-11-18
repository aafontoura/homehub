docker pull portainer/portainer-ce:linux-amd64
sudo docker run --restart always -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:linux-amd64

# docker-compose -f ~/homehub/docker/zigbee2mqtt/docker-compose.yml pull
# docker-compose -f ~/homehub/docker/zigbee2mqtt/docker-compose.yml up -d