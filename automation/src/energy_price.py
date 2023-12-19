import pandas as pd
import json
import pytz
from datetime import datetime

def load_csv(csv_file):
    df = pd.read_csv(csv_file)
    df['Time'] = pd.to_datetime(df['Time'])
    df['Time'] = df['Time'].dt.tz_localize(None)
    return df

def load_json_from_string( json_data):
    data = json.loads(json_data)
    df = pd.DataFrame(data)
    df['start_time'] = pd.to_datetime(df['start_time'])
    return df

def load_json_from_file( json_file):
    with open(json_file, 'r') as file:
        data = json.load(file)
    df = pd.DataFrame(data)
    df['start_time'] = pd.to_datetime(df['start_time'])
    return df

class EnergyPriceAnalyzer:
    def __init__(self, appliance_profile, prices):
        self.appliance_profile = appliance_profile
        self.prices = prices
        self.prepare_data()

    def prepare_data(self):
        # Convert prices['start_time'] to timezone-naive
        self.prices['start_time'] = self.prices['start_time'].dt.tz_localize(None)

        # Make current_time timezone-naive
        current_time = datetime.now().replace(second=0, microsecond=0)
        print(self.prices)
        # self.prices = self.prices[self.prices['start_time'] >= current_time] # TODO uncomment

        # Find the smallest time interval in the appliance profile
        self.min_interval = self.appliance_profile['Time'].diff().min()

        # Resample appliance data
        self.energy_resampled = self.appliance_profile.set_index('Time').resample(self.min_interval).mean().ffill()

        print(self.prices)
        # Resample price data
        self.price_resampled = self.prices.set_index('start_time').resample(self.min_interval).ffill()

        # Ensure that the index is a single-level DatetimeIndex
        if isinstance(self.price_resampled.index, pd.MultiIndex):
            self.price_resampled.index = self.price_resampled.index.get_level_values(0)

        # Now safely localize the index to None
        self.price_resampled.index = self.price_resampled.index.tz_localize(None)

        print(self.price_resampled)

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


# Usage example
appliance_profile = load_csv('profile.csv')
prices = load_json_from_file('prices.json')

analyzer = EnergyPriceAnalyzer(appliance_profile, prices)
start_time, min_cost = analyzer.find_cheapest_period()

if start_time:
    print(f"The cheapest start time is {start_time} with a cost of {min_cost:.2f}")
else:
    print("No cheapest period found.")
