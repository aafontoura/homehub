#!/bin/bash
serverServices=( "mosquitto" "unifi" "zigbee2mqtt" "ghostfolio" )

./update_portainer.sh x64

# Iterate over the services to pull the updated image and start it over
for str in ${serverServices[@]}; do
    echo "Updating $str ..."
    docker-compose -f ~/homehub/docker/$str/docker-compose.yml pull
    docker-compose -f ~/homehub/docker/$str/docker-compose.yml up -d
done



