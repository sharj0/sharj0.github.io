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
from .Strip_Class import Strip_Class
from .functions import (sort_lines_and_tofs,
                        get_name_of_non_existing_output_file,
                        load_pickle,
                        ColorCycler)
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
    line_direction_reverse = settings_dict["line_direction_reverse"]
    line_flight_order_reverse = settings_dict["line_flight_order_reverse"]
    plugin_global.lead_in = settings_dict["lead_in"]
    plugin_global.lead_out = settings_dict["lead_out"]
    prefer_even_number_of_lines = settings_dict["prefer_even_number_of_lines"]
    plugin_global.add_smooth_turns = settings_dict["add_smooth_turns"]
    plugin_global.turn_segment_length = settings_dict["turn_segment_length"]
    plugin_global.turn_diameter = settings_dict["turn_diameter"]
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
        epsg_int = lines_source_and_target_crs['target_crs_epsg_int']
    else:
        flight_lines_path = flight_lines_input_path
        flight_lines_layer = flight_lines_input_layer
        epsg_int = lines_source_and_target_crs['source_crs_epsg_int']
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
    lines = extract_line_obj_from_line_layer(flight_lines_layer, flight_lines_path)
    tofs = extract_tof_obj_from_tof_layer(tof_points_layer, tof_points_path, show_feedback_popup=show_feedback_popup)

    validate_inputs.validate_and_process_lines(lines)
    if not line_flight_order_reverse:
        sort_angle = (plugin_global.ave_line_ang_cwN + 90) % 360
    else:
        sort_angle = (plugin_global.ave_line_ang_cwN - 90) % 360

    # sort
    lines, tofs = sort_lines_and_tofs(lines, tofs, sort_angle)

    strips = []
    if plugin_global.has_strips:
        strips_lines = [line.strip for line in lines if not line.strip is None]
        different_strip_names = np.unique(strips_lines)
        for name in different_strip_names:
            strip_lines = [line for line in lines if line.strip == name]
            strip = Strip_Class(name, strip_lines, tofs)
            strips.append(strip)
    else:
        strip = Strip_Class('', lines, tofs)
        strips.append(strip)

    flight_list = []
    for strip in strips:
        strip.flip_every_other_line_starting_with(line_direction_reverse)
        for fa in strip.flight_area_list:
            flight_list.extend(fa.generate_flights_within_fa(max_number_of_lines_per_flight,
                                                 max_flt_size,
                                                 prefer_even_number_of_lines))
            strip.children_flights.extend(fa.children_flights)

    color_cycle = ColorCycler()
    for flight in flight_list:
        flight.color = next(color_cycle)

    plugin_global.flight_list = flight_list
    for strip in strips:
        strip.run_more_flight_calcs()

    save_pickle = Save_Pickle()
    save_pickle.strips = strips
    save_pickle.settings_dict = settings_dict_for_pickle
    save_pickle.global_crs_target = global_crs_target

    return save_pickle

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    do_load_pickle = settings_dict["Modify Existing Flights"]

    base_name = "saved_flights._2D_flts"

    if not do_load_pickle:
        flight_lines_input_path = settings_dict["Flight lines file_path"]
        pickle_obj = make_new_flights(settings_dict)
        pickle_path_out = os.path.join(os.path.dirname(flight_lines_input_path), base_name)

    else:
        pickle_path_in = settings_dict["Modify Existing Flights file"]
        pickle_obj = load_pickle(pickle_path_in)
        pickle_path_out = os.path.join(os.path.dirname(pickle_path_in), base_name)

    pickle_path_out = get_name_of_non_existing_output_file(pickle_path_out)
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

    #run_qgis_gui(iface, pickle_obj)






