'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

import os
from . import plugin_load_settings
from .plugin_tools import (
    show_error,)
from .loading_functions import (get_source_and_target_crs_from_layer,
                                reproject_vector_layer,
                                reproject_coords, # UN-USED
                                load_raster)
from .functions import (buffer_extent, group_segments)
from .plotting import plot_with_colored_segments
from qgis.core import (QgsVectorLayer)
#from .class_definitions import Line, Point
from .flight_segment_class import Segment, plot_segment_samples
from .functions import extract_coords_from_line_layer, extract_coords_from_array_list
import numpy as np
from .save_data_functions import save_excel_file, \
    save_kml_lines_where_steep, \
    save_shapefile_lines_where_steep, \
    load_vector_layer_into_qgis
import shutil

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)
    flight_lines_input_path = settings_dict['Flight_lines']
    elevation_data_path = settings_dict['Elevation_Data_Raster']
    analysis_resolution_meters = settings_dict['analysis_resolution_meters']
    slope_percent_threshold = settings_dict['slope_percent_threshold']
    output_kml_lines_where_steep = settings_dict['output_kml_lines_where_steep']
    output_shp_lines_where_steep = settings_dict['output_shp_lines_where_steep']
    output_analysis_result_data_to_excel = settings_dict['output_analysis_result_data_to_excel']
    settings_dict = None # don't use settings_dict from here on

    flight_lines_input_layer = QgsVectorLayer(flight_lines_input_path,"flight_lines_input_path","ogr")

    if flight_lines_input_layer.isValid():
        lines_source_and_target_crs = get_source_and_target_crs_from_layer(flight_lines_input_layer)
    else:
        show_error('selected layer not valid')

    if not str(lines_source_and_target_crs['source_crs_epsg_int'])[:-2] in ['326', '327']:
        print(f"Will now convert lines to UTM zone {lines_source_and_target_crs['target_utm_num_int']} "
              f"'{lines_source_and_target_crs['target_utm_letter']}'")
        reprojected_lines_path = os.path.splitext(flight_lines_input_path)[0] + '_UTM.shp'

        reproject_vector_layer(flight_lines_input_layer,
                               reprojected_lines_path,
                               lines_source_and_target_crs['target_crs_epsg_int'])

        flight_lines_path = reprojected_lines_path
        flight_lines_layer = QgsVectorLayer(flight_lines_path, "flight_lines_path", "ogr")
        epsg_int = lines_source_and_target_crs['target_crs_epsg_int']

    else:
        flight_lines_path = flight_lines_input_path
        flight_lines_layer = flight_lines_input_layer
        epsg_int = lines_source_and_target_crs['source_crs_epsg_int']

    if not flight_lines_layer.isValid():
        show_error('selected layer not valid')


    extent = flight_lines_layer.extent()
    extent_dict = {"x_min": extent.xMinimum(),"x_max": extent.xMaximum(),
                   "y_min": extent.yMinimum(),"y_max": extent.yMaximum()}
    extent_buffered = buffer_extent(extent_dict, buffer_percent=25)
    surf_arr, surf_x_coords, surf_y_coords, surf_nodata_value, pix_size = \
        load_raster(elevation_data_path, extent_buffered, epsg_int)

    coords = extract_coords_from_line_layer(flight_lines_layer)
    segments = [Segment(two_tups[0], two_tups[1]) for two_tups in coords]

    surf_samples = []
    for seg_ind, seg in enumerate(segments):
        surf_sample, surf_telem = seg.sample_rast(surf_arr, surf_x_coords, surf_y_coords, 5)
        surf_samples.append(surf_sample)
        plot_segment_sampling = False
        if plot_segment_sampling:
            plot_segment_samples(*surf_telem)
            plot_segment_samples(*grnd_telem)

    # what each column represents:
    # surf_samples[0].T[0] -> distance along segment,
    # surf_samples[0].T[1] -> dist_to each side_of_seg,
    # surf_samples[0].T[2] -> alt,
    # surf_samples[0].T[3] -> UTME,
    # surf_samples[0].T[4] -> UTMN.

    regular_spaced = [seg.regular_spacing(analysis_resolution_meters, plot=False) for seg in segments]

    # what each column represents:
    # regular_spaced[0].T[0] -> distance along segment,
    # regular_spaced[0].T[1] -> empty (0),
    # regular_spaced[0].T[2] -> TBD,
    # regular_spaced[0].T[3] -> UTME,
    # regular_spaced[0].T[4] -> UTMN.

    for indx, (_surf_sample, _regular_spaced) in enumerate(zip(surf_samples, regular_spaced)):
        _regular_spaced_y = np.interp(_regular_spaced.T[0], _surf_sample.T[0], _surf_sample.T[2])
        regular_spaced[indx][:, 2] = _regular_spaced_y

    # what each column represents:
    # regular_spaced[0].T[0] -> distance along segment,
    # regular_spaced[0].T[1] -> empty (0),
    # regular_spaced[0].T[2] -> alt,
    # regular_spaced[0].T[3] -> UTME,
    # regular_spaced[0].T[4] -> UTMN.

    regular_spacing_per_segment = []
    total_x_distance_above_thresh_per_segment = []
    segment_len = []
    average_slope_per_segment = []
    for indx, (_surf_sample, _regular_spaced) in enumerate(zip(surf_samples, regular_spaced)):
        rise = np.diff(regular_spaced[indx][:, 2])
        run = np.diff(regular_spaced[indx][:, 0])
        regular_spacing_per_segment.append(run[0])
        slope_percent = rise / run * 100
        slope_percent = np.append(0, slope_percent) # append a zero to the end so that the size matches
        slope_percent = np.abs(slope_percent)
        regular_spaced[indx][:, 1] = slope_percent
        is_steep = slope_percent > slope_percent_threshold
        regular_spaced[indx] = np.column_stack((regular_spaced[indx], is_steep))
        run = np.append(0, run)
        total_x_distance_above_thresh_per_segment.append(np.sum(run[is_steep]))
        segment_len.append(np.sum(run))
        average_slope_per_segment.append(np.mean(slope_percent))

    total_x_distance_above_thresh = np.sum(np.array(total_x_distance_above_thresh_per_segment))
    all_segments_len_sum = np.sum(np.array(segment_len))
    percent_dist_above_thresh = total_x_distance_above_thresh / all_segments_len_sum * 100
    total_average_slope = np.mean(np.array(average_slope_per_segment))


    # what each column represents:
    # regular_spaced[0].T[0] -> distance along segment,
    # regular_spaced[0].T[1] -> slope_percent (following section),
    # regular_spaced[0].T[2] -> alt,
    # regular_spaced[0].T[3] -> UTME,
    # regular_spaced[0].T[4] -> UTMN.
    # regular_spaced[0].T[5] -> is steep? boolean cast to float (following section).

    grouped = [group_segments(_regular_spaced) for _regular_spaced in regular_spaced]

    accepted = plot_with_colored_segments(surf_samples, grouped, surf_x_coords, surf_y_coords, surf_arr,
                                            percent_dist_above_thresh, total_average_slope)
    if not accepted:
        return

    line_coords_tups_lat_lon = extract_coords_from_array_list(grouped, epsg_int)

    if output_shp_lines_where_steep:
        shp_file_path = os.path.splitext(flight_lines_input_path)[0] + '_steep_line_parts.shp'
        save_shapefile_lines_where_steep(line_coords_tups_lat_lon, shp_file_path)
        style_source_path = os.path.join(os.path.dirname(__file__), 'steep_lines_style.qml')
        style_dest_path = os.path.splitext(shp_file_path)[0] + '.qml'
        shutil.copyfile(style_source_path, style_dest_path)
        load_vector_layer_into_qgis(shp_file_path)

    if output_kml_lines_where_steep:
        kml_file_path = os.path.splitext(flight_lines_input_path)[0] + '_steep_line_parts.kml'
        save_kml_lines_where_steep(line_coords_tups_lat_lon, kml_file_path)
        os.startfile(kml_file_path)

    if output_analysis_result_data_to_excel:
        excel_file_path = os.path.splitext(flight_lines_input_path)[0] + '_analysis_result.xls'
        save_excel_file(segment_len,
                        average_slope_per_segment,
                        total_x_distance_above_thresh_per_segment,
                        excel_file_path)





