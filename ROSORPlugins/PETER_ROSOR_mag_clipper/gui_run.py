import os
import numpy as np
import pandas as pd
import matplotlib

from shapely.geometry import LineString, Point

from PyQt5.QtWidgets import QDialog, QPushButton, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QIcon

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5 import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, hex2color
import matplotlib.ticker as ticker

from . import plot_dataframe_to_pdf
from .plugin_tools import show_error
from .tools import (CustomNavigationToolbar,
                                           calculate_4th_difference,
                                           calculate_range_noise,
                                           load_csv_data_to_qgis)

from .detect_belonging_flight_name import detect_belonging_flight_name
from matplotlib.patches import Polygon

from .split_csv_by_flightlines import run_flightline_splitter_gui

from .segment_length_calculation_Sharj import flightline_lkm


def darken_color_map(color_map_original, scale_factor = 0.75):
    # Create a new colormap by modifying the original Viridis colors
    # Here we simply scale the RGB values to make them darker
    # Adjust the scale factor to control how much darker you want the colormap to be
    colors_darker = color_map_original(np.arange(256)) * scale_factor
    colors_darker[:, 3] = 1  # Ensure alpha channel is set to 1 (fully opaque)
    color_map_darker = LinearSegmentedColormap.from_list("viridis_darker", colors_darker)
    return color_map_darker

def get_offset_annot_mag(index):
    sequence = [15, 25]
    return sequence[(index-1) % len(sequence)]

def get_offset_annot_mag2(index):
    sequence = [-18, 18]
    return sequence[(index-1) % len(sequence)]

