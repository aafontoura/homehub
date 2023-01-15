import time,json, logging
import paho.mqtt.client as paho

from homehub_mqtt import AutomationPubSub

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
)

class VentilationAutomation(AutomationPubSub):
    TIMEOUT = 180
    ROOT_TOPIC = "zigbee2mqtt"
    BATHROOM_TEMPERATURE_SENSOR = "Bathroom Sensor"
    TOPICS = [f'{ROOT_TOPIC}/{BATHROOM_TEMPERATURE_SENSOR}']

    def __init__(self, broker_ip:str, name:str):
        super().__init__(broker_ip,name)
        self._subscribe_to_topics(self.TOPICS)

        

    def handle_message(self, topic, payload):
        """ Change the switch according to the door sensor
        Expects the following message format:
        {
            "battery":80,
            "humidity":52.46,
            "linkquality":255,
            "pressure":997,
            "temperature":20.73,
            "voltage":2965}        
        """
        if topic == f'{self.ROOT_TOPIC}/{self.BATHROOM_TEMPERATURE_SENSOR}':           
        
            try:
                if bathroom_sensor['humidity'] > 85:
                    self.set_ventilation(95)
                elif bathroom_sensor['humidity'] > 80:
                    self.set_ventilation(70)
                elif bathroom_sensor['humidity'] > 75:
                    self.set_ventilation(50)
                else:
                    self.set_ventilation(8)
                
                
            except KeyError as e:
                logging.error(f'Error:{e}') 
                return  
        else:
            logging.debug(f'Skipping topic: {topic}') 
        

    def set_ventilation(self, power_percentage : int):
        if power_percentage <= 100 and power_percentage > 0:
            self.client.publish("itho/cmd",str(int(power_percentage*2.55)))
        



broker = "192.168.1.10"
name = "automation.ventilation"

ventilation_automation = VentilationAutomation(broker_ip = broker, name = name)
ventilation_automation.connect()


while True:
    time.sleep(2)


