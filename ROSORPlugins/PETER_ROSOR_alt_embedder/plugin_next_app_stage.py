'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

import os
from PyQt5.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsVectorLayer
from . import load_data, buffer_points, drape_wps_over_buffer, plot_and_accept
from .load_data import (
    get_source_and_target_crs_from_layer,
    raster_convert_to_meters_crs)
from .tools import (
    remove_duplicates,
    compute_heading,
    compute_heading_for_samples,
    compute_vertical_distances,
    add_UAV_alt_col,
    simple_sample_arr,
    compute_max_point_radius,
    convert_coords_UTM2LATLON,
    get_RTH_alt_above_takeoff_req,
    extract_2D_subarray_with_buffer,
    get_extent_coords,
    show_error,
    get_whether_midline,
    get_new_folder_name,
    remove_steep_angles)

from .flight_segment_class import Segment, plot_segment_samples, merge_segments
from .package_output import (
    lat_lon_UAValt_turnRad_to_DJI_wp_kmz,
    lat_lon_to_DJI_with_P1_corridor_kmz,
    lat_lon_UAValt_turnRad_heading_to_DJI_with_P1_wp_kmz,
    lat_lon_UAValt_to_mp_wp,
    lat_lon_UAValt_to_altaX_QGC_Plan)
from . import plugin_load_settings
import numpy as np
import sys
import re

# PROFILER CHUNK 1/3 START ////////////////////////////////////////////////////////////////////////////////////
#import cProfile
#import pstats
#import io
# PROFILER CHUNK 1/3 END ////////////////////////////////////////////////////////////////////////////////////

def get_list_of_paths_os_walk_folder(folder_path, ext):
    file_paths = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if os.path.splitext(filename)[1].lower() == ext.lower():
                file_path = os.path.join(root, filename)
                file_paths.append(file_path)

    def natural_sort_key(s):
        # This function will create a sort key that handles numbers properly
        return [int(text) if text.isdigit() else text.lower() for text in re.split('(\d+)', s)]

    file_paths.sort(key=natural_sort_key)
    return file_paths

