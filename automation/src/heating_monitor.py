#!/usr/bin/env python3
"""
Heating System Monitor - Sensor health monitoring and predictive maintenance

Features:
- Battery level monitoring with predictive alerts
- Zigbee link quality (LQI) tracking
- Sensor health reports
- Independent operation from heating control
"""

import time
import logging
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from homehub_mqtt import AutomationPubSub


class HeatingMonitor(AutomationPubSub):
    """
    Independent monitoring service for heating system sensor health.

    Tracks battery levels, link quality, and sensor uptime for proactive
    maintenance alerts.
    """

    def __init__(self, broker_ip, config_file='heating_config.yaml', mqtt_username=None, mqtt_password=None):
        super().__init__(broker_ip, "heating_monitor", username=mqtt_username, password=mqtt_password)

        # Load configuration (shared with heating_control.py)
        self.config = self.read_config(config_file)
        if not self.config:
            raise RuntimeError(f"Failed to load config from {config_file}")

        # Sensor health tracking
        # Format: {sensor_topic: {battery%, linkquality, last_seen_timestamp, zone_name}}
        self.sensors = {}

        # Extract sensor topics from config
        self.zone_sensors = {}  # {zone_name: sensor_topic}
        for zone_name, zone_config in self.config['zones'].items():
            sensor_topic = zone_config.get('temperature_sensor_topic')
            if sensor_topic:
                self.zone_sensors[zone_name] = sensor_topic
                logging.info(f"Monitoring sensor for {zone_name}: {sensor_topic}")

        # Monitoring thresholds
        self.battery_low_threshold = 20  # Alert if battery < 20%
        self.lqi_low_threshold = 100     # Alert if LQI < 100
        self.no_update_timeout_minutes = 30  # Alert if no update for 30 min

        # Subscribe only to configured heating sensors (not all Zigbee devices)
        sensor_topics = list(self.zone_sensors.values())
        self._subscribe_to_topics(sensor_topics)
        logging.info(f"Subscribed to {len(sensor_topics)} heating sensor topics")

        # Also subscribe to heating system metrics for context
        self._subscribe_to_topics(['heating/#'])

        logging.info("Heating Monitor initialized")
        logging.info(f"Monitoring {len(self.zone_sensors)} temperature sensors")
        logging.info(f"Battery threshold: {self.battery_low_threshold}%")
        logging.info(f"LQI threshold: {self.lqi_low_threshold}")

    def handle_message(self, topic, payload):
        """
        Handle incoming MQTT messages.

        Args:
            topic: MQTT topic
            payload: Message payload (JSON or string)
        """
        try:
            # Handle Zigbee2MQTT sensor messages
            if topic.startswith('zigbee2mqtt/') and not topic.endswith('/set'):
                self._process_zigbee_message(topic, payload)

            # Handle heating system messages (for context)
            elif topic.startswith('heating/'):
                self._process_heating_message(topic, payload)

        except Exception as e:
            logging.error(f"Error processing message from {topic}: {e}", exc_info=True)

    def _process_zigbee_message(self, topic, payload):
        """
        Process Zigbee2MQTT sensor messages to track health.

        Args:
            topic: Zigbee2MQTT topic (e.g., "zigbee2mqtt/Living Room Sensor")
            payload: Sensor data including battery and linkquality
        """
        # Only track sensors we care about (temperature sensors from config)
        if topic not in self.zone_sensors.values():
            return  # Not a heating sensor, ignore

        # Extract sensor name from topic
        sensor_name = topic.replace('zigbee2mqtt/', '')

        # Parse JSON payload
        try:
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload
        except json.JSONDecodeError:
            logging.warning(f"Invalid JSON from {topic}")
            return

        # Extract health metrics
        battery = data.get('battery')
        linkquality = data.get('linkquality')
        temperature = data.get('temperature')

        # Determine which zone this sensor belongs to
        zone_name = None
        for zname, ztopic in self.zone_sensors.items():
            if ztopic == topic:
                zone_name = zname
                break

        # Update sensor health tracking
        if topic not in self.sensors:
            self.sensors[topic] = {
                'sensor_name': sensor_name,
                'zone_name': zone_name,
                'battery': None,
                'linkquality': None,
                'last_seen': None,
                'temperature': None
            }

        sensor_info = self.sensors[topic]
        sensor_info['last_seen'] = time.time()

        if battery is not None:
            sensor_info['battery'] = battery
        if linkquality is not None:
            sensor_info['linkquality'] = linkquality
        if temperature is not None:
            sensor_info['temperature'] = temperature

        # Publish sensor health metrics to MQTT
        self._publish_sensor_health(sensor_info)

        # Check thresholds and publish alerts
        self._check_battery_threshold(sensor_info)
        self._check_lqi_threshold(sensor_info)

    def _process_heating_message(self, topic, payload):
        """
        Process heating system messages for context.

        Args:
            topic: Heating MQTT topic
            payload: Message payload
        """
        # Currently just logging for context
        # Future: Could correlate pump activity with sensor readings
        pass

    def _publish_sensor_health(self, sensor_info):
        """
        Publish sensor health metrics to MQTT.

        Args:
            sensor_info: Sensor health data dict
        """
        zone_name = sensor_info['zone_name']
        if not zone_name:
            return

        # Format last_seen timestamp as human-readable string
        last_seen_timestamp = sensor_info.get('last_seen')
        last_seen_formatted = None
        if last_seen_timestamp is not None:
            last_seen_formatted = datetime.fromtimestamp(last_seen_timestamp).strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]

        # Publish individual metrics for Home Assistant sensors
        metrics = {
            'battery': sensor_info.get('battery'),
            'linkquality': sensor_info.get('linkquality'),
            'last_seen': last_seen_formatted,
            'sensor_name': sensor_info['sensor_name'],
            'temperature': sensor_info.get('temperature')
        }

        self.client.publish(
            f"heating/monitor/{zone_name}/sensor_health",
            json.dumps(metrics),
            qos=1,
            retain=True
        )

        logging.debug(
            f"{zone_name}: Sensor health | "
            f"Battery: {metrics['battery']}%, "
            f"LQI: {metrics['linkquality']}, "
            f"Temp: {metrics['temperature']}°C"
        )

    def _check_battery_threshold(self, sensor_info):
        """
        Check if battery is below threshold and publish alert.

        Args:
            sensor_info: Sensor health data dict
        """
        battery = sensor_info.get('battery')
        zone_name = sensor_info['zone_name']

        if battery is None or zone_name is None:
            return

        if battery < self.battery_low_threshold:
            alert_payload = {
                'alert_id': 'HEAT-MN-001',
                'zone': zone_name,
                'sensor': sensor_info['sensor_name'],
                'battery': battery,
                'threshold': self.battery_low_threshold,
                'message': f"{zone_name} sensor battery at {battery}% (threshold: {self.battery_low_threshold}%)",
                'timestamp': time.time()
            }

            self.client.publish(
                f"heating/monitor/{zone_name}/alert/battery_low",
                json.dumps(alert_payload),
                qos=1,
                retain=False
            )

            logging.warning(
                f"[HEAT-MN-001] {zone_name}: BATTERY LOW - "
                f"{battery}% (threshold: {self.battery_low_threshold}%)"
            )

    def _check_lqi_threshold(self, sensor_info):
        """
        Check if link quality is below threshold and publish alert.

        Args:
            sensor_info: Sensor health data dict
        """
        lqi = sensor_info.get('linkquality')
        zone_name = sensor_info['zone_name']

        if lqi is None or zone_name is None:
            return

        if lqi < self.lqi_low_threshold:
            alert_payload = {
                'alert_id': 'HEAT-MN-002',
                'zone': zone_name,
                'sensor': sensor_info['sensor_name'],
                'linkquality': lqi,
                'threshold': self.lqi_low_threshold,
                'message': f"{zone_name} sensor LQI at {lqi} (threshold: {self.lqi_low_threshold})",
                'timestamp': time.time()
            }

            self.client.publish(
                f"heating/monitor/{zone_name}/alert/lqi_low",
                json.dumps(alert_payload),
                qos=1,
                retain=False
            )

            logging.warning(
                f"[HEAT-MN-002] {zone_name}: LQI LOW - "
                f"{lqi} (threshold: {self.lqi_low_threshold})"
            )

    def _check_stale_sensors(self):
        """
        Periodic check for sensors that haven't reported recently.
        Called from main loop every 60 seconds.
        """
        current_time = time.time()
        timeout_seconds = self.no_update_timeout_minutes * 60

        for _, sensor_info in self.sensors.items():
            last_seen = sensor_info.get('last_seen')
            zone_name = sensor_info['zone_name']

            if last_seen is None or zone_name is None:
                continue

            elapsed_seconds = current_time - last_seen

            if elapsed_seconds > timeout_seconds:
                elapsed_minutes = elapsed_seconds / 60

                alert_payload = {
                    'alert_id': 'HEAT-MN-003',
                    'zone': zone_name,
                    'sensor': sensor_info['sensor_name'],
                    'elapsed_minutes': int(elapsed_minutes),
                    'threshold_minutes': self.no_update_timeout_minutes,
                    'message': f"{zone_name} sensor not reporting for {int(elapsed_minutes)} minutes",
                    'timestamp': time.time()
                }

                self.client.publish(
                    f"heating/monitor/{zone_name}/alert/no_update",
                    json.dumps(alert_payload),
                    qos=1,
                    retain=False
                )

                logging.warning(
                    f"[HEAT-MN-003] {zone_name}: SENSOR NOT REPORTING - "
                    f"{int(elapsed_minutes)} min (threshold: {self.no_update_timeout_minutes} min)"
                )


