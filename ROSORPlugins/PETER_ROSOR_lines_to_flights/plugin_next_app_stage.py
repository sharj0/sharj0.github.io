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

from qgis.core import QgsVectorLayer, QgsFeature, QgsWkbTypes


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
from .cutting_and_extending_lines import cut_and_extend_lines
from .filter_lines import filter_lines_by_type

import os
import numpy as np
from .plugin_tools import show_error

import pickle
from itertools import compress

class Save_Pickle():
    def __init__(self):
        pass

def make_new_flights(settings_dict):
    plugin_global = Global_Singleton()
    tof_points_input_path = settings_dict["Take-off file"]
    max_flt_size = settings_dict["max_flt_size"]
    max_number_of_lines_per_flight = settings_dict["max_number_of_lines_per_flight"]
    line_flight_order_reverse = settings_dict["line_flight_order_reverse"]
    prefer_even_number_of_lines = settings_dict["prefer_even_number_of_lines"]
    hussein_drone_swarm = settings_dict["Hussein Drone Swarm Generation"]
    flight_settings = {
        "max_flight_size": settings_dict["max_flt_size"],
        "lead_in": settings_dict["lead_in"],
        "lead_out": settings_dict["lead_out"],
        "add_smooth_turns": settings_dict["add_smooth_turns"],
        "turn_segment_length": settings_dict["turn_segment_length"],
        "turn_diameter": settings_dict["turn_diameter"],
        "line_direction_reverse": settings_dict["line_direction_reverse"],
        "name_tie_not_flt": settings_dict["Tie"]
    }
    apply_cutting = not settings_dict["⏒—⏒ A single line file that has already been cut and extended manually"]
    if apply_cutting:
        cutter_lines_file_path = settings_dict["Cutter file"]
        extend_distance_meters = settings_dict["Extend by"]
        initial_flight_lines_input_path = settings_dict["Lines file"]
    else:
        initial_flight_lines_input_path = settings_dict["Cut extended lines file path"]

    settings_dict_for_pickle = settings_dict.copy()
    settings_dict = None # don't use settings_dict from here on

    flight_lines_input_layer = QgsVectorLayer(initial_flight_lines_input_path, "initial_flight_lines_input_path", "ogr")

    #######################################
    type = flight_settings["name_tie_not_flt"]
    filtered_layer = filter_lines_by_type(flight_lines_input_layer, type)
    if filtered_layer.featureCount() == 0:
        show_error(f"No '{type}' lines found in the input layer.")
        return
    ########################################

    if filtered_layer.isValid():
        lines_source_and_target_crs = get_source_and_target_crs_from_layer(filtered_layer)
    else:
        show_error('selected layer not valid')

    if not str(lines_source_and_target_crs['source_crs_epsg_int'])[:-2] in ['326', '327']:
        print(f"Will now convert lines to UTM zone {lines_source_and_target_crs['target_utm_num_int']} "
              f"'{lines_source_and_target_crs['target_utm_letter']}'")
        reprojected_lines_path = os.path.splitext(initial_flight_lines_input_path)[0] + '_UTM.shp'

        reproject_vector_layer(filtered_layer,
                               reprojected_lines_path,
                               lines_source_and_target_crs['target_crs_epsg_int'])
        flight_lines_path = reprojected_lines_path
        flight_lines_layer = QgsVectorLayer(flight_lines_path, "flight_lines_path", "ogr")
    else:
        flight_lines_path = initial_flight_lines_input_path
        flight_lines_layer = filtered_layer
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

    if apply_cutting:
            # split & extend lines before continuing
            flight_lines_path, flight_lines_layer = cut_and_extend_lines(
                cutter_lines_file_path,
                flight_lines_path,
                extend_distance_meters,
                global_crs_target
            )

    lines_obs, user_assigned_unique_strip_letters = extract_line_obj_from_line_layer(flight_lines_layer, flight_lines_path)
    show_feedback_popup = False
    tofs = extract_tof_obj_from_tof_layer(tof_points_layer, tof_points_path, show_feedback_popup=show_feedback_popup)

    #raise ValueError("yo ima stopp here")

    unique_strip_letters, line_groups = validate_inputs.validate_and_process_lines(lines_obs, user_assigned_unique_strip_letters)

    if not line_flight_order_reverse:
        sort_angle = (plugin_global.ave_line_ang_cwN + 90) % 360
    else:
        sort_angle = (plugin_global.ave_line_ang_cwN - 90) % 360

    # sort
    lines_obs_sorted, tofs = sort_lines_and_tofs(lines_obs, tofs, sort_angle)

    only_use_lines_list = [line.only_use for line in lines_obs_sorted]
    if any(only_use_lines_list):
        lines = list(compress(lines_obs_sorted, only_use_lines_list))
    else:
        use_lines_list = [not line.dont_use for line in lines_obs_sorted]
        lines = list(compress(lines_obs_sorted, use_lines_list))

    '''
    parent_line_groups = [line.parent_line_group for line in lines]
    num_chil = [len(line_group.children) for line_group in parent_line_groups]
    '''

    survey_area = construct_the_upper_hierarchy(lines, tofs, unique_strip_letters, prefer_even_number_of_lines, sort_angle)
    survey_area.line_groups = line_groups
    survey_area.global_crs_target = global_crs_target
    survey_area.flight_settings = flight_settings
    survey_area.color_cycle = ColorCycler()

    if hussein_drone_swarm:
        pass
        # Add hussein's functions here
    else:
        construct_the_lower_hierarchy(survey_area, max_flt_size, max_number_of_lines_per_flight, prefer_even_number_of_lines)

    survey_area.rename_everything()
    survey_area.recolor_everything()
    survey_area.backup_colors()
    survey_area.past_states = []



    # TESTING
    # TESTING  ------------------------------------------------------------
    # flight_test =  survey_area.flight_list[2]
    #flight_test.flip_lines()
    #line_groups[0]
    # TESTING  ------------------------------------------------------------
    # TESTING

    print("FINISHED INITIAL CREATION")
    survey_area.initial_creation_stage = False

    return survey_area