def main(settings_file_path):
    # PROFILER CHUNK 2/3 START ////////////////////////////////////////////////////////////////////////////////////
    #pr = cProfile.Profile()
    #pr.enable()
    # PROFILER CHUNK 2/3 END ////////////////////////////////////////////////////////////////////////////////////

    # load settings and allow for the re-naming of settings with a conversion step between the .json name and the internal code
    settings_dict = plugin_load_settings.run(settings_file_path)

    run_file_not_folder = settings_dict['🗏  A singe 2D flight file']
    waypoint_folder = settings_dict['📂 2D flights folder']
    input_waypoint_file = settings_dict['🗏 2D flight file']

    surface_geotiff = settings_dict['surface_geotiff']
    no_elevation_data = settings_dict['no_elevation_data']
    elevation_geotiff = settings_dict['elevation_geotiff']


    closest_allowable_dist_between_waypoints = float(settings_dict['closest_allowable_dist_between_waypoints'])
    horizontal_safety_buffer_per_side = float(settings_dict['horizontal_safety_buffer_per_side'])
    payload_separation_from_surface = float(settings_dict['payload_separation_from_surface'])
    payload_distance_from_ground = float(settings_dict['payload_distance_from_ground'])
    reg_dist = float(settings_dict['regular_distance_between_waypoints'])
    payload_rope_length = float(settings_dict['payload_rope_length'])
    speed = float(settings_dict['flight_speed'])
    max_turn_radius = float(settings_dict['max_turn_radius'])
    max_slope_percent = float(settings_dict['max_slope_percent'])

    geotiffs_vertical_datum_is_ASL = settings_dict['geotiffs_vertical_datum_is_ASL']
    skip_flights_where_geotiff_data_missing = settings_dict['Skip flights where Geotiff data is missing']

    create_mag_flight = settings_dict['DJI Mag or Lidar Flight']
    create_ortho_photo_waypoint_flight = settings_dict['DJI Ortho Photo Flight']
    create_as_mission_planner_waypoints = settings_dict['Ardupilot 3D Waypoints']
    #create_as_PX4_waypoints = settings_dict['PX4 3D Waypoints']
    altaX_QGC_Plan = settings_dict['AltaX QGC Plan']

    auto_accept = settings_dict['No manual checking']
    manually_remove_noise = settings_dict["Manually remove noise"]
    detect_noise_distance = settings_dict["Detect noise distance"]

    create_ortho_photo_corridor_flight = False
    settings_description = settings_dict.copy()
    settings_dict = None # don't use settings_dict from here on

    plot_details = False

    #raise ('yo chillll bruh')

    #output_selections = [create_mag_flight,
    #                     create_ortho_photo_waypoint_flight,
    #                     create_ortho_photo_corridor_flight]
    #true_count = sum(map(int, output_selections))
    #if true_count > 1:
    #    message = 'Select only one of the output options please.'
    #    show_error(message)

    if no_elevation_data:
        elevation_geotiff = surface_geotiff

    if not run_file_not_folder:
        new_waypoint_folder = get_new_folder_name(waypoint_folder)
        waypoint_files_kml = get_list_of_paths_os_walk_folder(waypoint_folder, ".kml")
        waypoint_files_shp = get_list_of_paths_os_walk_folder(waypoint_folder, ".shp")
        if len(waypoint_files_kml) == 0:
            waypoint_files = waypoint_files_shp
        elif len(waypoint_files_shp) == 0:
            waypoint_files = waypoint_files_kml
        else:
            assert False, 'Mixed files types detected, you should either have .kml or .shp inputs exclusively'

        waypoint_file_path = os.path.join(waypoint_folder, waypoint_files[0])
        waypoint_file_used_to_determine_target_crs = waypoint_file_path
    else:
        waypoint_file_used_to_determine_target_crs = input_waypoint_file
        waypoint_files = [input_waypoint_file]

    wpt_layer = QgsVectorLayer(waypoint_file_used_to_determine_target_crs,
                               "file_used_to_determine_target_crs",
                               "ogr")
    if wpt_layer.isValid():
        wp_source_and_target_crs = get_source_and_target_crs_from_layer(wpt_layer)
    else:
        message = 'selected layer not valid'
        show_error(message)

    # load geotiffs
    # the coords are of the bottom left of the pixel.
    surf_arr, surf_x_coords, surf_y_coords, surf_nodata_value, surf_epsg = \
        load_data.raster(surface_geotiff,wp_source_and_target_crs['target_crs_epsg_int'])
    grnd_arr, grnd_x_coords, grnd_y_coords, grnd_nodata_value, grnd_epsg = \
        load_data.raster(elevation_geotiff,wp_source_and_target_crs['target_crs_epsg_int'])
    if surf_epsg != grnd_epsg:
        show_error(f"The surface and ground geotiffs must have the same epsg!")
    common_epsg = surf_epsg

    if len(waypoint_files) == 0:
        err_message = f"There are no .kml or .shp files in the waypoint folder!"
        QMessageBox.critical(None, "Error", err_message)
        raise ValueError(err_message)
    for waypoint_filename in waypoint_files:
        waypoint_file = os.path.join(waypoint_folder, waypoint_filename)
        # load 2D waypoints
        wpts_xy = load_data.waypoints(waypoint_file, common_epsg)
        segments_srts_ends = zip(wpts_xy[:-1], wpts_xy[1:])
        segments = [Segment(two_tups[0], two_tups[1]) for two_tups in segments_srts_ends]
        if closest_allowable_dist_between_waypoints > min([seg.length for seg in segments]):
            err_message = f"input waypoints violate the provided setting 'closest_allowable_dist_between_wp'"
            QMessageBox.critical(None, "Error", err_message)
            raise ValueError(err_message)

        #check that there is at least some overlap between the geotiffs and the waypoints

        coords_array = np.array(wpts_xy)
        # Finding the extent (min and max for x and y)
        x_min, y_min = np.min(coords_array, axis=0)
        x_max, y_max = np.max(coords_array, axis=0)
        extent = (x_min, x_max, y_min, y_max)

        # Finding extents for surf and grnd coordinates
        surf_extent = (np.min(surf_x_coords), np.max(surf_x_coords), np.min(surf_y_coords), np.max(surf_y_coords))
        grnd_extent = (np.min(grnd_x_coords), np.max(grnd_x_coords), np.min(grnd_y_coords), np.max(grnd_y_coords))

        # Checking if wpts_xy is within surf_extent and grnd_extent
        wpts_within_surf = all(x_min >= surf_extent[0] and x_max <= surf_extent[1] and
                               y_min >= surf_extent[2] and y_max <= surf_extent[3] for x_min, x_max, y_min, y_max in
                               [extent])
        wpts_within_grnd = all(x_min >= grnd_extent[0] and x_max <= grnd_extent[1] and
                               y_min >= grnd_extent[2] and y_max <= grnd_extent[3] for x_min, x_max, y_min, y_max in
                               [extent])

        wpts_are_wthin_bounds = wpts_within_surf and wpts_within_grnd
        if not wpts_are_wthin_bounds:
            if not skip_flights_where_geotiff_data_missing:
                err_message = f"The waypoints are not within the bounds of the provided geotiffs!"
                QMessageBox.critical(None, "Error", err_message)
                raise ValueError(err_message)
            else:
                print("Skipping a flight where Geotiff data is missing")
                continue

        # sample the geotiffs
        sample_rect_width = horizontal_safety_buffer_per_side * 2
        surf_samples = []
        grnd_samples = []
        for seg_ind, seg in enumerate(segments):
            if seg_ind > 0:
                pass # look at all segments
                # continue # temp just look at first segment
            surf_sample, surf_telem = seg.sample_rast(surf_arr, surf_x_coords, surf_y_coords, sample_rect_width)
            surf_samples.append(surf_sample)
            grnd_sample, grnd_telem = seg.sample_rast(grnd_arr, grnd_x_coords, grnd_y_coords, sample_rect_width)
            grnd_samples.append(grnd_sample)
            plot_segment_sampling = False
            if plot_segment_sampling:
                plot_segment_samples(*surf_telem)
                plot_segment_samples(*grnd_telem)

        # segments generate regularly spaced 2D waypoints for output
        regular_spaced = [seg.regular_spacing(reg_dist, plot=False) for seg in segments]

        # surf / grnd samples and regular_spaced format what each col represents
        #0-dist_allong_seg,
        #1-dist_to each side_of_seg,
        #2-alt,
        #3-UTME
        #4-UTMN

        segs_lengths = [seg.length for seg in segments]
        regular_spaced_merged = merge_segments(regular_spaced, segs_lengths)
        regular_spaced_merged = remove_duplicates(regular_spaced_merged, print_number_of_dupes=False)
        surf_samples_merged = merge_segments(surf_samples, segs_lengths)
        grnd_samples_merged = merge_segments(grnd_samples, segs_lengths)

        # re-naming
        new_waypoints = regular_spaced_merged

        test_samples = False
        if test_samples:
            for row in surf_samples_merged[:20,:]:
                print(', '.join(map(str, list(row))))

        # surf / grnd samples_merged and new_waypoints format what each col represents
        #0-dist_allong_whole_flight,
        #1-dist_allong_seg,
        #2-dist_to each side_of flight path,
        #3-alt,
        #4-UTME
        #5-UTMN
        #6-seg_number

        buffer_line = buffer_points.run(grnd_samples_merged.T[0], grnd_samples_merged.T[3],
                                        payload_distance_from_ground, grnd_nodata_value,
                                        surf_samples_merged.T[0], surf_samples_merged.T[3],
                                        payload_separation_from_surface, surf_nodata_value, detect_noise_distance,
                                        skip_flights_where_geotiff_data_missing, manually_remove_noise,
                                        plot=plot_details)

        if buffer_line is None:
            print("Skipping a flight where Geotiff data is missing")
            continue

        # TEMP plot buffer line buffer_line and new_waypoints.T[0]
        #import matplotlib.pyplot as plt
        #plt.plot(buffer_line[0], buffer_line[1], 'r')
        #plt.show()
        #pass

        new_waypoints.T[3] = drape_wps_over_buffer.run(buffer_line,
                                                               new_waypoints.T[0],
                                                               plot=plot_details)

        new_waypoints = compute_heading(new_waypoints)
        # Compute heading for samples
        surf_samples_merged = compute_heading_for_samples(surf_samples_merged, new_waypoints)
        grnd_samples_merged = compute_heading_for_samples(grnd_samples_merged, new_waypoints)

        # Compute distances for samples
        surf_samples_merged = compute_vertical_distances(surf_samples_merged, new_waypoints)
        grnd_samples_merged = compute_vertical_distances(grnd_samples_merged, new_waypoints)

        new_waypoints.T[3] = remove_steep_angles(new_waypoints.T[0], new_waypoints.T[3], max_slope_percent, plot=False)

        new_waypoints = add_UAV_alt_col(new_waypoints, payload_rope_length)

        # surf / grnd samples_merged and new_waypoints format what each col represents
        # 0-dist_allong_whole_flight,
        # 1-dist_allong_seg,
        # 2-dist_to each side_of flight path,
        # 3-alt,
        # 4-UTME
        # 5-UTMN
        # 6-seg_number
        # 7-heading
        # 8-(if samples: vert_dist) OR (if new_waypoints: UAV_alt)

        #extract_smaller_parts_of_dsm_dem
        # extent of waypoints
        min_extent_coord, max_extent_coord = get_extent_coords(new_waypoints.T[4], new_waypoints.T[5])

        # calulate buffer based on being 30% the max extent of waypoints
        buff_percent = 30
        buffer = max([max_extent_coord[0] - min_extent_coord[0],
                      max_extent_coord[1] - min_extent_coord[1]]) * buff_percent / 100

        # Extract a subarray of the dsm and dem with a buffer
        surf_arr_smol, surf_x_smol, surf_y_smol = extract_2D_subarray_with_buffer(surf_arr, surf_x_coords, surf_y_coords,
                                                                                 buffer, min_extent_coord, max_extent_coord)
        grnd_arr_smol, grnd_x_smol, grnd_y_smol = extract_2D_subarray_with_buffer(grnd_arr, grnd_x_coords, grnd_y_coords,
                                                                                 buffer, min_extent_coord, max_extent_coord)
        surf_arr_smol[surf_arr_smol == surf_nodata_value] = np.nan
        grnd_arr_smol[grnd_arr_smol == grnd_nodata_value] = np.nan


        skip_plot = False
        if skip_plot or create_ortho_photo_corridor_flight or auto_accept:
            accepted = True
        else:
            accepted = plot_and_accept.run(waypoints=new_waypoints,
                                           dsm=(surf_arr_smol, surf_x_smol, surf_y_smol),
                                           dem=(grnd_arr_smol, grnd_x_smol, grnd_y_smol),
                                           surf_samples=surf_samples_merged,
                                           grnd_samples=grnd_samples_merged)

        if not accepted:
            pass
            #sys.exit()

        print(f'accepted: {accepted}')
        if not accepted:
            break
        # The following is applicable to DJI M300 RTK

        point_radii = compute_max_point_radius(new_waypoints.T[4], new_waypoints.T[5], max_turn_radius)

        # new_waypoints col index 9 (new_waypoints.T[9]) is point turn radius
        new_waypoints = np.column_stack((new_waypoints, point_radii))

        # load the tiff that converts ellipsoid to ASL via EGM96
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        path_egm96 = os.path.join(plugin_dir, "convert_ellipsoid_to_ASL_with_EGM96.tif")

        egm96_sampled = load_data.sample_lat_lon_tiff(path_egm96, common_epsg,
                                                      new_waypoints.T[4], new_waypoints.T[5])

        if geotiffs_vertical_datum_is_ASL:
            # new_waypoints col index 10 is UAV altitude above sea level
            new_waypoints = np.column_stack((new_waypoints, new_waypoints.T[8]))
            new_waypoints.T[8] = new_waypoints.T[8]+egm96_sampled
        else:
            # new_waypoints col index 10 is UAV altitude above sea level
            new_waypoints = np.column_stack((new_waypoints, new_waypoints.T[8]-egm96_sampled))


        lat, lon = convert_coords_UTM2LATLON(new_waypoints.T[4], new_waypoints.T[5],
                                                source_epsg=common_epsg)

        # new_waypoints col index 11 is latitude index 12 is longitude
        new_waypoints = np.column_stack((new_waypoints, lat, lon))

        # new_waypoints format what each col represents
        # 0-dist_allong_whole_flight
        # 1-dist_allong_seg
        # 2-dist_to each side_of flight path
        # 3-sensor_alt ellipsoid
        # 4-UTME
        # 5-UTMN
        # 6-seg_number
        # 7-heading
        # 8-UAV_alt ellipsoid
        # 9-point turn radius
        # 10-UAV altitude above sea level
        # 11-latitude
        # 12-longitude

        og_waypoint_filename = os.path.splitext(os.path.basename(waypoint_file))[0]

        surf_alt_at_takeoff = surf_samples_merged.T[3][np.argmin(np.abs(surf_samples_merged.T[0]))]

        RTH_alt_above_takeoff_req = get_RTH_alt_above_takeoff_req(surf_arr_smol,
                                                                  surf_alt_at_takeoff,
                                                                  max([payload_separation_from_surface,
                                                                       payload_distance_from_ground]))

        new_waypoint_filename = og_waypoint_filename + f'_RTH{RTH_alt_above_takeoff_req}m.kmz'
        if not run_file_not_folder:
            if not os.path.exists(new_waypoint_folder):
                os.mkdir(new_waypoint_folder)

            # Extract the relative path from the waypoint_file by removing the waypoint_folder part
            relative_path = os.path.relpath(waypoint_file, waypoint_folder)

            # Combine the new_waypoint_folder with the relative path and new filename
            new_waypoint_filepath = os.path.join(new_waypoint_folder, os.path.dirname(relative_path), new_waypoint_filename)

        else:
            input_waypoint_file_parent_dir = os.path.dirname(os.path.dirname(input_waypoint_file))
            new_waypoint_filepath = os.path.join(input_waypoint_file_parent_dir,new_waypoint_filename)

        if create_mag_flight:
            lat_lon_UAValt_turnRad_to_DJI_wp_kmz(output_file_path=new_waypoint_filepath,
                                                 settings_description=settings_description,
                                                 lat=new_waypoints.T[11],
                                                 lon=new_waypoints.T[12],
                                                 UAValtAsl=new_waypoints.T[10],
                                                 UAValtEll=new_waypoints.T[8],
                                                 turnRad=new_waypoints.T[9],
                                                 speed=speed)

        if create_ortho_photo_waypoint_flight:
            is_midline = get_whether_midline(new_waypoints.T[6])
            lat_lon_UAValt_turnRad_heading_to_DJI_with_P1_wp_kmz(output_file_path=new_waypoint_filepath,
                                                                 lat=new_waypoints.T[11],
                                                                 lon=new_waypoints.T[12],
                                                                 UAValtAsl=new_waypoints.T[10],
                                                                 UAValtEll=new_waypoints.T[8],
                                                                 turnRad=new_waypoints.T[9],
                                                                 heading=new_waypoints.T[7],
                                                                 is_midline=is_midline,
                                                                 speed=speed)

        if create_as_mission_planner_waypoints:
            lat_lon_UAValt_to_mp_wp(output_file_path=new_waypoint_filepath,
                                    lats=new_waypoints.T[11],
                                    lons=new_waypoints.T[12],
                                    UAValtAsls=new_waypoints.T[10])

        if altaX_QGC_Plan:
            lat_lon_UAValt_to_altaX_QGC_Plan(output_file_path=new_waypoint_filepath,
                                             lats=new_waypoints.T[11],
                                             lons=new_waypoints.T[12],
                                             UAValtAsls=new_waypoints.T[10],
                                             heading=new_waypoints.T[7])

        if create_ortho_photo_corridor_flight:
            lat_lon_to_DJI_with_P1_corridor_kmz(output_file_path=new_waypoint_filepath,
                                                lat=new_waypoints.T[11],
                                                lon=new_waypoints.T[12],
                                                speed=speed)



        # Create a vector layer
        kmz_layer = QgsVectorLayer(new_waypoint_filepath, f"{new_waypoint_filename}", "ogr")

        # PROFILER CHUNK 3/3 START ////////////////////////////////////////////////////////////////////////////////////
        #pr.disable()
        #s = io.StringIO()
        #sortby = 'cumulative'  # Can be 'calls', 'time', 'cumulative', etc.
        #ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        #ps.print_stats()
        #print(s.getvalue())
        # PROFILER CHUNK 3/3  TEMP END ////////////////////////////////////////////////////////////////////////////////////


        # Check if the layer is valid
        if not kmz_layer.isValid():
            print("Layer failed to load!")
        else:
            # Add the layer to the map
            QgsProject.instance().addMapLayer(kmz_layer)
        "temp start"

