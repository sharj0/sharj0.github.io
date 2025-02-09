import os
import sys
import gc
import time
import numpy as np
import matplotlib.pyplot as plt
from osgeo import gdal
import json

# If you use relative imports inside a QGIS plugin or another package, adjust as needed:
from .pm_utils import (
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
    compute_centerline,
    get_time_sofar,
    detect_if_gappy_overlap_mask,
    connect_sorted_ends,
    narrow_overlap_vrt,
    get_vrt_shape,
    calculate_overlapping_pixels,
    simplified_name,
    downsample_two_masks,
    polygonize_and_find_intersections,
    combine_masks_in_common_frame,
    flatten_and_find_furthest_points,
    get_rid_of_extra_cutpath_arms,
    calls
)

from .save_geotiffs import (
    save_rast_as_geotiff,
    create_wide_ext_overlap_vrt,
    get_footprint_mask,
    apply_mask_to_rgb_rast,
    save_bit_mask_with_gdal,
    merge_vrt_rasters,
    save_output_to_raster,
    save_vrt_as_tiff,
)

from .Load_into_QGIS import load_mask_into_qgis
from . import plugin_tools

def print_ram(all_vars):
    # Convert sizes to GB and filter variables larger than 100 MB
    all_vars_filtered = [(name, size / (1024 ** 3)) for name, size in all_vars if size >= 100 * (1024 ** 2)]

    # Sort by size (descending)
    all_vars_sorted = sorted(all_vars_filtered, key=lambda x: x[1], reverse=True)

    # Print the results
    for var_name, size_gb in all_vars_sorted:
        print(f"{var_name}: {size_gb:.2f} GB")

