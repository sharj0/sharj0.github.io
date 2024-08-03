'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

import os
import csv
import pandas as pd
import shutil

from PETER_ROSOR_mag_clipper.surveymanger_automation import automated_survey_manager
from PETER_ROSOR_mag_clipper import plugin_load_settings
from PETER_ROSOR_mag_clipper.tools import mag_arrow_parse_to_df, load_and_transform_vector_lines, load_csv_data_to_qgis
from PETER_ROSOR_mag_clipper.gui_run import gui_run
from PETER_ROSOR_mag_clipper.plugin_tools import show_error


from qgis.core import QgsProject

from .split_csv_by_flightlines import run_flightline_splitter_gui

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    #"First Time Setup"
    executable_path = settings_dict['Survey_Manager_exe_path']

    #"Input files"
    magdata_path = settings_dict['Magdata_file_path']
    Flight_lines_file_path = settings_dict['Flight_lines_file_path']

    #"Output folders"
    output_csv_into_input_magdata_folder = settings_dict['output_csv_into_input_magdata_folder']
    output_csv_folder = settings_dict['output_csv_folder']
    output_pdf_into_input_magdata_folder = settings_dict['output_pdf_into_input_magdata_folder']
    output_pdf_folder = settings_dict['output_pdf_folder']

    #"Parameters"
    epsg_target = int(settings_dict['EPSG_code_of_area'])
    line_detection_threshold = settings_dict['line_detection_threshold']
    filter_lines_direction_thresh = settings_dict['filter_out_lines_based_on_direction_thresh_percent']
    Y_axis_display_range_override = settings_dict['Y_axis_display_range_override']
    use_parent_folder_as_group_name = settings_dict['use_parent_folder_name_as_layer_group_name']
    deviation_thresh = settings_dict['acceptable_deviation_from_flightline']
    acceptable_minimum_velocity = settings_dict['acceptable_minimum_velocity']

    do_auto_rename = settings_dict['Auto_rename']
    path_to_2d_flights = settings_dict['Provide_path_to_2d_flights']
    split_data_if_no_match = settings_dict['If no match, split data']

    noise_detection_params = {}
    noise_detection_params['range_noise_threshold'] = settings_dict['range_noise_threshold']
    noise_detection_params['range_noise_number_of_points'] = settings_dict['range_noise_number_of_points']
    save_project_when_done = settings_dict['save_whole_qgis_project_when_done']
    settings_dict = None # don't use settings_dict from here on

    #gui_instance = run_flightline_splitter_gui('yrs', 'yrs')
    #print(gui_instance)

    if not do_auto_rename:
        path_to_2d_flights = None

    noise_detection_params['z_score_smoothing_factor'] = 2 # changing this causes a bug
    # so I'm removing it from the changeable settings

    if str(epsg_target).startswith('327') or str(epsg_target).startswith('326'):
        pass
    else:
        show_error('"EPSG_code_of_area" must be either 326XX or 327XX')

    if magdata_path.endswith(".csv"):
        import_csv_file_instead_of_magdata = True
    elif magdata_path.endswith(".magdata"):
        import_csv_file_instead_of_magdata = False
    else:
        raise "ERROR UNRECOGNISED FILE INPUT"

    if import_csv_file_instead_of_magdata:
        raw_csv_file_path = magdata_path
    else:
        raw_csv_file_path = ''.join(magdata_path.split('.')[:-1]) + '_10Hz.csv'
        if not os.path.exists(raw_csv_file_path):
            automated_survey_manager(executable_path, magdata_path, raw_csv_file_path)

    with open(raw_csv_file_path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        headers = reader.fieldnames  # Get the list of column names from the header
        # Check for the specific column names to identify the type
        if 'Mag' in headers:
            # raw data
            print('Parsing raw data...')
            df = mag_arrow_parse_to_df(raw_csv_file_path, epsg_target)
        elif 'Mag_TMI_nT' in headers:
            # clipped data
            print('Parsing clipped data...')
            df = pd.read_csv(raw_csv_file_path)
        else:
            print('Unknown file type. Exiting...')
            exit()

    flight_lines, grid_line_names = load_and_transform_vector_lines(Flight_lines_file_path, epsg_target)

    outputt = gui_run(df,
                      flight_lines,
                      grid_line_names,
                      noise_detection_params,
                      deviation_thresh,
                      acceptable_minimum_velocity,
                      raw_csv_file_path,
                      line_detection_threshold,
                      filter_lines_direction_thresh,
                      Y_axis_display_range_override,
                      path_to_2d_flights,
                      epsg_target)

    result, mag_output_df, temp_pdf_out_path, csv_out_file_path, flightline_splitter_data = outputt


    if not result:
        print("User canceled or closed the dialog.")
        return

    print("User accepted, new saving files...")

    # create output csv path
    file_basen_no_ex = os.path.basename(csv_out_file_path).split('.')[0]
    if output_csv_into_input_magdata_folder:
        output_csv_path_no_ex = os.path.join(os.path.dirname(csv_out_file_path), file_basen_no_ex)
    else:
        if not os.path.exists(output_csv_folder):
            # the user specified folder does not exist.
            # their intention to put it in a folder is clear lets make one for them
            output_csv_folder = os.path.join(os.path.dirname(csv_out_file_path), 'Clean_CSV_Folder')
            if not os.path.exists(output_csv_folder):
                os.makedirs(output_csv_folder)
        output_csv_path_no_ex = os.path.join(output_csv_folder, file_basen_no_ex)
    version = ""  # Start with an empty version for the first file
    output_csv_path = f"{output_csv_path_no_ex}{version}.csv"
    # If the base file exists, start the versioning from 2
    if os.path.exists(output_csv_path):
        version = "_v2"  # Start with version 2 if the base file exists
        output_csv_path = f"{output_csv_path_no_ex}{version}.csv"
        while os.path.exists(output_csv_path):
            # Extract the numeric part and increment
            version_number = int(version[2:]) + 1  # Skip '_v' and convert to int
            version = f"_v{version_number}"
            output_csv_path = f"{output_csv_path_no_ex}{version}.csv"
    mag_output_df.to_csv(output_csv_path, index=False)
    print(f"Output .csv saved: {output_csv_path}")

    if flightline_splitter_data and split_data_if_no_match:
        gui_instance = run_flightline_splitter_gui(output_csv_path, flightline_splitter_data)
        print(gui_instance)

    # create output pdf path
    if output_pdf_into_input_magdata_folder:
        output_pdf_path_no_ex = os.path.join(os.path.dirname(csv_out_file_path), file_basen_no_ex)
    else:
        if not os.path.exists(output_pdf_folder):
            # the user specified folder does not exist.
            # their intention to put it in a folder is clear lets make one for them
            output_pdf_folder = os.path.join(os.path.dirname(csv_out_file_path), 'QaQc_Report_Folder')
            if not os.path.exists(output_pdf_folder):
                os.makedirs(output_pdf_folder)
        output_pdf_path_no_ex = os.path.join(output_pdf_folder, file_basen_no_ex)
    version = ""  # Start with an empty version for the first file
    output_pdf_path = f"{output_pdf_path_no_ex}{version}.pdf"
    # If the base file exists, start the versioning from 2
    if os.path.exists(output_pdf_path):
        version = "_v2"  # Start with version 2 if the base file exists
        output_pdf_path = f"{output_pdf_path_no_ex}{version}.pdf"
        while os.path.exists(output_pdf_path):
            # Extract the numeric part and increment
            version_number = int(version[2:]) + 1  # Skip '_v' and convert to int
            version = f"_v{version_number}"
            output_pdf_path = f"{output_pdf_path_no_ex}{version}.pdf"
    shutil.copyfile(temp_pdf_out_path, output_pdf_path)
    print(f"Output .pdf saved: {output_pdf_path}")


    if use_parent_folder_as_group_name:
        group_name = os.path.basename(os.path.dirname(csv_out_file_path))
    else:
        group_name = ''
    load_csv_data_to_qgis(output_csv_path, group_name)

    if save_project_when_done:
        QgsProject.instance().write()
        QgsProject.instance().read()




