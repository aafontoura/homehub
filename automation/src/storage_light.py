import time,json, logging, threading
import paho.mqtt.client as paho

from homehub_mqtt import AutomationPubSub

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)




class StorageLightAutomation(AutomationPubSub):
    TIMEOUT = 180
    ROOT_TOPIC = "zigbee2mqtt"
    STORAGE_WINDOW_SENSOR = "0x00158d00054d63cc"
    TOPICS = [f'{ROOT_TOPIC}/{STORAGE_WINDOW_SENSOR}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)
        self.new_topics(self.TOPICS)

        

    def on_message(self,client, userdata, message):
        """ Change the switch according to the door sensor
        Expects the following message format:
        {
            "battery":97,
            "contact":bool,
            "linkquality":255,
            "temperature":25,
            "voltage":2995
        }

        
        """
        received = str(message.payload.decode("utf-8"))
    
        try:
            storage_sensor = json.loads(message.payload.decode("utf-8"))
            logging.debug("New Message")
            logging.debug(received)
            logging.debug(message.topic)

            if storage_sensor["contact"]:
                self.set_light(status = False)
            else: 
                self.set_light(status = True)
                self.timer = threading.Timer(self.TIMEOUT, self.set_light)
                self.timer.start()
        except Exception as e:
            return

    def set_light(self,status = False):
        if status:
            command = '{"state_right":"ON"}'
        else:
            command = '{"state_right":"OFF"}'
        logging.debug(f'sending: {command}')
        self.client.publish("zigbee2mqtt/storage_switch/set",command)



broker = "192.168.1.10"
name = "automation.storage_switch"

storage_automation = StorageLightAutomation(broker_ip = broker, name = name)
storage_automation.connect()


while True:
    time.sleep(2)

