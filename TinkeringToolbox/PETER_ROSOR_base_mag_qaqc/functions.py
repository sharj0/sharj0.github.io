# standard libs
import os
import re
from datetime import datetime

# other libs
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

def custom_parse_datetime(date_str, time_str):
    # Determine the separator in the date string
    if '-' in date_str:
        date_format = '%Y-%m-%d'
    else:
        date_format = '%Y/%m/%d'

    # Attempt to parse with microseconds
    try:
        return datetime.strptime(date_str + ' ' + time_str, date_format + ' %H:%M:%S.%f')
    except ValueError:
        # If parsing fails due to the absence of microseconds, try without them
        return datetime.strptime(date_str + ' ' + time_str, date_format + ' %H:%M:%S')


def parse_air_mag_data(log_file_path):
    try:
        data = pd.read_csv(log_file_path)

        if 'UTC_time_stamps' in data.columns and 'Date' in data.columns:
            # Apply the custom parse function to each row
            datetimes = data.apply(lambda row: custom_parse_datetime(row['Date'], row['UTC_time_stamps']), axis=1)
            start_time = datetimes.iloc[0]
            end_time = datetimes.iloc[-1]
            return start_time, end_time, (datetimes.to_numpy(), data['Mag_TMI_nT'].to_numpy())
        else:
            print(f"Required columns not found in the file.")
            return None, None, (None, None)

    except Exception as e:
        print(f"An error occurred: im {log_file_path} -> {e}")
        return None, None, (None, None)

def df_merge_date_time_columns_from_str(gnd_df):
    gnd_df['datetime'] = gnd_df['UTC_date'] + ' ' + gnd_df['UTC_time']
    # convert the new column to datetime type
    gnd_df['datetime'] = pd.to_datetime(gnd_df['datetime'], format='%d-%m-%Y %H:%M:%S.%f')
    #print(gnd_df['datetime'])
    gnd_df['minutes_elapsed'] = (gnd_df['datetime'] - gnd_df['datetime'].iloc[0]).dt.total_seconds() / 60
    return gnd_df

def parse_smartmag_to_df(filepath, sep_tab_or_comma = 'tab'):
    # Read the file into a DataFrame
    if sep_tab_or_comma == 'tab':
        sep = '\t'
    elif sep_tab_or_comma == 'comma':
        sep = ','
    else:
        raise 'unrecognised input for separator, input "tab" or "comma".'
    df = pd.read_csv(filepath, sep=sep, low_memory=False)
    df = df_merge_date_time_columns_from_str(df)
    return df

def process_base_mag_file(filepath, base_mag_ignore_start_end_mins):
    start_time, end_time, mag_data = None, None, (None, None)
    with open(filepath, 'r') as file:
        df = parse_smartmag_to_df(filepath)
        # Calculate the time bounds to exclude the first and last two minutes
        start_time = df['datetime'].iloc[0] + pd.Timedelta(minutes=base_mag_ignore_start_end_mins)
        end_time = df['datetime'].iloc[-1] - pd.Timedelta(minutes=base_mag_ignore_start_end_mins)

        # Filter the DataFrame to exclude the first and last two minutes
        df_filtered = df[(df['datetime'] >= start_time) & (df['datetime'] <= end_time)]

        # Extract the relevant data
        start_time = df_filtered['datetime'].iloc[0]
        end_time = df_filtered['datetime'].iloc[-1]
        mag_data = (df_filtered['datetime'].to_numpy(), df_filtered['Field'].to_numpy())

    return start_time, end_time, mag_data

def process_folder(base_folder,base_mag_ignore_start_end_mins):
    mag_datas = []
    for root, dirs, files in os.walk(base_folder):
        for file in files:
            if file.lower().endswith('.csv'):
                full_path = os.path.join(root, file)
                start_time, end_time, mag_data = parse_air_mag_data(full_path)
                mag_datas.append((start_time, end_time, full_path, True, mag_data)) # true means it is a flight file
            if file.endswith('.txt'):
                full_path = os.path.join(root, file)
                start_time, end_time, mag_data = process_base_mag_file(full_path,base_mag_ignore_start_end_mins)
                mag_datas.append((start_time, end_time, full_path, False, mag_data)) # false means it is a base file
    return mag_datas

def get_time_mask_seconds(times, window):
    # Convert times to seconds since the start
    start_time = times[0]
    times_in_seconds = (times - start_time) / np.timedelta64(1, 's')

    # Initialize a mask with zeros
    mask = np.zeros((len(times_in_seconds), len(times_in_seconds)), dtype=bool)

    # Populate the mask using broadcasting
    diff_matrix = np.abs(times_in_seconds[:, np.newaxis] - times_in_seconds[np.newaxis, :])
    mask[diff_matrix <= window / 2] = True

    return mask


def calculate_differences(sub_sampled_mag, mask_30s):
    # Use broadcasting to apply the mask and filter values within each window
    valid_values = np.where(mask_30s, sub_sampled_mag[np.newaxis, :], np.nan)

    # Calculate the max and min values ignoring NaNs
    max_values = np.nanmax(valid_values, axis=1)
    min_values = np.nanmin(valid_values, axis=1)

    # Compute the difference between max and min values
    differences = max_values - min_values

    return differences

