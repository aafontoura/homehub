docker-compose -f ~/homehub/docker/hassio/docker-compose.yml up -d

mkdir ../config/unifi && cd ../config/unifi
curl -O https://raw.githubusercontent.com/ryansch/docker-unifi-rpi/master/docker-compose.yml
docker-compose up -d

# deConz

# Set user USB access rights
sudo gpasswd -a pi dialout

mkdir -p ~/config/deCONZ
docker-compose -f ~/homehub/docker/deConz/docker-compose.yml up -d