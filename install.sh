docker-compose -f ~/homehub/docker/hassio/docker-compose.yml up -d

mkdir ../config/unifi && cd ../config/unifi
curl -O https://raw.githubusercontent.com/ryansch/docker-unifi-rpi/master/docker-compose.yml
docker-compose up -d
