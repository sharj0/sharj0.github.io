'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

import os
import csv
import pandas as pd
import shutil
from pathlib import Path

from .surveymanger_automation import automated_survey_manager
from . import plugin_load_settings
from .tools import mag_arrow_parse_to_df, load_and_transform_vector_lines, load_csv_data_to_qgis
from .gui_run import gui_run
from .plugin_tools import show_error

from qgis.core import QgsProject

from .split_csv_by_flightlines import run_flightline_splitter_gui

from . import pdf_export_setting_json_Sharj

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    #"First Time Setup"
    executable_path = settings_dict['Survey_Manager_exe_path']

    #"Input files"
    magdata_path = settings_dict['Magdata_file_path']
    Flight_lines_file_path = settings_dict['Flight_lines_file_path']

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


    settings_pdf_output_path = Path(Path(magdata_path).parent,Path("json_settings.pdf")).as_posix()

    pdf_export_setting_json_Sharj.create_settings_json_pdf_page(settings_pdf_output_path=settings_pdf_output_path,settings_dict=settings_dict)

    settings_dict = None # don't use settings_dict from here on


    #In case we ever want to change the folders in the future
    raw_folder_name_string = "Raw_CSV_folder"
    clean_folder_name_string = "clean"

    # Creating folder path, file name strings for easy reference
    raw_folder_path = Path(Path(magdata_path).parent,raw_folder_name_string).as_posix()
    survey_manager_csv_target = Path(Path(magdata_path).parent, Path(magdata_path).stem + "_10Hz_RAW.csv").as_posix()

    # Defaulting csv boolean to be false (if the limiter is csv and there is no .csv the if tree will raise an error)
    import_csv_file_instead_of_magdata = False

    #If the user input a magdata with file with a checkmark it means there is already a raw file
    #This could definetely be condensed with the magdata if nest that is later in the code but oh well
    if Path(magdata_path).suffix.startswith(".magdata") and Path(magdata_path).stem.startswith("✅ "):
        raw_csv_file_path = Path(Path(raw_folder_path), Path(magdata_path).stem[2:] + "_10Hz_RAW.csv").as_posix()
        import_csv_file_instead_of_magdata = True
    else:
        raw_csv_file_path = Path(Path(magdata_path).parent, Path(magdata_path).stem + ".csv").as_posix()


    # Create string for output csv folder
    output_csv_folder = Path(Path(magdata_path).parent, clean_folder_name_string).as_posix()


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


    if Path(magdata_path).suffix.startswith(".magdata"):

        # Checks if a "Raw" folder exists within the magdata working directory (where the file is)
        if Path(raw_folder_path).exists():

            # Checks to see if the raw csv file exists, otherwise move on
            if Path(raw_csv_file_path).exists():

                # Sets the boolean to true if it finds the csv file
                import_csv_file_instead_of_magdata = True


        # If there is no "Raw" folder, create it and move on
        else:
            Path(raw_folder_path).mkdir(parents=True, exist_ok=True)

    # Checks if the user input a raw csv and then if it follows the folder structure
    elif Path(magdata_path).suffix == ".csv":

        #Checks if there is a raw csv file
        if Path(magdata_path).stem.endswith("_RAW"):
            import_csv_file_instead_of_magdata = True

            #Checks if the raw csv file's directory is called "raw", because the raw file should not be in the same folder as the magdata
            if not Path(magdata_path).parent.stem == raw_folder_name_string:

                #Creates the "raw" folder since it doesn't exist
                new_path = Path(Path(magdata_path).parent, Path(raw_folder_name_string)).as_posix()
                Path(new_path).mkdir(parents=True, exist_ok=True)

                #Copies the raw csv
                shutil.copy(Path(magdata_path).as_posix(), Path(new_path, Path(magdata_path).stem + Path(magdata_path).suffix))

                input_file = Path(magdata_path).as_posix()
                magdata_path = Path(Path(new_path), Path(input_file).stem + Path(input_file).suffix).as_posix()

                Path(input_file).unlink()
                raw_csv_file_path = magdata_path

        else:
            raise "If this is a raw file please have it end with _RAW (double check)"
    else:
        raise "ERROR UNRECOGNIZED FILE INPUT"


    #If the raw csv file doesn't exist, then start the proprietary software, which currently saves the raw csv to the same folder as the magdata (work in progress)
    if not import_csv_file_instead_of_magdata:
        if not os.path.exists(raw_csv_file_path):
            if not os.path.exists(survey_manager_csv_target):
                automated_survey_manager(executable_path, magdata_path, survey_manager_csv_target)

            shutil.copy(survey_manager_csv_target, raw_csv_file_path)
            os.remove(survey_manager_csv_target)



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

    if not import_csv_file_instead_of_magdata:
        csv_output_path = Path(magdata_path).as_posix()
    elif import_csv_file_instead_of_magdata:
        csv_output_path = Path(Path(raw_csv_file_path).parent).as_posix()

    outputt = gui_run(df,
                      flight_lines,
                      grid_line_names,
                      noise_detection_params,
                      deviation_thresh,
                      acceptable_minimum_velocity,
                      csv_output_path,
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

    #Need to specify if input was magdata or not
    if not import_csv_file_instead_of_magdata:
        file_basen_no_ex = os.path.basename(csv_out_file_path).split('.')[0]
    elif import_csv_file_instead_of_magdata:
        if Path(magdata_path).stem.endswith("_RAW"):
            file_basen_no_ex = Path(magdata_path).stem[:-4]
        else:
            file_basen_no_ex = Path(magdata_path).stem

    # if output_csv_into_input_magdata_folder:
    #     output_csv_path_no_ex = os.path.join(os.path.dirname(csv_out_file_path), file_basen_no_ex)
    # else:
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

    # Checks if the file name has a check mark, if it does move on. Otherwise it should append to the beginning of the magdata file.
    if not Path(magdata_path).suffix.startswith(".csv"):
        if not Path(magdata_path).stem.startswith("✅ "):
            Path(magdata_path).rename(Path(magdata_path).with_name("✅ " + Path(magdata_path).stem + Path(magdata_path).suffix))
            print(f"Renamed magdata file to {Path(magdata_path).stem + Path(magdata_path).suffix}")

    # create output pdf path (always output by default)
    output_pdf_folder = Path(Path(csv_out_file_path).parent, "QAQC Report").as_posix()
    if not os.path.exists(output_pdf_folder):
        Path(output_pdf_folder).mkdir(parents=True,exist_ok=True)

    output_pdf_path_no_ex = os.path.join(os.path.dirname(csv_out_file_path), "QAQC Report", file_basen_no_ex)

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

    pdf_export_setting_json_Sharj.append_pdf_page(pdf_path_existing=output_pdf_path,pdf_path_to_append=settings_pdf_output_path,pdf_path_merged=output_pdf_path)

    if os.path.exists(settings_pdf_output_path):
        os.remove(settings_pdf_output_path)

    print(f"Output .pdf saved: {output_pdf_path}")

    if use_parent_folder_as_group_name:
        group_name = os.path.basename(os.path.dirname(csv_out_file_path))
    else:
        group_name = ''
    load_csv_data_to_qgis(output_csv_path, group_name)

    if save_project_when_done:
        QgsProject.instance().write()
        QgsProject.instance().read()




