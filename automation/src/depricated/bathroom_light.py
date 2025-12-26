import time,json, logging, threading, traceback
import paho.mqtt.client as paho

from homehub_mqtt import AutomationPubSub

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)




class BathroomAutomation(AutomationPubSub):
    ROOT_TOPIC = "zigbee2mqtt"
    BATHROOM_MOTION_SENSOR = "Bathroom Motion Sensor"
    BATHROOM_DIMMER = "Bathroom Dimmer"
    COMMAND_TIMEOUT = 30
    TOPICS = [f'{ROOT_TOPIC}/{BATHROOM_MOTION_SENSOR}',
            f'{ROOT_TOPIC}/{BATHROOM_DIMMER}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)
        self._subscribe_to_topics(self.TOPICS)

        self.command_status = False
        self.light_status = False
        # TODO: initialize Timer.

        

    def handle_message(self, topic, payload):
        """ Change the dimmer control according to the bathroom motion sensor
        Expects the following message format:
        {
            "battery":97,
            "contact":bool,
            "linkquality":255,
            "temperature":25,
            "voltage":2995
        }

        
        """
        
    
        try:            

            if topic == f'{self.ROOT_TOPIC}/{self.BATHROOM_MOTION_SENSOR}':
                if payload["occupancy"]:
                    self.set_light(status = True)
                else: 
                    self.set_light(status = False)

            if topic == f'{self.ROOT_TOPIC}/{self.BATHROOM_DIMMER}':
                if payload["state"].lower() == "on":
                    self.light_status = True
                if payload["state"].lower() == "off":
                    self.light_status = False

                if self.light_status == self.command_status:
                    # TODO: check if timer is not None or if it was initialized
                    self.timer.stop()
                
        except AttributeError as e:
        # except Exception as e:
            # logging.error(e)
            # logging.error(repr(traceback.format_stack()))
            return

    def set_light(self,status = False):
        if status:
            command = '{"state":"ON"}'
            self.command_status = True
        else:
            command = '{"state":"OFF"}'
            self.command_status = False
        logging.debug(f'sending: {command}')
        self.client.publish("zigbee2mqtt/Bathroom Dimmer/set",command)
        self.timer = threading.Timer(self.COMMAND_TIMEOUT,self.timeout)
        self.timer.start()

    def timeout(self):
        logging.info(f'Retry command: {self.command_status}' )
        if self.command_status != self.light_status:
            self.set_light(self.command_status)



broker = "192.168.1.60"
name = "automation.bathroom_switch"

bathroom_automation = BathroomAutomation(broker_ip = broker, name = name)
bathroom_automation.connect()


while True:
    time.sleep(2)

