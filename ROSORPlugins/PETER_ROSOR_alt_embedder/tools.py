import os
import re
import numpy as np
from osgeo import osr
from PyQt5.QtWidgets import QMessageBox
import matplotlib.pyplot as plt

def show_error(mesage):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setText(mesage)
    msg.setWindowTitle("Error")
    msg.setStandardButtons(QMessageBox.Ok)
    retval = msg.exec_()
    assert False, mesage

def show_information(message):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)  # Set icon to Information type
    msg.setText(message)
    msg.setWindowTitle("Information")
    msg.setStandardButtons(QMessageBox.Ok)
    retval = msg.exec_()

def get_next_filename(directory, original_filename):
    base, ext = os.path.splitext(original_filename)
    parts = base.split('_')
    if parts[-1].startswith('v') and parts[-1][1:].isdigit():
        # Increment the last part if it's a version number
        version = int(parts[-1][1:])
        parts[-1] = f"v{version + 1}"
    else:
        # Append '_v2' if no version number found
        parts.append('v2')

    # Construct the new base name from parts
    new_base = '_'.join(parts)
    new_filename = f"{new_base}{ext}"
    # Check for existence and adjust if necessary
    while os.path.exists(os.path.join(directory, new_filename)):
        version = int(parts[-1][1:])
        parts[-1] = f"v{version + 1}"
        new_base = '_'.join(parts)
        new_filename = f"{new_base}{ext}"

    return os.path.join(directory, new_filename)


def remove_steep_angles(in_x, in_y, slope_percent, plot=False):
    slope = slope_percent / 100
    big_sqr = np.broadcast_to(in_y, [in_y.shape[0], in_y.shape[0]]).copy()
    delta_x = np.broadcast_to(in_x, [in_x.shape[0], in_x.shape[0]]).copy()
    for ind, row in enumerate(delta_x):
        delta_x[ind, :] = (row - row[ind])
    delta_y = np.abs(delta_x * slope) * -1
    all_ys = big_sqr + delta_y
    result = all_ys.max(axis=1)

    if plot:
        plt.figure(figsize=(10, 6))
        plt.plot(in_x, in_y, label='Input')
        plt.plot(in_x, result, label='Output', linestyle='--')
        plt.xlabel('X')
        plt.ylabel('Y')
        plt.title('Input vs Output with Steep Angles Removed')
        plt.legend()
        plt.show()

    return result

def get_new_folder_name(base_path):
    """
    Generate a new folder name based on the given base path.
    If '2D' exists in the name, replace it with '3D'.
    If '3D' already exists, check the existing folders and increment the version number.
    """
    base_dir, folder_name = os.path.split(base_path)
    if '2D' in folder_name:
        new_folder_name = folder_name.replace('2D', '3D')
    elif '3D' not in folder_name:
        new_folder_name = folder_name + '_3D'
    else:
        new_folder_name = folder_name
    # Check in the directory for existing versions and increment if needed
    version = 2
    new_folder_path = os.path.join(base_dir, new_folder_name)
    while os.path.exists(new_folder_path):
        if '3D_V' in new_folder_name:
            base, _ = new_folder_name.rsplit('_V', 1)
        else:
            base = new_folder_name
        new_folder_name = f"{base}_V{version}"
        new_folder_path = os.path.join(base_dir, new_folder_name)
        version += 1
    return new_folder_path

def get_whether_midline(seg_number):
    # for debug np.column_stack([np.arange(1,len(seg_number)+1),seg_number,is_midline])

    diff = np.concatenate([np.array([1.0]), np.diff(seg_number)])
    diff_shift = np.concatenate([np.diff(seg_number), np.array([1.0])])
    is_midline = np.logical_not(np.logical_or(diff, diff_shift))

    return is_midline

def get_whether_midline_old(seg_number):
    # Ensure the array is a numpy array in case it isn't already
    seg_number = np.array(seg_number)

    # Calculate the differences between consecutive elements, starting from the second element
    differences = np.diff(seg_number[1:]) == 0

    # Prepare the output array of booleans initialized to False
    is_midline = np.zeros_like(seg_number, dtype=bool)

    # Set True at the first occurrence of consecutive duplicates
    # We assign True back one index from where the difference was found
    if differences.size > 0:  # Check if there are any differences
        is_midline[1:-1][differences] = True  # Adjusting index to match first occurrence

    # The first element remains False as per the requirement
    is_midline[0] = False

    return is_midline

