# tests/test_dishwasher_control.py
import sys
import types
from unittest.mock import MagicMock, patch
import pytest
import logging

# Constants representing various Home Assistant entity IDs.
SENSOR_REMOTE_START = (
    "binary_sensor.011040519583042054_bsh_common_status_remotecontrolstartallowed"
)
SENSOR_READY = "sensor.011040519583042054_bsh_common_status_operationstate"
SENSOR_DISHWASHER_DOOR = (
    "binary_sensor.011040519583042054_bsh_common_status_doorstate"
)
SENSOR_DISHWASHER_CONNECTED = "binary_sensor.011040519583042054_connected"
SENSOR_OPERSTATE = "sensor.011040519583042054_bsh_common_status_operationstate"
SENSOR_START_RELATIVE = "sensor.011040519583042054_bsh_common_option_startinrelative"
SELECT_PROGRAM = "select.011040519583042054_programs"
BUTTON_START = "button.011040519583042054_start_pause"
HELPER_COST_INPUT = "input_number.dishwasher_cost"
HELPER_SAVINGS = "input_number.dishwasher_savings"
HELPER_NEXT_CYCLE = "input_datetime.next_dishwasher_cycle"
HELPER_NEXT_CYCLE_IN = "input_number.dishwasher_starts_in"
DEVICE_ID = "71a8e29be99faa5d4ff021056e54324d"
ENABLE_LOG = True
OPERSTATE_FINISHED = "BSH.Common.EnumType.OperationState.Finished"
OPERSTATE_READY = "BSH.Common.EnumType.OperationState.Ready"



# Create a dummy module for hassapi
mock_hassapi = types.ModuleType('hassapi')
# Add a mock Hass class to the dummy module
class MockHass:
    # Add mock implementations or MagicMock for methods used from hass.Hass
    def get_state(self, *args, **kwargs):
        return MagicMock()

    def log(self, *args, **kwargs):
        pass

    def set_value(self, *args, **kwargs):
        pass

    def call_service(self, *args, **kwargs):
        pass
    
    def listen_state(self, *args, **kwargs):
        pass

mock_hassapi.Hass = MockHass
sys.modules['hassapi'] = mock_hassapi

# Now we can safely import DishwasherControl
from src.appdaemon.dishwasher_control import DishwasherControl

@pytest.fixture
def dishwasher_control(request):
    control = DishwasherControl()
    control.initialize()

    entity_states = request.param

    def get_state_side_effect(entity_id, attribute=None):
        if entity_id in entity_states:
            return entity_states[entity_id]
        elif entity_id == "sensor.epex_spot_data_net_price_2" and attribute == "data":
            return "[{'start_time': '2023-12-26T23:00:00+00:00', 'end_time': '2023-12-27T00:00:00+00:00', 'price_ct_per_kwh': 28.303109999999997}]"
        return MagicMock()  # Default return for other cases

    control.get_state = MagicMock(side_effect=get_state_side_effect)
    
    return control

# Parameterize the test function for different combinations of entity states
@pytest.mark.parametrize('dishwasher_control, expected', [
    ({SENSOR_REMOTE_START: "on",
      SENSOR_READY: "BSH.Common.EnumType.OperationState.Ready",
      SENSOR_DISHWASHER_DOOR: "off",
      SENSOR_DISHWASHER_CONNECTED: "on",
      SENSOR_START_RELATIVE: "some_value",
      SELECT_PROGRAM: "some_program"}, True),
    # Add more scenarios as needed
], indirect=["dishwasher_control"])
def test_is_dishwasher_ready(dishwasher_control, expected):
    assert dishwasher_control.is_dishwasher_ready() == expected