def plotting_on_canvas(df, title_filename, kml_flt_coords, box_coords_list, local_grid_line_names, flight_line_sort_direction):
    #fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, gridspec_kw={'height_ratios': [2.5, 1]})
    #plt.subplots_adjust(bottom=0.18, hspace=0.2)

    fig, ax1= plt.subplots(nrows=1, ncols=1, figsize=(10, 10))
    #plt.subplots_adjust(bottom=0.18, hspace=0.2)
    ax1.set_title(title_filename, fontsize=10, fontweight='bold')

    flt_2d_color = "cyan"
    if kml_flt_coords:
        ax1.plot(kml_flt_coords[0], kml_flt_coords[1], flt_2d_color, linestyle='--', zorder=0)

    if box_coords_list:
        for box_coords in box_coords_list:
            ax1.add_patch(Polygon(box_coords,
                                  closed=True, facecolor='white',
                                  linestyle='--', edgecolor=flt_2d_color, zorder=1))

    # Plot all points not part of positive flight lines and not marked as noisy
    non_flightline_non_noisy_points = df[(df['Flightline'] <= 0) & (df['noise_bad'] == 0)]
    ax1.scatter(non_flightline_non_noisy_points['UTME'], non_flightline_non_noisy_points['UTMN'],
                c=non_flightline_non_noisy_points[['r', 'g', 'b', 'a']].values,
                s=non_flightline_non_noisy_points['size'],
                marker='o', lw=1)  # Regular marker for non-flight line and non-noisy points

    # Scatter plot for noise-free points in positive flight lines
    noise_free_flightline_points = df[(df['noise_bad'] == 0) & (df['Flightline'] > 0)]
    ax1.scatter(noise_free_flightline_points['UTME'], noise_free_flightline_points['UTMN'],
                c=noise_free_flightline_points[['r', 'g', 'b', 'a']].values, s=noise_free_flightline_points['size'],
                marker='o', lw=1)  # Regular marker for noise-free flight line points

    # Scatter plot for points with noise_bad = 1 (using 'x' marker)
    # Scatter plot for points with noise_bad = 1
    for condition, lw in [(df['Flightline'] > 0, 3), (df['Flightline'] <= 0, 1)]:  # Conditions for line width
        noise_points = df[(df['noise_bad'] == 1) & condition]
        ax1.scatter(noise_points['UTME'], noise_points['UTMN'],
                    c=noise_points[['r', 'g', 'b', 'a']].values, s=noise_points['size'],
                    marker='x', lw=lw)  # Adjust 'lw' based on flightline condition

    # Calculate and annotate the start and end points for each positive, noise-free flight line
    for flightline in noise_free_flightline_points['Flightline'].unique():
        flightline_df = noise_free_flightline_points[
            noise_free_flightline_points['Flightline'] == flightline].sort_values(by=['UTME', 'UTMN'])
        if not flightline_df.empty:
            # Calculate angle for text annotation based on flight line direction
            start_point = flightline_df.sort_values(by=flight_line_sort_direction[flightline]).iloc[0]
            end_point = flightline_df.sort_values(by=flight_line_sort_direction[flightline]).iloc[-1]
            dy = end_point['UTMN'] - start_point['UTMN']
            dx = end_point['UTME'] - start_point['UTME']
            angle = np.degrees(np.arctan2(dy, dx))

            # Calculate offset for annotations based on the angle
            #offset_mag = 15  # constant Magnitude of the offset
            offset_mag = get_offset_annot_mag(flightline) # dynamic
            offset_angle_rad = np.radians(angle)  # Convert angle to radians for calculations
            offset_dx = offset_mag * np.cos(offset_angle_rad)
            offset_dy = offset_mag * np.sin(offset_angle_rad)


            # Annotations for start and end points with offset
            ax1.annotate(str(flightline),
                         xy=(start_point['UTME'], start_point['UTMN']),
                         xytext=(-offset_dx, -offset_dy),
                         textcoords="offset points",
                         ha='center', va='center',
                         fontweight='bold',  # Make the text bold
                         alpha=0.7,
                         bbox=dict(boxstyle="round,pad=0.1", facecolor='white', alpha=0.5, linewidth=0))

            ax1.annotate(str(flightline),
                         xy=(end_point['UTME'], end_point['UTMN']),
                         xytext=(offset_dx, offset_dy),
                         textcoords="offset points",
                         ha='center', va='center',
                         fontweight='bold',  # Make the text bold
                         alpha=0.7,
                         bbox=dict(boxstyle="round,pad=0.1", facecolor='white', alpha=0.5, linewidth=0))

            # Place fl_grid_name halfway between start_point and end_point
            fl_grid_name = local_grid_line_names[flightline - 1]
            if fl_grid_name:
                offset_mag = get_offset_annot_mag2(flightline)
                offset_angle_rad = np.radians(angle)  # Convert angle to radians for calculations
                # Adjust angle to be more upright
                if round(angle/10)*10 > 90:
                    angle_upright = round(angle/10)*10 - 180
                elif round(angle/10)*10 < -90:
                    angle_upright = round(angle/10)*10 + 180
                else:
                    angle_upright = round(angle/10)*10

                offset_dx = offset_mag * np.cos(offset_angle_rad)
                offset_dy = offset_mag * np.sin(offset_angle_rad)
                midpoint_x = (start_point['UTME'] + end_point['UTME']) / 2
                midpoint_y = (start_point['UTMN'] + end_point['UTMN']) / 2
                ax1.annotate(fl_grid_name,
                             xy=(midpoint_x, midpoint_y),
                             xytext=(-offset_dx, -offset_dy),
                             textcoords="offset points",
                             rotation=angle_upright,
                             ha='center', va='center',
                             fontsize=7,  # Half the size of the other annotations
                             fontweight='bold',  # Make the text bold
                             alpha=0.5,
                             bbox=dict(boxstyle="round,pad=0.1", facecolor='white', alpha=0.3, linewidth=0))

    # After all plotting is done, adjust the view limits
    x_min, x_max = ax1.get_xlim()
    y_min, y_max = ax1.get_ylim()
    x_padding = (x_max - x_min) * 0.05  # Add 5% padding to each side
    y_padding = (y_max - y_min) * 0.05  # Add 5% padding to each side

    set_more_square_aspect_ratio = True
    if set_more_square_aspect_ratio:
        # Calculate the current width and height after adding initial padding
        current_width = x_max - x_min + 2 * x_padding
        current_height = y_max - y_min + 2 * y_padding

        # Calculate the desired width and height based on the desired ratio of 3:2
        desired_ratio = 16 / 9  # width to height
        current_ratio = current_width / current_height

        if current_ratio > desired_ratio:
            # The plot is too wide, increase y_padding to adjust
            target_height = current_width / desired_ratio
            total_y_padding = target_height - (y_max - y_min)
            y_padding = total_y_padding / 2  # Divide by 2 to split padding on top and bottom
        else:
            # The plot is too tall, increase x_padding to adjust
            target_width = current_height * desired_ratio
            total_x_padding = target_width - (x_max - x_min)
            x_padding = total_x_padding / 2  # Divide by 2 to split padding on left and right

    ax1.set_xlim(x_min - x_padding, x_max + x_padding)
    ax1.set_ylim(y_min - y_padding, y_max + y_padding)

    # Set the axis to display full integer values and avoid scientific notation
    ax1.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax1.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))

    ax1.tick_params(axis='x', rotation=45)  # Rotate tick labels to 45 degrees

    ax1.set_xlabel('UTM East [meters]', fontsize=9, fontweight='bold')
    ax1.set_ylabel('UTM North [meters]', fontsize=9, fontweight='bold')

    ax1.set_aspect('equal', adjustable='box')

    plt.show()
    return fig

