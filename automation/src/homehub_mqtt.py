import time,json, logging, threading, socket
import paho.mqtt.client as paho

class AutomationPubSub:
    RECONNECTION_TIMER = 10
    def __init__(self, broker_ip:str, name:str):
        self.name = name
        self.client= paho.Client(client_id=self.name, clean_session=False)
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.broker_ip = broker_ip
        self.topics = []
        self._timer_reconnect = None

    def new_topics(self,topics):
        for topic in topics:
            self.topics.append(topic)

    def connect(self):
        logging.info(f"Connecting to broker {self.broker_ip}")
        self.client.connect(self.broker_ip)     
        self.client.loop_start()
         

    def on_message(self,client, userdata, message):
        assert("Not Implemented")

    def on_connect(self,client, userdata, message, properties=None):
        logging.debug("on_connect fired")        
        for topic in self.topics:
            client.subscribe(topic,qos=1)

    def on_disconnect(self,client, userdata, message):
        
        logging.debug("on_disconnect fired")
        self.reconnect()
        

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