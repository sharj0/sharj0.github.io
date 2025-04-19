'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from . import plugin_tools
from . import plotting
from .loading_functions import (get_source_and_target_crs_from_layer,
                                reproject_vector_layer,
                                extract_line_obj_from_line_layer,
                                extract_tof_obj_from_tof_layer)

from qgis.core import QgsVectorLayer


from .qgis_gui import run_qgis_gui
from qgis.utils import iface

from . import validate_inputs
from .Global_Singleton import Global_Singleton
from .functions import (sort_lines_and_tofs,
                        get_name_of_non_existing_output_file,
                        load_pickle,
                        ColorCycler,
                        construct_the_upper_hierarchy,
                        construct_the_lower_hierarchy)
import os
import numpy as np
from .plugin_tools import show_error

import pickle

class Save_Pickle():
    def __init__(self):
        pass


def make_new_flights(settings_dict):
    plugin_global = Global_Singleton()
    flight_lines_input_path = settings_dict["Flight lines file_path"]
    tof_points_input_path = settings_dict["Take-off file path"]
    max_flt_size = settings_dict["max_flt_size"]
    max_number_of_lines_per_flight = settings_dict["max_number_of_lines_per_flight"]
    line_flight_order_reverse = settings_dict["line_flight_order_reverse"]
    prefer_even_number_of_lines = settings_dict["prefer_even_number_of_lines"]
    flight_settings = {
        "lead_in": settings_dict["lead_in"],
        "lead_out": settings_dict["lead_out"],
        "add_smooth_turns": settings_dict["add_smooth_turns"],
        "turn_segment_length": settings_dict["turn_segment_length"],
        "turn_diameter": settings_dict["turn_diameter"],
        "line_direction_reverse": settings_dict["line_direction_reverse"]
    }
    settings_dict_for_pickle = settings_dict.copy()
    settings_dict = None # don't use settings_dict from here on

    flight_lines_input_layer = QgsVectorLayer(flight_lines_input_path, "flight_lines_input_path", "ogr")

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
    else:
        flight_lines_path = flight_lines_input_path
        flight_lines_layer = flight_lines_input_layer
    if not flight_lines_layer.isValid():
        show_error('selected layer not valid')

    global_crs_target = {key: value for key, value in lines_source_and_target_crs.items() if 'target' in key}

    tof_points_input_layer = QgsVectorLayer(tof_points_input_path, "tof_points_input_path", "ogr")
    if not int(tof_points_input_layer.crs().authid().replace("EPSG:",'')) == global_crs_target['target_crs_epsg_int']:
        print(f"Will now convert tof points to UTM zone {global_crs_target['target_utm_num_int']} "
              f"'{global_crs_target['target_utm_letter']}'")
        reprojected_tof_points_path = os.path.splitext(tof_points_input_path)[0] + '_UTM.shp'

        reproject_vector_layer(tof_points_input_layer,
                               reprojected_tof_points_path,
                               global_crs_target['target_crs_epsg_int'])
        tof_points_path = reprojected_tof_points_path
        tof_points_layer = QgsVectorLayer(tof_points_path, "tof_points_path", "ogr")
    else:
        tof_points_path = tof_points_input_path
        tof_points_layer = tof_points_input_layer
    if not tof_points_layer.isValid():
        show_error('selected layer not valid')

    show_feedback_popup = False
    lines, user_assigned_unique_strip_letters = extract_line_obj_from_line_layer(flight_lines_layer, flight_lines_path)
    tofs = extract_tof_obj_from_tof_layer(tof_points_layer, tof_points_path, show_feedback_popup=show_feedback_popup)

    unique_strip_letters = validate_inputs.validate_and_process_lines(lines, user_assigned_unique_strip_letters)

    if not line_flight_order_reverse:
        sort_angle = (plugin_global.ave_line_ang_cwN + 90) % 360
    else:
        sort_angle = (plugin_global.ave_line_ang_cwN - 90) % 360

    # sort
    lines, tofs = sort_lines_and_tofs(lines, tofs, sort_angle)

    '''
    parent_line_groups = [line.parent_line_group for line in lines]
    num_chil = [len(line_group.children) for line_group in parent_line_groups]
    '''

    survey_area = construct_the_upper_hierarchy(lines, tofs, unique_strip_letters, prefer_even_number_of_lines)
    survey_area.global_crs_target = global_crs_target
    survey_area.flight_settings = flight_settings
    survey_area.color_cycle = ColorCycler()
    construct_the_lower_hierarchy(survey_area,
                                  max_flt_size,
                                  max_number_of_lines_per_flight,
                                  prefer_even_number_of_lines)

    survey_area.rename_everything()
    survey_area.recolor_everything()
    survey_area.past_states = []
    survey_area.initial_creation_stage = False
    return survey_area


def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    do_load_pickle = settings_dict["🔧Modify Existing Flights"]

    base_name = "saved_flights._2D_flts"

    if not do_load_pickle:
        flight_lines_input_path = settings_dict["Flight lines file_path"]
        pickle_obj = make_new_flights(settings_dict)
        pickle_path_out = os.path.join(os.path.dirname(flight_lines_input_path), base_name)

    else:
        pickle_path_in = settings_dict["🔧Modify Existing Flights file"]
        pickle_obj = load_pickle(pickle_path_in)
        pickle_path_out = os.path.join(os.path.dirname(pickle_path_in), base_name)

    pickle_path_out = get_name_of_non_existing_output_file(pickle_path_out)
    pickle_obj.current_pickle_path_out = pickle_path_out
    with open(pickle_path_out, 'wb') as file:
        pickle.dump(pickle_obj, file)

    ''' obj hierarchy
    pickle_obj.strips
    ↳ strip.fa_list
    ↳↳ flight_area.children_flights
    ↳↳↳ flight.sorted_line_list
    ↳↳↳↳ line.start line.end
    ↳↳↳↳↳ line_end.xy
    '''

    run_qgis_gui(iface, pickle_obj)






