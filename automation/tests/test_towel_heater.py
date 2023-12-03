import pytest
from src.towel_heater import TowelHeaterAutomation
from unittest.mock import patch



@pytest.fixture
def mock_time():
    with patch('time.time') as mock_time:
        mock_time.return_value = 0  # starting time
        yield mock_time




@pytest.fixture
def mock_delayed_heater():
    with patch('src.towel_heater.TowelHeaterAutomation.delayed_towel_heater') as mock:
        yield mock



def test_delayed_towel_heater_behavior(mock_delayed_heater, mock_time):
    ROOT_TOPIC = "zigbee2mqtt"
    TOWEL_HEATER = "Bathroom Socket"
    SHORT_CYCLE_TIME = 1
    LONG_CYCLE_TIME = 30

    test_cases = [{"trigger_payload":{"state":"ON"}, "expected_status":False, "time_increment": SHORT_CYCLE_TIME, "expected_command": '{"state":"OFF"}'},
                  {"trigger_payload":{"state":"OFF"}, "expected_status":True, "time_increment": SHORT_CYCLE_TIME, "expected_command": '{"state":"ON"}'},
                  {"trigger_payload":{"state":"ON"}, "expected_status":False, "time_increment": LONG_CYCLE_TIME, "expected_command": '{"state":"OFF"}'},
                  {"trigger_payload":{"state":"ON"}, "expected_status":None, "time_increment": SHORT_CYCLE_TIME, "expected_command": None},
                  {"trigger_payload":{"state":"OFF"}, "expected_status":None, "time_increment": SHORT_CYCLE_TIME, "expected_command": None},
                  {"trigger_payload":{"state":"ON"}, "expected_status":False, "time_increment": SHORT_CYCLE_TIME, "expected_command": '{"state":"OFF"}'},]
    
    topic_set = f'{ROOT_TOPIC}/{TOWEL_HEATER}/set'
    topic_status = f'{ROOT_TOPIC}/{TOWEL_HEATER}'



    with patch('paho.mqtt.client.Client') as MockClient:
        mock_client = MockClient.return_value
        towel_heater = TowelHeaterAutomation(broker_ip='127.0.0.1', name='test')
        towel_heater.client = mock_client

        mock_time.return_value += 100

        for test_case in test_cases:            

            towel_heater.handle_message(topic_status, test_case["trigger_payload"])
            # Ensure delayed_towel_heater was called with expected arguments
            if test_case["expected_status"] != None:
                mock_delayed_heater.assert_called_with(test_case["expected_status"], test_case["time_increment"])
                mock_time.return_value += test_case["time_increment"]
                towel_heater.set_towel_heater(test_case["expected_status"])

                # Test the effects of what should happen after delayed_towel_heater
                # For instance, check if the correct MQTT message was published
                print("Assert call")
                mock_client.publish.assert_called_with(topic_set, test_case["expected_command"])
                

            else:
                print("Assert NOT call")
                mock_delayed_heater.assert_not_called()
                mock_time.return_value += test_case["time_increment"]

            mock_delayed_heater.reset_mock()
            

            



if __name__ == '__main__':
    assert("Not implemented")