def main():
    """Main entry point"""
    # Configure logging first
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed, use system environment only
    except Exception as e:
        logging.warning(f"Could not load .env file: {e}")

    # Get MQTT broker IP from environment
    broker_ip = os.getenv('MQTT_BROKER_IP', '192.168.1.10')

    # Get MQTT credentials from environment (optional)
    mqtt_username = os.getenv('MQTT_USERNAME')
    mqtt_password = os.getenv('MQTT_PASSWORD')

    logging.info("=" * 80)
    logging.info("Heating System Monitor v1.0.0")
    logging.info("=" * 80)
    logging.info(f"MQTT Broker: {broker_ip}")

    if mqtt_username and mqtt_password:
        logging.info(f"MQTT authentication configured for user: {mqtt_username}")
    else:
        logging.info("MQTT authentication not configured (anonymous access)")

    logging.info(f"Config file: heating_config.yaml")

    # Create and start monitor
    monitor = HeatingMonitor(broker_ip, mqtt_username=mqtt_username, mqtt_password=mqtt_password)

    # Start MQTT connection
    monitor.connect()

    # Run periodic check for stale sensors
    logging.info("Starting periodic sensor staleness check (every 60 seconds)")

    try:
        while True:
            time.sleep(60)  # Check every minute
            monitor._check_stale_sensors()
    except KeyboardInterrupt:
        logging.info("Shutting down Heating Monitor...")


if __name__ == "__main__":
    main()
