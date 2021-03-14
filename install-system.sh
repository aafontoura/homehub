#!/bin/sh

echo "Installing homehub system"
echo

case $(arch) in
    "armv7l")   RELEASE=":linux-arm";;
    "x86_64")   RELEASE="";;
esac

apt-get install curl
apt-get install docker-compose

echo "Installing docker..."
if ! command -v docker
then
    # install docker
    curl -sSL https://get.docker.com | sh
    usermod -aG docker pi
else
    echo "Docker already installed..."
fi

# fix for rpi installation
if [ $(arch) = "armv7l"]
then
    echo "Applying raspberry pi fix"
    wget http://ftp.us.debian.org/debian/pool/main/libs/libseccomp/libseccomp2_2.4.4-1~bpo10+1_armhf.deb
    dpkg -i libseccomp2_2.4.4-1~bpo10+1_armhf.deb

fi

echo "Installing protainer..."
# install portainer image
docker pull portainer/portainer$RELEASE
docker run --restart always -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer$RELEASE

