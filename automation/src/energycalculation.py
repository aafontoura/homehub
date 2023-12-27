import pandas as pd
import json, pytz
import time
from datetime import datetime, timedelta
# from icecream import ic

def load_csv(csv_file):
    """
    Load a CSV file into a DataFrame and parse the 'Time' column to datetime objects.

    Parameters:
    csv_file (str): Path to the CSV file.

    Returns:
    pd.DataFrame: DataFrame with the 'Time' column as datetime objects.
    """
    df = pd.read_csv(csv_file)
    df['Time'] = pd.to_datetime(df['Time'])
 
    # If the times are known to be in a specific timezone, localize to that timezone
    # df['Time'] = df['Time'].dt.tz_localize('UTC')  # Replace 'UTC' with the appropriate timezone
    return df


def load_json_from_string( json_data):
    """
    Load data from a JSON string into a DataFrame and parse the 'start_time' to UTC datetime objects.

    Parameters:
    json_data (str): JSON data in string format.

    Returns:
    pd.DataFrame: DataFrame with 'start_time' as UTC datetime objects.
    """
    data = json.loads(json_data)
    df = pd.DataFrame(data)
    df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
    return df

def load_json_from_file( json_file):
    """
    Load data from a JSON file into a DataFrame and parse the 'start_time' to UTC datetime objects.

    Parameters:
    json_file (str): Path to the JSON file.

    Returns:
    pd.DataFrame: DataFrame with 'start_time' as UTC datetime objects.
    """
    with open(json_file, 'r') as file:
        data = json.load(file)
    df = pd.DataFrame(data)
    df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
    return df

