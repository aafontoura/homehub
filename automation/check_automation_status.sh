
#!/bin/bash


# Define an array of folders
services=("storage-light" "automation-ventilation" "logger-ventilation" "storage-light" "automation-bed-ledstrip" "automation-kitchen-lights" "automation-bathroom-light" "automation-towel-heater")

# Loop through the folders and call docker-compose for each one
for service in "${services[@]}"
do
    echo "$service".service:
    systemctl status "$service".service | grep Active
done


