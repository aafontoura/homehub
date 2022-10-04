docker-compose -f ~/homehub/docker/hassio/docker-compose.yml up -d

mkdir ../config/unifi && cd ../config/unifi
curl -O https://raw.githubusercontent.com/ryansch/docker-unifi-rpi/master/docker-compose.yml
docker-compose up -d

# deConz

# Set user USB access rights
sudo gpasswd -a pi dialout

# mkdir -p ~/config/deCONZ
# docker-compose -f ~/homehub/docker/deConz/docker-compose.yml up -d

mkdir -p ~/config/mosquitto
mkdir -p ~/config/mosquitto/data
mkdir -p ~/config/mosquitto/log
echo "persistence true" > ~/config/mosquitto/mosquitto.conf
echo "persistence_location /mosquitto/data/" >> ~/config/mosquitto/mosquitto.conf
echo "log_dest file /mosquitto/log/mosquitto.log" >> ~/config/mosquitto/mosquitto.conf
docker-compose -f ~/homehub/docker/mosquitto/docker-compose.yml up -d