def find_key_in_nested_dict(nested_dict, search_key):
    if search_key in nested_dict:
        return nested_dict[search_key]

    for key, value in nested_dict.items():
        if isinstance(value, dict):
            result = find_key_in_nested_dict(value, search_key)
            if result is not None:
                return result
    return None

def get_newest_file_in(plugin_dir, folder='settings', filter='.json'):
    # Construct the path to the 'settings_folder'
    settings_folder_path = os.path.join(plugin_dir, folder)
    files = os.listdir(settings_folder_path)
    paths = [os.path.join(settings_folder_path, basename) for basename in files if basename[-5:] == filter]
    return max(paths, key=os.path.getmtime)

def remove_duplicates(arr, print_number_of_dupes=False):
    # Find unique values in the first column and their indices
    _, unique_indices = np.unique(arr[:, 0], return_index=True)

    if print_number_of_dupes:
        # Calculate the number of duplicates
        number_of_dupes = arr.shape[0] - unique_indices.size
        print(f"Number of duplicates: {number_of_dupes}")
    return arr[unique_indices]

def extract_2D_subarray_with_buffer(array_2D, x_coords, y_coords, buffer, start_coord, end_coord):
    # Ensure start_coord and end_coord are in the right order for x and y
    x_start, x_end = sorted([start_coord[0], end_coord[0]])
    y_start, y_end = sorted([start_coord[1], end_coord[1]])

    # Find indices in the x and y coordinates for the start and end coordinates, considering the buffer
    x_start_idx = np.searchsorted(x_coords, x_start - buffer, side='left')
    x_end_idx = np.searchsorted(x_coords, x_end + buffer, side='right')

    y_start_idx = np.searchsorted(y_coords, y_start - buffer, side='left')
    y_end_idx = np.searchsorted(y_coords, y_end + buffer, side='right')

    # Adjust indices to add an extra pixel on each edge, ensuring they are within array bounds
    x_start_idx = max(x_start_idx - 2, 0)
    x_end_idx = min(x_end_idx + 2, array_2D.shape[1])

    y_start_idx = max(y_start_idx - 2, 0)
    y_end_idx = min(y_end_idx + 2, array_2D.shape[0])

    # Extract the sub-array and corresponding coordinate arrays
    sub_array = array_2D[y_start_idx:y_end_idx, x_start_idx:x_end_idx]
    sub_x_coords = x_coords[x_start_idx:x_end_idx]
    sub_y_coords = y_coords[y_start_idx:y_end_idx]

    return sub_array, sub_x_coords, sub_y_coords

def compute_heading(waypoints):
    # Calculate the differences in x and y coordinates
    dx = np.diff(waypoints[:, 4])
    dy = np.diff(waypoints[:, 5])
    # Calculate the angles using arctan2
    angles_rad = np.arctan2(dy, dx)
    # Convert angles from radians to degrees
    angles_deg = np.degrees(angles_rad)
    # Append a NaN or the previous angle for the last waypoint
    angles_deg = np.append(angles_deg, angles_deg[-1])
    waypoints = np.column_stack((waypoints, angles_deg))
    return waypoints

def compute_heading_for_samples(samples, waypoints):
    # Create a boolean array with True where each sample's dist_allong_whole_flight
    # is greater than or equal to each waypoint's dist_allong_whole_flight
    mask = samples[:, 0][:, np.newaxis] >= waypoints[:, 0]

    # Find the last True value along each row, this gives the index of the waypoint
    # the sample belongs to in the waypoints array
    idx = np.argmax(mask[:, ::-1], axis=1)
    idx = mask.shape[1] - 1 - idx

    # Use advanced indexing to get the headings
    headings = waypoints[idx, -1]

    # Assign heading of the first waypoint to samples with negative dist_allong_whole_flight
    negative_dist_mask = samples[:, 0] < 0
    headings[negative_dist_mask] = waypoints[0, -1]

    return np.column_stack((samples, headings))