def process_overlap_and_cutline(
    testing,
    proj,
    epsg_code_int,
    gt1,
    gt2,
    start_time,
    prefer_centre_factor,
    first_input_related_save_base,
    second_input_related_save_base,
    merge_related_save_base,
    telem_path,
    cut_path_mask_custom_common_frame_path,
    input_mask_path_1,
    input_mask_path_2,
    first_raster_path,
    second_raster_path,
):
    first_low_res_mask_path = first_input_related_save_base + '_low_res_mask.tiff'
    second_low_res_mask_path = second_input_related_save_base + '_low_res_mask.tiff'

    if not testing:
        downsample_two_masks(input_mask_path_1,
                             input_mask_path_2,
                             first_low_res_mask_path,
                             second_low_res_mask_path)

    get_time_sofar(start_time, f'[{calls.p}] Low res masks created...')

    mask_outline_intersections_kml_path = merge_related_save_base + "_mask_outline_intersections.kml"

    intersections_per_ovelap_area = polygonize_and_find_intersections(
        first_low_res_mask_path,
        second_low_res_mask_path,
        mask_outline_intersections_kml_path,
        target_epsg_code=epsg_code_int,
        save_intersections_to_shp=True,
        show_plot=False
    )

    print(f"intersections saved to:{mask_outline_intersections_kml_path}")
    get_time_sofar(start_time, f'[{calls.p}] Mask outline intersections found...')

    wide_ext_overlap_vrt = merge_related_save_base + "_overlap_wide_ext.vrt"
    create_wide_ext_overlap_vrt(input_mask_path_1, input_mask_path_2, wide_ext_overlap_vrt)

    get_time_sofar(start_time, f'[{calls.p}] wide ext overlap vrt created')

    overlap_path = merge_related_save_base + "_overlap.tiff"
    if not testing:
        overlap_geotransform = narrow_overlap_vrt(wide_ext_overlap_vrt, overlap_path)
    else:
        overlap_geotransform = gdal.Open(overlap_path, gdal.GA_ReadOnly).GetGeoTransform()

    get_time_sofar(start_time, f'[{calls.p}] overlap mask tiff created')

    mask_dataset = gdal.Open(overlap_path)

    overlap_mask_npy_path = merge_related_save_base + "_overlap_mask.npy"
    shape = (mask_dataset.RasterYSize, mask_dataset.RasterXSize)
    overlap_mask = np.memmap(overlap_mask_npy_path, dtype=np.uint8, mode='w+', shape=shape)
    overlap_mask[:] = mask_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

    overlap_mask_number_of_pixels = overlap_mask.size

    print('determining if overlap area has gaps...')
    overlap_masks = detect_if_gappy_overlap_mask(overlap_mask)

    origin_x, pixel_width, _, origin_y, _, pixel_height = overlap_geotransform

    intersections_per_ovelap_area_pixel_coords = []
    for intersections in intersections_per_ovelap_area:
        intersections_pixel_coords = []
        for point in intersections:
            x, y = point.x, point.y
            # Compute pixel coordinates
            col = (x - origin_x) / pixel_width
            row = (origin_y - y) / abs(pixel_height)
            intersections_pixel_coords.append((int(col), int(row)))  # Use int() for pixel indices
        intersections_per_ovelap_area_pixel_coords.append(intersections_pixel_coords)

    if len(overlap_masks) > 1:
        gappy_overlap = True
        print(f'{gappy_overlap=}')
        print(f'# of overlap mask areas {len(overlap_masks)}')
        stubby_centre_lines = []
        endss = []
        for i, partial_overlap_mask in enumerate(overlap_masks):
            stubby_centre_line_partial, ends = compute_centerline(
                partial_overlap_mask,
                intersections_per_ovelap_area_pixel_coords,
                show_plot=False
            )
            stubby_centre_lines.append(stubby_centre_line_partial)
            endss.append(ends)

        connecting_lines_mask = connect_sorted_ends(endss, overlap_mask.shape, show_plot=False)
        stubby_centre_line = np.logical_or.reduce([*stubby_centre_lines, connecting_lines_mask])
        del stubby_centre_line_partial
        del connecting_lines_mask
        gc.collect()
    else:
        gappy_overlap = False
        print(f'{gappy_overlap=}')
        stubby_centre_line, _ = compute_centerline(
            overlap_masks[0],
            intersections_per_ovelap_area_pixel_coords,
            show_plot=False
        )

    get_time_sofar(start_time, f'[{calls.p}] Stubby centreline')

    first_raster_in_overlap = first_input_related_save_base + '_in_overlap.vrt'
    second_raster_in_overlap = second_input_related_save_base + '_in_overlap.vrt'

    first_tiff_in_overlap = first_raster_in_overlap[:-4] + ".tiff"
    second_tiff_in_overlap = second_raster_in_overlap[:-4] + ".tiff"

    if not testing:
        print('saving first_raster_in_overlap ...')
        apply_mask_to_rgb_rast(first_raster_path, overlap_path, first_raster_in_overlap)
        save_vrt_as_tiff(first_raster_in_overlap, first_tiff_in_overlap)

        print('saving second_raster_in_overlap ...')
        apply_mask_to_rgb_rast(second_raster_path, overlap_path, second_raster_in_overlap)
        save_vrt_as_tiff(second_raster_in_overlap, second_tiff_in_overlap)


    get_time_sofar(start_time, f'[{calls.p}] RGB overlap tiffs')

    linestring_coords = generate_linestring(stubby_centre_line, num_points=30, show_plot=False)
    del stubby_centre_line
    gc.collect()

    # Generate the footprint mask
    footprint_mask_path = merge_related_save_base + "_footprint_mask.vrt"
    footprint_geotransform = get_footprint_mask(input_mask_path_1, input_mask_path_2, footprint_mask_path)

    # Convert linestring coords [row, col] -> [x, y]
    linestring_coords_xy = np.zeros_like(linestring_coords)
    linestring_coords_xy[:, 0] = linestring_coords[:, 1]
    linestring_coords_xy[:, 1] = linestring_coords[:, 0]

    footprint_shape = get_vrt_shape(footprint_mask_path)
    furthest_intersection_points = flatten_and_find_furthest_points(intersections_per_ovelap_area)

    full_centreline_coords_xy = extend_linestring_past_footprint(
        linestring_coords_xy,
        overlap_path,
        footprint_mask_path,
        furthest_intersection_points,
        show_plot=False
    )

    pixels_along_centreline = sample_line_over_raster(overlap_mask, full_centreline_coords_xy, show_plot=False)
    pixels_along_centreline_rev = reverse_order_sample_arr(pixels_along_centreline, show_plot=False)

    pixels_along_centreline_mask = np.zeros_like(pixels_along_centreline, dtype=np.uint8)
    pixels_along_centreline_mask[np.where(pixels_along_centreline > 0)] = 1
    pixels_along_centreline_mask_path = merge_related_save_base + "_centreline_mask.tiff"


    if not testing:
        save_bit_mask_with_gdal(pixels_along_centreline_mask, pixels_along_centreline_mask_path, overlap_geotransform, proj)

    get_time_sofar(start_time,f'[{calls.p}] Centreline mask')

    path_preference_path = merge_related_save_base + "_path_preference.tiff"


    if not testing:
        color_similarity = compute_similarity_old(
            first_tiff_in_overlap,
            second_tiff_in_overlap,
            overlap_mask,
            show_plot=False
        )

        print("calculating closeness_to_centreline_arr ... ")
        closeness_to_centreline_arr = closeness_to_centreline(
            overlap_mask,
            full_centreline_coords_xy,
            show_plot=False
        )

        centreline_mask = (closeness_to_centreline_arr > 0).astype(np.uint8)

        print("compute_path_preference_arr ... ")
        path_preference = compute_path_preference_arr(
            color_similarity,
            closeness_to_centreline_arr,
            prefer_centre_factor,
            show_plot=False
        )

        del closeness_to_centreline_arr, color_similarity
        gc.collect()

        save_rast_as_geotiff(path_preference * 254, path_preference_path, overlap_geotransform, proj)

    if testing:
        path_preference_dataset = gdal.Open(path_preference_path)
        path_preference = path_preference_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

    get_time_sofar(start_time, f'[{calls.p}] Path preference')

    start_pix_overall = first_match_position(pixels_along_centreline, overlap_mask, show_plot=False)
    end_pix_overall = first_match_position(pixels_along_centreline_rev, overlap_mask, show_plot=False)

    get_time_sofar(start_time, f'[{calls.p}] start_pix, end_pix')
    overlap_mask_shape = overlap_mask.shape
    cut_path_mask_path = merge_related_save_base + "_cut_path_mask.tiff"
    if not testing:
        if len(overlap_masks) > 1:
            start_pixs = []
            end_pixs = []
            for i, partial_overlap_mask in enumerate(overlap_masks):
                start_pixs.append(first_match_position(pixels_along_centreline, partial_overlap_mask, show_plot=False))
                end_pixs.append(first_match_position(pixels_along_centreline_rev, partial_overlap_mask, show_plot=False))

            del pixels_along_centreline, pixels_along_centreline_rev
            gc.collect()

            cut_path_masks = []
            for partial_overlap_mask, start_pix, end_pix in zip(overlap_masks, start_pixs, end_pixs):
                cut_path_masks.append(find_path(
                    path_preference * partial_overlap_mask,
                    partial_overlap_mask,
                    start_pix,
                    end_pix,
                    pixels_along_centreline_mask,
                    full_centreline_coords_xy,
                    show_plot=False
                ))

            cut_endss = list(zip(start_pixs, end_pixs))
            connecting_lines_mask = connect_sorted_ends(cut_endss, overlap_mask.shape)
            cut_path_mask = np.logical_or.reduce([*cut_path_masks, connecting_lines_mask])

            del connecting_lines_mask
            gc.collect()
        else:
            del pixels_along_centreline, pixels_along_centreline_rev
            gc.collect()

            print_ram([(name, sys.getsizeof(obj)) for name, obj in locals().items()])

            start_pix = start_pix_overall
            end_pix = end_pix_overall

            cut_path_mask = find_path(
                path_preference,
                overlap_mask,
                start_pix,
                end_pix,
                pixels_along_centreline_mask,
                full_centreline_coords_xy,
                show_plot=False
            )

        del overlap_mask, path_preference, pixels_along_centreline_mask
        gc.collect()
        save_bit_mask_with_gdal(cut_path_mask, cut_path_mask_path, overlap_geotransform, proj)

    elif testing:
        del overlap_mask, path_preference, pixels_along_centreline_mask, pixels_along_centreline, pixels_along_centreline_rev
        gc.collect()
        cut_path_mask_dataset = gdal.Open(cut_path_mask_path)
        cut_path_mask = cut_path_mask_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)

    get_time_sofar(start_time, f'[{calls.p}] Cut path mask')

    if not testing:
        line_ends_mask_temp_cust_frame, gt_temp_cust_frame = rasterize_line_ends(
            full_centreline_coords_xy,
            footprint_shape,
            footprint_geotransform,
            overlap_geotransform,
            start_pix_overall,
            end_pix_overall,
            show_plot=False
        )

        get_time_sofar(start_time, f'[{calls.p}] Rasterize line ends')

        cut_path_mask_custom_common_frame, gt_cust_custom_common_frame = combine_masks_in_common_frame(
            mask1=cut_path_mask,
            gt1=overlap_geotransform,
            mask2=line_ends_mask_temp_cust_frame,
            gt2=gt_temp_cust_frame,
            fill_value=0
        )
        save_bit_mask_with_gdal(cut_path_mask_custom_common_frame,
                                cut_path_mask_custom_common_frame_path,
                                gt_cust_custom_common_frame, proj)
        del line_ends_mask_temp_cust_frame
        gc.collect()

    del cut_path_mask,
    gc.collect()

    get_time_sofar(start_time, f'[{calls.p}] Cut path mask with ends')
    
    print(footprint_geotransform)
    print(footprint_shape)
    print(overlap_geotransform)
    print(overlap_mask_shape)
    save_telem_data(telem_path,
                    (overlap_geotransform, overlap_mask_shape, overlap_mask_number_of_pixels),
                    start_pix_overall, end_pix_overall)

