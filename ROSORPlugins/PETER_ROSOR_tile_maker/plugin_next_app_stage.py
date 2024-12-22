'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from . import plugin_tools
from . import plotting

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    #"First Time Setup"
    executable_path = settings_dict['Survey_Manager_exe_path']

    settings_dict = None # don't use settings_dict from here on

    plugin_tools.show_information(f"JUST TESTING TEMPLATE {executable_path=}")
    #plugin_tools.show_error(" NOT ACTUALLY AN EROROROR, JUST TESTING TEMPLATE ")
    #plotting.plot_stuff([1, 2], [3, 4])