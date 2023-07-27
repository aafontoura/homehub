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
    STORAGE_WALL_SWITCH = "Storage Wall Switch"
    STORAGE_WINDOW_SENSOR = "Storage Door Switch"    
    TOPICS = [f'{ROOT_TOPIC}/{STORAGE_WINDOW_SENSOR}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)        
        self._subscribe_to_topics(self.TOPICS)        
    

    def handle_message(self, topic, payload):
        """ 
        Expects the following message format:
        {
            "battery":97,
            "contact":bool,
            "linkquality":255,
            "temperature":25,
            "voltage":2995
        }

        
        """
        if topic == f'{self.ROOT_TOPIC}/{self.STORAGE_WINDOW_SENSOR}':
            storage_sensor = payload
            try:
                if storage_sensor["contact"]:
                    self.set_light(status = False)
                else: 
                    self.set_light(status = True)
                    self.timer = threading.Timer(self.TIMEOUT, self.set_light)
                    self.timer.start()
            except KeyError as e:
                logging.error(f'Error:{e}')
        else:
            logging.debug(f'Skipping: {topic}')

    def set_light(self,status = False):
        if status:
            command = '{"state_right":"ON"}'
        else:
            command = '{"state_right":"OFF"}'
        logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.STORAGE_WALL_SWITCH}/set')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.STORAGE_WALL_SWITCH}/set',command)
        


    

        

broker = "192.168.1.10"
name = "automation.strorage_light"

storage_automation = StorageLightAutomation(broker_ip = broker, name = name)
storage_automation.connect()


while True:
    time.sleep(2)

