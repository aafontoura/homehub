import hassapi as hass
import os, logging
from datetime import datetime, timedelta
import pytz

from src.energycalculation import EnergyPriceAnalyzer, load_csv, load_json_from_string


def get_data_file_path(relative_path):
    """
    Gets the absolute path of a file given its relative path.
    This is used to locate data files needed by the application.

    Parameters:
    relative_path (str): The relative path to the file.

    Returns:
    str: The absolute path to the file.
    """
    # Retrieves the absolute file path of the given relative path.
    dir_name = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path
    return os.path.join(dir_name, relative_path)


class DishwasherControl(hass.Hass):
    """
    A class to control a dishwasher using Home Assistant APIs.
    This class includes functionality to determine the best time to start the dishwasher
    based on energy prices and the dishwasher's availability.

    Attributes are constants representing various Home Assistant entity IDs.
    """
    
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

    def initialize(self):
        """
        Initialize the DishwasherControl class, setting up timers and state variables.
        Also, it fetches initial energy prices and checks if the dishwasher is ready.
        """
        
        self.program_timer = None
        self.start_time = None

        # Log the current state of the savings helper.
        self.log(self.get_state(self.HELPER_SAVINGS))

        
        self.energy = EnergyPriceAnalyzer(
            load_csv(get_data_file_path("data/dishwasher_eco_profile.csv")),
        )

        # Check if the dishwasher is ready and program it if so.
        if self.is_dishwasher_ready():
            self.program_dishwasher()

        # Set up listeners for dishwasher state changes.
        self.listen_state(
            self.dishwasher_ready_cb, self.SENSOR_DISHWASHER_DOOR, new="off"
        )
        self.listen_state(
            self.dishwasher_finished_cb,
            self.SENSOR_OPERSTATE,
            new=self.OPERSTATE_FINISHED,
        )

    def dishwasher_finished_cb(self, entity, attribute, old, new, kwargs):
        """
        Callback function that gets triggered when the dishwasher finishes its cycle.
        It calculates and logs the cost savings achieved by running the dishwasher.

        Parameters:
        entity, attribute, old, new, kwargs: Parameters provided by the callback mechanism.
        """
        
        
        self.log("Program finished")
        savings = float(self.get_state(self.HELPER_SAVINGS))
        cost = float(self.get_state(self.HELPER_COST_INPUT))
        self.set_value(self.HELPER_SAVINGS, cost / 100 + savings)

    def program_dishwasher(self):
        """
        Determines the optimal start time for the dishwasher based on energy prices and
        programs the dishwasher to start at that time.
        """
        
        self.log("Programming...")

        start_time, self.cost, self.max_cost = self.calculate_start_time()
        if self.ENABLE_LOG:
            self.log(f"{start_time}, {self.cost}, {self.max_cost}")
        self.start_dishwasher(start_time)

        self.set_value(self.HELPER_COST_INPUT, round(self.cost / 100, ndigits=4))

        self.log(f"Dishwasher will start at ({start_time}) \nCost: {self.cost}")

    def is_dishwasher_ready(self):
        """
        Checks if the dishwasher is ready to start a new cycle. It checks various sensors like
        door state, connectivity, etc., to ensure the dishwasher can be started remotely.
        """
        remote_start = self.get_state(self.SENSOR_REMOTE_START)
        sensor_ready = self.get_state(self.SENSOR_READY)
        door_closed = self.get_state(self.SENSOR_DISHWASHER_DOOR)
        connected = self.get_state(self.SENSOR_DISHWASHER_CONNECTED)

        if self.ENABLE_LOG:
            self.log(door_closed)
            self.log(remote_start)
            self.log(sensor_ready)
            self.log(connected)

        if (
            door_closed == "off"
            and connected == "on"
            and remote_start == "on"
            and sensor_ready == "BSH.Common.EnumType.OperationState.Ready"
        ):
            self.log("Dishwasher is ready to start.")
            return True
        else:
            self.log(
                f"Dishwasher is NOT ready to start: {self.get_state(self.SENSOR_OPERSTATE)}"
            )
            if (
                self.get_state(self.SENSOR_OPERSTATE)
                == "BSH.Common.EnumType.OperationState.DelayedStart"
            ):
                self.log(
                    f'Program will start in {self.get_state("sensor.011040519583042054_bsh_common_option_startinrelative")}'
                )
            return False

    def calculate_start_time(self):
        """
        Calculates the best start time for the dishwasher based on energy price data.
        This method considers the cheapest energy period for running the dishwasher.
        """
        
        prices = str(
            self.get_state("sensor.epex_spot_data_net_price_2", attribute="data")
        )
        
        
        prices = prices.replace("'", '"')
        if self.ENABLE_LOG:
            self.log(prices)

        json_prices = load_json_from_string(prices)        

        # Get today's date and time in UTC
        now_utc = datetime.now(pytz.utc)

        # Get tomorrow's date
        tomorrow = now_utc + timedelta(days=1)
        
        today_12pm_utc = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        today_8am_utc = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)
        
        if now_utc < today_12pm_utc and now_utc > today_8am_utc:
            self.log(f'{now_utc} is too early to get prices for next day')
            

        # Set the time to 9 AM UTC on tomorrow's date
        tomorrow_8am_utc = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)

        # Ensure the result is timezone-aware and in UTC
        tomorrow_8am_utc = tomorrow_8am_utc.astimezone(pytz.utc)

        start_time = now_utc.replace(hour=21, minute=0, second=0).astimezone(pytz.utc)

        if now_utc > start_time:
            start_time = None

        if self.ENABLE_LOG:
            self.log(
                f"self.energy.find_cheapest_period(start_time={start_time}, end_time={tomorrow_8am_utc}) "
            )
            
        self.energy.update_prices()

        return self.energy.find_cheapest_period(
            start_time=start_time, end_time=tomorrow_8am_utc
        )

    def terminate(self):
        """
        Method to clean up or close resources when the DishwasherControl instance is terminated.
        """
        self.log("Terminating")

    def dishwasher_ready_cb(self, entity, attribute, old, new, kwargs):
        """
        Callback function that gets triggered when the dishwasher becomes ready.
        If the dishwasher is ready, it proceeds to program it.

        Parameters:
        entity, attribute, old, new, kwargs: Parameters provided by the callback mechanism.
        """
        
        self.log("Callback")

        if self.is_dishwasher_ready():
            self.program_dishwasher()

    def start_dishwasher(self, start_time):
        """
        Starts the dishwasher program at the calculated optimal time.
        It calculates the time difference from now until the start time and
        schedules the dishwasher accordingly.

        Parameters:
        start_time (datetime): The calculated optimal start time for the dishwasher.
        """
        
        self.log("Starting dishwasher")

        current_time = datetime.now(pytz.utc)
        time_difference = start_time - current_time
        if self.ENABLE_LOG:
            self.log(f"start_dishwasher({start_time}) -> Diff: {time_difference}")
            self.log(
                f'Starting program: "key":"BSH.Common.Option.StartInRelative","value":{int(time_difference.total_seconds())}]'
            )
        self.log(time_difference.total_seconds())
        self.call_service(
            "home_connect_alt/start_program",
            device_id=self.DEVICE_ID,
            program_key="Dishcare.Dishwasher.Program.Eco50",
            options=[
                {
                    "key": "BSH.Common.Option.StartInRelative",
                    "value": int(time_difference.total_seconds()),
                }
            ],
        )
