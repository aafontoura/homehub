docker-compose -f ~/homehub/docker/media_server/docker-compose.yml pull
# docker-compose -f ~/homehub/docker/mosquitto/docker-compose.yml pull
docker-compose -f ~/homehub/docker/nextcloud/docker-compose.yml pull
docker-compose -f ~/homehub/docker/nginx/docker-compose.yml pull
# docker-compose -f ~/homehub/docker/organizr/docker-compose.yml pull
# docker-compose -f ~/homehub/docker/unifi/docker-compose.yml pull
# docker-compose -f ~/homehub/docker/zigbee2mqtt/docker-compose.yml pull
docker-compose -f ~/homehub/docker/influx_grafana/docker-compose.yml pull
docker-compose -f ~/homehub/docker/hassio/docker-compose.yml pull
docker-compose -f ~/homehub/docker/duplicati/docker-compose.yml pull

docker-compose -f ~/homehub/docker/hassio/docker-compose.yml up -d
docker-compose -f ~/homehub/docker/duplicati/docker-compose.yml up -d
docker-compose -f ~/homehub/docker/influx_grafana/docker-compose.yml up -d
docker-compose -f ~/homehub/docker/media_server/docker-compose.yml up -d
# docker-compose -f ~/homehub/docker/mosquitto/docker-compose.yml up -d
docker-compose -f ~/homehub/docker/nextcloud/docker-compose.yml up -d
docker-compose -f ~/homehub/docker/nginx/docker-compose.yml up -d
# docker-compose -f ~/homehub/docker/organizr/docker-compose.yml up -d
# docker-compose -f ~/homehub/docker/unifi/docker-compose.yml up -d
# docker-compose -f ~/homehub/docker/zigbee2mqtt/docker-compose.yml up -d