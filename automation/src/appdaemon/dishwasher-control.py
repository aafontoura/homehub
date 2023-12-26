import hassapi as hass
import os
from datetime import datetime, timedelta
import pytz

from src.energycalculation import EnergyPriceAnalyzer, load_csv, load_json_from_string

def get_data_file_path(relative_path):
    # Get the directory of the current test file
    dir_name = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path
    return os.path.join(dir_name, relative_path)

class PriceCalculator():
    def __init__(self): 
        print("hello")

class DishwasherControl(hass.Hass):  
    SENSOR_REMOTE_START = "binary_sensor.011040519583042054_bsh_common_status_remotecontrolstartallowed"
    SENSOR_READY = "sensor.011040519583042054_bsh_common_status_operationstate"
    SENSOR_DISHWASHER_DOOR = "binary_sensor.011040519583042054_bsh_common_status_doorstate"
    SENSOR_DISHWASHER_CONNECTED = "binary_sensor.011040519583042054_connected"
    BUTTON_START = "button.011040519583042054_start_pause"
    HELPER_COST_INPUT = "input_number.dishwasher_cost"
    ENABLE_LOG = True
    
    def initialize(self):
        
        self.program_timer = None
               
        
        prices = str(self.get_state("sensor.epex_spot_data_net_price_2", attribute="data"))
        prices = prices.replace("'", '"')
        self.energy = EnergyPriceAnalyzer(load_csv(get_data_file_path("data/dishwasher_eco_profile.csv")),load_json_from_string(prices))
        
        if self.is_dishwasher_ready():
             self.program_dishwasher()
            
        

        self.listen_state(self.disch_washer_ready_cb, "sensor.cube_action", new="slide")
        self.listen_state(self.disch_washer_ready_cb, "binary_sensor.011040519583042054_bsh_common_status_doorstate", new="off")
        
        

    def program_dishwasher(self):
        self.log("Programming...")
        if self.program_timer is not None:
            self.cancel_timer(self.program_timer)
        
        start_time, cost = self.calculate_start_time()
        
        current_time = datetime.now(pytz.utc)
        time_difference = start_time - current_time
        
        self.program_timer = self.run_in(self.start_dishwasher, time_difference.total_seconds())
        self.set_value(self.HELPER_COST_INPUT, cost/100)
        self.log(f'Dishwasher will start in {time_difference.total_seconds():.0f} seconds ({start_time}) \nCost: {cost}')

    def is_dishwasher_ready(self):
        remote_start = self.get_state(self.SENSOR_REMOTE_START)
        sensor_ready = self.get_state(self.SENSOR_READY)
        door_closed = self.get_state(self.SENSOR_DISHWASHER_DOOR)
        connected = self.get_state(self.SENSOR_DISHWASHER_CONNECTED)
        
        if self.ENABLE_LOG:        
            self.log(door_closed)
            self.log(remote_start)
            self.log(sensor_ready)        
            self.log(connected) 
        
        
        if door_closed == "off" and connected == "on" and remote_start == "on" and \
            sensor_ready == "BSH.Common.EnumType.OperationState.Ready":
            self.log("Dishwasher is ready to start.")
            return True
        else:
            self.log("Dishwasher is NOT ready to start.")
            return False
        
    def calculate_start_time(self):
        prices = str(self.get_state("sensor.epex_spot_data_net_price_2", attribute="data"))
        prices = prices.replace("'", '"')        
        if self.ENABLE_LOG:
            self.log(prices)
        
        self.energy.update_prices(load_json_from_string(prices))
        
        # Get today's date and time in UTC
        now_utc = datetime.now(pytz.utc)
         
        # Get tomorrow's date
        tomorrow = now_utc + timedelta(days=1)

        # Set the time to 9 AM UTC on tomorrow's date
        tomorrow_8am_utc = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)

        # Ensure the result is timezone-aware and in UTC
        tomorrow_8am_utc = tomorrow_8am_utc.astimezone(pytz.utc)
        
        
        return self.energy.find_cheapest_period(end_time=tomorrow_8am_utc) 
        
        

    def terminate(self):
        self.log("Terminating") 
    
    def disch_washer_ready_cb(self, entity, attribute, old, new, kwargs):
        self.log("Callback")
        
        if self.is_dishwasher_ready():
             self.program_dishwasher()
        

    def start_dishwasher(self,  cb_args):
        self.log("Starting dishwasher")
        self.call_service("button.press", entity=self.BUTTON_START)





        