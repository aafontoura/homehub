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
    STORAGE_WINDOW_SENSOR = "Double Switch Bed/action"
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
        action = str(message.payload.decode("utf-8"))
    
        try:
            
            logging.debug("New Message")
            logging.debug(action)
            logging.debug(message.topic)

            if "single_right" == action:
                self.toggle_bed_LED()
            else: 
                self.toggle_bed_LED()
            
        except Exception as e:
            return

    def toggle_bed_LED(self):
        
        command = 'TOGGLE'
        logging.debug(f'sending: {command}')
        self.client.publish("homehub/cmnd/sonoff-bedroom/POWER",command)



broker = "192.168.1.10"
name = "automation.bed_ledstrip"

bed_ledstrip = BedLEDStripAutomation(broker_ip = broker, name = name)
bed_ledstrip.connect()


while True:
    time.sleep(2)

