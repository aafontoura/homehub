import pandas as pd
import json, pytz
import time
from datetime import datetime

def load_csv(csv_file):
    df = pd.read_csv(csv_file)
    df['Time'] = pd.to_datetime(df['Time'])
 
    # If the times are known to be in a specific timezone, localize to that timezone
    # df['Time'] = df['Time'].dt.tz_localize('UTC')  # Replace 'UTC' with the appropriate timezone
    return df


def load_json_from_string( json_data):
    data = json.loads(json_data)
    df = pd.DataFrame(data)
    df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
    return df

def load_json_from_file( json_file):
    with open(json_file, 'r') as file:
        data = json.load(file)
    df = pd.DataFrame(data)
    df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
    return df

class EnergyPriceAnalyzer:
    def __init__(self, appliance_profile, prices):
        self._set_appliance_profile(appliance_profile)
        self.update_prices(prices)
        # self._resample_data()

    def _set_prices(self, prices):
        self.prices = prices
        
        # Make current_time timezone-naive
        # Make current_time timezone-aware, preferably in UTC
        current_time = datetime.now(pytz.utc).replace(second=0, microsecond=0)
        self.prices = self.prices[self.prices['start_time'] >= current_time]


    def update_prices(self, prices):
        self._set_prices(prices)

        if self.appliance_profile is not None:
            # Resample price data
            self.price_resampled = self.prices.set_index('start_time').resample(self.min_interval).ffill()

            # Ensure that the index is a single-level DatetimeIndex
            if isinstance(self.price_resampled.index, pd.MultiIndex):
                self.price_resampled.index = self.price_resampled.index.get_level_values(0)

            # Now safely localize the index to None
            # self.price_resampled.index = self.price_resampled.index.tz_localize('UTC')

    def _set_appliance_profile(self, appliance_profile):
        self.appliance_profile = appliance_profile      

        # Find the smallest time interval in the appliance profile
        self.min_interval = self.appliance_profile['Time'].diff().min()

        # Resample appliance data
        self.energy_resampled = self.appliance_profile.set_index('Time').resample(self.min_interval).mean().ffill()
        self.energy_resampled.index = self.energy_resampled.index.tz_localize('UTC')


    # def calculate_cost(self, start_time):

    

    def calculate_cost(self, shift_min):
        shifted_profile = self.energy_resampled.copy()
        shifted_profile.index += pd.Timedelta(minutes=shift_min)
        merged = pd.merge_asof(shifted_profile, self.price_resampled, left_index=True, right_index=True, direction='nearest')
        merged['cost'] = merged['Power'] / 1000 * merged['price_ct_per_kwh'] / (3600 / int(self.min_interval.total_seconds()))
        return merged['cost'].sum()

    def find_cheapest_period(self):
        # Check if the price_resampled DataFrame is empty
        print (self.price_resampled)
        if self.price_resampled.empty:
            print("No future price data available.")
            return None, None

        min_cost = float('inf')
        cheapest_start = None

        # Ensure that there are at least two data points to calculate the total minutes
        if len(self.price_resampled.index) < 2:
            print("Insufficient data for analysis.")
            return None, None

        total_minutes = int((self.price_resampled.index[-1] - self.price_resampled.index[0]).total_seconds() / 60)
        for start_minute in range(total_minutes):
            total_cost = self.calculate_cost(start_minute)
            if total_cost < min_cost:
                min_cost = total_cost
                cheapest_start = start_minute

        if cheapest_start is not None:
            cheapest_start_time = self.price_resampled.index[0] + pd.Timedelta(minutes=cheapest_start)
            return cheapest_start_time, min_cost

        return None, None


if __name__ == '__main__':
    # Usage example
    start_load = time.time()
    appliance_profile = load_csv('profile.csv')
    prices = load_json_from_file('prices.json')
    print(f'Loading files time: {time.time() - start_load}')

    start_class = time.time()
    analyzer = EnergyPriceAnalyzer(appliance_profile, prices)
    print(f'class init time: {time.time() - start_class}')

    start_calculation = time.time()
    start_time, min_cost = analyzer.find_cheapest_period()
    print(f'calculation time: {time.time() - start_calculation}')

    if start_time:
        print(f"The cheapest start time is {start_time} with a cost of {min_cost:.2f}")
    else:
        print("No cheapest period found.")