def get_continuous_sections(inds):
    diffs = np.diff(inds)

    # Find the indexes where the difference is greater than 1 (indicating a new section)
    split_indexes = np.where(diffs > 1)[0] + 1

    # Split the inds array into continuous sections
    continuous_sections = np.split(inds, split_indexes)

    # Convert arrays in list of lists
    continuous_sections = [list(section) for section in continuous_sections]
    return continuous_sections

def get_acceptable_box(line_to_points, flight_lines, thresh, mag_x, mag_y):
    mask_whole = np.zeros_like(mag_x).astype(bool)
    box_list = []
    
    for line_num, indices in line_to_points.items():
        # Instead of using the flight line coordinates (which only have 2 points),
        # use the actual data points that belong to this flight line
        line_x = mag_x[indices['start']:indices['end']]
        line_y = mag_y[indices['start']:indices['end']]
        
        # Create a LineString from the actual data points
        if len(line_x) > 1:
            line_coords = list(zip(line_x, line_y))
            flight_line = LineString(line_coords)
        else:
            # If only one point, create a small buffer around it
            flight_line = Point(line_x[0], line_y[0])

        # Create a buffer around the actual flight path
        buffered = flight_line.buffer(thresh)
        exterior_coords = buffered.exterior.coords
        box_list.append(exterior_coords)

        mask_local = []
        for x, y in zip(mag_x[indices['start']:indices['end']], mag_y[indices['start']:indices['end']]):
            point = Point(x, y)
            if buffered.covers(point):
                mask_local.append(False)
            else:
                mask_local.append(True)
        mask_whole[indices['start']:indices['end']] = mask_local
    
    return mask_whole, box_list

def get_close_points_and_line_indices(flight_lines, mag_x, mag_y, thresh):
    # Initialize lists to hold the index of the closest point and the index of the line it belongs to
    closest_point_indices = []
    line_indices = []
    fl_point_indices = []

    debug = {}
    # Iterate through each line and its points
    for line_idx, line in enumerate(flight_lines):
        for fl_point_ind, fl_point in enumerate(line):
            # Convert flight line point to a NumPy array for calculations
            fl_point_array = np.array(fl_point)

            # Calculate squared distances from this flight line point to all data points
            differences = np.vstack((mag_x, mag_y)).T - fl_point_array
            squared_distances = np.sum(differences ** 2, axis=1)

            dists = np.sqrt(squared_distances)
            debug[f'{line_idx=} {fl_point_ind=}'] = dists.astype(int).tolist()

            inds = np.where(dists < thresh)[0]
            if not inds.shape == (0,):
                continuous_sections = get_continuous_sections(inds)
                for section in continuous_sections:
                    closest_point_indices.append(section[np.argmin(dists[section])])
                    line_indices.append(line_idx)
                    fl_point_indices.append(fl_point_ind)

            if line_idx==0 and fl_point_ind==0:
                pass

    sort_ind = np.argsort(closest_point_indices)
    return np.array(closest_point_indices)[sort_ind], np.array(line_indices)[sort_ind], np.array(fl_point_indices)[sort_ind]

from scipy.spatial import cKDTree
def get_close_points_and_line_indices_optimized(flight_lines, mag_x, mag_y, thresh):
    coords = np.column_stack((mag_x, mag_y))
    tree = cKDTree(coords)

    closest_point_indices = []
    line_indices = []
    fl_point_indices = []

    for line_idx, line in enumerate(flight_lines):
        for fl_point_idx, fl_point in enumerate(line):
            indices = tree.query_ball_point(fl_point, r=thresh)
            if indices:
                continuous_sections = get_continuous_sections(np.array(indices))
                for section in continuous_sections:
                    min_idx = section[np.argmin(np.linalg.norm(coords[section] - fl_point, axis=1))]
                    closest_point_indices.append(min_idx)
                    line_indices.append(line_idx)
                    fl_point_indices.append(fl_point_idx)

    sort_idx = np.argsort(closest_point_indices)
    return (np.array(closest_point_indices)[sort_idx],
            np.array(line_indices)[sort_idx],
            np.array(fl_point_indices)[sort_idx])

