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
    SENSOR_OPERSTATE = "sensor.011040519583042054_bsh_common_status_operationstate"
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
    
    def initialize(self):
        
        self.program_timer = None
        self.start_time = None
        
        self.log(self.get_state(self.HELPER_SAVINGS))
        
        prices = str(self.get_state("sensor.epex_spot_data_net_price_2", attribute="data"))
        prices = prices.replace("'", '"')
        self.energy = EnergyPriceAnalyzer(load_csv(get_data_file_path("data/dishwasher_eco_profile.csv")),load_json_from_string(prices))
        
        if self.is_dishwasher_ready():
             self.program_dishwasher()            
        

        self.listen_state(self.dishwasher_ready_cb, self.SENSOR_DISHWASHER_DOOR, new="off")
        self.listen_state(self.dishwasher_finished_cb, self.SENSOR_OPERSTATE, new=self.OPERSTATE_FINISHED)
        
    
    def dishwasher_finished_cb(self, entity, attribute, old, new, kwargs):
        self.log("Program finished")
        savings = self.get_state(self.HELPER_SAVINGS)
        cost = self.get_state(self.HELPER_COST_INPUT)
        self.set_value(self.HELPER_SAVINGS, cost/100 + savings)

    def program_dishwasher(self):
        self.log("Programming...")
        
        start_time, self.cost, self.max_cost = self.calculate_start_time()
        self.start_dishwasher(start_time)        
        
        self.set_value(self.HELPER_COST_INPUT, round(self.cost/100, ndigits=4))
        
        self.log(f'Dishwasher will start at ({start_time}) \nCost: {self.cost}')

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
            self.log(f'Dishwasher is NOT ready to start: {self.get_state(self.SENSOR_OPERSTATE)}')
            if self.get_state(self.SENSOR_OPERSTATE) == "BSH.Common.EnumType.OperationState.DelayedStart":                               
                self.log(f'Program will start in {self.get_state("sensor.011040519583042054_bsh_common_option_startinrelative")}')
                
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
        
        start_time = now_utc.replace(hour=21, minute=0, second=0).astimezone(pytz.utc)
    
        if now_utc > start_time:
            start_time = None
        
        
        return self.energy.find_cheapest_period(start_time=start_time, end_time=tomorrow_8am_utc) 
        
        

    def terminate(self):
        self.log("Terminating") 
    
    def dishwasher_ready_cb(self, entity, attribute, old, new, kwargs):
        self.log("Callback")
        
        if self.is_dishwasher_ready():
             self.program_dishwasher()
            
        

    def start_dishwasher(self,  start_time):
        self.log("Starting dishwasher")
        
        current_time = datetime.now(pytz.utc)
        time_difference = start_time - current_time
        if self.ENABLE_LOG:
            self.log(f'start_dishwasher({start_time}) -> Diff: {time_difference}')
            self.log(f'Starting program: "key":"BSH.Common.Option.StartInRelative","value":{int(time_difference.total_seconds())}]')
        self.log(time_difference.total_seconds())
        self.call_service("home_connect_alt/start_program", device_id=self.DEVICE_ID,
                          program_key="Dishcare.Dishwasher.Program.Eco50",
                            options=[{"key":"BSH.Common.Option.StartInRelative","value":int(time_difference.total_seconds())}]
                          )
        
        
        





        