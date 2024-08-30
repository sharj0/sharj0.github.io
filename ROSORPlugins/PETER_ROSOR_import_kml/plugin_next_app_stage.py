'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from .Global_Singleton import Global_Singleton
from .run_lkm_calculations import run_lkm_calculations, \
    create_flight_dist_csv, \
    get_line_coords, \
    get_what_line_belongs_to_what_flight_dists
from .load_kml import load_kml_as_layer
import os
import re
import numpy as np

from pathlib import Path

from qgis.core import QgsProject, QgsLayerTreeGroup

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    input_folder = settings_dict['📂 Input folder']
    use_test_data = settings_dict["Use Test Data"]
    insert_at_bottom_instead_of_top = False
    get_group_name_from_parent_dir = False
    collapse_groups = settings_dict['Completely']
    calculate_flown_lkm = settings_dict['Calculate flown inline kilometers']
    line_file_path = settings_dict["Production Lines"]

    settings_dict = None  # don't use settings_dict from here on

    global_singleton = Global_Singleton()
    global_singleton.import_dict  = {}

    if use_test_data:
        input_folder = (Path(__file__).parent / "test_data").as_posix()

    process_folder(input_folder,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                   insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                   collapse_groups=collapse_groups)

    if calculate_flown_lkm:
        names = list(global_singleton.import_dict.keys())
        utm_coords_list, flown_distances, source_and_target_crs_info = run_lkm_calculations(global_singleton.import_dict, names)

        line_coords = get_line_coords(line_file_path, source_and_target_crs_info['target_crs_epsg_int'])
        flight_prod_dists = get_what_line_belongs_to_what_flight_dists(names, utm_coords_list, line_coords)

        flown_distances_km = list(np.array(flown_distances) / 1000)
        flight_prod_dists_km = list(np.array(flight_prod_dists) / 1000)
        create_flight_dist_csv(names, flown_distances_km, flight_prod_dists_km)




def alphanum_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


# Recursive function to process folders and subfolders, creating groups and sub-groups
def process_folder(path,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=False,
                   insert_at_bottom_instead_of_top=False,
                   collapse_groups=False):
    counter = 0  # Counter for successfully added files
    folder_counter = 0  # Counter for processed folders
    root = QgsProject.instance().layerTreeRoot() if parent_group is None else parent_group
    folder_name = os.path.basename(path)

    # Create a new group for this folder
    if get_group_name_from_parent_dir:
        group = QgsLayerTreeGroup(os.path.basename(os.path.dirname(path)))
    else:
        group = QgsLayerTreeGroup(folder_name)

    if insert_at_bottom_instead_of_top:
        root.insertChildNode(-1, group)
    else:
        root.insertChildNode(0, group)

    # Calculate indentation based on the depth
    indent = '↴ ' * depth

    items = os.listdir(path)
    items.sort(key=alphanum_key)

    for item in items:
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            # Increment the folder counter and process the subfolder
            folder_counter += 1
            process_folder(full_path,
                           group,
                           depth + 1,
                           get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                           insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                           collapse_groups=collapse_groups)  # Increase depth for subfolders
        else:
            # Increment the file counter if a file is processed
            layer_name = os.path.splitext(item)[0]
            if item.endswith(".kml"):
                counter += 1
                load_kml_as_layer(full_path, layer_name, group)

    # Print with indentation based on the depth
    if counter == 0 and folder_counter == 0:
        parent_group.removeChildNode(group)
        #print(f"{indent}{folder_name} -> Removed empty folder")
    else:
        print(f"{indent}{folder_name} -> {counter} files, {folder_counter} folders")

    # these things are applied to the top level loaded group at the end:
    if depth == 0:
        #print(f'{root=} {depth=}')
        check_and_remove_empty_groups(root)
        if collapse_groups:
            collapse_group_and_children(root)
        else:
            collapse_group_and_children_if_contains_layers_only(root)
    else:
        pass


def check_and_remove_empty_groups(group):
    child_nodes = group.children()
    empty_groups = []
    for node in child_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            # Recursively check the child groups
            check_and_remove_empty_groups(node)
            # If the group is empty (no children), mark it for removal
            if not node.children():
                empty_groups.append(node)
    # Remove all marked empty groups
    for empty_group in empty_groups:
        group.removeChildNode(empty_group)


def collapse_group_and_children(group):
    group.setExpanded(False)
    child_nodes = group.children()
    for node in child_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            # Recursively collapse the child groups
            collapse_group_and_children(node)
            # Collapse the group
            node.setExpanded(False)


def collapse_group_and_children_if_contains_layers_only(group):
    child_nodes = group.children()
    only_contains_layers = True

    for node in child_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            # If there's a child group, mark the current group as containing groups
            only_contains_layers = False
            # Recursively check the child groups
            collapse_group_and_children_if_contains_layers_only(node)

    if only_contains_layers:
        # Collapse the group if it contains only layers
        group.setExpanded(False)

if __name__ == "__main__":
    flight_distances =\
    [3779.1244910872597,
     4016.735671805802,
     3735.6120004891673,
     3821.1821770334127,
     3629.567398446148,
     3692.3765065668435,
     3446.682991615446]
    names =\
    ['G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_S_flts\\tof_1S_flt_1_3.8km.kml',
     'G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_S_flts\\tof_1S_flt_2_4.1km.kml',
     'G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_E_flts\\tof_1E_flt_3_3.8km.kml',
     'G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_E_flts\\tof_1E_flt_4_3.9km.kml',
     'G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_E_flts\\tof_1E_flt_5_3.7km.kml',
     'G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_W_flts\\tof_1W_flt_6_3.8km.kml',
     'G:\\Shared drives\\Rosor\\2024 - 2025\\Projects\\project-dlm-equity-bmc-kzk\\priority_1_area\\2D_Flights\\TOF_1\\TOF_1_W_flts\\tof_1W_flt_7_3.5km.kml']