def determine_line_start_end(closest_indices, line_indices, fl_point_ind) -> dict:
    #[12145, 9527, 12598, 686, 1266, 1342, 8557, 9026, 9124, 15216, 15888, 4608, 1987, 5056, 7675] [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 3, 3] [0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1]
    lines, counts = np.unique(line_indices, return_counts=True)
    sorted_line_to_points = {}  # Initialize result dictionary
    for line_ind, count in zip(lines, counts):
        bool_line_indices = line_indices == line_ind
        cand_closest_indices = closest_indices[bool_line_indices]
        cand_fl_point_indices = fl_point_ind[bool_line_indices]
        if count == 1:
            # Only one point; cannot determine start and end, so skip
            continue
        elif count == 2:
            # Exactly two points; straightforward start and end
            sorted_line_to_points[line_ind] = {'start': cand_closest_indices[0], 'end': cand_closest_indices[1]}
        else:
            # More than two points; find best start and end based on flag indicators
            ends = cand_closest_indices[cand_fl_point_indices.astype(bool)]
            starts = cand_closest_indices[np.logical_not(cand_fl_point_indices.astype(bool))]
            # if none of the points are a start or end skip cuz impossible
            if ends.shape == (0,) or starts.shape == (0,):
                continue

            # Calculate all possible start-end combinations and their index differences
            min_difference = np.inf  # Initialize with infinity for comparison
            for start in starts:
                for end in ends:
                    difference = abs(start - end)  # Absolute difference
                    if difference < min_difference:
                        min_difference = difference
                        best_start = start
                        best_end = end

            if best_start > best_end:
                best_start, best_end = best_end, best_start
            # Update result for this line with the best start and end found
            sorted_line_to_points[line_ind] = {'start': best_start, 'end': best_end}
    # sorted_line_to_points = {1: {'start': 686, 'end': 15888}, 2: {'start': 1987, 'end': 4608}, 3: {'start': 5056, 'end': 7675}, 0: {'start': 9527, 'end': 12145}}
    return sorted_line_to_points



def get_custom_spectral_colormap():
    # Define your colors
    hex_colors = ['#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c']
    # Convert hex to RGB
    rgb_colors = [hex2color(color) for color in hex_colors]

    # Create the custom colormap
    custom_cmap_name = 'custom_colormap'
    n_bins = 256  # Increase this number for a smoother transition between colors
    custom_cmap = LinearSegmentedColormap.from_list(custom_cmap_name, rgb_colors, N=n_bins)
    return custom_cmap

def sort_for_plotting(df):
    """
    Sorts the DataFrame first by 'Flightline', and then within each flight line,
    sorts based on the larger extent between 'UTME' and 'UTMN'. Additionally,
    ensures rows with 'fourth_diff_noise' or 'range_noise' marked as 1 are put last.

    Parameters:
        df (DataFrame): The input DataFrame containing flight line, coordinate data,
                        and noise identification columns.

    Returns:
        DataFrame: A new DataFrame where the entire dataset is sorted first by flight line,
                   and then each flight line subset is sorted based on its larger geographical extent,
                   with rows flagged for noise put last.
    """
    # Create a temporary sorting key where noise rows are given highest sort value
    df['_sort_key'] = df['noise_bad'] == 1

    sorted_subsets = []
    # Ensure flight lines are sorted numerically including -1
    flightlines = sorted(df['Flightline'].unique(), key=lambda x: (x == -1, x))

    sorted_by = {}
    for flightline in flightlines:
        subset = df[df['Flightline'] == flightline]

        # Calculate the extents for 'UTME' and 'UTMN'
        x_extent = subset['UTME'].max() - subset['UTME'].min()
        y_extent = subset['UTMN'].max() - subset['UTMN'].min()

        # Sort the subset first by noise, then by 'UTME' or 'UTMN' based on which extent is larger
        if x_extent >= y_extent:
            sorted_subset = subset.sort_values(by=['_sort_key', 'UTME'])
            if not flightline == -1:
                sorted_by[flightline] = 'UTME'
        else:
            sorted_subset = subset.sort_values(by=['_sort_key', 'UTMN'])
            if not flightline == -1:
                sorted_by[flightline] = 'UTMN'

        # Append the sorted subset to the list
        sorted_subsets.append(sorted_subset)

    # Concatenate all sorted subsets back into a single DataFrame
    sorted_df = pd.concat(sorted_subsets).reset_index(drop=True)

    # Remove the temporary sorting key from the DataFrame
    sorted_df.drop(columns=['_sort_key'], inplace=True)

    return sorted_df, sorted_by

def detect_duplicate_lines(lines_dict):
    # Create a set to store unique line start-end tuples
    seen_lines = set()

    # Iterate through each line in the dictionary
    for line in lines_dict.values():
        # Create a tuple of the start and end points
        line_tuple = (line['start'], line['end'])

        # Check if this line is already in the set
        if line_tuple in seen_lines:
            # If it is, we've found a duplicate
            return True
        else:
            # Otherwise, add this line to the set of seen lines
            seen_lines.add(line_tuple)

    # If we've gone through all lines and found no duplicates, return False
    return False

def re_name_line_numbers(line_to_points):
    new_dict = {}
    for indx, key in enumerate(line_to_points):
        new_dict[indx] = line_to_points[key]
    return new_dict

