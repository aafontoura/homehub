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




class BedLEDStripAutomation(AutomationPubSub):
    TIMEOUT = 180
    ROOT_TOPIC = "zigbee2mqtt"
    STORAGE_WINDOW_SENSOR = "Double Switch Bed"
    TOPICS = [f'{ROOT_TOPIC}/{STORAGE_WINDOW_SENSOR}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)
        self._subscribe_to_topics(self.TOPICS)

        

    def handle_message(self, topic, payload):
        """ Change the switch according to the door sensor
        Expects the following message format:
        {
            "battery":97,
            
        }

        
        """
        if topic == f'{self.ROOT_TOPIC}/{self.STORAGE_WINDOW_SENSOR}':
            try:            
                if "single_right" == payload['action']:
                    self.toggle_bed_LED()
                
            except KeyError as e:
                logging.error(f'Error:{e}')
        else:
            logging.debug(f'Skipping topic: {topic}')

    def toggle_bed_LED(self):
        
        command = 'TOGGLE'
        logging.debug(f'sending: {command}')
        self.client.publish("homehub/cmnd/sonoff-bedroom/POWER",command)



broker = "192.168.1.60"
name = "automation.bed_ledstrip"

bed_ledstrip = BedLEDStripAutomation(broker_ip = broker, name = name)
bed_ledstrip.connect()


while True:
    time.sleep(2)