def compute_vertical_distances(samples, waypoints):
    # Interpolate the altitudes of waypoints using the distances along the flight
    interpolated_altitudes = np.interp(samples[:, 0], waypoints[:, 0], waypoints[:, 3])

    # Calculate the vertical distances
    distances = interpolated_altitudes - samples[:, 3]
    samples = np.column_stack((samples, distances))
    return samples

def add_UAV_alt_col(waypoints, payload_rope_length):
    uav_alt = waypoints[:, 3] + payload_rope_length
    return np.column_stack((waypoints, uav_alt))


def simple_sample_arr(array, x_coords, y_coords, x, y):
    pix_width = x_coords[1] - x_coords[0]
    pix_height = y_coords[1] - y_coords[0]
    # must offset by half a pixel to get centre coords. right now, the coords are the top left corner of each pixel
    x_coords_centre = x_coords + pix_width / 2
    y_coords_centre = y_coords - pix_height / 2

    # Find the nearest indices in x_coords and y_coords for each x and y
    x_indices = np.abs(x_coords_centre[None, :] - x[:, None]).argmin(axis=1)
    y_indices = np.abs(y_coords_centre[None, :] - y[:, None]).argmin(axis=1)

    # Sample values from the array using the indices
    sampled_z = array[y_indices, x_indices]

    return sampled_z


def compute_max_point_radius(x_coords, y_coords, max_safest_radius):

    xy_coords = np.column_stack((x_coords, y_coords))

    # Compute the Euclidean distances between consecutive points
    distances = np.linalg.norm(np.diff(xy_coords, axis=0), axis=1)

    # Prepare an array to hold the minimum distances for each point
    min_distances = np.empty(len(x_coords))

    # The minimum distance for the first point is the distance to the second point
    min_distances[0] = distances[0]

    # The minimum distance for the last point is the distance to the second to last point
    min_distances[-1] = distances[-1]

    # For all other points, the minimum distance is the smallest of the distances
    # to the previous and next points
    min_distances[1:-1] = np.minimum(distances[:-1], distances[1:])
    # radious can't overlap at all
    max_possible_rad = (min_distances - 1) / 2
    # because this will round corners when wp radius is too big it can crash so it must be kept reasonable ~ 15m
    radius = max_possible_rad
    radius[max_possible_rad > max_safest_radius] = max_safest_radius

    # round down to the nearest meter
    radius = np.floor(radius).astype(int)
    # Combine the original coordinates with the computed minimum distances
    # to create the new list of tuples
    return radius

def convert_coords_UTM2LATLON(x, y, source_epsg, target_epsg=4326):
    """
    Converts coordinates from one coordinate system to another using GDAL.

    :param x: 1D numpy array of x coordinates (longitude/easting)
    :param y: 1D numpy array of y coordinates (latitude/northing)
    :param source_epsg: EPSG code of the source coordinate system
    :param target_epsg: EPSG code of the target coordinate system (default: 4326)
    :return: Two 1D numpy arrays containing the converted x and y coordinates
    """
    source = osr.SpatialReference()
    source.ImportFromEPSG(source_epsg)

    target = osr.SpatialReference()
    target.ImportFromEPSG(target_epsg)

    transform = osr.CoordinateTransformation(source, target)

    lat = []
    lon = []
    for xi, yi in zip(x, y):
        latr, lonr, _ = transform.TransformPoint(xi, yi)
        lat.append(latr)
        lon.append(lonr)

    return np.array(lat), np.array(lon)

def get_RTH_alt_above_takeoff_req(surf_arr, surf_alt_at_takeoff, alt):
    max_surf_in_area = np.nanmax(surf_arr)
    RTH_alt_above_takeoff_req = max_surf_in_area - surf_alt_at_takeoff + alt
    RTH_alt_above_takeoff_req_round_up = int(np.ceil(RTH_alt_above_takeoff_req / 25) * 25)
    return RTH_alt_above_takeoff_req_round_up

def get_extent_coords(x_coords, y_coords):
    min_extent_x = np.min(x_coords)
    max_extent_x = np.max(x_coords)

    min_extent_y = np.min(y_coords)
    max_extent_y = np.max(y_coords)

    min_extent = (min_extent_x, min_extent_y)
    max_extent = (max_extent_x, max_extent_y)

    return min_extent, max_extent