def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    #not implemented
    #do_load_pickle = settings_dict["🔧Modify Existing Flights"]
    # not implemented ^^^
    do_load_pickle = False
    pickle_ext = "._2D_flts"

    base_name = "saved_flights._2D_flts"

    if not do_load_pickle:
        apply_cutting = not settings_dict["⏒—⏒ A single line file that has already been cut and extended manually"]
        if apply_cutting:
            flight_lines_input_path = settings_dict["Lines file"]
        else:
            flight_lines_input_path = settings_dict["Cut extended lines file path"]
        pickle_obj = make_new_flights(settings_dict)
        pickle_obj.main_input_name = os.path.splitext(os.path.basename(flight_lines_input_path))[0]
        pickle_obj.save_folder_dir_path = os.path.dirname(flight_lines_input_path)

    else:
        pickle_path_in = settings_dict["🔧Modify Existing Flights file"]
        if not pickle_path_in.endswith(pickle_ext):
            err_msg = f'The previously made flights are saved as a "{pickle_ext}" file'
            plugin_tools.show_error(err_msg)
            raise ValueError(err_msg)
        pickle_obj = load_pickle(pickle_path_in)
        pickle_obj.main_input_name = os.path.splitext(os.path.basename(pickle_path_in))[0]
        pickle_obj.save_folder_dir_path = os.path.dirname(pickle_path_in)


    pickle_obj.pickle_ext = pickle_ext
    ''' obj hierarchy
    pickle_obj.strips
    ↳ strip.fa_list
    ↳↳ flight_area.children_flights
    ↳↳↳ flight.sorted_line_list
    ↳↳↳↳ line.start line.end
    ↳↳↳↳↳ line_end.xy
    '''

    run_qgis_gui(iface, pickle_obj)
