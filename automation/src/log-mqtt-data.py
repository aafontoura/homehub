import time,json, logging
import paho.mqtt.client as paho
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)

broker = "192.168.1.60"




client = InfluxDBClient(url="http://192.168.1.150:8086", token="pN-D6xk4CYOROjBBRvSCmQEPq_9w3_u1EkrUHQSlmyYGQHx-TLJRhmzzDOTGlSueEtP012AxPgJNijtlCa2eYQ==", org="homehub")

write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()


#define callback
def on_message(client, userdata, message):
    global write_api
    received = str(message.payload.decode("utf-8"))
    
    try:
        itho_info = json.loads(message.payload.decode("utf-8"))
        p = Point("ventilation").field(message.topic, itho_info)
        write_api.write(bucket=bucket, record=p)
        
        logging.debug(message.topic)
        logging.debug(itho_info)        

        
    except Exception as e:
        return 

bucket = "homehub-bucket"




client= paho.Client("client-itho") #create client object client1.on_publish = on_publish #assign function to callback client1.connect(broker,port) #establish connection client1.publish("house/bulb1","on")
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
client.subscribe("itho/#")#subscribe
# client.subscribe("zigbee2mqtt/#")#subscribe
while True:
    time.sleep(2)
    
    
