"""
Controlling the tower heater through the smart socket (https://www.zigbee2mqtt.io/devices/HG06337.html)
Model	HG06337
Description	Silvercrest smart plug (EU, CH, FR, BS, DK)
Exposes	switch (state), power_on_behavior, indicator_mode, linkquality
To control this switch publish a message to topic zigbee2mqtt/FRIENDLY_NAME/set with payload {"state": "ON"}, {"state": "OFF"} or {"state": "TOGGLE"}

"""

import time,json, logging, threading
import paho.mqtt.client as paho
from enum import Enum
from icecream import ic
import time

from .homehub_mqtt import AutomationPubSub




logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)




class TowelHeaterAutomation(AutomationPubSub):
    """
    A class to automate a towel heater using a MQTT controlled smart socket.

    This class extends AutomationPubSub and controls a towel heater by publishing
    MQTT messages to a specified topic. It implements a state machine to manage 
    the heater's state and to control its behavior based on incoming MQTT messages.
    The state machine purpose is to implement a health indication on the towel heater, 
    so when an user turns on the towel heater, the socker will cycle once (ON->OFF->ON).

    Life cycle of the relay might be a concern, but given that the smart socket is not
    used throughout the whole year, the wear is limited.

    Attributes:
        SHORT_CYCLE_TIME (float): Time in seconds for the health indication cycle.
        LONG_CYCLE_TIME (float): Time in seconds for the heating cycle.
        TIME_THRESHOLD_BETWEEN_MESSAGES (float): Minimum time threshold in seconds 
            between handling consecutive MQTT messages to avoid undesired duplicate messages .
        ROOT_TOPIC (str): The root MQTT topic to listen for messages.
        TOWEL_HEATER (str): The name of the MQTT topic specific to the towel heater.
        TOPICS (list): List of MQTT topics that this class subscribes to.

    Args:
        broker_ip (str): IP address of the MQTT broker.
        name (str): Name of the automation instance.
    """
    SHORT_CYCLE_TIME = 1 #  seconds
    LONG_CYCLE_TIME = 35*60 # 35 minutes  
    TIME_THRESHOLD_BETWEEN_MESSAGES = 0.01 # seconds
    ROOT_TOPIC = "zigbee2mqtt"
    TOWEL_HEATER = "Bathroom Socket"
    TOPICS = [f'{ROOT_TOPIC}/{TOWEL_HEATER}']

    class TowelStateMachine(Enum):
        IDLE = 0
        HEALTH_INDICATION_ON_SLEEP = 1
        HEALTH_INDICATION_OFF_SLEEP = 2
        HEATING = 3


    def __init__(self, broker_ip:str, name:str):
        """Initialize the TowelHeaterAutomation class with MQTT broker details and subscribe to topics."""
        super().__init__(broker_ip,name)        
        self._subscribe_to_topics(self.TOPICS) 
        self._health_indication_state = False # Flag to indicate if we are in the middle of a sequence     
        self._heater_active = False
        self._timer = None
        self._state = self.TowelStateMachine.IDLE
        self._time_at_last_message = 0
        
    

    def handle_message(self, topic, payload):
        """ 
        Handle incoming MQTT messages and filter undesired messages.
        Args:
            topic (str): The MQTT topic of the incoming message.
            payload (dict): The payload of the message containing the heater state and other information.
        Expects the following message format:
    
        {
            "indicator_mode":null,
            "linkquality":69,
            "power_on_behavior":null,
            "state":"ON"
        }

        
        """        
        if topic == f'{self.ROOT_TOPIC}/{self.TOWEL_HEATER}':
            try:
                current_time = time.time()
                ic(f'Received message: {topic} {payload} at {time.time()}')
                logging.debug(payload)

                if current_time - self._time_at_last_message < self.TIME_THRESHOLD_BETWEEN_MESSAGES:
                    ic(f'Ignoring message: {topic} {payload} at {time.time()}')
                    self._time_at_last_message = current_time
                    return
                
                self._time_at_last_message = current_time
                self.towel_heater_sm(payload)

            except KeyError as e:
                logging.error(f'Error: {e}')
            except json.JSONDecodeError as e:
                logging.error(f'JSON Decode Error: {e}')
        else:
            logging.debug(f'Skipping: {topic}')

    def towel_heater_sm(self, payload):
        """
        Control the state machine of the towel heater based on the payload.

        This method is responsible for transitioning the state of the towel heater
        and executing the corresponding actions like turning on/off the heater.

        Args:
            payload (dict): The payload received from the MQTT message.
        """
        towel_heater = payload
        logging.debug(f'state: {self._state}')
        if self._state == self.TowelStateMachine.IDLE:
            
            if towel_heater["state"] == "ON":
                self._state = self.TowelStateMachine.HEALTH_INDICATION_ON_SLEEP                        
                self.delayed_towel_heater(False, self.SHORT_CYCLE_TIME)
                logging.debug(f'new state: {self._state}')
                
            return
        
        if self._state == self.TowelStateMachine.HEALTH_INDICATION_ON_SLEEP:
            if towel_heater["state"] == "OFF":
                self._state = self.TowelStateMachine.HEALTH_INDICATION_OFF_SLEEP
                logging.debug(f'new state: {self._state}')
                self.delayed_towel_heater(True, self.SHORT_CYCLE_TIME)                        
            return
        
        if self._state == self.TowelStateMachine.HEALTH_INDICATION_OFF_SLEEP:
            if towel_heater["state"] == "ON":
                self._state = self.TowelStateMachine.HEATING
                logging.debug(f'new state: {self._state}')
                self.delayed_towel_heater(False, self.LONG_CYCLE_TIME)
                
            return
        
        if self._state == self.TowelStateMachine.HEATING:
            if towel_heater["state"] == "OFF":
                self._state = self.TowelStateMachine.IDLE
                logging.debug(f'new state: {self._state}')
                if self._timer:
                    self._timer.cancel()

                
            return

    def set_towel_heater(self, status=False):
        command = '{"state":"ON"}' if status else '{"state":"OFF"}'
        logging.debug(f'sending: {command} to {self.ROOT_TOPIC}/{self.TOWEL_HEATER}/set')
        self.client.publish(f'{self.ROOT_TOPIC}/{self.TOWEL_HEATER}/set', command)
        


    def delayed_towel_heater(self, status, duration):
        """
        Set the state of the towel heater after a delay.

        This method uses a timer to delay setting the state of the heater. It's useful
        for implementing the cycles of the heater's operation.

        Args:
            status (bool): The desired state of the heater after the delay.
            duration (float): The duration of the delay in seconds.
        """
        if self._timer:
            self._timer.cancel()  # Cancel any existing timer
        self._timer = threading.Timer(duration, self.set_towel_heater, args=(status, ))
        self._timer.start()



if __name__ == '__main__':

    broker = "192.168.1.60"
    name = "automation.towel_heater"

    storage_automation = TowelHeaterAutomation(broker_ip = broker, name = name)
    storage_automation.connect()


    while True:
        time.sleep(2)