class EnergyPriceAnalyzer:
    """
    A class for analyzing energy prices and appliance profiles to find the cheapest operation period.
    """
    def __init__(self, appliance_profile, prices):
        """
        Initialize the EnergyPriceAnalyzer with appliance profile and price data.

        Parameters:
        appliance_profile (pd.DataFrame): Appliance usage profile DataFrame.
        prices (pd.DataFrame): Energy price data DataFrame.
        """
        self._set_appliance_profile(appliance_profile)
        self.update_prices(prices)
        # self._resample_data()

    def _set_prices(self, prices):
        """
        Set the price data and filter prices from the current time onwards.

        Parameters:
        prices (pd.DataFrame): Energy price data DataFrame.
        """
        self.prices = prices
        
        # Make current_time timezone-naive
        # Make current_time timezone-aware, preferably in UTC
        current_time = datetime.now(pytz.utc).replace(second=0, microsecond=0)
        self.prices = self.prices[self.prices['start_time'] >= current_time]


    def update_prices(self, prices):
        """
        Update the price data and resample it according to the appliance profile's minimum interval.

        Parameters:
        prices (pd.DataFrame): New energy price data DataFrame.
        """
        self._set_prices(prices)

        if self.appliance_profile is not None:
            # Resample price data
            self.price_resampled = self.prices.set_index('start_time').resample(self.min_interval).ffill()

            # Ensure that the index is a single-level DatetimeIndex
            if isinstance(self.price_resampled.index, pd.MultiIndex):
                self.price_resampled.index = self.price_resampled.index.get_level_values(0)

    def _set_appliance_profile(self, appliance_profile):
        """
        Set the appliance profile data and calculate its minimum interval and total duration.

        Parameters:
        appliance_profile (pd.DataFrame): Appliance usage profile DataFrame.
        """
        self.appliance_profile = appliance_profile      

        # Find the smallest time interval in the appliance profile
        self.min_interval = self.appliance_profile['Time'].diff().min()

        # Resample appliance data
        self.energy_resampled = self.appliance_profile.set_index('Time').resample(self.min_interval).mean().ffill()
        self.energy_resampled.index = self.energy_resampled.index.tz_localize('UTC')

        self.profile_duration = int((self.energy_resampled.index[-1] - self.energy_resampled.index[0]).total_seconds() / 60)

 
    def calculate_cost(self, shift_min):
        """
        Calculate the total cost for running the appliance, shifted by a certain number of minutes.

        Parameters:
        shift_min (int): Number of minutes to shift the appliance profile.

        Returns:
        float: Total cost of running the appliance.
        """
        shifted_profile = self.energy_resampled.copy()
        shifted_profile.index += pd.Timedelta(minutes=shift_min)
        aligned_profile, aligned_prices = shifted_profile.align(self.price_resampled, join='inner', axis=0)
        result = aligned_profile['Power'] / 1000 * aligned_prices['price_ct_per_kwh'] / (3600 / int(self.min_interval.total_seconds()))
        return result.sum()

    def find_cheapest_period(self, start_time = None, end_time = None):
        """
        Find the cheapest period to run the appliance within a specified timeframe.

        Parameters:
        end_time (datetime, optional): The end time to consider for finding the cheapest period.

        Returns:
        tuple: Start time of the cheapest period and the corresponding cost.
        """
        
        # Check if the price_resampled DataFrame is empty
        # print (self.price_resampled)
        if self.price_resampled.empty:
            print("No future price data available.")
            return None, None, None
        
        # Calculate the time difference in seconds (or another appropriate unit)
        time_diff_seconds = int((self.price_resampled.index[0] - self.energy_resampled.index[0]).total_seconds())

        # Shift the energy_resampled DataFrame by the calculated number of seconds
        self.energy_resampled = self.energy_resampled.shift(periods=time_diff_seconds, freq='S')

        # The above code is assigning the value of `self.price_resampled` to the variable `prices`.
        prices = self.price_resampled
        # keep oly the prices within the time frame that the machine should run 
        if end_time is not None:
            prices = prices[prices.index < pd.to_datetime(end_time)]
            
        if start_time is not None:
            prices = prices[prices.index > pd.to_datetime(start_time)]
      


        min_cost = float('inf')
        max_cost = float('-inf')
        cheapest_start = None

        # Ensure that there are enough data points to calculate 
        total_minutes = int((prices.index[-1] - prices.index[0]).total_seconds() / 60)
        total_minutes -= self.profile_duration
        if total_minutes < 0:
            return None, None, None
        
        for start_minute in range(total_minutes):
            total_cost = self.calculate_cost(start_minute)
            # ic(f'{prices.index[0]+timedelta(minutes=start_minute)}: {total_cost}')

            if total_cost < min_cost:
                min_cost = total_cost
                cheapest_start = start_minute
                
            if total_cost > max_cost:
                max_cost = total_cost

        if cheapest_start is not None:
            cheapest_start_time = prices.index[0] + pd.Timedelta(minutes=cheapest_start)
            return cheapest_start_time, min_cost, max_cost

        return None, None, None


