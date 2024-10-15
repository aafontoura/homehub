import time, json, logging
import paho.mqtt.client as paho
import signal
import sys
import os

from homehub_mqtt import AutomationPubSub

# Configure logging to output debug information to the console
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

class VentilationAutomation(AutomationPubSub):
    # Constants used for MQTT topics and timeout
    TIMEOUT = 180
    ROOT_TOPIC = "zigbee2mqtt"
    BATHROOM_TEMPERATURE_SENSOR = "Bathroom Sensor"
    TOPICS = [f'{ROOT_TOPIC}/{BATHROOM_TEMPERATURE_SENSOR}']

    # Humidity thresholds and corresponding ventilation levels
    HUMIDITY_HIGH_THRESHOLD = 85
    HUMIDITY_MEDIUM_THRESHOLD = 80
    HUMIDITY_LOW_THRESHOLD = 75
    VENTILATION_HIGH = 95
    VENTILATION_MEDIUM = 70
    VENTILATION_LOW = 50
    VENTILATION_MIN = 8

    def __init__(self, broker_ip: str, name: str):
        # Initialize the parent class with broker IP and name, and subscribe to topics
        super().__init__(broker_ip, name)
        self._subscribe_to_topics(self.TOPICS)

    def handle_message(self, topic, payload):
        """ Handle incoming MQTT messages and control ventilation based on humidity
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
        # Check if the topic matches the expected bathroom sensor topic
        if topic == f'{self.ROOT_TOPIC}/{self.BATHROOM_TEMPERATURE_SENSOR}':
            try:
                humidity = payload['humidity']
                # Determine the ventilation level based on humidity
                if humidity > self.HUMIDITY_HIGH_THRESHOLD:
                    power_percentage = self.VENTILATION_HIGH
                elif humidity > self.HUMIDITY_MEDIUM_THRESHOLD:
                    power_percentage = self.VENTILATION_MEDIUM
                elif humidity > self.HUMIDITY_LOW_THRESHOLD:
                    power_percentage = self.VENTILATION_LOW
                else:
                    power_percentage = self.VENTILATION_MIN
                self.set_ventilation(power_percentage)
            except KeyError as e:
                # Log an error if a required key is missing from the payload
                logging.error(f'Key Error: {e}')
                return
            except TypeError as e:
                # Log an error if the payload is of an unexpected type
                logging.error(f'Type Error: {e}')
                return
        else:
            # Log a warning if the message is from an unexpected topic
            logging.warning(f'Received message from unknown topic: {topic}')

    def set_ventilation(self, power_percentage: int):
        # Ensure the power percentage is within valid range (0-100)
        if 0 <= power_percentage <= 100:
            logging.info(f'Setting ventilation to {power_percentage}% - itho/cmd - {str(int(power_percentage * 2.55))}')
            try:
                # Publish the calculated value to the MQTT topic to control ventilation
                self.client.publish("itho/cmd", str(int(power_percentage * 2.55)))
            except paho.mqtt.client.MQTTException as e:
                # Log an error if there's an issue publishing the message
                logging.error(f'Failed to publish MQTT message: {e}')


# Signal handler for graceful shutdown of the script
def signal_handler(sig, frame):
    logging.info('Gracefully shutting down...')
    sys.exit(0)

# Function to get the broker IP from environment variables (default to a specific IP if not set)
def get_broker_ip():
    return os.getenv('MQTT_BROKER_IP', '192.168.1.60')

if __name__ == "__main__":
    # Get the broker IP address and define the automation name
    broker = get_broker_ip()
    name = "automation.ventilation"

    # Create an instance of the VentilationAutomation class and connect to the broker
    ventilation_automation = VentilationAutomation(broker_ip=broker, name=name)
    ventilation_automation.connect()

    # Register signal handlers for graceful shutdown (SIGINT for Ctrl+C, SIGTERM for termination)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Keep the program running and wait for signals
    signal.pause()