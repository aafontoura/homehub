import time,json, logging, threading
import paho.mqtt.client as paho
from enum import Enum

from homehub_mqtt import AutomationPubSub

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)

class State(Enum):
    ON = 1
    OFF = 2
    UNKNOWN = 3


class KitchenLightAutomation(AutomationPubSub):
    TIMEOUT = 180
    ROOT_TOPIC = "zigbee2mqtt"
    LIVING_ROOM_LIGHT_SWITCH = "Living Room Wall Switch"
    STORAGE_SWITCH = "Storage Wall Switch"
    KITCHEN_ISLAND_LIGHTS = "Kitchen Island Lights"

    
    TOPICS = [f'{ROOT_TOPIC}/{LIVING_ROOM_LIGHT_SWITCH}',
              f'{ROOT_TOPIC}/{STORAGE_SWITCH}',
              f'{ROOT_TOPIC}/{KITCHEN_ISLAND_LIGHTS}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)
        self.__spotlight_status = State.UNKNOWN
        self.__islandlight_status = State.UNKNOWN
        
        self._subscribe_to_topics(self.TOPICS)        
    

    def handle_message(self, topic, payload):
        """ 
        Expects the following message format:
        {
            
        }

        
        """
                
        logging.debug(f'Current state-> spot:{self.spotlight_status} island:{self.islandlight_status}')

        
        if topic == f'{self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}':            
            self.islandlight_status = payload["state"]

        if topic == f'{self.ROOT_TOPIC}/{self.STORAGE_SWITCH}':            
            self.spotlight_status = payload["state_left"]

        try:
            if topic == f'{self.ROOT_TOPIC}/{self.LIVING_ROOM_LIGHT_SWITCH}' and \
                payload["action"] == "single_right":
                
                if self.spotlight_status:
                    if self.islandlight_status:
                        self.set_kitchen_lights("off")
                    else:
                        self.set_island_light("on")
                else:
                    self.set_kitchen_lights("on")
        except KeyError as e:
            logging.error(f'Error: {e}. \n\nPayload: {payload}\n\n')


    def get_lights_status(self):
        command = '{"state": ""}'
        logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}/get')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.KITCHEN_ISLAND_LIGHTS}/get',command)

        command = '{"state_left": ""}'
        logging.debug(f'sending: {command}')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.STORAGE_SWITCH}/get',command)

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
 
    @property
    def spotlight_status(self):
        return self.__spotlight_status==State.ON

    @spotlight_status.setter
    def spotlight_status(self,status):
        logging.debug(f'Setter spot light:{status}')
        if status.lower() == "on":
            self.__spotlight_status = State.ON
        elif status.lower() == "off":
            self.__spotlight_status = State.OFF

    @property
    def islandlight_status(self):
        return self.__islandlight_status

    @islandlight_status.setter
    def islandlight_status(self,status):
        logging.debug(f'Setter insland light:{status}')
        if status.lower() == "on":
            self.__islandlight_status = True
        elif status.lower() == "off":
            self.__islandlight_status = False

        

broker = "192.168.1.10"
name = "automation.kitchen_lights"

kitchen_lights = KitchenLightAutomation(broker_ip = broker, name = name)
kitchen_lights.connect()
kitchen_lights.get_lights_status()


while True:
    time.sleep(2)

