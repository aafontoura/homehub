import os
import instaloader
import argparse
import time
import logging
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
from dotenv import load_dotenv
from instaloader.exceptions import ProfileNotExistsException, ConnectionException

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to log data into InfluxDB
def log_to_influxdb(username, followers, followees, posts, influx_host, influx_port, influx_db):
    client = None  # Initialize client variable
    try:
        # Retrieve the token from environment variables
        influx_token = os.getenv("INFLUXDB_TOKEN")
        influx_org = os.getenv("INFLUXDB_ORG")
        
        if not influx_token or not influx_org:
            raise ValueError("InfluxDB token or organization not set in the .env file")

        # Connect to InfluxDB using the token (InfluxDB 2.x client)
        client = InfluxDBClient(url=f"http://{influx_host}:{influx_port}", token=influx_token, org=influx_org)

        # Prepare the data to be written to InfluxDB
        write_api = client.write_api(write_options=SYNCHRONOUS)
        point = Point("instagram_profile") \
            .tag("username", username) \
            .field("followers", followers) \
            .field("followees", followees) \
            .field("posts", posts)

        # Write the data to the specified bucket
        write_api.write(bucket=influx_db, org=influx_org, record=point)
        logging.info(f"Logged data for {username}: {followers} followers, {followees} followees, {posts} posts.")
    
    except ApiException as api_error:
        logging.error(f"InfluxDB API error: {api_error}")
    
    except ValueError as ve:
        logging.error(f"Configuration error: {ve}")
        exit()
    
    except Exception as general_error:
        logging.error(f"An unexpected error occurred during InfluxDB operation: {general_error}")
        exit()
    
    finally:
        if client is not None:
            client.close()

# Main function to fetch profile data and log it
def fetch_and_log_instagram_data(account_name, interval, influx_host, influx_port, influx_db):
    # Creating an instance of Instaloader
    bot = instaloader.Instaloader()
    
    while True:
        try:
            # Load the Instagram profile
            profile = instaloader.Profile.from_username(bot.context, account_name)
            
            # Extract the required information
            followers = profile.followers
            followees = profile.followees
            posts = profile.mediacount
            
            # Log the data to InfluxDB
            log_to_influxdb(profile.username, followers, followees, posts, influx_host, influx_port, influx_db)
        
        except ProfileNotExistsException as profile_error:
            logging.error(f"Profile does not exist: {profile_error}")
            break  # Exit the loop since the profile doesn't exist
        
        except ConnectionException as conn_error:
            logging.error(f"Network connection error: {conn_error}")
        
        except Exception as general_error:
            logging.error(f"An unexpected error occurred during data fetching: {general_error}")
        
        # Wait for the specified interval before making the next request
        time.sleep(interval)

# Argument parser for command-line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description="Instagram profile logger to InfluxDB")
    
    # Arguments for Instagram account and interval
    parser.add_argument("account_name", type=str, help="Instagram account name to fetch data from")
    parser.add_argument("interval", type=int, help="Interval in seconds between data fetches")
    
    # Arguments for InfluxDB connection
    parser.add_argument("--influx-host", type=str, default="ubuntuserver", help="InfluxDB host (default: localhost)")
    parser.add_argument("--influx-port", type=int, default=8086, help="InfluxDB port (default: 8086)")
    parser.add_argument("--influx-db", type=str, default="instagram_metrics", help="InfluxDB bucket name (default: instagram_metrics)")
    
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_arguments()

    # Start fetching and logging Instagram data
    fetch_and_log_instagram_data(
        account_name=args.account_name,
        interval=args.interval,
        influx_host=args.influx_host,
        influx_port=args.influx_port,
        influx_db=args.influx_db
    )