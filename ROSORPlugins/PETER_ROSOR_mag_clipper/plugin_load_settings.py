'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

import json

from .plugin_settings_suffixes import get_suffixes

def run(settings_file_path):
    suffixes = get_suffixes()
    with open(settings_file_path) as data:
        settings_dict_dirty = json.loads(data.read())

    # Function to recursively remove keys with specified suffixes
    def remove_suffix_keys(d):
        if not isinstance(d, dict):
            return d
        new_dict = {}
        for k, v in d.items():
            if not any(k.endswith(suffix) for suffix in suffixes):
                new_dict[k] = remove_suffix_keys(v)
        return new_dict

    # Flatten the dictionary
    flattened = {}

    def flatten(d):
        for k, v in d.items():
            if isinstance(v, dict):
                flatten(v)
            else:
                if k in flattened:
                    raise ValueError(f"Duplicated key found: {k}")
                flattened[k] = v

    flatten(settings_dict_dirty)

    flattened_clean = remove_suffix_keys(flattened)
    return flattened_clean
