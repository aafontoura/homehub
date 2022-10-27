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




class KitchenLightAutomation(AutomationPubSub):
    TIMEOUT = 180
    ROOT_TOPIC = "zigbee2mqtt"
    LIVING_ROOM_LIGHT_SWITCH = "Living Room Wall Switch"
    STORAGE_SWITCH = "storage_switch"
    KITCHEN_ISLAND_LIGHTS = "Kitchen Island Lights"

    
    TOPICS = [f'{ROOT_TOPIC}/{LIVING_ROOM_LIGHT_SWITCH}',
              f'{ROOT_TOPIC}/{STORAGE_SWITCH}',
              f'{ROOT_TOPIC}/{KITCHEN_ISLAND_LIGHTS}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)
        self._spotlight_status = False
        self._islandlight_status = False
        
        self.new_topics(self.TOPICS)
        
        
        

    def get_lights_status(self):
        command = '{"state": ""}'
        logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}/get')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}/get',command)

        command = '{"state_left": ""}'
        logging.debug(f'sending: {command}')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.STORAGE_SWITCH}/get',command)
        
    @property
    def spotlight_status(self):
        return self._spotlight_status

    @spotlight_status.setter
    def spotlight_status(self,status):
        logging.debug(f'Setter spot light:{status}')
        if status.lower() == "on":
            self._spotlight_status = True
        elif status.lower() == "off":
            self._spotlight_status = False

    @property
    def islandlight_status(self):
        return self._islandlight_status

    @islandlight_status.setter
    def islandlight_status(self,status):
        logging.debug(f'Setter insland light:{status}')
        if status.lower() == "on":
            self._islandlight_status = True
        elif status.lower() == "off":
            self._islandlight_status = False

    def on_message(self, client, userdata, message):
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
        payload = json.loads(str(message.payload.decode("utf-8")))
    
        # try:
            
        logging.debug("New Message")
        logging.debug(f'spot:{self.spotlight_status} island:{self.islandlight_status}')
        logging.debug(payload)
        logging.debug(message.topic)
        logging.debug(self.LIVING_ROOM_LIGHT_SWITCH)

       
        
        if message.topic == f'{self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}':
            
            self.islandlight_status = payload["state"]

        if message.topic == f'{self.ROOT_TOPIC}/{self.STORAGE_SWITCH}':
            
            self.spotlight_status = payload["state_left"]

        if message.topic == f'{self.ROOT_TOPIC}/{self.LIVING_ROOM_LIGHT_SWITCH}' and \
            payload["action"] == "single_right":
            
            if self.spotlight_status:
                if self.islandlight_status:
                    self.set_kitchen_lights("off")
                else:
                    self.set_island_light("on")
            else:
                self.set_kitchen_lights("on")




    def set_kitchen_lights(self, status):
        if status.lower() == "on":
            command = '{"state_left":"ON"}'
            logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.STORAGE_SWITCH}/set')
            self.client.publish(f'{self.ROOT_TOPIC}/{self.STORAGE_SWITCH}/set',command)


        else:
            command = '{"state_left":"OFF"}'
            logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.STORAGE_SWITCH}/set')
            self.client.publish(f'{self.ROOT_TOPIC}/{self.STORAGE_SWITCH}/set',command)
            self.islandlight_status = "off"

    def set_island_light(self, status="ON"):
        print("Setting Kitchen Island")
        command = '{"state":"ON"}'
        logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}/set')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}/set',command)
 


        

    def toggle_bed_LED(self):
        
        command = 'TOGGLE'
        logging.debug(f'sending: {command}')
        self.client.publish("homehub/cmnd/sonoff-bedroom/POWER",command)



broker = "192.168.1.10"
name = "automation.kitchen_lights"

kitchen_lights = KitchenLightAutomation(broker_ip = broker, name = name)
kitchen_lights.connect()
kitchen_lights.get_lights_status()


while True:
    time.sleep(2)

