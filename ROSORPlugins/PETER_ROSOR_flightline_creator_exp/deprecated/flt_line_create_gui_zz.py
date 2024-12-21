import os
from PyQt5.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsVectorLayer
from . import load_data, buffer_points, drape_wps_over_buffer
from .tools import \
    remove_duplicates, \
    compute_heading, \
    compute_heading_for_samples, \
    compute_vertical_distances, \
    add_UAV_alt_col, \
    simple_sample_arr, \
    compute_max_point_radius,\
    convert_coords_UTM2LATLON, \
    get_RTH_alt_above_takeoff_req, \
    extract_2D_subarray_with_buffer, \
    get_extent_coords
from .flight_segment_class import Segment, plot_segment_samples, merge_segments
from .package_output import lat_lon_UAValt_turnRad_to_DJI_kmz
import numpy as np
import sys

from . import plot_and_accept

def flt_line_create_window(settings_file_path):
    # load settings and allow for the re-naming of settings with a conversion step between the .json name and the internal code
    settings_dict = load_data.settings(settings_file_path)
    surface_geotiff = settings_dict['surface_geotiff']
    elevation_geotiff = settings_dict['elevation_geotiff']
    waypoint_folder = settings_dict['waypoint_folder']
    closest_allowable_dist_between_waypoints = float(settings_dict['closest_allowable_dist_between_waypoints'])
    horizontal_safety_buffer_per_side = float(settings_dict['horizontal_safety_buffer_per_side'])
    payload_separation_from_surface = float(settings_dict['payload_separation_from_surface'])
    payload_distance_from_ground = float(settings_dict['payload_distance_from_ground'])
    reg_dist = float(settings_dict['regular_distance_between_waypoints'])
    payload_rope_length = float(settings_dict['payload_rope_length'])
    speed = float(settings_dict['flight_speed'])
    settings_dict = None # don't use settings_dict from here on

    accepted = plot_and_accept.run()



