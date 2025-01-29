'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''
import matplotlib.pyplot as plt

from . import plugin_load_settings
from . import plugin_tools

import gc
import sys
import os
import numpy as np
from osgeo import gdal
import time
import json
import shutil
import subprocess
import winreg


from .align_rasters import (align_rasters,
                           get_list_of_paths_os_walk_folder,
                            is_raster_aligned)

from .pm_utils import (
    get_file_size_in_gb,
    plot_array,
    get_relative_direction,
    cutline_to_mask,
    save_metrics_to_csv,
    get_time_sofar,
    get_vrt_shape,
    calculate_overlapping_pixels,
    simplified_name,
    shift_mask_frame_and_extend,
    get_rid_of_extra_cutpath_arms,
    get_epsg_code,
    flatten_raster_construction_tree,
    calls
    )

from .overlap_cutline_funcs import process_overlap_and_cutline, load_telem_data
from .save_geotiffs import (apply_mask_to_rgb_rast,
                            apply_mask_rel_path_to_rgb_rast,
                            apply_mask_to_mask,
                            save_bit_mask_with_gdal,
                            merge_vrt_rasters,
                            create_mask_with_gdal_translate,
                            save_vrt_as_tiff,
                            extract_raster_sources_from_vrt,
                            extract_mask_and_rgb_from_vrt,
                            )

from .Load_into_QGIS import load_mask_into_qgis

