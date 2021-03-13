docker pull portainer/portainer:linux-arm
sudo docker run --restart always -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer:linux-arm

# docker-compose -f ~/homehub/docker/zigbee2mqtt/docker-compose.yml pull
# docker-compose -f ~/homehub/docker/zigbee2mqtt/docker-compose.yml up -d