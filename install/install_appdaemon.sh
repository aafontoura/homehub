
docker exec -it appdaemon-appdaemon-1 kill 1
docker stop appdaemon-appdaemon-1

rm -r ~/homehub/automation/src/appdaemon/__pycache__
cp -r ~/homehub/automation/src/appdaemon/* ~/appdata/appdaemon/apps
cp -r ~/homehub/automation/src/energycalculation.py ~/appdata/appdaemon/apps/src

./start_image.sh appdaemon


