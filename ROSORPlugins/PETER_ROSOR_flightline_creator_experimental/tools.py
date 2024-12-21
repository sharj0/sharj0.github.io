import os
import re
import numpy as np
from osgeo import osr

def get_next_filename(directory, original_filename):
    base, ext = os.path.splitext(original_filename)
    parts = base.split('_')
    if parts[-1].startswith('v') and parts[-1][1:].isdigit():
        # Increment the last part if it's a version number
        version = int(parts[-1][1:])
        parts[-1] = f"v{version + 1}"
    else:
        # Append '_v2' if no version number found
        parts.append('v2')

    # Construct the new base name from parts
    new_base = '_'.join(parts)
    new_filename = f"{new_base}{ext}"
    # Check for existence and adjust if necessary
    while os.path.exists(os.path.join(directory, new_filename)):
        version = int(parts[-1][1:])
        parts[-1] = f"v{version + 1}"
        new_base = '_'.join(parts)
        new_filename = f"{new_base}{ext}"

    return os.path.join(directory, new_filename)

def find_key_in_nested_dict(nested_dict, search_key):
    if search_key in nested_dict:
        return nested_dict[search_key]

    for key, value in nested_dict.items():
        if isinstance(value, dict):
            result = find_key_in_nested_dict(value, search_key)
            if result is not None:
                return result
    return None

def get_newest_file_in(plugin_dir, folder='settings', filter='.json', time_rounding=10):
    # Construct the path to the 'settings_folder'
    settings_folder_path = os.path.join(plugin_dir, folder)

    # List all files in the settings directory that match the filter
    files = [f for f in os.listdir(settings_folder_path) if f.endswith(filter)]

    # Construct full paths and filter files by modification time
    paths = [os.path.join(settings_folder_path, f) for f in files]
    mod_times = [round(os.path.getmtime(p) / time_rounding) * time_rounding for p in paths]

    # If all modification times are the same, use numeric ending from filenames
    if len(set(mod_times)) == 1:
        def extract_numeric_ending(fname):
            # Extracts the last numeric part of the file name, returns 0 if none is found
            match = re.search(r'(\d+)\.json$', fname)
            return int(match.group(1)) if match else 0

        # Get the file with the highest numeric ending
        highest_numeric_file = max(paths, key=lambda x: extract_numeric_ending(x))
        return highest_numeric_file
    else:
        # Get the file with the latest modification time
        latest_file = max(paths, key=lambda x: os.path.getmtime(x))
        return latest_file