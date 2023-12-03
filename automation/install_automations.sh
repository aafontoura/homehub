#!/bin/bash


# Define an array of folders
services=("automation-ventilation" "logger-ventilation" "storage-light" "automation-bed-ledstrip" "automation-kitchen-lights" "automation-bathroom-light" "automation-towel-heater")

# Loop through the folders and call docker-compose for each one
for service in "${services[@]}"
do
    echo "Installing $service"
    cp services/"$service".service /etc/systemd/system
    systemctl enable "$service".service
    systemctl restart "$service".service
done

