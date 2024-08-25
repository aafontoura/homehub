if [ -z $1 ]
then
    echo "Provide architecture (arm,x64)"
elif [ $1 == "arm" ]
    then
        docker pull portainer/portainer-ce:linux-arm-2.0.0-alpine
        sudo docker run --restart always -d -p 9000:9000 portainer  -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:linux-arm-2.0.0-alpine
        
    elif [ $1 == "x64" ]
    then
        docker pull portainer/portainer-ce:linux-amd64
        sudo docker run --restart always -d -p 9000:9000 portainer -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:linux-amd64
    else
        echo "Architecture not recognized: $1"
    fi