def merge_two_tiffs(Ortho_photo_1_file_path,
                    Ortho_photo_2_file_path,
                    target_GSD_cm,
                    prefer_centre_factor,
                    output_folder_name_override):
    r''' \/  \/  \/  \/  \/  \/ FOR TESTING \/  \/  \/  \/  \/  \/ '''

    r''' \/  \/  \/  \/  \/  \/ FOR TESTING \/  \/  \/  \/  \/  \/ '''

    #to run in powershell
    # & "C:/Program Files/QGIS 3.38.0/bin/python-qgis.bat" "C:\Users\pyoty\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\debug_PETER_ROSOR_Ortho_Photo_Merger.py"

    testing = True
    #output_folder_testing_override = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\test_100_gsd_100_GSD_v15"
    #output_folder_testing_override = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\test_up_down_mg_100_GSD"
    output_folder_testing_override = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\North_half_10_GSD"

    r''' /\  /\  /\  /\  /\  /\ FOR TESTING /\  /\  /\  /\  /\  /\ '''

    r''' /\  /\  /\  /\  /\  /\ FOR TESTING /\  /\  /\  /\  /\  /\ '''

    target_GSD_meters = target_GSD_cm / 100
    if not target_GSD_meters in [0.05, 0.1, 0.2, 0.5, 1]:
        plugin_tools.show_error("target_GSD_meters must be either a whole number of meters or a factor of a meter [0.05, 0.1, 0.2, 0.5, 1]")

    print('__________________________________________________________________________________________________________')
    print(f'Merging {Ortho_photo_1_file_path} & {Ortho_photo_2_file_path} at {target_GSD_cm}cm GSD')
    print('__________________________________________________________________________________________________________')
    output_folder_name_override = output_folder_name_override.replace('.', ',')

    start_time = time.time()

    assert Ortho_photo_1_file_path != Ortho_photo_2_file_path, "must load different files"


    source_files = [Ortho_photo_1_file_path, Ortho_photo_2_file_path]

    dirnames = [os.path.dirname(path) for path in source_files]

    folder_path = dirnames[0]

    size_of_all_inputs_gb = 0
    for tif_file in source_files:
        size_of_all_inputs_gb += get_file_size_in_gb(tif_file)

    target_GSD_cm = round(target_GSD_meters * 100)
    print(" ############################################################################################# ")
    print(f"Starting processing on {round(size_of_all_inputs_gb, 2)} GBs of data at {target_GSD_cm} cm GSD")


    if output_folder_name_override is None:
        additional_suffix = f'_merging_at_{target_GSD_cm}_GSD'
        output_folder = get_name_of_non_existing_output_file(folder_path,
                                                             additional_suffix=additional_suffix)
    else:
        additional_suffix = f'_{target_GSD_cm}_GSD'
        override_folder_path = os.path.join(os.path.dirname(folder_path),output_folder_name_override)
        output_folder = get_name_of_non_existing_output_file(override_folder_path,
                                                             additional_suffix=additional_suffix)

    if testing:
        output_folder = output_folder_testing_override

    print(f'{output_folder=}')

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    raster_construction_tree = {}

    for idxx, file in enumerate(source_files, start=1):
        ext = os.path.splitext(file)[1].lower()
        file_key = f'Source_{idxx}'

        if ext == '.vrt':
            # Check alignment
            geotransform = gdal.Open(file).GetGeoTransform()
            #if not is_raster_aligned(geotransform, target_GSD_cm / 100):
            #    raise ValueError("The virtual raster must be aligned")

            # Extract constituent files
            raster_vrt_sources = extract_raster_sources_from_vrt(file)
            children = {
                "source_type": "vrt",
                "source_path": file,
                "sub_sources": {}
            }

            for idx, raster_vrt_source in enumerate(raster_vrt_sources, start=1):
                # Extract mask and aligned RGB for child VRT
                mask_sub_source_path, rgb_tiff_sub_source_path = extract_mask_and_rgb_from_vrt(raster_vrt_source)
                children["sub_sources"][idx] = {
                    "msk": mask_sub_source_path,
                    "tif": rgb_tiff_sub_source_path
                }

            raster_construction_tree[file_key] = children

        elif ext in ['.tif', '.tiff']:
            # TIFF files have no children
            raster_construction_tree[file_key] = {
                "source_type": "tif",
                "source_path": file
            }

    '''
    Here are rough estimates of relative execution times for different alignment sample_alg (where nearest is the baseline):
    nearest: 1x
    bilinear: ~1.5x (slightly slower than nearest)
    cubic: ~2-3x (moderate increase in computation)
    cubicSpline: ~3-5x (slower due to smoother interpolation)
    lanczos: ~4-10x (highest quality, slowest due to large kernel and complexity)
    '''

    # Align the rasters
    output_files = align_rasters(source_files, output_folder, target_GSD_cm, load_into_QGIS=False)

    print("Aligned raster files:", output_files)

    align_rasters_time = time.time() - start_time

    get_time_sofar(start_time, f'{calls.p} Align rasters')

    # Guard clause: Check if we have enough rasters to proceed
    if len(output_files) < 2:
        print("Need at least two output files to compute overlap.")
        exit()

    first_raster_path = output_files[0]
    second_raster_path = output_files[1]
    first_raster_shape = get_vrt_shape(first_raster_path)
    second_raster_shape = get_vrt_shape(second_raster_path)
    first_ds = gdal.Open(first_raster_path)
    second_ds = gdal.Open(second_raster_path)
    gt1 = first_ds.GetGeoTransform()
    gt2 = second_ds.GetGeoTransform()
    proj1 = first_ds.GetProjection()
    proj2 = second_ds.GetProjection()
    if proj1 != proj2:
        print("The two rasters have different projections.")
        exit()
    proj = proj1

    epsg_code_int = get_epsg_code(first_ds)

    overlap_mask_rough_number_of_pixels = calculate_overlapping_pixels(gt1, gt2,
                                                                       first_raster_shape,
                                                                       second_raster_shape)

    ##################################################################
    #   Get all the naming stuff and folder creation out of the way  #
    ##################################################################
    raster_name_1, _ = os.path.splitext(os.path.basename(first_raster_path))
    raster_name_2, _ = os.path.splitext(os.path.basename(second_raster_path))

    first_simplified_name, _ = os.path.splitext(os.path.basename(simplified_name(first_raster_path)))
    second_simplified_name, _ = os.path.splitext(os.path.basename(simplified_name(second_raster_path)))
    first_input_related_folder_path = os.path.join(output_folder, '1st_input_' + first_simplified_name + '_related')
    second_input_related_folder_path = os.path.join(output_folder, '2nd_input_' +second_simplified_name + '_related')
    if not os.path.exists(first_input_related_folder_path):
        os.makedirs(first_input_related_folder_path)
    if not os.path.exists(second_input_related_folder_path):
        os.makedirs(second_input_related_folder_path)
    first_input_related_save_base = os.path.join(first_input_related_folder_path, first_simplified_name)
    second_input_related_save_base = os.path.join(second_input_related_folder_path, second_simplified_name)

    merge_related_folder_path = os.path.join(output_folder, "merge_related")
    if not os.path.exists(merge_related_folder_path):
        os.makedirs(merge_related_folder_path)
    merge_related_save_base = os.path.join(merge_related_folder_path, os.path.basename(output_folder))

    telem_path = merge_related_save_base + '_extra_info.json'
    cut_path_mask_custom_common_frame_path = merge_related_save_base + "cut_path_mask_longest_custom_common_frame.tiff"

    input_mask_path_1 = first_input_related_save_base+'_input_mask.tiff'

    if not testing:
        print("Creating input raster mask 1...")
        print(input_mask_path_1)
        create_mask_with_gdal_translate(first_raster_path, input_mask_path_1)
    get_time_sofar(start_time, f'{calls.p} Input raster mask 1')

    input_mask_path_2 = second_input_related_save_base+'_input_mask.tiff'
    if not testing:
        print("Creating input raster mask 2...")
        print(input_mask_path_2)
        create_mask_with_gdal_translate(second_raster_path, input_mask_path_2)
    get_time_sofar(start_time, f'{calls.p} Input raster mask 2')

    input_mask_pathss = [input_mask_path_1, input_mask_path_2]

    for idx, (source_key, source_data) in enumerate(raster_construction_tree.items()):
        if source_data["source_type"] == "tif":
            # Add "msk" and "tif" to the source
            source_data["msk"] = input_mask_pathss[idx]
            source_data["tif"] = source_data["source_path"]  # Copy the existing source path to "tif"

    # Now insert the extra fields we need: raster_name, inputrelated_save_base, gt
    for idx, (source_key, source_data) in enumerate(raster_construction_tree.items()):
        # Decide which inputrelated_save_base to use
        if idx == 0:
            base_save = first_input_related_save_base
        else:
            base_save = second_input_related_save_base

        # If sub_sources exist (typical for a VRT scenario)
        if "sub_sources" in source_data:
            for sub_key, sub_val in source_data["sub_sources"].items():
                tif_path = sub_val.get("tif")
                msk_path = sub_val.get("msk")
                if tif_path and msk_path:
                    # 1) raster_name
                    sub_val["raster_name"] = os.path.splitext(os.path.basename(tif_path))[0]

                    # 2) inputrelated_save_base
                    sub_val["inputrelated_save_base"] = base_save

                    # 3) gt (GeoTransform) from GDAL
                    ds = gdal.Open(tif_path)
                    if ds:
                        sub_val["gt"] = list(ds.GetGeoTransform())
                        sub_val["shape"] = (ds.RasterYSize, ds.RasterXSize)  # Shape as (rows, cols)
                        ds = None
        else:
            # Otherwise, the source itself has .tif and .msk at top level
            tif_path = source_data.get("tif")
            msk_path = source_data.get("msk")
            if tif_path and msk_path:
                # 1) raster_name
                source_data["raster_name"] = os.path.splitext(os.path.basename(tif_path))[0]

                # 2) inputrelated_save_base
                source_data["inputrelated_save_base"] = base_save

                # 3) gt (GeoTransform)
                ds = gdal.Open(tif_path)
                if ds:
                    source_data["gt"] = list(ds.GetGeoTransform())
                    source_data["shape"] = (ds.RasterYSize, ds.RasterXSize)  # Shape as (rows, cols)
                    ds = None

    ##################################################################
    #   Finally, save out the updated raster_construction_tree       #
    ##################################################################

    # Dump the dictionary to a JSON string
    json_output = json.dumps(raster_construction_tree, indent=4)

    # Save the JSON to a file
    output_path = merge_related_save_base + "_raster_construction_tree.json"
    with open(output_path, "w") as json_file:
        json_file.write(json_output)

    if not testing:
        process_overlap_and_cutline(
            testing=testing,
            proj=proj,
            epsg_code_int=epsg_code_int,
            gt1=gt1,
            gt2=gt2,
            start_time=start_time,
            prefer_centre_factor=prefer_centre_factor,
            first_input_related_save_base=first_input_related_save_base,
            second_input_related_save_base=second_input_related_save_base,
            merge_related_save_base=merge_related_save_base,
            telem_path=telem_path,
            cut_path_mask_custom_common_frame_path=cut_path_mask_custom_common_frame_path,
            input_mask_path_1=input_mask_path_1,
            input_mask_path_2=input_mask_path_2,
            first_raster_path=first_raster_path,
            second_raster_path=second_raster_path,
        )
    else:
        for i in range(12):
            calls.p # this adds 12 to the calls counter. the counter is the thins that sais 6/22 done ... 7/22 done etc...
    get_time_sofar(start_time, f'{calls.p} Whole cutline creation')

    cut_path_mask_custom_common_frame_path_dataset = gdal.Open(cut_path_mask_custom_common_frame_path)
    gt_cust_custom_common_frame = cut_path_mask_custom_common_frame_path_dataset.GetGeoTransform()
    cut_path_mask_custom_common_frame = (cut_path_mask_custom_common_frame_path_dataset.GetRasterBand(1)
                                         .ReadAsArray().astype(np.uint8))

    footprint_geotransform, footprint_shape, overlap_mask_number_of_pixels, start_pix_overall, end_pix_overall \
        = load_telem_data(telem_path)
    
    
    
    def apply_common_cutline_to_source_mask(
            # Raster-specific inputs:
            raster_name,
            input_related_save_base,
            input_mask_path,
            cut_path_mask_custom_common_frame,
            gt_cust_custom_common_frame,
            raster_shape,
            raster_gt,
            proj,
            # Optional controls:
            show_plot=False,
            testing=False,
            start_time=None
    ):
        """
        Process a single raster, handling the following steps:
        1. Shift the cut-path mask to the raster's frame (or load from disk in testing mode).
        2. Generate the 'keep' mask.
        3. Combine the 'keep' mask with the input mask.

        Parameters:
        - raster_name: Name of the raster for output naming.
        - input_related_save_base: Base path for intermediate files.
        - input_mask_path: Path to the original input mask.
        - cut_path_mask_custom_common_frame: Shared cut-path mask in the common frame.
        - gt_cust_custom_common_frame: GeoTransform of the common frame.
        - raster_shape: Shape of the raster.
        - raster_gt: GeoTransform of the raster.
        - proj: Projection for saving the masks.
        - show_plot: Whether to show plots during processing (default: False).
        - testing: Whether to run in testing mode, loading pre-saved files (default: False).
        - start_time: Start time for tracking performance (optional).

        Returns:
        - combined_mask_tiff_path: Path to the final combined mask TIFF.
        """
        print(f'Updating mask for {input_mask_path}')

        cut_path_output_path = input_related_save_base + '_cut_path_mask_input_frame.tiff'
        combined_mask_vrt_path = input_related_save_base + '_combined_mask.vrt'
        chonky_keep_mask_path = input_related_save_base + '_keep_mask.tiff'
        combined_mask_tiff_path = os.path.join(output_folder, raster_name + '.mask.tiff')

        testing = False
        
        # Step 1: Shift the cut-path mask to the raster's frame
        if not testing:
            cut_shifted = shift_mask_frame_and_extend(
                cut_path_mask_custom_common_frame,
                gt_cust_custom_common_frame,
                raster_gt,
                raster_shape,
                show_plot=show_plot
            )
            if cut_shifted is None:
                shutil.copy(input_mask_path, combined_mask_tiff_path)
                return combined_mask_tiff_path
            save_bit_mask_with_gdal(cut_shifted, cut_path_output_path, raster_gt, proj)
        else:
            ds = gdal.Open(cut_path_output_path)
            cut_shifted = ds.GetRasterBand(1).ReadAsArray().astype(np.uint8)

        get_time_sofar(start_time, f'{calls.p} Shifted cut-path mask for {raster_name}')

        # Step 2: Compute the 'keep' direction vector
        keep_dir_unit_vector = get_relative_direction(
            footprint_geotransform,
            footprint_shape,
            raster_gt,
            raster_shape,
            show_plot=show_plot
        )
        get_time_sofar(start_time, f'{calls.p} Computed keep direction for {raster_name}')

        # Step 3: Generate the 'keep' mask
        if not testing:
            keep_mask = cutline_to_mask(cut_shifted, keep_dir_unit_vector, input_related_save_base, show_plot=False)
            save_bit_mask_with_gdal(keep_mask, chonky_keep_mask_path, raster_gt, proj)

        # Clean up to free memory
        del cut_shifted
        gc.collect()
        get_time_sofar(start_time, f'{calls.p} Generated keep mask for {raster_name}')

        # Step 4: Combine the 'keep' mask with the input mask
        apply_mask_to_mask(input_mask_path, chonky_keep_mask_path, combined_mask_vrt_path)
        save_vrt_as_tiff(combined_mask_vrt_path, combined_mask_tiff_path)
        get_time_sofar(start_time, f'{calls.p} Created combined mask for {raster_name}')

        return combined_mask_tiff_path

    base_source_list = flatten_raster_construction_tree(raster_construction_tree)

    for base_source in base_source_list:
        # Call the internal function twice, once for each raster
        (base_source["combined_mask_tiff_path"]) = apply_common_cutline_to_source_mask(
            raster_name=base_source['raster_name'], # input raster
            input_related_save_base=base_source['inputrelated_save_base'], # input raster
            input_mask_path=base_source['msk'], # input raster mask
            raster_gt=base_source['gt'], # input raster
            raster_shape=base_source['shape'],  # input raster
            cut_path_mask_custom_common_frame=cut_path_mask_custom_common_frame, # common
            gt_cust_custom_common_frame=gt_cust_custom_common_frame, # common
            proj=proj, # common
            show_plot=False, # common
            testing=testing, # common
            start_time=start_time # common
        )

    for base_source in base_source_list:
        base_source['masked_vrt_path'] = os.path.join(output_folder, base_source['raster_name'] + '_rgb_masked.vrt')
        apply_mask_rel_path_to_rgb_rast(base_source['tif'], base_source["combined_mask_tiff_path"], base_source['masked_vrt_path'])
        get_time_sofar(start_time, f'{calls.p} Applied mask to RGB raster for {base_source['raster_name']}')

    merged_out_path = os.path.join(output_folder, '_' + os.path.basename(output_folder) + '_MERGED.VRT')
    masked_vrt_paths = [base_source['masked_vrt_path'] for base_source in base_source_list]
    merge_vrt_rasters(masked_vrt_paths, merged_out_path)



    first_raster_number_of_pixels = first_raster_shape[0] * first_raster_shape[1]
    second_raster_number_of_pixels = second_raster_shape[0] * second_raster_shape[1]

    total_execution_time = time.time() - start_time
    csv_file_path = merge_related_save_base + "_metrics.csv"
    save_metrics_to_csv(csv_file_path,
                        overlap_mask_number_of_pixels=overlap_mask_number_of_pixels,
                        overlap_mask_rough_number_of_pixels=overlap_mask_rough_number_of_pixels,
                        first_raster_number_of_pixels=first_raster_number_of_pixels,
                        second_raster_number_of_pixels=second_raster_number_of_pixels,
                        total_execution_time=total_execution_time,
                        align_rasters_time=align_rasters_time,
                        size_of_all_inputs_gb=size_of_all_inputs_gb,
                        target_GSD_cm=target_GSD_cm)
    get_time_sofar(start_time, 'ALL')

    default_shp_app = get_default_app('.shp')
    for base_source in base_source_list:
        command = f'"{default_shp_app}" "{base_source["combined_mask_tiff_path"]}"'
        subprocess.Popen(command, shell=True)

    return merged_out_path

