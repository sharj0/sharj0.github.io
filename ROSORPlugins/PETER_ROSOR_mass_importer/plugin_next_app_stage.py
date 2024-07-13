'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from . import plugin_tools
from .load_csv import load_csv_as_layer, clean_subbed_csvs
from .load_kml import load_kml_as_layer
from .org_csvs_by_kml_flight import org_csvs_by_kml_flight, get_all_files_in_folder_recursive
from .split_csv_by_flightlines import run_flightline_splitter_gui
import os
import re
import subprocess

from qgis.core import QgsProject, QgsLayerTreeGroup
import csv

"""↓↓ Sharj's Additions ↓↓"""
from .Global_Singleton import Global_Singleton #THE MOST SINGLEST POINT OF FAILURE AND SUCCESS
from . import output_lkm_deploy_to_excel_Sharj
"""↑↑ Sharj's Additions ↑↑"""

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    input_folder = settings_dict['📂 Input folder']
    import_kml_instead = settings_dict["2D Flights ( .kml )"]
    insert_at_bottom_instead_of_top = False
    get_group_name_from_parent_dir = False
    reorganise_by_kml_flights = settings_dict['Re_organise_by_flights']
    reorganise_by_kml_flights_path = settings_dict['Re_organise_by_flights_path']
    csv_load_dict = {}
    clean_out_sub_sampled_csv = settings_dict['clean_out_sub_sampled_csv']  # doesn't need to be in dict
    csv_load_dict["sub_sample_csv_displayed_points"] = settings_dict['sub_sample_csv_displayed_points']
    csv_load_dict["load_existing_subed"] = settings_dict['load_existing_if_available']
    csv_load_dict["point_size_multiplier"] = settings_dict['point_size_multiplier']
    split_up_files_with_no_match = settings_dict['Split_up_files_with_no_match']
    collapse_groups = settings_dict['Completely']
    output_lkm = settings_dict['output lkm file?']

    """↓↓ Sharj's Additions ↓↓"""
    #I wanted a funny variable name for this singleton (props if you get the reference)

    #Creates global attributes to leap frog across functions and files (instead of passing down through the functions)
    everything_everywhere_all_at_once = Global_Singleton()
    everything_everywhere_all_at_once.output_lkm = output_lkm
    everything_everywhere_all_at_once.total_lkm = 0
    everything_everywhere_all_at_once.input_folder = input_folder
    """↑↑ Sharj's Additions ↑↑"""

    settings_dict = None  # don't use settings_dict from here on

    if import_kml_instead:
        reorganise_by_kml_flights = False

    # Start processing from the root folder

    if clean_out_sub_sampled_csv:
        clean_subbed_csvs(input_folder)

    if not csv_load_dict["sub_sample_csv_displayed_points"] in [0, 1]:
        csv_file_ext = f'.subed{int(csv_load_dict["sub_sample_csv_displayed_points"])}csv'
    else:
        csv_file_ext = f'.csv'
    csv_load_dict["csv_file_ext"] = csv_file_ext

    if reorganise_by_kml_flights:
        input_folder, match_data_to_flt = org_csvs_by_kml_flight(input_folder,
                                                                 reorganise_by_kml_flights_path,
                                                                 csv_load_dict)

    process_folder(input_folder,
                   csv_load_dict=csv_load_dict,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                   import_kml_instead=import_kml_instead,
                   insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                   collapse_groups=collapse_groups)


    """↓↓ Sharj's Additions ↓↓"""
    if everything_everywhere_all_at_once.output_lkm and not import_kml_instead:

        total_lkm = everything_everywhere_all_at_once.total_lkm

        #create and open Excel file after process folder has navigated through all its files and branches
        try:
            output_lkm_excel_file_path = str(output_lkm_deploy_to_excel_Sharj.create_excel_file(input_folder,total_lkm))
            output_lkm_deploy_to_excel_Sharj.open_excel_file(output_lkm_excel_file_path)
        except AttributeError:
            print("There seems to be an issue with the singleton attributes")
    """↑↑ Sharj's Additions ↑↑"""

    if reorganise_by_kml_flights and split_up_files_with_no_match:
        no_match_folder_path = os.path.join(input_folder, "No_Matches")
        if os.path.exists(no_match_folder_path):
            no_match_csv_path_list = get_all_files_in_folder_recursive(no_match_folder_path, ".csv")
        else:
            no_match_csv_path_list = []
        for idx, no_match_csv_path in enumerate(no_match_csv_path_list):
            how_done = f'{idx + 1} out of {len(no_match_csv_path_list)}'
            run_flightline_splitter_gui(no_match_csv_path, match_data_to_flt, how_done)
            # Open file explorer in the csv_path folder
        if no_match_csv_path_list:
            plugin_tools.show_message('Done splitting the flights. Consider replacing the original with this output')
            folder_path = os.path.dirname(no_match_csv_path)
            subprocess.Popen(f'explorer "{folder_path}"')


def alphanum_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


# Recursive function to process folders and subfolders, creating groups and sub-groups
def process_folder(path,
                   csv_load_dict,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=False,
                   import_kml_instead=False,
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
            process_folder(full_path, csv_load_dict, group, depth + 1,
                           get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                           import_kml_instead=import_kml_instead,
                           insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                           collapse_groups=collapse_groups)  # Increase depth for subfolders
        else:
            # Increment the file counter if a file is processed
            layer_name = os.path.splitext(item)[0]
            if import_kml_instead and item.endswith(".kml"):
                counter += 1
                load_kml_as_layer(full_path, layer_name, group)
            elif not import_kml_instead and item.endswith(".csv"):
                counter += 1
                load_csv_as_layer(full_path, layer_name, group, csv_load_dict)

    # Print with indentation based on the depth
    if counter == 0 and folder_counter == 0:
        parent_group.removeChildNode(group)
        #print(f"{indent}{folder_name} -> Removed empty folder")
    else:
        print(f"{indent}{folder_name} -> {counter} files, {folder_counter} folders")

    # these things are applied to the top level loaded group at the end:
    if depth == 0:
        print(f'{root=} {depth=}')
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
