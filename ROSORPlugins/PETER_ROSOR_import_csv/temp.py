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
    items.sort()  # Sort items alphabetically

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
        check_and_remove_empty_groups(root)
        if collapse_groups:
            collapse_group_and_children(root)
        else:
            collapse_group_and_children_if_contains_layers_only(root)
