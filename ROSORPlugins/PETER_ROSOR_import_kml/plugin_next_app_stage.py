'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings

from .load_kml import load_kml_as_layer
import os
import re

from pathlib import Path


from qgis.core import QgsProject, QgsLayerTreeGroup





def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    input_folder = settings_dict['📂 Input folder']
    use_test_data = settings_dict["Use Test Data"]
    insert_at_bottom_instead_of_top = False
    get_group_name_from_parent_dir = False
    collapse_groups = settings_dict['Completely']
    settings_dict = None  # don't use settings_dict from here on


    if use_test_data:
        input_folder = (Path(__file__).parent / "test_data").as_posix()

    process_folder(input_folder,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                   insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                   collapse_groups=collapse_groups)



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
