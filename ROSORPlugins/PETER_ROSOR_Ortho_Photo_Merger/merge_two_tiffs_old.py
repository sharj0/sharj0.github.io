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


from .align_rasters import (align_rasters,
                           get_list_of_paths_os_walk_folder)

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
    )

from .overlap_cutline_funcs import process_overlap_and_cutline, load_telem_data
from .save_geotiffs import (apply_mask_to_rgb_rast,
                            apply_mask_rel_path_to_rgb_rast,
                            apply_mask_to_mask,
                            save_bit_mask_with_gdal,
                            merge_vrt_rasters,
                            create_mask_with_gdal_translate,
                            save_vrt_as_tiff)

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

    testing = False
    #output_folder_testing_override = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\test_100_gsd_100_GSD_v15"
    output_folder_testing_override = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\test_jank_ovelap_merge_10_GSD"

    r''' /\  /\  /\  /\  /\  /\ FOR TESTING /\  /\  /\  /\  /\  /\ '''

    r''' /\  /\  /\  /\  /\  /\ FOR TESTING /\  /\  /\  /\  /\  /\ '''

    target_GSD_meters = target_GSD_cm / 100
    if not target_GSD_meters in [0.05, 0.1, 0.2, 0.5, 1]:
        plugin_tools.show_error("target_GSD_meters must be either a whole number of meters or a factor of a meter [0.05, 0.1, 0.2, 0.5, 1]")

    output_folder_name_override = output_folder_name_override.replace('.', ',')

    start_time = time.time()

    assert Ortho_photo_1_file_path != Ortho_photo_2_file_path, "must load different files"


    tif_files = [Ortho_photo_1_file_path, Ortho_photo_2_file_path]

    dirnames = [os.path.dirname(path) for path in tif_files]

    folder_path = dirnames[0]

    size_of_all_inputs_gb = 0
    for tif_file in tif_files:
        size_of_all_inputs_gb += get_file_size_in_gb(tif_file)

    target_GSD_cm = round(target_GSD_meters * 100)
    print("###############################################################################################")
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

    '''
    Here are rough estimates of relative execution times for different alignment sample_alg (where nearest is the baseline):
    nearest: 1x
    bilinear: ~1.5x (slightly slower than nearest)
    cubic: ~2-3x (moderate increase in computation)
    cubicSpline: ~3-5x (slower due to smoother interpolation)
    lanczos: ~4-10x (highest quality, slowest due to large kernel and complexity)
    '''

    # Align the rasters
    output_files = align_rasters(tif_files, output_folder, target_GSD_cm, load_into_QGIS=False)

    print("Aligned raster files:", output_files)

    align_rasters_time = time.time() - start_time

    get_time_sofar(start_time, 'Align rasters')

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
    print("Creating input raster mask 1...")
    if not testing:
        create_mask_with_gdal_translate(first_raster_path, input_mask_path_1)
    get_time_sofar(start_time, 'Input raster mask 1 created')

    input_mask_path_2 = second_input_related_save_base+'_input_mask.tiff'
    print("Creating input raster mask 2...")
    if not testing:
        create_mask_with_gdal_translate(second_raster_path, input_mask_path_2)
    get_time_sofar(start_time, 'Input raster mask 2 created')


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

    get_time_sofar(start_time, 'Whole cutline creation')

    cut_path_mask_custom_common_frame_path_dataset = gdal.Open(cut_path_mask_custom_common_frame_path)
    gt_cust_custom_common_frame = cut_path_mask_custom_common_frame_path_dataset.GetGeoTransform()
    cut_path_mask_custom_common_frame = (cut_path_mask_custom_common_frame_path_dataset.GetRasterBand(1)
                                         .ReadAsArray().astype(np.uint8))

    footprint_geotransform, footprint_shape, overlap_mask_number_of_pixels, start_pix_overall, end_pix_overall \
        = load_telem_data(telem_path)

    first_raster_cutpath_output_path = first_input_related_save_base + '_cut_path_mask_input_frame.tiff'
    second_raster_cutpath_output_path = second_input_related_save_base + '_cut_path_mask_input_frame.tiff'

    if not testing:
        cut_shifted_1 = shift_mask_frame_and_extend(
            cut_path_mask_custom_common_frame,
            gt_cust_custom_common_frame,
            gt1,
            first_raster_shape,
            show_plot=False
        )
        save_bit_mask_with_gdal(cut_shifted_1, first_raster_cutpath_output_path, gt1, proj)

        cut_shifted_2 = shift_mask_frame_and_extend(
            cut_path_mask_custom_common_frame,
            gt_cust_custom_common_frame,
            gt2,
            second_raster_shape,
            show_plot=False
        )
        save_bit_mask_with_gdal(cut_shifted_2, second_raster_cutpath_output_path, gt2, proj)
    elif testing:
        cut_shifted_1_dataset = gdal.Open(first_raster_cutpath_output_path)
        cut_shifted_1 = cut_shifted_1_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)
        cut_shifted_2_dataset = gdal.Open(second_raster_cutpath_output_path)
        cut_shifted_2 = cut_shifted_2_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

    del cut_path_mask_custom_common_frame
    gc.collect()

    # Now continue with the rest of your code:
    get_time_sofar(start_time, 'Cut path masks in original frame')

    keep_dir_unit_vector_1 = get_relative_direction(footprint_geotransform, footprint_shape, gt1,
                                                    first_raster_shape, show_plot=False)
    keep_dir_unit_vector_2 = get_relative_direction(footprint_geotransform, footprint_shape, gt2,
                                                    second_raster_shape, show_plot=False)

    get_time_sofar(start_time, 'Keep direction unit vectors')

    chonky_keep_mask_path_1 = first_input_related_save_base + '_keep_mask.tiff'
    print(f'cutline to mask {first_raster_path=} {keep_dir_unit_vector_1=}')
    keep_mask_1 = cutline_to_mask(cut_shifted_1, keep_dir_unit_vector_1, show_plot=False)
    save_bit_mask_with_gdal(keep_mask_1, chonky_keep_mask_path_1, gt1, proj)
    del cut_shifted_1
    gc.collect()


    chonky_keep_mask_path_2 = second_input_related_save_base + '_keep_mask.tiff'
    print(f'cutline to mask {second_raster_path=} {keep_dir_unit_vector_2=}')
    keep_mask_2 = cutline_to_mask(cut_shifted_2, keep_dir_unit_vector_2, show_plot=False)
    save_bit_mask_with_gdal(keep_mask_2, chonky_keep_mask_path_2, gt2, proj)
    del cut_shifted_2
    gc.collect()

    get_time_sofar(start_time, 'Chonky keep masks')

    combined_mask_vrt_path_1 = first_input_related_save_base + '_combined_mask.vrt'
    combined_mask_vrt_path_2 = second_input_related_save_base + '_combined_mask.vrt'

    apply_mask_to_mask(input_mask_path_1, chonky_keep_mask_path_1, combined_mask_vrt_path_1)
    apply_mask_to_mask(input_mask_path_2, chonky_keep_mask_path_2, combined_mask_vrt_path_2)

    combined_mask_tiff_path_1 = os.path.join(output_folder, raster_name_1 + '.mask.tiff')
    combined_mask_tiff_path_2 = os.path.join(output_folder, raster_name_2 + '.mask.tiff')

    save_vrt_as_tiff(combined_mask_vrt_path_1, combined_mask_tiff_path_1)
    save_vrt_as_tiff(combined_mask_vrt_path_2, combined_mask_tiff_path_2)

    get_time_sofar(start_time, 'Cumulative keep masks')

    masked_vrt_path_1 = os.path.join(output_folder, raster_name_1 + '_rgb_masked.vrt')
    masked_vrt_path_2 = os.path.join(output_folder, raster_name_2 + '_rgb_masked.vrt')

    apply_mask_rel_path_to_rgb_rast(first_raster_path, combined_mask_tiff_path_1, masked_vrt_path_1)
    apply_mask_rel_path_to_rgb_rast(second_raster_path, combined_mask_tiff_path_2, masked_vrt_path_2)

    merged_out_path = os.path.join(output_folder, '_' + os.path.basename(output_folder) + '_MERGED.VRT')

    merge_vrt_rasters(masked_vrt_path_1, masked_vrt_path_2, merged_out_path)

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

