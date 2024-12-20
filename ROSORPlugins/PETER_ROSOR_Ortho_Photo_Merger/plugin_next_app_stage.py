'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from . import plugin_tools

import gc
import winsound
import sys
import os
import numpy as np
from osgeo import gdal
import time

from .align_rasters import (align_rasters,
                           get_list_of_paths_os_walk_folder,
                           get_name_of_non_existing_output_file)

from .overlap_mask_and_other_funcs import (
    get_file_size_in_gb,
    get_footprint_mask,
    generate_linestring,
    plot_array,
    extend_linestring_past_footprint,
    closeness_to_centreline,
    compute_similarity_old,
    compute_path_preference_arr,
    sample_line_over_raster,
    reverse_order_sample_arr,
    first_match_position,
    find_path,
    rasterize_line_ends,
    shift_mask_frame,
    shift_mask_frame_and_extend,
    get_relative_direction,
    cutline_to_mask,
    compute_centerline,
    save_metrics_to_csv,
    get_time_sofar,
    select_folder,
    select_tiff_files,
    detect_if_gappy_overlap_mask,
    connect_closest_ends,
    gdal_dtype_to_numpy,
    narrow_overlap_vrt,
    get_vrt_shape,
    normalize_to_unit_range,
    plot_2_arrays,
    calculate_overlapping_pixels,
    simplified_name
    )

from .save_geotiffs import (save_rast_as_geotiff,
                            create_wide_ext_overlap_vrt,
                            get_footprint_mask,
                            apply_mask_to_rgb_rast,
                            create_mask_with_gdal_translate,
                            save_bit_mask_with_gdal,
                            merge_vrt_rasters,
                            save_output_to_raster,
                            save_vrt_as_tiff)

from .Load_into_QGIS import load_mask_into_qgis

def print_ram(all_vars):
    # Convert sizes to GB and filter variables larger than 100 MB
    all_vars_filtered = [(name, size / (1024 ** 3)) for name, size in all_vars if size >= 100 * (1024 ** 2)]

    # Sort by size (descending)
    all_vars_sorted = sorted(all_vars_filtered, key=lambda x: x[1], reverse=True)

    # Print the results
    for var_name, size_gb in all_vars_sorted:
        print(f"{var_name}: {size_gb:.2f} GB")