def save_telem_data(telem_path, data, start_pix_overall=None, end_pix_overall=None):
    """
    Save the variables to a file in a human-readable JSON format.

    Parameters:
    - telem_path (str): Path to the file where the data will be saved.
    - data (tuple): The variables to save (geotransform, shape, value).
    - start_pix_overall (tuple): Start pixel coordinates (optional).
    - end_pix_overall (tuple): End pixel coordinates (optional).
    """
    geotransform, shape, value = data

    # Convert numpy.int64 to Python int
    if start_pix_overall:
        start_pix_overall = tuple(int(x) for x in start_pix_overall)
    if end_pix_overall:
        end_pix_overall = tuple(int(x) for x in end_pix_overall)

    # Create a dictionary for better readability
    data_dict = {
        "geotransform": {
            "top_left_x": geotransform[0],
            "pixel_width": geotransform[1],
            "rotation_1": geotransform[2],
            "top_left_y": geotransform[3],
            "rotation_2": geotransform[4],
            "pixel_height": geotransform[5],
        },
        "shape": {
            "rows": shape[0],
            "cols": shape[1],
        },
        "value": value,
        "start_pixel": start_pix_overall,
        "end_pixel": end_pix_overall,
    }

    # Save to JSON file
    with open(telem_path, "w") as file:
        json.dump(data_dict, file, indent=4)


def load_telem_data(telem_path):
    """
    Load the variables from a file saved in JSON format.

    Parameters:
    - telem_path (str): Path to the file to read the data from.

    Returns:
    - tuple: The loaded variables (geotransform, shape, value, start_pix_overall, end_pix_overall).
    """
    with open(telem_path, "r") as file:
        data_dict = json.load(file)

    # Reconstruct the original tuple
    geotransform = (
        data_dict["geotransform"]["top_left_x"],
        data_dict["geotransform"]["pixel_width"],
        data_dict["geotransform"]["rotation_1"],
        data_dict["geotransform"]["top_left_y"],
        data_dict["geotransform"]["rotation_2"],
        data_dict["geotransform"]["pixel_height"],
    )

    shape = (
        data_dict["shape"]["rows"],
        data_dict["shape"]["cols"],
    )

    value = data_dict["value"]
    start_pix_overall = data_dict.get("start_pixel")
    end_pix_overall = data_dict.get("end_pixel")

    return geotransform, shape, value, start_pix_overall, end_pix_overall