string_prices = '[{"start_time": "2023-12-26T23:00:00+00:00", "end_time": "2023-12-27T00:00:00+00:00", "price_ct_per_kwh": 28.303109999999997}, {"start_time": "2023-12-27T00:00:00+00:00", "end_time": "2023-12-27T01:00:00+00:00", "price_ct_per_kwh": 27.0072}, {"start_time": "2023-12-27T01:00:00+00:00", "end_time": "2023-12-27T02:00:00+00:00", "price_ct_per_kwh": 24.39723}, {"start_time": "2023-12-27T02:00:00+00:00", "end_time": "2023-12-27T03:00:00+00:00", "price_ct_per_kwh": 23.7039}, {"start_time": "2023-12-27T03:00:00+00:00", "end_time": "2023-12-27T04:00:00+00:00", "price_ct_per_kwh": 23.477629999999998}, {"start_time": "2023-12-27T04:00:00+00:00", "end_time": "2023-12-27T05:00:00+00:00", "price_ct_per_kwh": 24.16491}, {"start_time": "2023-12-27T05:00:00+00:00", "end_time": "2023-12-27T06:00:00+00:00", "price_ct_per_kwh": 25.296259999999997}, {"start_time": "2023-12-27T06:00:00+00:00", "end_time": "2023-12-27T07:00:00+00:00", "price_ct_per_kwh": 26.81965}, {"start_time": "2023-12-27T07:00:00+00:00", "end_time": "2023-12-27T08:00:00+00:00", "price_ct_per_kwh": 27.43796}, {"start_time": "2023-12-27T08:00:00+00:00", "end_time": "2023-12-27T09:00:00+00:00", "price_ct_per_kwh": 27.16934}, {"start_time": "2023-12-27T09:00:00+00:00", "end_time": "2023-12-27T10:00:00+00:00", "price_ct_per_kwh": 26.485689999999998}, {"start_time": "2023-12-27T10:00:00+00:00", "end_time": "2023-12-27T11:00:00+00:00", "price_ct_per_kwh": 26.46391}, {"start_time": "2023-12-27T11:00:00+00:00", "end_time": "2023-12-27T12:00:00+00:00", "price_ct_per_kwh": 26.35259}, {"start_time": "2023-12-27T12:00:00+00:00", "end_time": "2023-12-27T13:00:00+00:00", "price_ct_per_kwh": 26.136}, {"start_time": "2023-12-27T13:00:00+00:00", "end_time": "2023-12-27T14:00:00+00:00", "price_ct_per_kwh": 26.3417}, {"start_time": "2023-12-27T14:00:00+00:00", "end_time": "2023-12-27T15:00:00+00:00", "price_ct_per_kwh": 27.104}, {"start_time": "2023-12-27T15:00:00+00:00", "end_time": "2023-12-27T16:00:00+00:00", "price_ct_per_kwh": 27.00236}, {"start_time": "2023-12-27T16:00:00+00:00", "end_time": "2023-12-27T17:00:00+00:00", "price_ct_per_kwh": 27.149980000000003}, {"start_time": "2023-12-27T17:00:00+00:00", "end_time": "2023-12-27T18:00:00+00:00", "price_ct_per_kwh": 26.42398}, {"start_time": "2023-12-27T18:00:00+00:00", "end_time": "2023-12-27T19:00:00+00:00", "price_ct_per_kwh": 25.2769}, {"start_time": "2023-12-27T19:00:00+00:00", "end_time": "2023-12-27T20:00:00+00:00", "price_ct_per_kwh": 24.04633}, {"start_time": "2023-12-27T20:00:00+00:00", "end_time": "2023-12-27T21:00:00+00:00", "price_ct_per_kwh": 20.41754}, {"start_time": "2023-12-27T21:00:00+00:00", "end_time": "2023-12-27T22:00:00+00:00", "price_ct_per_kwh": 19.47979}, {"start_time": "2023-12-27T22:00:00+00:00", "end_time": "2023-12-27T23:00:00+00:00", "price_ct_per_kwh": 17.4482}, {"start_time": "2023-12-27T23:00:00+00:00", "end_time": "2023-12-28T00:00:00+00:00", "price_ct_per_kwh": 17.42158}, {"start_time": "2023-12-28T00:00:00+00:00", "end_time": "2023-12-28T01:00:00+00:00", "price_ct_per_kwh": 17.329620000000002}, {"start_time": "2023-12-28T01:00:00+00:00", "end_time": "2023-12-28T02:00:00+00:00", "price_ct_per_kwh": 17.25097}, {"start_time": "2023-12-28T02:00:00+00:00", "end_time": "2023-12-28T03:00:00+00:00", "price_ct_per_kwh": 17.25581}, {"start_time": "2023-12-28T03:00:00+00:00", "end_time": "2023-12-28T04:00:00+00:00", "price_ct_per_kwh": 17.189259999999997}, {"start_time": "2023-12-28T04:00:00+00:00", "end_time": "2023-12-28T05:00:00+00:00", "price_ct_per_kwh": 17.29816}, {"start_time": "2023-12-28T05:00:00+00:00", "end_time": "2023-12-28T06:00:00+00:00", "price_ct_per_kwh": 17.339299999999998}, {"start_time": "2023-12-28T06:00:00+00:00", "end_time": "2023-12-28T07:00:00+00:00", "price_ct_per_kwh": 19.367259999999998}, {"start_time": "2023-12-28T07:00:00+00:00", "end_time": "2023-12-28T08:00:00+00:00", "price_ct_per_kwh": 22.0462}, {"start_time": "2023-12-28T08:00:00+00:00", "end_time": "2023-12-28T09:00:00+00:00", "price_ct_per_kwh": 22.11759}, {"start_time": "2023-12-28T09:00:00+00:00", "end_time": "2023-12-28T10:00:00+00:00", "price_ct_per_kwh": 21.005599999999998}, {"start_time": "2023-12-28T10:00:00+00:00", "end_time": "2023-12-28T11:00:00+00:00", "price_ct_per_kwh": 21.64569}, {"start_time": "2023-12-28T11:00:00+00:00", "end_time": "2023-12-28T12:00:00+00:00", "price_ct_per_kwh": 18.833650000000002}, {"start_time": "2023-12-28T12:00:00+00:00", "end_time": "2023-12-28T13:00:00+00:00", "price_ct_per_kwh": 18.8034}, {"start_time": "2023-12-28T13:00:00+00:00", "end_time": "2023-12-28T14:00:00+00:00", "price_ct_per_kwh": 20.614769999999996}, {"start_time": "2023-12-28T14:00:00+00:00", "end_time": "2023-12-28T15:00:00+00:00", "price_ct_per_kwh": 23.561120000000003}, {"start_time": "2023-12-28T15:00:00+00:00", "end_time": "2023-12-28T16:00:00+00:00", "price_ct_per_kwh": 22.36927}, {"start_time": "2023-12-28T16:00:00+00:00", "end_time": "2023-12-28T17:00:00+00:00", "price_ct_per_kwh": 26.910400000000003}, {"start_time": "2023-12-28T17:00:00+00:00", "end_time": "2023-12-28T18:00:00+00:00", "price_ct_per_kwh": 26.910400000000003}, {"start_time": "2023-12-28T18:00:00+00:00", "end_time": "2023-12-28T19:00:00+00:00", "price_ct_per_kwh": 25.291420000000002}, {"start_time": "2023-12-28T19:00:00+00:00", "end_time": "2023-12-28T20:00:00+00:00", "price_ct_per_kwh": 25.2769}, {"start_time": "2023-12-28T20:00:00+00:00", "end_time": "2023-12-28T21:00:00+00:00", "price_ct_per_kwh": 23.958}, {"start_time": "2023-12-28T21:00:00+00:00", "end_time": "2023-12-28T22:00:00+00:00", "price_ct_per_kwh": 22.264}, {"start_time": "2023-12-28T22:00:00+00:00", "end_time": "2023-12-28T23:00:00+00:00", "price_ct_per_kwh": 17.666}]'

