'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

import json

from . import plugin_settings_suffixes

def run(settings_file_path):
    suffixes = plugin_settings_suffixes.get()
    # suffixes = ["_SELECT_LAYER", "_COMMENT", "_TOOLTIP"]
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

    settings_dict_dirty = remove_suffix_keys(settings_dict_dirty)

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
    return flattened
