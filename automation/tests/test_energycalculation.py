import pytest
from src.energycalculation import EnergyPriceAnalyzer, load_csv, load_json_from_file
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch
import pytz
import os

def get_data_file_path(relative_path):
    # Get the directory of the current test file
    dir_name = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path
    return os.path.join(dir_name, relative_path)

# Sample Data
SAMPLE_CSV_DATA = "data/test_profile.csv"
SAMPLE_JSON_DATA = "data/test_prices.json"

# Mock current time
MOCKED_CURRENT_TIME = datetime(2023, 12, 19, 1, 0, 0, tzinfo=pytz.utc)

test_data = [
    {"Current Time": datetime(2023, 12, 19, 1, 0, 0, tzinfo=pytz.utc), 
     "Start Time": datetime(2023, 12, 19, 3, 0, 0, tzinfo=pytz.utc), 
     "Min Cost": 34.62},    
    
    # current time in the future
    {"Current Time": datetime(2023, 12, 21, 1, 0, 0, tzinfo=pytz.utc), 
     "Start Time": None, 
     "Min Cost": None},

    # current time in the past
    # {"Current Time": datetime(2023, 11, 21, 1, 0, 0, tzinfo=pytz.utc), 
    #  "Start Time": None, 
    #  "Min Cost": None},

]

# 2023-12-19T01:00:00+00:00

# Fixtures for Sample Data
@pytest.fixture
def sample_appliance_profile():
    return load_csv(get_data_file_path(SAMPLE_CSV_DATA))

@pytest.fixture
def sample_prices():
    return load_json_from_file(get_data_file_path(SAMPLE_JSON_DATA))

# Test for Data Loading
def test_load_csv(sample_appliance_profile):
    df = sample_appliance_profile
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_load_json_from_file(sample_prices):
    df = sample_prices
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

# Test for Price Update
# def test_update_prices(sample_appliance_profile, sample_prices):
#     analyzer = EnergyPriceAnalyzer(sample_appliance_profile, sample_prices)
#     analyzer.update_prices(sample_prices)  # Update with new price data
#     assert not analyzer.price_resampled.empty

# Test for Cost Calculation
def test_calculate_cost(sample_appliance_profile, sample_prices):
    analyzer = EnergyPriceAnalyzer(sample_appliance_profile)
    analyzer.update_prices(sample_prices)
    cost = analyzer.calculate_cost(30)  # Example shift in minutes
    assert cost >= 0

# Test for Finding Cheapest Period
def test_find_cheapest_period(sample_appliance_profile, sample_prices):
    analyzer = EnergyPriceAnalyzer(sample_appliance_profile)
    analyzer.update_prices(sample_prices)
    start_time, min_cost, max_cost = analyzer.find_cheapest_period()
    assert isinstance(start_time, datetime) or start_time is None
    assert isinstance(min_cost, float) or min_cost is None


# Test for Price Update with Mocked Current Time
@patch('src.energycalculation.datetime')
def test_update_prices(mock_datetime, sample_appliance_profile, sample_prices):
    mock_datetime.now.return_value = MOCKED_CURRENT_TIME
    analyzer = EnergyPriceAnalyzer(sample_appliance_profile)
    analyzer.update_prices(sample_prices)  # Update with new price data
    assert not analyzer.price_resampled.empty


# Test for Price Update with Mocked Current Time
@patch('src.energycalculation.datetime')
def test_calculation(mock_datetime, sample_appliance_profile, sample_prices):

    # mock_datetime.now.return_value = MOCKED_CURRENT_TIME
    # analyzer = EnergyPriceAnalyzer(sample_appliance_profile, sample_prices)
    # start_time, min_cost = analyzer.find_cheapest_period()
    # assert start_time == datetime(2023, 12, 19, 3, 27, 0, tzinfo=pytz.utc)
    # assert round(min_cost, 2) == 34.62

    mock_datetime.now.return_value = test_data[0]['Current Time']
    analyzer = EnergyPriceAnalyzer(sample_appliance_profile)
    for data in test_data:
        mock_datetime.now.return_value = data['Current Time']
        analyzer.update_prices(sample_prices)
        start_time, min_cost, max_cost = analyzer.find_cheapest_period()
        assert start_time == data['Start Time']
        test_min_cost = None if min_cost is None else round(min_cost, 2)
        assert test_min_cost == data['Min Cost']
    