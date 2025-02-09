import os
import csv
import math
import re
import time
from osgeo import gdal, osr
import numpy as np
from remotior_sensus.util.files_directories import output_path
import winsound
import subprocess

# "C:/Program Files/QGIS 3.38.0/bin/python-qgis.bat" "C:\Users\pyoty\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\PETER_ROSOR_Ortho_Photo_Merger\align_rasters.py"

def align_rasters(tif_files,
                  output_folder,
                  target_GSD_cm=100,
                  load_into_QGIS=True,
                  sample_alg='bilinear',
                  do_save_metrics_to_csv=False,
                  beep_when_finished=False,
                  epsg_int_override=None):
    start_time = time.time()
    target_GSD = target_GSD_cm / 100
    assert target_GSD in [0.05, 0.1, 0.2, 0.5, 1], \
        "target_GSD must be either a whole number of meters or a factor of a meter [0.05, 0.1, 0.2, 0.5, 1]"

    print("Please wait...")
    gdal.UseExceptions()

    output_files = substitute_output_folder(tif_files, output_folder)

    extents = []
    number_of_pixs = []
    for i, (input_file, output_file) in enumerate(zip(tif_files, output_files)):
        assert not input_file == output_file
        dataset = gdal.Open(input_file)
        if not dataset:
            print(f"Failed to open {input_file}")
            continue

        geotransform = dataset.GetGeoTransform()
        input_crs = dataset.GetProjection()

        top_left_x = geotransform[0]
        pixel_size_x = geotransform[1]
        top_left_y = geotransform[3]
        pixel_size_y = geotransform[5]

        if is_raster_aligned(geotransform, target_GSD, debug_print=False):
            print(f"{input_file} is already aligned. Skipping alignment.")
            output_files[i] = input_file  # Use original file path if already aligned
            dataset = None
            continue

        raster_x_size = dataset.RasterXSize
        raster_y_size = dataset.RasterYSize

        number_of_pix = raster_x_size * raster_y_size
        number_of_pixs.append(number_of_pix)

        # Calculate new alignment
        left = top_left_x
        top = top_left_y
        right = left + pixel_size_x * raster_x_size
        bottom = top + pixel_size_y * raster_y_size

        new_left = math.floor(left / target_GSD) * target_GSD
        new_right = math.ceil(right / target_GSD) * target_GSD
        new_top = math.ceil(top / target_GSD) * target_GSD
        new_bottom = math.floor(bottom / target_GSD) * target_GSD

        output_file = simplified_name(output_file)
        output_files[i] = output_file
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        output_data_type = dataset.GetRasterBand(1).DataType

        if epsg_int_override:
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(epsg_int_override)  # EPSG code for WGS 84 / UTM zone 21N
            outp_epsg = srs.ExportToWkt()  # Get the WKT string

        else:
            outp_epsg=input_crs

        warp_options = gdal.WarpOptions(
            format='GTiff',
            outputBounds=(new_left, new_bottom, new_right, new_top),
            xRes=target_GSD,
            yRes=-target_GSD,
            dstSRS=outp_epsg,
            resampleAlg=sample_alg,
            outputType=output_data_type,
            creationOptions=['COMPRESS=LZW', 'BIGTIFF=YES'],
            callback=progress_callback,
            callback_data=None
        )
        print(f"Shifting raster {os.path.basename(output_file)}")
        print(f"{input_file} -> {output_file}")
        os.makedirs(output_folder, exist_ok=True)
        gdal.Warp(output_file, dataset, options=warp_options)

        extents.append((new_left, new_bottom, new_right, new_top))
        dataset = None

        alignment_execution_time = time.time() - start_time
        batch = f'{i+1}/{len(tif_files)}'
        if do_save_metrics_to_csv:
            if alignment_execution_time > 1:
                number_of_all_pix_aligned = np.sum(number_of_pixs)
                csv_file_path = os.path.join(os.path.dirname(output_file),'alignment_stats.csv')
                save_metrics_to_csv(csv_file_path,
                                    alignment_execution_time=alignment_execution_time,
                                    sample_alg=sample_alg,
                                    target_GSD_cm=target_GSD_cm,
                                    number_of_all_pix_aligned=number_of_all_pix_aligned,
                                    file_name=input_file,
                                    batch=batch)

    if beep_when_finished and __name__ == '__main__':
        print('Playing completion notification noises...')
        while True:
            winsound.Beep(200, 1000)
            sound_path = os.path.join(os.path.dirname(__file__),"The_geotiffs_have_been_merged.wav")
            winsound.PlaySound(sound_path, winsound.SND_FILENAME)
            time.sleep(2)

    elif beep_when_finished:
        print('Playing completion notification noises...')
        for _ in range(3):
            winsound.Beep(200, 1000)
            sound_path = os.path.join(os.path.dirname(__file__), "The_geotiffs_have_been_merged.wav")
            winsound.PlaySound(sound_path, winsound.SND_FILENAME)
            time.sleep(2)

    if not load_into_QGIS:
        return output_files

    try:
        from qgis.core import QgsProject, QgsRasterLayer
        from qgis.utils import iface

        # Load output files as layers if in QGIS
        if iface:  # Check if in QGIS Desktop environment
            for output_file in output_files:
                layer_name = os.path.basename(output_file)
                raster_layer = QgsRasterLayer(output_file, layer_name)
                if raster_layer.isValid():
                    QgsProject.instance().addMapLayer(raster_layer)
                    print(f"Loaded {layer_name} into QGIS.")
                else:
                    print(f"Failed to load {layer_name} into QGIS.")
    except ImportError:
        print("Not running within QGIS Desktop; skipping layer loading.")


    return output_files

