# standard libs
import os
import re
import sys
from datetime import datetime

# other libs
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import colormaps
import mplcursors
import pandas as pd


flights_folder = r"I:\PORTABLE_SCRIPTS\May 22 (Day 2)"

color_by_file = True
plot_ground_mag_gaps = False

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


def parse_air_mag_time(log_file_path):
    try:
        data = pd.read_csv(log_file_path)

        if 'UTC_time_stamps' in data.columns and 'Date' in data.columns:
            # Apply the custom parse function to each row
            datetimes = data.apply(lambda row: custom_parse_datetime(row['Date'], row['UTC_time_stamps']), axis=1)

            start_time = datetimes.iloc[0]
            end_time = datetimes.iloc[-1]

            return start_time, end_time
        else:
            print(f"Required columns not found in the file.")
            return None, None

    except Exception as e:
        print(f"An error occurred: im {log_file_path} -> {e}")
        return None, None

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

def process_base_mag_file(filepath):
    start_time, end_time = None, None
    with open(filepath, 'r') as file:
        df = parse_smartmag_to_df(filepath)

        # Plotting gaps in ground mag
        if plot_ground_mag_gaps:
            plt.figure(figsize=(10, 2))  # Set the size of the plot
            plt.plot(df['datetime'], [1] * len(df), 'o')  # 'o' creates a scatter plot
            plt.yticks([])  # Hide y-axis ticks
            plt.xlabel(f'Datetime {filepath}')
            plt.title('1D Datetime Plot')
            plt.tight_layout()
            plt.show()

        start_time = df['datetime'].iloc[0]
        end_time = df['datetime'].iloc[-1]
    return start_time, end_time

def process_folder(base_folder):
    rec_times = []
    for root, dirs, files in os.walk(base_folder):
        for file in files:
            if file.lower().endswith('.csv'):
                full_path = os.path.join(root, file)
                start_time, end_time = parse_air_mag_time(full_path)
                rec_times.append((start_time, end_time, full_path, True)) # true means it is a flight file
            if file.endswith('.txt'):
                full_path = os.path.join(root, file)
                start_time, end_time = process_base_mag_file(full_path)
                rec_times.append((start_time, end_time, full_path, False)) # false means it is a base file
    return rec_times

def on_hover(sel):
    sel.annotation.set_text(sel.artist.get_label())
    sel.annotation.get_bbox_patch().set_facecolor(sel.artist.get_color())
    sel.annotation.get_bbox_patch().set_alpha(0.7)


# Process the flights folder and plot the times
fig, ax = plt.subplots()
rec_times = process_folder(flights_folder)
# Sort the flight times by start time
rec_times.sort(key=lambda x: x[0] or datetime.min)

lines = []

# LiDAR flight plotting
current_row = 1
row_cycle = 5

colors = colormaps['tab20'].colors
color_map = {}

# GNSS plotting
gnss_row_T = 17  # (row in the graph not the file)
gnss_row_V = 30  # (row in the graph not the file)

for start_time, end_time, flight_name, true_flt_false_base in rec_times:
    parent_folder = os.path.basename(os.path.dirname(flight_name))
    if parent_folder not in color_map:
        color_map[parent_folder] = colors[len(color_map) % len(colors)]
    color = color_map[parent_folder]
    gnss_row = gnss_row_T if 'TM' in os.path.basename(flight_name) else gnss_row_V
    if color_by_file:
        if true_flt_false_base:
            line, = ax.plot([start_time, end_time], [current_row, current_row], marker='o', label=flight_name,
                            color=color)
        else:

            line, = ax.plot([start_time, end_time], [gnss_row, gnss_row], marker='o', label=flight_name,
                            color=color)
    else:
        if true_flt_false_base:
            line, = ax.plot([start_time, end_time], [current_row, current_row], marker='o', label=flight_name)
        else:
            line, = ax.plot([start_time, end_time], [gnss_row, gnss_row], marker='o', label=flight_name)
    lines.append(line)
    current_row = (current_row % row_cycle) + 1



cursor = mplcursors.cursor(lines, hover=True)
cursor.connect("add", on_hover)

# Set y-ticks and labels
ax.set_yticks([1, 2, 3, 4, 5, gnss_row_T, gnss_row_V])
ax.set_yticklabels(['', '', '', '', 'MagArrow Flights', 'SmartMag "T"', 'SmartMag "V"'])
plt.xlabel('Time')
plt.title('Recording Times')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
