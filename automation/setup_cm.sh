#!/bin/bash
cd /home/antau/homehub/automation/src/instagram
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


cd /home/antau/homehub/automation

# Define an array of folders
services=("cm-followers-fetch")

# Loop through the folders and call docker-compose for each one
for service in "${services[@]}"
do
    echo "Installing $service"
    cp services/"$service".service /etc/systemd/system
    systemctl enable "$service".service
    systemctl restart "$service".service
done

cd -