def detect_and_eliminate_overlaps(line_to_points):
    lines = list(line_to_points.items())
    lines.sort(key=lambda x: (x[1]['start'], x[1]['end'] - x[1]['start']))  # Sort by start and then by range length

    non_overlapping_lines = {}

    for i in range(len(lines)):
        line_i, indices_i = lines[i]
        start_i, end_i = indices_i['start'], indices_i['end']
        overlap = False

        for j in range(i + 1, len(lines)):
            line_j, indices_j = lines[j]
            start_j, end_j = indices_j['start'], indices_j['end']

            if start_i <= end_j and end_i >= start_j:
                overlap = True
                break

        if not overlap:
            non_overlapping_lines[line_i] = indices_i

    return non_overlapping_lines

def detect_and_eliminate_overlaps_optimized(line_to_points):
    # Step 1: Convert to sorted list of (line_index, start, end)
    sorted_lines = sorted(
        line_to_points.items(),
        key=lambda item: (item[1]['start'], item[1]['end'] - item[1]['start'])
    )

    non_overlapping_lines = {}
    last_accepted_end = -1

    # Step 2: Sweep through sorted list and add non-overlapping ranges
    for line_index, indices in sorted_lines:
        start, end = indices['start'], indices['end']
        if start > last_accepted_end:
            non_overlapping_lines[line_index] = {'start': start, 'end': end}
            last_accepted_end = end  # Update the end marker

    return non_overlapping_lines


def debug_ranges(line_to_points):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()

    for line, indices in line_to_points.items():
        start = indices['start']
        end = indices['end']
        ax.plot([start, end], [line, line], marker='o')

    ax.set_xlabel('Indices')
    ax.set_ylabel('Line Number')
    ax.set_yticks(range(len(line_to_points)))
    ax.set_title('Line Ranges')

    plt.show()


def detect_peaks(angles_degrees, filter_lines_direction_thresh):
    hist, bin_edges = np.histogram(angles_degrees, bins=33, range=(np.mean(angles_degrees)-361, np.mean(angles_degrees)+361))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    count_thresh = angles_degrees.shape[0] * filter_lines_direction_thresh / 100

    if np.max(hist) > count_thresh:
        has_single_peak = True
    else:
        has_single_peak = False

    debug_plot = False
    if debug_plot:
        plt.figure(figsize=(10, 6))
        plt.bar(bin_centers, hist, label='Smoothed Histogram')
        plt.xlabel('Angle (degrees)')
        plt.ylabel('Count')
        plt.title('Smoothed Histogram of Angles')
        plt.grid(True)
        plt.legend()
        plt.show()

    return has_single_peak


def remove_lines_with_multiple_primary_directions(line_to_points, x,y, filter_lines_direction_thresh):
    lines_with_multiple_directions = []
    for line, indices in line_to_points.items():
        x_line = x.loc[indices['start']:indices['end']].to_numpy()
        y_line = y.loc[indices['start']:indices['end']].to_numpy()
        # Calculate the differences
        dx = np.diff(x_line)
        dy = np.diff(y_line)
        # Calculate the angles
        angles = np.arctan2(dy, dx)
        angles_degrees = np.degrees(angles)
        # Normalize angles to the range 0 to 360 degrees
        angles_degrees = angles_degrees % 360
        angles_degrees_offset = angles_degrees - 90
        angles_degrees_offset = angles_degrees_offset % 360
        offset_has_single_peak = detect_peaks(angles_degrees_offset, filter_lines_direction_thresh)
        norm_has_single_peak = detect_peaks(angles_degrees, filter_lines_direction_thresh)
        has_single_peak = offset_has_single_peak or norm_has_single_peak
        if not has_single_peak:
            lines_with_multiple_directions.append(line)
    # Remove lines with_multiple_directions from line_to_points
    filtered_line_to_points = {key: value for key, value in line_to_points.items() if
                               key not in lines_with_multiple_directions}
    return filtered_line_to_points

def plot_vels(cumulative_distances, velocities):
    plt.figure(figsize=(10, 6))
    plt.plot(cumulative_distances, velocities, marker='o')
    plt.xlabel('Cumulative Distance Along the Line (m)')
    plt.ylabel('Velocity (m/s)')
    plt.title('Velocity vs. Distance Along the Line')
    plt.grid(True)
    plt.show()


