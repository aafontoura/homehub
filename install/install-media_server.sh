if [ ! -z $1 ]
then
    MEDIA_FOLDER=$1
    mkdir ${MEDIA_FOLDER}/series
    mkdir ${MEDIA_FOLDER}/movies

    # install dependencies for plex
    sudo apt install ocl-icd-libopencl1 beignet-opencl-icd -y

    docker-compose -f ~/homehub/docker/media_server/docker-compose.yml up -d
else
    echo "inform media folder"
fi