# Function to save metrics to a CSV
def save_metrics_to_csv(csv_path, **metrics):
    """
    Save metrics to a CSV file dynamically based on the input variables.

    Parameters:
        csv_path (str): Path to the CSV file.
        **metrics: Arbitrary keyword arguments representing metric names and values.

    Example usage:
        save_metrics_to_csv('metrics.csv', execution_time=12.34, file_size_gb=1.23, gsd=15.6)
    """
    # Get the names of the metrics from the arguments
    metric_names = list(metrics.keys())
    metric_values = list(metrics.values())

    # Check if CSV exists to determine if headers are needed
    file_exists = os.path.isfile(csv_path)
    # Open the CSV file and write data
    with open(csv_path, mode='a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(metric_names)
        writer.writerow([round(value, 2) if isinstance(value, (float, int)) else value for value in metric_values])

    print(f"Metrics saved to {csv_path}")

def is_raster_aligned(geotransform, target_GSD, debug_print=False):
    """
    Check if a raster is aligned to the specified target GSD.

    Parameters:
        geotransform (tuple): Geotransform of the raster.
        target_GSD (float): Target ground sampling distance.
        debug_print (bool): If True, prints debug information.

    Returns:
        bool: True if the raster is aligned, False otherwise.
    """
    top_left_x, pixel_size_x, _, top_left_y, _, pixel_size_y = geotransform
    threshold = 1e-8

    pixel_size_x_matches_target_GSD = math.isclose(pixel_size_x, target_GSD, rel_tol=threshold, abs_tol=threshold)
    pixel_size_y_matches_target_GSD = math.isclose(pixel_size_y, -target_GSD, rel_tol=threshold, abs_tol=threshold)

    if debug_print:
        print(f"\n{pixel_size_x=}")
        print(f"{pixel_size_y=}")
        print(f"{target_GSD=}")
        print(f"pixel_size_x == target_GSD {pixel_size_x_matches_target_GSD}")
        print(f"pixel_size_y == -target_GSD {pixel_size_y_matches_target_GSD}")
        print(f"{top_left_x=}")
        print(f"{top_left_y=}")
        print(f"abs(top_left_x / target_GSD - round(top_left_x / target_GSD)) < 1e-6 {abs(top_left_x / target_GSD - round(top_left_x / target_GSD)) < 1e-6}")
        print(f"abs(top_left_y / target_GSD - round(top_left_y / target_GSD)) < 1e-6 {abs(top_left_y / target_GSD - round(top_left_y / target_GSD)) < 1e-6}")
        print()

    return (
        pixel_size_x_matches_target_GSD and
        pixel_size_y_matches_target_GSD and
        abs(top_left_x / target_GSD - round(top_left_x / target_GSD)) < 1e-6 and
        abs(top_left_y / target_GSD - round(top_left_y / target_GSD)) < 1e-6
    )


def calculate_single_overview_level(file_path, target_resolution=2000):
    """
    Calculates the closest single overview level to make the longest edge close to the target resolution.
    """
    # Open the raster file
    dataset = gdal.Open(file_path)
    if dataset is None:
        print(f"Failed to open {file_path}")
        return None

    # Get raster dimensions
    width = dataset.RasterXSize
    height = dataset.RasterYSize
    longest_edge = max(width, height)

    # Calculate the single closest downsampling factor (power of 2)
    factor = 1
    while longest_edge / factor > target_resolution:
        factor *= 2

    return factor


def build_single_internal_overview(file_path, target_resolution=2000):
    print("Building overview...")
    """
    Builds a single internal overview with LZW compression for a GeoTIFF.
    """
    # Calculate the overview level
    overview_level = calculate_single_overview_level(file_path, target_resolution)

    if overview_level is None:
        print("Failed to calculate the overview level.")
        return

    # Run gdaladdo with the single calculated level
    command = [
        "gdaladdo",
        "--config", "COMPRESS_OVERVIEW", "LZW",  # Enable LZW compression
        "--config", "INTERLEAVE_OVERVIEW", "PIXEL",  # Ensure pixel interleaving
        "-r", "average",  # Resampling method
        file_path,
        str(overview_level)  # Single overview level
    ]

    print(f"Running command: {' '.join(command)}")
    subprocess.run(command, check=True)

def simplified_name(file_path):
    # Get the directory and filename
    directory, filename = os.path.split(file_path)

    # Remove leading underscores and '_MERGED', and convert to lowercase
    simplified_filename = filename.lstrip('_').replace('_MERGED', '').lower()

    outp = os.path.splitext(os.path.join(directory, simplified_filename))[0] + '.tiff'
    # Combine back into the full path

    ''' add code to edit the gsd number, cuz right now if it was called 5_gsd beofre allignment, its still 5_gsd after conversion to 100 gsd'''

    return outp

def get_list_of_paths_os_walk_folder(folder_path, ext):
    file_paths = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if os.path.splitext(filename)[1].lower() == ext.lower():
                file_path = os.path.join(root, filename)
                file_paths.append(file_path)

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

    file_paths.sort(key=natural_sort_key)
    return file_paths


def substitute_output_folder(path_list, substitute_folder):
    new_paths = []
    for path in path_list:
        filename = os.path.basename(path)  # Extract only the filename
        new_path = os.path.join(substitute_folder, filename)  # Combine with the new folder
        new_path = os.path.normpath(new_path)  # Normalize the path
        new_paths.append(new_path)
    return new_paths


def get_name_of_non_existing_output_file(base_filepath, additional_suffix='', new_extension=''):
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

def progress_callback(complete, message, _userdata):
    """
    A simple progress callback that prints the percentage of completion.
    """
    percent = int(complete * 100)
    print(f"Alignment: {percent}% completed", end="\r")
    # Return 1 to signal GDAL to continue processing
    return 1

if __name__ == '__main__':
    #folder_path = r"E:\ORTHO_STUFF\DEL_AREA\UN-ALIGNED\TOF2"
    #align_raster_list = get_list_of_paths_os_walk_folder(folder_path, ".tiff")
    '''
    OR
    '''
    align_raster_list = [r"R:\ORTHO_STUFF\BAN_TIMMINS\split_patched_UNaligned_chunks\TOF2_20_to_25_better.tiff"]

    output_folder = r"R:\ORTHO_STUFF\BAN_TIMMINS"

    print("starting")

    '''
    Here are rough estimates of relative execution times for different alignment sample_alg (where nearest is the baseline):
    nearest: 1x
    bilinear: ~1.5x (slightly slower than nearest)
    cubic: ~2-3x (moderate increase in computation)
    cubicSpline: ~3-5x (slower due to smoother interpolation)
    lanczos: ~4-10x (highest quality, slowest due to large kernel and complexity)
    '''

    align_rasters(align_raster_list, output_folder, target_GSD_cm=5, load_into_QGIS=False, sample_alg='bilinear', do_save_metrics_to_csv=True, beep_when_finished=True, epsg_int_override=6660)

    #build_single_internal_overview(output_file, target_resolution=2000)


