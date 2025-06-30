'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

import os
from . import plugin_load_settings, plugin_tools
from . import display_w_ties, display_no_ties
from .functions import \
    get_name, \
    get_crs,\
    save_excel_file,\
    get_pure_inpoly_name,\
    make_next_folder,\
    get_anchor_xy,\
    show_error,\
    extract_and_check_anchor_coordinates, \
    save_lines, \
    save_polygon,\
    load_vector_layer_into_qgis,\
    combine_kml_files,\
    open_different_kinds_of_input_polys

from .generate_lines import generate_lines
from .make_swaths import make_swaths
from .output_to_kml import \
    output_swaths_to_kml, \
    line_geometries_to_kml,\
    save_kml_polygon

import time
from qgis.core import QgsGeometry, QgsWkbTypes, QgsVectorLayer, QgsProcessing, QgsFeature
from  qgis import processing
import numpy as np

def main(settings_file_path):
    # load settings and allow for the re-naming of settings with a conversion step between the .json name and the internal code
    settings_dict = plugin_load_settings.run(settings_file_path)
    poly_file = settings_dict['Polygon_file']
    poly_buffer_distance = settings_dict['Polygon_buffer_distance']
    place_output_folder_into = settings_dict['Output_folder']
    Convert_to_specific_crs = settings_dict['Convert_to_specific_crs']
    open_KML_files_when_complete = settings_dict['Open_KML_files_when_complete']

    flight_line_angle = settings_dict['flight_line_angle']
    flight_line_spacing = settings_dict['flight_line_spacing']
    flight_line_buffer_distance = settings_dict['flight_line_buffer_distance']
    flight_line_shift_sideways = settings_dict['flight_line_shift_sideways']

    tie_line_spacing = settings_dict['tie_line_spacing']
    tie_line_buffer_distance = settings_dict['tie_line_buffer_distance']
    tie_lines_shift_sideways = settings_dict['tie_lines_shift_sideways']

    tie_line_box_buffer = settings_dict['flight_line_overshoot_after_intersection']

    anchor_coordinates_str = settings_dict['anchor_coordinates']
    merge_gaps_smaller_than = settings_dict['merge_gaps_smaller_than']
    delete_lines_smaller_than = settings_dict['delete_lines_smaller_than']

    ouput_mag = settings_dict['Mag']
    ouput_lidar = settings_dict['Lidar']
    ouput_ortho = settings_dict['Ortho']
    ouput_none = settings_dict['None']

    swath_width = settings_dict['swath_width']
    settings_dict = None # don't use settings_dict from here on

    output_swaths = False
    output_swaths = ouput_lidar or ouput_ortho or ouput_none

    if not os.path.exists(poly_file):
        message = f"File does not not exist: " \
                  f"\n{poly_file} "
        show_error(message)
        return

    poly_file, poly_layer, utm_letter = open_different_kinds_of_input_polys(poly_file, Convert_to_specific_crs)


    if poly_buffer_distance != 0:
        # Create a new memory layer for the buffered features
        buffered_layer = QgsVectorLayer("Polygon?crs=" + poly_layer.crs().authid(), "Buffered", "memory")
        buffered_provider = buffered_layer.dataProvider()
        buffered_provider.addAttributes(poly_layer.fields())
        buffered_layer.updateFields()

        # Parameters for the buffer operation:
        buffer_distance = poly_buffer_distance

        # Iterate over each feature and apply the miter buffer
        for feat in poly_layer.getFeatures():
            geom = feat.geometry()
            # Create a buffered geometry with miter join style
            buffered_geom = geom.buffer(buffer_distance, 5, QgsGeometry.EndCapStyle.Flat, QgsGeometry.JoinStyle.Miter, 5)
            new_feat = QgsFeature()
            new_feat.setGeometry(buffered_geom)
            new_feat.setAttributes(feat.attributes())
            buffered_provider.addFeature(new_feat)

        buffered_layer.updateExtents()
    else:
        buffered_layer = poly_layer

    anchor_xy = extract_and_check_anchor_coordinates(anchor_coordinates_str, buffered_layer)
    generated_anchor_coordinates = False
    if anchor_xy is None:
        print('auto generating anchor coordinates')
        anchor_xy = get_anchor_xy(buffered_layer)
        generated_anchor_coordinates = True

    the_rest_of_the_flt_line_gen_params = (flight_line_spacing,
                                           flight_line_angle,
                                           flight_line_shift_sideways,
                                           merge_gaps_smaller_than,
                                           delete_lines_smaller_than,
                                           anchor_xy)

    if not tie_line_spacing == 0:

        flt_lines = generate_lines(buffered_layer,
                                   tie_line_box_buffer,# this is set to buffer the shape differently
                                   *the_rest_of_the_flt_line_gen_params)

        the_rest_of_the_tie_line_gen_params = (
                       tie_line_spacing,
                       flight_line_angle+90,
                       tie_lines_shift_sideways,
                       merge_gaps_smaller_than,
                       delete_lines_smaller_than,
                       anchor_xy)

        tie_lines = generate_lines(buffered_layer,
                                   tie_line_box_buffer,# this is set to buffer the shape differently
                                   *the_rest_of_the_tie_line_gen_params)

        results = display_w_ties.gui(buffered_layer,
                                                                   flt_lines,
                                                                   tie_lines,
                                                                   flight_line_spacing,
                                                                   tie_line_spacing,
                                                                   tie_line_box_buffer,
                                                                   anchor_xy,
                                                                   generated_anchor_coordinates,
                                                                   flight_line_buffer_distance,
                                                                   tie_line_buffer_distance,
                                                                   the_rest_of_the_flt_line_gen_params,
                                                                   the_rest_of_the_tie_line_gen_params,
                                                                   poly_layer)

        if results[0]:
            (result,
             new_flt_lines,
             new_tie_lines,
             new_poly,
             the_rest_of_the_flt_line_gen_params,
             the_rest_of_the_tie_line_gen_params) = results
        else:
            result = results[0]

    else:
        flt_lines = generate_lines(buffered_layer,
                                   flight_line_buffer_distance,
                                   *the_rest_of_the_flt_line_gen_params
                                   )

        new_tie_lines = []
        results = display_no_ties.gui(buffered_layer,
                                                              flt_lines,
                                                              anchor_xy,
                                                              generated_anchor_coordinates,
                                                              flight_line_buffer_distance,
                                                              the_rest_of_the_flt_line_gen_params,
                                                              poly_layer)

        if results[0]:
            (result,
             new_flt_lines,
             new_poly,
             the_rest_of_the_flt_line_gen_params) = results
        else:
            result = results[0]

    if result:
        combined_lines = [QgsGeometry(obj) for obj in new_flt_lines+new_tie_lines]
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        style_folder = os.path.join(plugin_dir,'style_files')
        crs = get_crs(poly_layer)
        pure_name = get_pure_inpoly_name(poly_file)

        if ouput_mag:
            sensor_suffix = '_MAG'
        if ouput_lidar:
            sensor_suffix = '_LIDAR'
        if ouput_ortho:
            sensor_suffix = '_ORTHO'
        if ouput_none:
            sensor_suffix = ''

        pure_name += sensor_suffix

        suffix = '_output_package'
        out_folder_pure_name = pure_name + suffix

        if place_output_folder_into.lower() in ['', 'empty', 'auto']:
            out_folder_path, version = make_next_folder(os.path.dirname(poly_file),
                                                        out_folder_pure_name)
        else:
            out_folder_path, version = make_next_folder(place_output_folder_into,
                                                        out_folder_pure_name)

        lines_out_path = os.path.join(out_folder_path, f'LINES_{pure_name}{version}.shp')
        poly_out_path = os.path.join(out_folder_path, f'POLY_{pure_name}{version}.shp')
        excel_out_path = os.path.join(out_folder_path, f'META_DATA_{pure_name}{version}.xls')
        if output_swaths:
            swaths_out_path = os.path.join(out_folder_path, f'SWATHS_{pure_name}{version}.shp')

        lines_style_source = os.path.join(style_folder, 'LINES_STYLE.qml')
        save_lines(new_flt_lines, new_tie_lines, lines_out_path, crs, lines_style_source)
        lines_out_kml_path = lines_out_path[:-4] + '.kml'
        line_geometries_to_kml(new_flt_lines.copy() + new_tie_lines.copy(), lines_out_kml_path, crs)

        poly_style_source = os.path.join(style_folder, 'POLY_STYLE.qml')
        save_polygon(new_poly, poly_out_path, crs, poly_style_source)
        poly_out_kml_path = poly_out_path[:-4] + '.kml'
        save_kml_polygon(new_poly, poly_out_kml_path, crs)

        swaths_out_kml_path = ''
        if output_swaths:
            swath_style_source = os.path.join(style_folder, 'SWATH_STYLE.qml')
            make_swaths(lines_out_path, swaths_out_path, swath_width, crs, swath_style_source)
            swaths_out_kml_path = swaths_out_path[:-4]+'.kml'
            output_swaths_to_kml(swaths_out_path, swaths_out_kml_path)

        flight_line_angle = the_rest_of_the_flt_line_gen_params[1]

        save_excel_file(excel_out_path, new_poly, combined_lines, crs, utm_letter, flight_line_spacing, tie_line_spacing, flight_line_angle)

        kmls_to_combine_paths = [swaths_out_kml_path, lines_out_kml_path, poly_out_kml_path]
        combined_kml_path = os.path.join(out_folder_path, f'Combined_kmls_{pure_name}{version}.kml')
        combine_kml_files(kmls_to_combine_paths, combined_kml_path)

        print('done saving')
        #group_name = pure_name + version # not implemeted cuz qgis is buggy with adding them to a group
        if output_swaths:
            load_vector_layer_into_qgis(swaths_out_path)
        load_vector_layer_into_qgis(lines_out_path)
        load_vector_layer_into_qgis(poly_out_path)
        print('done loading into qgis')
        if open_KML_files_when_complete:
            os.startfile(combined_kml_path)
            print('done loading kmls')