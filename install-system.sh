# install docker
curl -sSL https://get.docker.com | sh
sudo usermod -aG docker pi

# wget http://ftp.us.debian.org/debian/pool/main/libs/libseccomp/libseccomp2_2.4.4-1~bpo10+1_armhf.deb
# sudo dpkg -i libseccomp2_2.4.4-1~bpo10+1_armhf.deb

# install portainer image
docker pull portainer/portainer:linux-arm
sudo docker run --restart always -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer:linux-arm