def get_acceptable_velocity(line_to_points, acceptable_minimum_velocity, elapsed_time_minutes_all, utme_all, utmn_all, plot=False):
    mask_too_slow = np.zeros_like(utme_all)

    for line, indices in line_to_points.items():
        utme = utme_all.loc[indices['start']:indices['end']].to_numpy()
        utmn = utmn_all.loc[indices['start']:indices['end']].to_numpy()
        elapsed_time_minutes = elapsed_time_minutes_all.loc[indices['start']:indices['end']].to_numpy()

        # Calculate the vector from the first to the last point
        direction_vector = np.array([utme[-1] - utme[0], utmn[-1] - utmn[0]])

        # Calculate the magnitude of the direction vector
        direction_magnitude = np.linalg.norm(direction_vector)

        # Unit vector in the direction from the first to the last point
        unit_vector = direction_vector / direction_magnitude

        # Calculate the differences between consecutive coordinates
        delta_x = np.diff(utme)
        delta_y = np.diff(utmn)

        # Create displacement vectors
        displacement_vectors = np.column_stack((delta_x, delta_y))

        # Project each displacement vector onto the unit vector
        projections = np.dot(displacement_vectors, unit_vector)

        # Calculate cumulative distances along the direction of the unit vector
        cumulative_distances = np.cumsum(np.insert(projections, 0, 0))  # Insert a 0 at the start for the initial position

        # Convert elapsed time from minutes to seconds
        elapsed_time_seconds = np.array(elapsed_time_minutes) * 60

        seconds_between_samples = np.diff(elapsed_time_seconds)

        # Calculate velocities (distance/time)
        velocities = projections / seconds_between_samples  # Ignore the first time point for velocity calculation

        if plot:
            plot_vels(cumulative_distances[1:], velocities)

        # Create a mask for velocities that are too slow
        mask_too_slow_line = velocities < acceptable_minimum_velocity

        mask_too_slow[indices['start']:indices['end']] = mask_too_slow_line

    return mask_too_slow

def get_mag_data_extent(utme, utmn):
    minx, maxx = utme.min(), utme.max()
    miny, maxy = utmn.min(), utmn.max()
    return minx, miny, maxx, maxy


def filter_lines_by_extent(flight_lines, extent):
    # Only keep lines that have both start and end points within the extent
    minx, miny, maxx, maxy = extent
    kept = {}
    new_idx = 0
    for orig_idx, line in enumerate(flight_lines):
        (x1, y1), (x2, y2) = line[0], line[-1]
        if (minx <= x1 <= maxx and miny <= y1 <= maxy and
            minx <= x2 <= maxx and miny <= y2 <= maxy):
            kept[new_idx] = (orig_idx, np.array(line))
            new_idx += 1
    return kept


def sample_data_on_lines(lines_dict, utme, utmn, dist_thresh):
    """
    For each line in lines_dict, sample magnetometer points within dist_thresh of each segment point.
    Returns three arrays: closest_indices, line_indices, fl_point_ind.
    line_indices and fl_point_ind are references to the new_index in lines_dict.
    """
    coords = np.column_stack((utme.values, utmn.values))
    tree = cKDTree(coords)

    closest_inds = []
    line_inds = []
    pt_inds = []

    for new_idx, (orig_idx, line_pts) in lines_dict.items():
        for pt_idx, pt in enumerate(line_pts):
            # find all data points within threshold
            hits = tree.query_ball_point(pt, r=dist_thresh)
            if hits:
                # choose nearest
                nearest = min(hits, key=lambda i: np.linalg.norm(coords[i] - pt))
                closest_inds.append(nearest)
                line_inds.append(new_idx)
                pt_inds.append(pt_idx)

    # sort by closest point index to keep consistency
    sort_order = np.argsort(closest_inds)
    return (np.array(closest_inds)[sort_order],
            np.array(line_inds)[sort_order],
            np.array(pt_inds)[sort_order])


def compute_line_coverage(closest_inds, line_inds, lines_dict):
    """
    Calculate coverage fraction for each line: ratio of unique sampled points to total line_points.
    Returns dict: {new_idx: coverage_fraction}
    """
    coverage = {}
    hits_by_line = {}

    for idx, line_idx in enumerate(line_inds):
        hits_by_line.setdefault(line_idx, set()).add(idx)

    for line_idx, (_, line_pts) in lines_dict.items():
        total = len(line_pts)
        hit_count = len(hits_by_line.get(line_idx, ()))
        coverage[line_idx] = hit_count / total if total > 0 else 0.0
    return coverage


def filter_lines_by_coverage(lines_dict, coverage, threshold):
    return {ln: lines_dict[ln] for ln, cov in coverage.items() if cov >= threshold}