def get_name_of_non_existing_output_file(base_filepath, additional_suffix='', new_extension=''):
    # Function to create a unique file path by adding a version number
    base, ext = os.path.splitext(base_filepath)
    if new_extension:
        ext = new_extension
    new_out_file_path = f"{base}{additional_suffix}{ext}"

    if not os.path.exists(new_out_file_path):
        return new_out_file_path

    version = 2
    while os.path.exists(f"{base}{additional_suffix}_v{version}{ext}"):
        version += 1
    return f"{base}{additional_suffix}_v{version}{ext}"

def get_default_app(extension):
    """
    Get the default application associated with a file extension on Windows.

    Parameters:
    - extension (str): File extension, e.g., '.shp' or '.qgz'.

    Returns:
    - str: Path to the default application, or None if not found.
    """
    try:
        # Ensure the extension starts with a dot
        if not extension.startswith('.'):
            extension = f'.{extension}'

        # Query the registry for the file association
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, extension) as key:
            prog_id = winreg.QueryValue(key, None)

        # Use the ProgID to find the associated application
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
            command = winreg.QueryValue(key, None)

        # Extract the application path from the command
        app_path = command.split('"')[1] if '"' in command else command.split()[0]
        return app_path
    except Exception as e:
        print(f"Error retrieving default app for '{extension}': {e}")
        return None