def main(settings_path):
    r''' \/  \/  \/  \/  \/  \/ FOR TESTING \/  \/  \/  \/  \/  \/ '''

    r''' \/  \/  \/  \/  \/  \/ FOR TESTING \/  \/  \/  \/  \/  \/ '''

    #to run in powershell
    # & "C:/Program Files/QGIS 3.38.0/bin/python-qgis.bat" "C:\Users\pyoty\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\debug_PETER_ROSOR_Ortho_Photo_Merger.py"

    testing = False
    output_folder_testing_override = r"E:\ORTHO_STUFF\DEL_AREA\3,1_5_GSD_v2"
    clean_up = True

    r''' /\  /\  /\  /\  /\  /\ FOR TESTING /\  /\  /\  /\  /\  /\ '''

    r''' /\  /\  /\  /\  /\  /\ FOR TESTING /\  /\  /\  /\  /\  /\ '''


    settings_dict = plugin_load_settings.run(settings_path)

    #"First Time Setup"
    target_GSD_cm = settings_dict['Target GSD cm']  # meters
    prefer_centre_factor = settings_dict['Prefer centre factor']
    num_points = settings_dict['Line sample points']
    Ortho_photo_1_file_path = settings_dict['Ortho_photo_1_file_path']
    Ortho_photo_2_file_path = settings_dict['Ortho_photo_2_file_path']
    output_folder_name_override = settings_dict['Over-ride output folder name']
    beep_when_finished = settings_dict['Beep when finished']
    get_cut_line_only = False # settings_dict['Get cut line only']
    settings_dict = None # don't use settings_dict from here on

    target_GSD_meters = target_GSD_cm / 100
    if not target_GSD_meters in [0.05, 0.1, 0.2, 0.5, 1]:
        plugin_tools.show_error("target_GSD_meters must be either a whole number of meters or a factor of a meter [0.05, 0.1, 0.2, 0.5, 1]")

    start_time = time.time()

    tif_files = [Ortho_photo_1_file_path, Ortho_photo_2_file_path]

    dirnames = [os.path.dirname(path) for path in tif_files]

    folder_path = dirnames[0]

    size_of_all_inputs_gb = 0
    for tif_file in tif_files:
        size_of_all_inputs_gb += get_file_size_in_gb(tif_file)

    target_GSD_cm = round(target_GSD_meters * 100)

    print(f"Starting processing on {round(size_of_all_inputs_gb, 2)} GBs of data at {target_GSD_cm} cm GSD")


    if output_folder_name_override is None:
        additional_suffix = f'_merging_at_{target_GSD_cm}_GSD'
        output_folder = get_name_of_non_existing_output_file(folder_path,
                                                             additional_suffix=additional_suffix,
                                                             new_extension='')
    else:
        additional_suffix = f'_{target_GSD_cm}_GSD'
        override_folder_path = os.path.join(os.path.dirname(folder_path),output_folder_name_override)
        output_folder = get_name_of_non_existing_output_file(override_folder_path,
                                                             additional_suffix=additional_suffix,
                                                             new_extension='')

    print(f'{testing=}')
    if testing:
        output_folder = output_folder_testing_override

    '''
    Here are rough estimates of relative execution times for different alignment sample_alg (where nearest is the baseline):
    nearest: 1x
    bilinear: ~1.5x (slightly slower than nearest)
    cubic: ~2-3x (moderate increase in computation)
    cubicSpline: ~3-5x (slower due to smoother interpolation)
    lanczos: ~4-10x (highest quality, slowest due to large kernel and complexity)
    '''

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Align the rasters
    output_files = align_rasters(tif_files, output_folder, target_GSD_cm, sample_alg='cubic', load_into_QGIS=False)

    print("Aligned raster files:", output_files)

    align_rasters_time = time.time() - start_time

    get_time_sofar(start_time, 'Align rasters')



    # Guard clause: Check if we have enough rasters to proceed
    if len(output_files) < 2:
        print("Need at least two output files to compute overlap.")
        exit()

    # Define paths for the first two rasters
    first_raster_path = output_files[0]
    second_raster_path = output_files[1]
    first_path_simplified = simplified_name(first_raster_path)
    second_path_simplified = simplified_name(second_raster_path)
    first_raster_shape = get_vrt_shape(first_raster_path)
    second_raster_shape = get_vrt_shape(second_raster_path)
    first_ds = gdal.Open(first_raster_path)
    second_ds = gdal.Open(second_raster_path)
    gt1 = first_ds.GetGeoTransform()
    gt2 = second_ds.GetGeoTransform()
    proj1 = first_ds.GetProjection()
    proj2 = second_ds.GetProjection()

    overlap_mask_rough_number_of_pixels = calculate_overlapping_pixels(gt1,gt2, first_raster_shape, second_raster_shape)

    if proj1 != proj2:
        print("The two rasters have different projections.")
        exit()
    proj = proj1


    def get_out_path(input_file, output_folder):
        name, ext = os.path.splitext(os.path.basename(input_file))
        mask_name = name + '_mask' + ext
        return os.path.join(output_folder, mask_name)


    print("Creating input raster mask 1...")
    mask_path_1 = get_out_path(first_path_simplified, output_folder)
    if not testing:
        create_mask_with_gdal_translate(first_raster_path, mask_path_1)
    get_time_sofar(start_time, 'Input raster mask 1 created')
    print("Creating input raster mask 2...")
    mask_path_2 = get_out_path(second_path_simplified, output_folder)
    if not testing:
        create_mask_with_gdal_translate(second_raster_path, mask_path_2)

    get_time_sofar(start_time, 'Input raster mask 2 created')
    save_base = os.path.join(output_folder, os.path.basename(output_folder))
    wide_ext_overlap_vrt = save_base + "_overlap_wide_ext.vrt"
    create_wide_ext_overlap_vrt(mask_path_1, mask_path_2, wide_ext_overlap_vrt)

    get_time_sofar(start_time, 'wide ext overlap vrt created')

    overlap_path = save_base + "_overlap.tiff"
    if not testing:
        overlap_geotransform = narrow_overlap_vrt(wide_ext_overlap_vrt, overlap_path)
    else:
        overlap_geotransform = gdal.Open(overlap_path, gdal.GA_ReadOnly).GetGeoTransform()

    get_time_sofar(start_time, 'overlap mask tiff created')

    mask_dataset = gdal.Open(overlap_path)
    overlap_mask = mask_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)  # Read the first band

    overlap_mask_number_of_pixels = overlap_mask.size

    overlap_masks = detect_if_gappy_overlap_mask(overlap_mask)

    if len(overlap_masks)>1:
        gappy_overlap = True
        print(f'{gappy_overlap=}')
        print(f'# of overlap mask areas {len(overlap_masks)}')
        stubby_centre_lines = []
        endss = []
        for i, partial_overlap_mask in enumerate(overlap_masks):
            stubby_centre_line_partial, ends = compute_centerline(partial_overlap_mask, show_plot=False)
            stubby_centre_lines.append(stubby_centre_line_partial)
            endss.append(ends)

        connecting_lines_mask = connect_closest_ends(endss, overlap_mask.shape)
        stubby_centre_line = np.logical_or.reduce([*stubby_centre_lines, connecting_lines_mask])
    else:
        gappy_overlap = False
        print(f'{gappy_overlap=}')
        stubby_centre_line, _ = compute_centerline(overlap_masks[0], show_plot=False)

    stubby_centre_line_partial = None  # Free memory for partial stubby lines
    connecting_lines_mask = None       # Free memory for connecting lines

    get_time_sofar(start_time, 'Stubby centreline')

    def get_out_path(input_file, output_folder):
        name, ext = os.path.splitext(os.path.basename(input_file))
        mask_name = name + '_in_overlap.vrt'
        return os.path.join(output_folder, mask_name)

    first_raster_in_overlap = get_out_path(first_path_simplified, output_folder)
    second_raster_in_overlap = get_out_path(second_path_simplified, output_folder)
    first_tiff_in_overlap = first_raster_in_overlap[:-4] + ".tiff"
    second_tiff_in_overlap = second_raster_in_overlap[:-4] + ".tiff"

    if not testing:
        print('saving first_raster_in_overlap ...')
        apply_mask_to_rgb_rast(first_raster_path, overlap_path, first_raster_in_overlap)
        save_vrt_as_tiff(first_raster_in_overlap, first_tiff_in_overlap)

    if not testing:
        print('saving second_raster_in_overlap ...')
        apply_mask_to_rgb_rast(second_raster_path, overlap_path, second_raster_in_overlap)
        save_vrt_as_tiff(second_raster_in_overlap, second_tiff_in_overlap)

    get_time_sofar(start_time, 'RGB overlap tiffs')


    linestring_coords = generate_linestring(stubby_centre_line, num_points=num_points, show_plot=False)
    del stubby_centre_line
    gc.collect()

    # Generate the footprint mask, save_it, load it
    footprint_mask_path = save_base + "_footprint_mask.vrt"
    footprint_geotransform = get_footprint_mask(mask_path_1, mask_path_2, footprint_mask_path)

    # Swap the y, x to x, y in linestring_coords to create linestring_coords_xy
    linestring_coords_xy = np.zeros_like(linestring_coords)
    linestring_coords_xy[:, 0] = linestring_coords[:, 1]
    linestring_coords_xy[:, 1] = linestring_coords[:, 0]

    footprint_shape = get_vrt_shape(footprint_mask_path)

    full_centreline_coords_xy = extend_linestring_past_footprint(
        linestring_coords_xy, overlap_path, footprint_mask_path, show_plot=False)

    pixels_along_centreline = sample_line_over_raster(overlap_mask, full_centreline_coords_xy, show_plot=False)
    pixels_along_centreline_rev = reverse_order_sample_arr(pixels_along_centreline, show_plot=False)


    pixels_along_centreline_mask = np.zeros_like(pixels_along_centreline, dtype=np.uint8)
    pixels_along_centreline_mask[np.where(pixels_along_centreline > 0)] = 1
    pixels_along_centreline_mask_path = save_base + "_centreline_mask.tiff"
    save_bit_mask_with_gdal(pixels_along_centreline_mask, pixels_along_centreline_mask_path, overlap_geotransform, proj)


    path_preference_path = save_base + "_path_preference.tiff"

    if not testing:
        color_similarity = compute_similarity_old(first_tiff_in_overlap, second_tiff_in_overlap, overlap_mask,
                                                  show_plot=False)  # <<< DEMO

        print("calculating closeness_to_centreline_arr ... ")
        closeness_to_centreline_arr = closeness_to_centreline(overlap_mask, full_centreline_coords_xy,
                                                              show_plot=False)  # <<< DEMO

        centreline_mask = (closeness_to_centreline_arr > 0).astype(np.uint8)

        print("compute_path_preference_arr ... ")
        path_preference = compute_path_preference_arr(color_similarity, closeness_to_centreline_arr, prefer_centre_factor,
                                                      show_plot=False)  # <<< DEMO

        del closeness_to_centreline_arr, color_similarity
        gc.collect()

        save_rast_as_geotiff(path_preference * 254, path_preference_path, overlap_geotransform, proj)
    if testing:
        path_preference_dataset = gdal.Open(path_preference_path)
        path_preference = path_preference_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)  # Read the first band

    get_time_sofar(start_time, 'Path preference')

    start_pix = first_match_position(pixels_along_centreline, overlap_mask, show_plot=False)
    end_pix = first_match_position(pixels_along_centreline_rev, overlap_mask, show_plot=False)

    get_time_sofar(start_time, 'start_pix, end_pix')

    # plot_array(cut_path_mask, title="cut path", cmap="gray")
    cut_path_mask_path = save_base + "_cut_path_mask.tiff"

    if not testing:
        if len(overlap_masks) > 1:
            start_pixs = []
            end_pixs = []
            for i, partial_overlap_mask in enumerate(overlap_masks):
                #if i == 0:
                #    continue
                start_pixs.append(first_match_position(pixels_along_centreline, partial_overlap_mask, show_plot=False))
                end_pixs.append(first_match_position(pixels_along_centreline_rev, partial_overlap_mask, show_plot=False))

            del pixels_along_centreline, pixels_along_centreline_rev
            gc.collect()

            cut_path_masks = []
            for partial_overlap_mask, start_pix, end_pix in zip(overlap_masks, start_pixs, end_pixs):
                cut_path_masks.append(find_path(path_preference*partial_overlap_mask,
                                                partial_overlap_mask,
                                                start_pix, end_pix,
                                                pixels_along_centreline_mask,
                                                full_centreline_coords_xy,
                                                show_plot=False))
            connecting_lines_mask = connect_closest_ends([end_pixs,start_pixs], overlap_mask.shape)
            cut_path_mask = np.logical_or.reduce([*cut_path_masks, connecting_lines_mask])
            del connecting_lines_mask
            gc.collect()
        else:
            del pixels_along_centreline, pixels_along_centreline_rev
            gc.collect()

            print_ram([(name, sys.getsizeof(obj)) for name, obj in locals().items()])

            cut_path_mask = find_path(path_preference,
                                      overlap_mask,
                                      start_pix, end_pix,
                                      pixels_along_centreline_mask,
                                      full_centreline_coords_xy,
                                      show_plot=False)

        del overlap_mask, path_preference, pixels_along_centreline_mask
        gc.collect()

        save_bit_mask_with_gdal(cut_path_mask, cut_path_mask_path, overlap_geotransform, proj)
    if testing:
        del overlap_mask, path_preference, pixels_along_centreline_mask, pixels_along_centreline, pixels_along_centreline_rev
        gc.collect()
        cut_path_mask_dataset = gdal.Open(cut_path_mask_path)
        cut_path_mask = cut_path_mask_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

    get_time_sofar(start_time, 'Cut path mask')

    if get_cut_line_only:
        return

    cut_path_mask_footprint_frame = shift_mask_frame(cut_path_mask, overlap_geotransform, footprint_geotransform,
                                                            footprint_shape)

    del cut_path_mask
    gc.collect()
    line_ends_mask = rasterize_line_ends(full_centreline_coords_xy, footprint_shape, footprint_geotransform,
                                         overlap_geotransform, start_pix, end_pix,
                                         cut_path_mask_footprint_frame, show_plot=False)

    full_cut_path_mask = np.logical_or(line_ends_mask, cut_path_mask_footprint_frame).astype(np.uint8)

    del cut_path_mask_footprint_frame, line_ends_mask
    gc.collect()

    def get_cut_path_output_path(input_file, output_folder):
        name, ext = os.path.splitext(os.path.basename(input_file))
        mask_name = name + '_cut_path_mask_input_frame.tiff'
        return os.path.join(output_folder, mask_name)

    first_raster_cutpath_output_path = get_cut_path_output_path(first_path_simplified, output_folder)
    second_raster_cutpath_output_path = get_cut_path_output_path(second_path_simplified, output_folder)

    if not testing:
        cut_shifted_1 = shift_mask_frame_and_extend(full_cut_path_mask, footprint_geotransform, gt1, first_raster_shape, show_plot=False)
        save_bit_mask_with_gdal(cut_shifted_1, first_raster_cutpath_output_path, gt1, proj)

        cut_shifted_2 = shift_mask_frame_and_extend(full_cut_path_mask, footprint_geotransform, gt2, second_raster_shape, show_plot=False)
        save_bit_mask_with_gdal(cut_shifted_2, second_raster_cutpath_output_path, gt2, proj)
    else:
        cut_shifted_1_dataset = gdal.Open(first_raster_cutpath_output_path)
        cut_shifted_1 = cut_shifted_1_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

        cut_shifted_2_dataset = gdal.Open(second_raster_cutpath_output_path)
        cut_shifted_2 = cut_shifted_2_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

    del full_cut_path_mask
    gc.collect()

    get_time_sofar(start_time, 'cut path masks in original frame')

    keep_dir_unit_vector_1 = get_relative_direction(footprint_geotransform, footprint_shape, gt1,
                                                    first_raster_shape, show_plot=False)
    keep_dir_unit_vector_2 = get_relative_direction(footprint_geotransform, footprint_shape, gt2,
                                                    second_raster_shape, show_plot=False)

    get_time_sofar(start_time, 'Keep direction unit vectors')

    def get_out_mask_path(input_file, output_folder):
        name, ext = os.path.splitext(os.path.basename(input_file))
        mask_name = name + '_keep_mask' + ext
        return os.path.join(output_folder, mask_name)

    print(f'cutline to mask {first_raster_path=} {keep_dir_unit_vector_1=}')
    keep_mask_1 = cutline_to_mask(cut_shifted_1, keep_dir_unit_vector_1, show_plot=False)
    out_mask_path_1 = get_out_mask_path(first_path_simplified, output_folder)
    save_bit_mask_with_gdal(keep_mask_1, out_mask_path_1, gt1, proj)
    del cut_shifted_1
    gc.collect()

    print(f'cutline to mask {second_raster_path=} {keep_dir_unit_vector_2=}')
    keep_mask_2 = cutline_to_mask(cut_shifted_2, keep_dir_unit_vector_2, show_plot=False)
    out_mask_path_2 = get_out_mask_path(second_path_simplified, output_folder)
    save_bit_mask_with_gdal(keep_mask_2, out_mask_path_2, gt2, proj)
    del cut_shifted_2
    gc.collect()

    get_time_sofar(start_time, 'Keep masks')

    def get_out_mask_path(input_file, output_folder):
        name, ext = os.path.splitext(os.path.basename(input_file))
        mask_name = name + '_masked.vrt'
        return os.path.join(output_folder, mask_name)

    masked_vrt_1 = get_out_mask_path(first_path_simplified, output_folder)
    apply_mask_to_rgb_rast(first_raster_path, out_mask_path_1, masked_vrt_1)

    masked_vrt_2 = get_out_mask_path(second_path_simplified, output_folder)
    apply_mask_to_rgb_rast(second_raster_path, out_mask_path_2, masked_vrt_2)

    def get_out_mask_path(input_file, output_folder):
        name, ext = os.path.splitext(os.path.basename(input_file))
        mask_name = '_' + name + '_MERGED.VRT'
        return os.path.join(output_folder, mask_name)

    merged_out_path = get_out_mask_path(save_base, output_folder)
    merge_vrt_rasters(masked_vrt_1, masked_vrt_2, merged_out_path)

    first_raster_number_of_pixels = first_raster_shape[0] * first_raster_shape[1]
    second_raster_number_of_pixels = second_raster_shape[0] * second_raster_shape[1]

    ''' clean up '''
    if not testing and clean_up:
        os.remove(first_tiff_in_overlap)
        os.remove(second_tiff_in_overlap)
    ''' clean up '''

    total_execution_time = time.time() - start_time
    csv_file_path = save_base + "_metrics.csv"
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

    if beep_when_finished:
        print('Playing completion notification noises...')
        while True:
            winsound.Beep(200, 1000)
            sound_path = os.path.join(os.path.dirname(__file__),"The_geotiffs_have_been_merged.wav")
            winsound.PlaySound(sound_path, winsound.SND_FILENAME)
            time.sleep(2)