import time, json, logging
import paho.mqtt.client as paho
import signal
import sys
import os

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

    def __init__(self, broker_ip: str, name: str):
        super().__init__(broker_ip, name)
        self._subscribe_to_topics(self.TOPICS)

    def handle_message(self, topic, payload):
        """ Change the switch according to the door sensor
        Expects the following message format:
        {
            "battery": 80,
            "humidity": 52.46,
            "linkquality": 255,
            "pressure": 997,
            "temperature": 20.73,
            "voltage": 2965
        }        
        """
        if topic == f'{self.ROOT_TOPIC}/{self.BATHROOM_TEMPERATURE_SENSOR}':
            try:
                if payload['humidity'] > 85:
                    self.set_ventilation(95)
                elif payload['humidity'] > 80:
                    self.set_ventilation(70)
                elif payload['humidity'] > 75:
                    self.set_ventilation(50)
                else:
                    self.set_ventilation(8)
            except KeyError as e:
                logging.error(f'Key Error: {e}')
                return
            except TypeError as e:
                logging.error(f'Type Error: {e}')
                return
        else:
            logging.warning(f'Received message from unknown topic: {topic}')

    def set_ventilation(self, power_percentage: int):
        if 0 <= power_percentage <= 100:
            logging.info(f'Setting ventilation to {power_percentage}% - itho/cmd - {str(int(power_percentage * 2.55))}')
            try:
                self.client.publish("itho/cmd", str(int(power_percentage * 2.55)))
            except paho.mqtt.client.MQTTException as e:
                logging.error(f'Failed to publish MQTT message: {e}')


def signal_handler(sig, frame):
    logging.info('Gracefully shutting down...')
    sys.exit(0)


def get_broker_ip():
    return os.getenv('MQTT_BROKER_IP', '192.168.1.60')


if __name__ == "__main__":
    broker = get_broker_ip()
    name = "automation.ventilation"

    ventilation_automation = VentilationAutomation(broker_ip=broker, name=name)
    ventilation_automation.connect()

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Keep the program running
    signal.pause()