def process_flight_lines(flight_lines, utme, utmn,
                         dist_thresh, coverage_thresh,
                         filter_dir_thresh,
                         determine_fn):

    # 1. Filter by mag data extent
    extent = get_mag_data_extent(utme, utmn)
    lines_in_extent = filter_lines_by_extent(flight_lines, extent)

    # 2. Sample data onto each line
    closest_inds, line_inds, pt_inds = sample_data_on_lines(
        lines_in_extent, utme, utmn, dist_thresh
    )

    # 3. Compute coverage and filter lines
    coverage = compute_line_coverage(closest_inds, line_inds, lines_in_extent)
    lines_kept = filter_lines_by_coverage(lines_in_extent, coverage, coverage_thresh)

    # 4. Re-sample to only kept lines
    mask = np.isin(line_inds, list(lines_kept.keys()))
    closest_inds = closest_inds[mask]
    line_inds = line_inds[mask]
    pt_inds = pt_inds[mask]

    # 5. Determine start/end pairs
    line_to_points = determine_fn(closest_inds, line_inds, pt_inds)

    return closest_inds, line_inds, pt_inds, line_to_points

def gui_run(df,
            flight_lines,
            grid_line_names,
            noise_detection_params,
            deviation_thresh,
            acceptable_minimum_velocity,
            export_file_path,
            line_detection_threshold,
            filter_lines_direction_thresh,
            Y_axis_display_range_override,
            path_to_2d_flights,
            epsg_target):

    matplotlib.use('Qt5Agg')

    # Create the dialog window
    dialog = QDialog()
    dialog.setWindowTitle("QaQc and clip the magnetic data")
    dialog_layout = QVBoxLayout(dialog)

    extent = get_mag_data_extent(df['UTME'], df['UTMN'])
    lines_in_extent = filter_lines_by_extent(flight_lines, extent)

    closest_indices, line_indices, fl_point_ind, line_to_points = process_flight_lines(
        flight_lines,
        df['UTME'],
        df['UTMN'],
        line_detection_threshold,
        0.75,
        filter_lines_direction_thresh,
        determine_line_start_end
    )

    do_detect_duplicate_lines = False
    if detect_duplicate_lines(line_to_points) and do_detect_duplicate_lines:
        mesage = 'THERE ARE TOO MANY MATCHES BETWEEN DATA AND FLIGHT LINES. REDUCE THE "line_detection_threshold" '
        retval = show_error(mesage)
        print(mesage)
        return False, retval, None

    if not line_to_points:
        mesage = 'THERE IS NO MATCH BETWEEN THE PROVIDED FLIGHT LINES AND THE DATA'
        retval = show_error(mesage)
        print(mesage)
        load_csv_data_to_qgis(export_file_path, set_symbols_and_colors = False)
        return False, retval, None

    line_to_points = re_name_line_numbers(line_to_points)
    renamed_lines_dict = {
        new_idx: lines_in_extent[orig_idx][1]
        for new_idx, (orig_idx, _) in enumerate(lines_in_extent.items())
    }

    mask_outside_box, box_coords_list = get_acceptable_box(line_to_points, renamed_lines_dict, deviation_thresh, df['UTME'], df['UTMN'])

    mask_too_slow = get_acceptable_velocity(line_to_points, acceptable_minimum_velocity, df['elapsed_time_minutes'], df['UTME'], df['UTMN'])

    local_grid_line_names = [
        grid_line_names[orig_idx]
        for new_idx, (orig_idx, _) in enumerate(lines_in_extent.items())
    ]

    """↓↓ Sharj's Addition ↓↓"""
    local_flightline_UTM_pairs = [
        lines_in_extent[orig_idx][1]
        for new_idx, (orig_idx, _) in enumerate(lines_in_extent.items())
    ]
    local_flightline_lkm, total_flightline_lkm = flightline_lkm(local_flightline_UTM_pairs)
    """↑↑ Sharj's Addition ↑↑"""

    # use this info to assign flightlines in the df
    df['Flightline'] = -1  # Initialize all values to -1
    df['Flightline_lkm'] = -1.0
    df['Total_lkm'] = -1.0


    for line, indices in line_to_points.items():
        df.loc[indices['start']:indices['end'], 'Flightline'] = line + 1
        if local_grid_line_names[line]:
            df.loc[indices['start']:indices['end'], 'Grid_Flightline'] = local_grid_line_names[line]
        df.loc[indices['start']:indices['end'], 'Flightline_lkm'] = float(local_flightline_lkm[line])
        df.loc[indices['start']:indices['end'], 'Total_lkm'] = float(total_flightline_lkm)

    #set colors for the data directly in the df
    colormap = get_custom_spectral_colormap()
    colormap_darker = darken_color_map(colormap, 0.85)
    df['r'] = df['g'] = df['b'] = 0.0
    # Determine the number of distinct flight lines (excluding -1)
    num_flightlines = df['Flightline'].max()
    # Assign colors from the modified Viridis colormap to each flight line
    for i in range(1, num_flightlines + 1):
        flightline_data = df[df['Flightline'] == i]['Mag_TMI_nT']
        min_val, max_val = flightline_data.min(), flightline_data.max()
        # Normalize 'Mag_TMI_nT' within each flightline and apply colormap
        norm = plt.Normalize(vmin=min_val, vmax=max_val)
        colors = colormap_darker(norm(flightline_data.values))
        # Update the dataframe with the new RGB values
        df.loc[df['Flightline'] == i, ['r', 'g', 'b']] = colors[:, :3]

    # Set the color for 'Flightline' == -1 to black
    df.loc[df['Flightline'] == -1, ['r', 'g', 'b']] = [0.0, 0.0, 0.0]
    df['a'] = 1.0
    df['size'] = 10.0
    df.loc[df['Flightline'] == -1, 'a'] = 0.5
    df.loc[df['Flightline'] == -1, 'size'] = 0.5

    # get indices of noisy data according to different noise definitions

    range_noise = calculate_range_noise(df['Mag_TMI_nT'],
                                        num_points=noise_detection_params['range_noise_number_of_points'],
                                        z_score_smoothing_factor=noise_detection_params['z_score_smoothing_factor'])

    range_noise_indices = np.where(range_noise > noise_detection_params['range_noise_threshold'])[0]
    df['range_noise'] = 0 ; df.loc[range_noise_indices, 'range_noise'] = 1

    df['noise_bad'] = df['range_noise']

    #set r,g,b (color), alpha (transparancy) and size for plotting noisy points
    df.loc[df['noise_bad'] == 1, ['r', 'g', 'b', 'a', 'size']] = [1, 0.1, 0.1, 1, 50]

    # set r,g,b (color), alpha (transparancy) and size for plotting points outside the accptable deviation from flight line
    df.loc[(mask_outside_box) & (df['Flightline'] > 0), ['r', 'g', 'b', 'a', 'size']] = [1, 0.1, 1, 1, 50]

    # set r,g,b (color), alpha (transparancy) and size for plotting points that are too slow
    df.loc[(mask_too_slow) & (df['Flightline'] > 0), ['r', 'g', 'b', 'a', 'size']] = [0.8, 0.1, 0.8, 1, 50]

    # If 'noise_bad' is 1 and 'Flightline' <= 0, set color to orange and size to 40
    df.loc[(df['noise_bad'] == 1) & (df['Flightline'] <= 0), ['r', 'g', 'b', 'a', 'size']] = [1, 0.65, 0, 1, 40]


    if path_to_2d_flights:
        export_file_path, kml_flt_coords, run_flightline_splitter = detect_belonging_flight_name(df,
                                                                                path_to_2d_flights,
                                                                                epsg_target,
                                                                                export_file_path)
    else:
        kml_flt_coords = []
        run_flightline_splitter = None

    # sort for optimal look when plotted
    sorted_df, flight_line_sort_direction = sort_for_plotting(df)

    fig = plotting_on_canvas(sorted_df, export_file_path, kml_flt_coords, box_coords_list, local_grid_line_names, flight_line_sort_direction)

    # plot line side view to pdf
    output_pdf_path = plot_dataframe_to_pdf.run(df,
                                                local_grid_line_names,
                                                flight_line_sort_direction,
                                                export_file_path,
                                                fig,
                                                Y_axis_display_range_override)

    canvas = FigureCanvas(fig)
    toolbar = CustomNavigationToolbar(canvas, dialog)

    # Bottom bar layout
    bottom_bar_layout = QHBoxLayout()
    # toolbar = CustomNavigationToolbar(canvas, dialog)
    btn_accept = QPushButton("Accept and Save", dialog)

    font = btn_accept.font()
    font.setPointSize(12)
    btn_accept.setFont(font)
    btn_accept.setFixedSize(300, 30)
    btn_accept.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


    bottom_bar_layout.addWidget(toolbar)
    bottom_bar_layout.addStretch(1)
    bottom_bar_layout.addWidget(btn_accept)

    dialog_layout.addWidget(canvas)
    dialog_layout.addLayout(bottom_bar_layout)

    btn_accept.clicked.connect(dialog.accept)

    # Set the window icon
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "plugin_icon.png")))


    # toolbar = NavigationToolbar(canvas, dialog)

    # dialog_layout.addWidget(toolbar)


    # Execute the dialog and wait for the user to close it
    dialog.show()
    dialog.exec_()
    result = dialog.result() == QDialog.Accepted

    #don't export data outside the flight lines
    df_clean = sorted_df.loc[sorted_df['Flightline'] > 0]

    del dialog
    return result, df_clean, output_pdf_path, export_file_path, run_flightline_splitter
