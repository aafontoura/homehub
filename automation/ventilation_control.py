import time,json, logging
import paho.mqtt.client as paho

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)

broker="192.168.1.10"
#define callback
def on_message(client, userdata, message):
    received = str(message.payload.decode("utf-8"))
    
    try:
        bathroom_sensor = json.loads(message.payload.decode("utf-8"))
        logging.debug("New Message")
        logging.debug(received)
        logging.debug(message.topic)

        if bathroom_sensor['humidity'] > 85:
            client.publish("itho/cmd",'220')
        elif bathroom_sensor['humidity'] > 80:
            client.publish("itho/cmd",'180')
        elif bathroom_sensor['humidity'] > 75:
            client.publish("itho/cmd",'127')
        else:
            client.publish("itho/cmd",'20')
        
        
        
    except Exception as e:
        return


client= paho.Client("client-001") #create client object client1.on_publish = on_publish #assign function to callback client1.connect(broker,port) #establish connection client1.publish("house/bulb1","on")
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
client.subscribe("zigbee2mqtt/Bathroom Temperature Sensor")#subscribe
# client.subscribe("zigbee2mqtt/#")#subscribe
while True:
    time.sleep(2)

print("publishing ")
client.publish("house/bulb1","on")#publish
time.sleep(4)
client.disconnect() #disconnect
client.loop_stop() #stop loop