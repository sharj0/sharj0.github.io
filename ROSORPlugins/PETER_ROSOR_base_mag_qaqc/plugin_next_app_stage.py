'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

import os.path

from . import plugin_load_settings
from . import plugin_tools
from . import plotting
from . import pdf_plotter
import webbrowser


def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    #"First Time Setup"
    mag_data_folder = settings_dict['Mag Data folder']
    color_by_folder = settings_dict['color_by_folder']
    sub_sample_base_for_calculations_and_display = settings_dict['sub_sample_base_for_calculations_and_display']
    base_mag_ignore_start_end_mins = settings_dict['base_mag_ignore_start_end_mins']
    Check_Forcast = settings_dict['Check_Forcast']
    Check_Forcast_at = settings_dict['Check_Forcast_at']
    settings_dict = None # don't use settings_dict from here on

    if Check_Forcast:
        webbrowser.open(Check_Forcast_at)

    accepted, pdf_plot_data = plotting.plot_stuff(mag_data_folder,
                                                  color_by_folder,
                                                  sub_sample_base_for_calculations_and_display,
                                                  base_mag_ignore_start_end_mins)

    if accepted:
        pdf_plotter.run(pdf_plot_data, mag_data_folder)
        #plugin_tools.show_information("JUST TESTING TEMPLATE ")
        #plugin_tools.show_error(" NOT ACTUALLY AN EROROROR, JUST TESTING TEMPLATE ")


