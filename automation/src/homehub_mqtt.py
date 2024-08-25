import time
import json
import logging
import threading
import socket
import paho.mqtt.client as paho
from json.decoder import JSONDecodeError
import yaml  # Ensure yaml is imported for the read_config method

class AutomationPubSub:
    RECONNECTION_TIMER = 10
    def __init__(self, broker_ip:str, name:str):
        self.name = name
        self.client= paho.Client(client_id=self.name, clean_session=False)
        self.client.on_message = self.__on_message
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.broker_ip = broker_ip
        self.topics = []
        self._timer_reconnect = None

    
    def new_topics(self,topics):
        """
        To support legacy calls
        """
        self._subscribe_to_topics(topics)

    def _subscribe_to_topics(self,topics):
        if not isinstance(topics, list):
            logging.error("Topics should be a list.")
            return
        
        for topic in topics:
            if topic not in self.topics:
                self.topics.append(topic)
            else:
                logging.debug(f"Topic '{topic}' is already subscribed.")

    def connect(self):
        
        while True:
            try:
                logging.info(f"Connecting to broker {self.broker_ip}")
                self.client.connect(self.broker_ip)  
                self.client.loop_start()   
                break
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                logging.error(f'Failed to connect: {e}')
                logging.info(f'Retrying connection...')
                time.sleep(self.RECONNECTION_TIMER)
                continue

        
         


    def __on_message(self, client, userdata, message):
        received = str(message.payload.decode("utf-8"))

        try:
            payload = json.loads(str(message.payload.decode("utf-8")))
        except JSONDecodeError as e:
            logging.debug(f'payload is not JSON: \n{received}\n Error:{e}')
            payload = received
            
        logging.debug(f'New message payload from {message.topic}:\n{payload}')


        self.handle_message(message.topic, payload)

    def on_message(self,client, userdata, message):
        assert("Not Implemented")

    def handle_message(self, topic, payload):
        assert("Not Implemented")

    def on_connect(self,client, userdata, message, properties=None):
        logging.debug("on_connect fired")        
        for topic in self.topics:
            logging.debug(f'Subscribing to: {topic}')
            client.subscribe(topic,qos=1)

    def on_disconnect(self,client, userdata, message):
        
        logging.debug("on_disconnect fired")
        self.reconnect()

    def read_config(self, file_path = "config.yaml"):
        logging.debug(f'Reading config file from {file_path}')
        try:
            with open(file_path, 'r') as file:
                data = yaml.safe_load(file)
                return data
        except FileNotFoundError:
            logging.error(f"File {file_path} not found.")
            return None
        except yaml.YAMLError as exc:
            logging.error(f"Error in YAML file: {exc}")
            return None

        

    def reconnect(self):
        try:
            logging.debug("Trying to reconnect")
            self.client.reconnect()
            # del(self._timer_reconnect)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logging.error(f'Reconnection failed: {e}') 
            self._timer_reconnect = threading.Timer(self.RECONNECTION_TIMER, self.reconnect)
            self._timer_reconnect.start()


if __name__ == '__main__':
    print("Not implemented")