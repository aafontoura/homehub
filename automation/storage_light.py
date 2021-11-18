import time,json, logging, threading
import paho.mqtt.client as paho

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)

TIMEOUT = 180

broker="192.168.1.10"
#define callback
def on_message(client, userdata, message):
    global timer
    received = str(message.payload.decode("utf-8"))
    
    try:
        storage_sensor = json.loads(message.payload.decode("utf-8"))
        logging.debug("New Message")
        logging.debug(received)
        logging.debug(message.topic)

        if storage_sensor["contact"]:
            command = '{"state_right":"OFF"}'
            logging.debug(f'sending: {command}')
            client.publish("zigbee2mqtt/storage_switch/set",command)
        else: 
            command = '{"state_right":"ON"}'
            logging.debug(f'sending: {command}')
            client.publish("zigbee2mqtt/storage_switch/set",command)
            timer = threading.Timer(TIMEOUT, turn_off_light)
            timer.start()
            
        
        
    except Exception as e:
        return

def turn_off_light():
    global client
    command = '{"state_right":"OFF"}'
    client.publish("zigbee2mqtt/storage_switch/set",command)



timer = threading.Timer(TIMEOUT, turn_off_light)


client= paho.Client("client-storage") #create client object client1.on_publish = on_publish #assign function to callback client1.connect(broker,port) #establish connection client1.publish("house/bulb1","on")
######Bind function to callback
client.on_message=on_message
#####
logging.info(f"connecting to broker {broker}")
client.connect(broker)#connect
client.loop_start() #start loop to process received messages

# client.publish("itho/cmd",'20')
# time.sleep(4)
# exit()
logging.info("subscribing ")
client.subscribe("zigbee2mqtt/0x00158d00054d63cc")#subscribe
# client.subscribe("zigbee2mqtt/#")#subscribe
while True:
    time.sleep(2)

print("publishing ")
client.publish("house/bulb1","on")#publish
time.sleep(4)
client.disconnect() #disconnect
client.loop_stop() #stop loop