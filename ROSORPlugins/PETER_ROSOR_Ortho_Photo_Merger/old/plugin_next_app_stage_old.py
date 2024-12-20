'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from . import plugin_tools
from . import plotting

import os
import numpy as np
from osgeo import gdal
import time

from .align_rasters import (align_rasters,
                           get_list_of_paths_os_walk_folder,
                           get_name_of_non_existing_output_file)

from .overlap_mask_and_other_funcs import (
    get_file_size_in_gb,
    get_overlap_mask,
    get_footprint_mask,
    generate_linestring,
    plot_array,
    extend_linestring_past_footprint,
    closeness_to_centreline,
    compute_similarity,
    compute_path_preference_arr,
    sample_line_over_raster,
    reverse_order_sample_arr,
    first_match_position,
    find_path,
    rasterize_line_ends,
    shift_mask_to_footprint,
    get_relative_direction,
    cut_out_pixels,
    compute_centerline,
    save_metrics_to_csv,
    get_time_sofar,
    select_folder,
    select_tiff_files
    )

from .save_geotiffs import save_mask_as_geotiff, merge_rasters_with_mask, save_output_to_raster

from .Load_into_QGIS import load_mask_into_qgis

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    #"First Time Setup"
    target_GSD_meters = settings_dict['Target GSD meters']  # meters
    prefer_centre_factor = settings_dict['Prefer centre factor']
    num_points = settings_dict['Line sample points']
    Ortho_photo_1_file_path = settings_dict['Ortho_photo_1_file_path']
    Ortho_photo_2_file_path = settings_dict['Ortho_photo_2_file_path']
    settings_dict = None # don't use settings_dict from here on
    if not target_GSD_meters in [0.05, 0.1, 0.2, 0.5, 1]:
        plugin_tools.show_error("target_GSD_meters must be either a whole number of meters or a factor of a meter [0.05, 0.1, 0.2, 0.5, 1]")

    start_time = time.time()

    tif_files = [Ortho_photo_1_file_path, Ortho_photo_2_file_path]

    dirnames = [os.path.dirname(path) for path in tif_files]

    # Assert that all directory names are the same
    assert len(set(dirnames)) == 1, f"All files must be in the same directory. Found directories: {set(dirnames)}"

    folder_path = dirnames[0]

    size_of_all_inputs_gb = 0
    for tif_file in tif_files:
        size_of_all_inputs_gb += get_file_size_in_gb(tif_file)

    target_GSD_cm = round(target_GSD_meters * 100)

    print(f"Starting processing on {round(size_of_all_inputs_gb, 2)} GBs of data at {target_GSD_cm} cm GSD")

    output_folder = get_name_of_non_existing_output_file(folder_path,
                                                         additional_suffix=f'_merging_at_{target_GSD_cm}_GSD',
                                                         new_extension='')

    # Align the rasters
    output_files = align_rasters(tif_files, output_folder, target_GSD_meters, load_into_QGIS=False)

    print("Aligned raster files:", output_files)

    get_time_sofar(start_time, 'Align rasters')

    # Guard clause: Check if we have enough rasters to proceed
    if len(output_files) < 2:
        print("Need at least two output files to compute overlap.")
        exit()

    # Define paths for the first two rasters
    first_raster_path = output_files[0]
    second_raster_path = output_files[1]

    save_base = os.path.join(output_folder, os.path.basename(output_folder))

    # Open the datasets
    first_ds = gdal.Open(first_raster_path)
    second_ds = gdal.Open(second_raster_path)

    # Read all bands into NumPy arrays for the entire datasets
    num_bands1_full = first_ds.RasterCount
    stacked_data1 = np.array([first_ds.GetRasterBand(i + 1).ReadAsArray() for i in range(num_bands1_full)])
    stacked_data1 = np.transpose(stacked_data1, (1, 2, 0))

    num_bands2_full = second_ds.RasterCount
    stacked_data2 = np.array([second_ds.GetRasterBand(i + 1).ReadAsArray() for i in range(num_bands2_full)])
    stacked_data2 = np.transpose(stacked_data2, (1, 2, 0))

    get_time_sofar(start_time, 'Extract bands')

    # Get geotransforms and projections
    gt1 = first_ds.GetGeoTransform()
    gt2 = second_ds.GetGeoTransform()
    proj1 = first_ds.GetProjection()
    proj2 = second_ds.GetProjection()

    if proj1 != proj2:
        print("The two rasters have different projections.")
        exit()
    proj = proj1

    overlap_mask, overlap_geotransform = get_overlap_mask(first_ds, second_ds)
    if overlap_mask is None: print("No overlap detected between the two rasters."); exit()
    # plot_array(overlap_mask, title="overlap_mask", cmap="gray")

    get_time_sofar(start_time, 'Overlap mask')

    stubby_centre_line = compute_centerline(overlap_mask, show_plot=False)
    # plot_array(stubby_centre_line, title="stubby_centre_line", cmap="gray")

    get_time_sofar(start_time, 'Stubby centreline')

    linestring_coords = generate_linestring(stubby_centre_line, num_points=num_points, show_plot=False)

    # Generate the footprint mask, save_it, load it
    footprint_mask, footprint_geotransform, proj = get_footprint_mask(first_raster_path, second_raster_path)

    # Swap the y, x to x, y in linestring_coords to create linestring_coords_xy
    linestring_coords_xy = np.zeros_like(linestring_coords)
    linestring_coords_xy[:, 0] = linestring_coords[:, 1]
    linestring_coords_xy[:, 1] = linestring_coords[:, 0]

    full_centreline_coords_xy = extend_linestring_past_footprint(
        linestring_coords_xy, footprint_mask, footprint_geotransform, overlap_geotransform, show_plot=False)

    overlap_mask_norm = overlap_mask / 255

    pixels_along_centreline = sample_line_over_raster(overlap_mask_norm, full_centreline_coords_xy, show_plot=False)
    pixels_along_centreline_rev = reverse_order_sample_arr(pixels_along_centreline, show_plot=False)

    pixels_along_centreline_mask = np.zeros_like(pixels_along_centreline)
    pixels_along_centreline_mask[np.where(pixels_along_centreline > 0)] = 1

    color_similarity = compute_similarity(first_ds, second_ds, overlap_mask, overlap_geotransform,
                                          show_plot=False)  # <<< DEMO
    closeness_to_centreline_arr = closeness_to_centreline(overlap_mask_norm, full_centreline_coords_xy,
                                                          show_plot=False)  # <<< DEMO
    path_preference = compute_path_preference_arr(color_similarity, closeness_to_centreline_arr, prefer_centre_factor,
                                                  show_plot=False)  # <<< DEMO

    path_preference_path = save_base + "_path_preference.tif"
    save_mask_as_geotiff(path_preference * 254, path_preference_path, overlap_geotransform, proj)

    get_time_sofar(start_time, 'Path preference')

    start_pix = first_match_position(pixels_along_centreline, overlap_mask_norm, show_plot=False)
    end_pix = first_match_position(pixels_along_centreline_rev, overlap_mask_norm, show_plot=False)

    pixels_along_centreline_mask_path = save_base + "_centreline_mask.tif"
    save_mask_as_geotiff(pixels_along_centreline_mask, pixels_along_centreline_mask_path, overlap_geotransform, proj)

    cut_path_mask = find_path(path_preference, start_pix, end_pix)
    # plot_array(cut_path_mask, title="cut path", cmap="gray")
    cut_path_mask_path = save_base + "_cut_path_mask.tif"
    save_mask_as_geotiff(cut_path_mask, cut_path_mask_path, overlap_geotransform, proj)


    cut_path_mask_footprint_frame = shift_mask_to_footprint(cut_path_mask, overlap_geotransform, footprint_geotransform,
                                                            footprint_mask.shape)

    line_ends_mask = rasterize_line_ends(full_centreline_coords_xy, footprint_mask, footprint_geotransform,
                                         overlap_geotransform, start_pix, end_pix,
                                         cut_path_mask_footprint_frame, show_plot=False)

    full_cut_path_mask = np.logical_or(line_ends_mask, cut_path_mask_footprint_frame).astype(np.uint8)

    # plot_array(full_cut_path_mask, title="cut path", cmap="gray")

    cut_shifted_1 = shift_mask_to_footprint(full_cut_path_mask, footprint_geotransform, gt1, stacked_data1.shape[:2])
    cut_shifted_2 = shift_mask_to_footprint(full_cut_path_mask, footprint_geotransform, gt2, stacked_data2.shape[:2])

    keep_dir_unit_vector_1 = get_relative_direction(footprint_geotransform, footprint_mask.shape, gt1,
                                                    stacked_data1.shape[:2], show_plot=False)
    keep_dir_unit_vector_2 = get_relative_direction(footprint_geotransform, footprint_mask.shape, gt2,
                                                    stacked_data2.shape[:2], show_plot=False)

    stacked_data_out_1 = cut_out_pixels(stacked_data1, cut_shifted_1, keep_dir_unit_vector_1, show_plot=False)
    stacked_data_out_2 = cut_out_pixels(stacked_data2, cut_shifted_2, keep_dir_unit_vector_2, show_plot=False)

    merged_out_path = save_base + "_merged.tiff"
    merged_data = merge_rasters_with_mask(stacked_data_out_1, stacked_data_out_2, gt1, gt2, footprint_geotransform,
                                          footprint_mask.shape)

    # plot_array(merged_data, title="merged_data", cmap="gray")

    save_output_to_raster(merged_data, merged_out_path, footprint_geotransform, proj)

    load_mask_into_qgis(merged_out_path)
    load_mask_into_qgis(path_preference_path)
    load_mask_into_qgis(pixels_along_centreline_mask_path)
    load_mask_into_qgis(cut_path_mask_path)

    end_time = time.time()
    execution_time = end_time - start_time
    csv_file_path = save_base + "_metrics.csv"
    save_metrics_to_csv(csv_file_path, execution_time, size_of_all_inputs_gb, target_GSD_cm)
    get_time_sofar(start_time, 'ALL')

    plugin_tools.show_information(f" ALL DONE {merged_out_path=}")
    #plugin_tools.show_error(" NOT ACTUALLY AN EROROROR, JUST TESTING TEMPLATE ")
    #plotting.plot_stuff([1, 2], [3, 4])