'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

from . import plugin_change_settings
from . import plugin_next_app_stage
import sys
import os

def run(skip=False):
    # IMPORT 3rd PARTY libraries
    plugin_dir = os.path.dirname(os.path.realpath(__file__))
    # Path to the subdirectory containing the external libraries
    lib_dir = os.path.join(plugin_dir, 'plugin_3rd_party_libs')
    # Add this directory to sys.path so Python knows where to find the external libraries
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    window = plugin_change_settings.run(settings_folder='plugin_settings',
                                 next_app_stage=plugin_next_app_stage.main,
                                 skip=skip)
    return window