if __name__ == '__main__':
    # Usage example
    start_load = time.time()
    appliance_profile = load_csv('tests/data/test_profile.csv')
    # prices = load_json_from_file('prices.json')
    prices = load_json_from_string(string_prices)
    print(f'Loading files time: {time.time() - start_load}')

    start_class = time.time()
    analyzer = EnergyPriceAnalyzer(appliance_profile, prices)
    print(f'class init time: {time.time() - start_class}')

    # Get today's date and time in UTC
    now_utc = datetime.now(pytz.utc)

    # Get tomorrow's date
    tomorrow = now_utc + timedelta(days=1)

    # Set the time to 9 AM UTC on tomorrow's date
    tomorrow_9am_utc = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    start_time = now_utc.replace(hour=21, minute=0, second=0).astimezone(pytz.utc)
    
    if now_utc > start_time:
        start_time = None

    # Ensure the result is timezone-aware and in UTC
    tomorrow_9am_utc = tomorrow_9am_utc.astimezone(pytz.utc)

    start_calculation = time.time()
    start_time, min_cost, max_cost = analyzer.find_cheapest_period(start_time=start_time, end_time=tomorrow_9am_utc)
    print(f'calculation time: {time.time() - start_calculation}')

    if start_time:
        print(f"The cheapest start time is {start_time} with a cost of {min_cost:.2f}. Max: {max_cost:.2f}")
    else:
        print("No cheapest period found.")
