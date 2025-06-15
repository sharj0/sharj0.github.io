from osgeo import gdal, osr, ogr
import numpy as np
from PyQt5.QtWidgets import QMessageBox
import os
import shutil
import uuid

import json
from .tools import show_error

from qgis.core import (QgsVectorLayer, QgsCoordinateReferenceSystem, QgsUnitTypes,
                       QgsProject, QgsCoordinateTransform, QgsFeature,
                       QgsVectorFileWriter, QgsWkbTypes)
from PyQt5.QtWidgets import QMessageBox
import subprocess

#suppress warnings
gdal.DontUseExceptions()
os.environ['CPL_LOG'] = 'NUL'      # For Windows systems

def get_source_raster_pix_size_xy(src_ds, epsg_int):
    # Get the source geotransform
    src_gt = src_ds.GetGeoTransform()
    src_pixel_size_x = src_gt[1]  # Size of one pixel in the x-direction
    src_pixel_size_y = -src_gt[5]  # Size of one pixel in the y-direction (negative if north up)

    # Get the source CRS
    src_crs = osr.SpatialReference()
    src_crs.ImportFromWkt(src_ds.GetProjection())

    # Define the target CRS
    target_crs = osr.SpatialReference()
    target_crs.ImportFromEPSG(epsg_int)

    # Create a coordinate transformation
    coord_trans = osr.CoordinateTransformation(src_crs, target_crs)

    # Use a point in the source CRS to calculate its position in the target CRS
    # and then calculate another point that is one pixel away in x and y direction
    point_x, point_y, _ = coord_trans.TransformPoint(src_gt[0], src_gt[3])
    point_x_1, point_y_1, _ = coord_trans.TransformPoint(src_gt[0] + src_pixel_size_x, src_gt[3] - src_pixel_size_y)

    # Calculate the pixel size in the target CRS
    target_pixel_size_x = abs(point_x_1 - point_x)
    target_pixel_size_y = abs(point_y_1 - point_y)

    return target_pixel_size_x,target_pixel_size_y


def raster_convert_to_meters_crs(src_filename, converted_file_path, target_epsg_int, use_pix_size):
    # Define the gdalwarp command as a list of arguments
    cmd = [
        'gdalwarp', '-overwrite', '-t_srs', f'EPSG:{target_epsg_int}',
        '-dstnodata', '0.0', '-tr', f'{use_pix_size}', f'{use_pix_size}',
        '-r', 'bilinear',
        '-of', 'GTiff',
        src_filename,
        converted_file_path
    ]

    # Run the command
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # return if the command was successful
    return not bool(process.returncode)

def get_layer_centroid(layer):
    if not layer.isValid():
        return None
    else:
        # Get the first feature from the layer
        it = layer.getFeatures()
        feature = next(it, None)  # Get the first feature

        if feature:
            # Get the geometry of the feature
            geom = feature.geometry()

            # Check if the geometry is not null
            if geom:
                # Calculate the centroid of the geometry
                x = geom.centroid().asPoint().x()
                y = geom.centroid().asPoint().y()
                centroid = (x, y)
            else:
                return None
        else:
            return None

    return centroid

def select_utm_zone_based_off_lat_lon(latitude, longitude):
    """
    Converts geographic coordinates (latitude, longitude) to UTM zone number and letter.

    Parameters:
    - latitude (float): Latitude in decimal degrees.
    - longitude (float): Longitude in decimal degrees.

    Returns:
    - tuple: UTM zone number and letter.
    """
    if not -80.0 <= latitude <= 84.0:
        show_error("Latitude must be between -80.0 and 84.0 degrees.")

    zone_number = int((longitude + 180) / 6) + 1

    # Determine the UTM zone letter based on latitude
    letters = 'CDEFGHJKLMNPQRSTUVWXX'
    zone_letter = letters[int((latitude + 80) / 8)]
    return zone_number, zone_letter

def utm_point_to_lat_lon(easting: float, northing: float, crs: int):
    """
    Converts UTM coordinates to latitude and longitude.

    Parameters:
    - easting (float): Easting (x-coordinate) in UTM.
    - northing (float): Northing (y-coordinate) in UTM.
    - crs (str): Coordinate Reference System in the format 'epsg:XXXX'.

    Returns:
    - tuple: Latitude and longitude in decimal degrees.
    """
    # Create UTM and lat/lon coordinate systems
    utm_crs = osr.SpatialReference()
    utm_crs.ImportFromEPSG(crs)
    latlon_crs = osr.SpatialReference()
    latlon_crs.ImportFromEPSG(4326)  # EPSG code for WGS84

    # Create a transformer
    transformer = osr.CoordinateTransformation(utm_crs, latlon_crs)

    # Transform UTM coordinates to latitude and longitude
    lon, lat, _ = transformer.TransformPoint(easting, northing)

    return lon, lat


def get_source_and_target_crs_from_layer(wpt_layer):
    waypoint_source_crs: int = int(wpt_layer.crs().authid().split(':')[-1])
    centroid_xy = get_layer_centroid(wpt_layer)

    if str(waypoint_source_crs)[:-2] == '326':
        lat, lon = utm_point_to_lat_lon(centroid_xy[0], centroid_xy[1], waypoint_source_crs)
        zone_number, zone_letter = select_utm_zone_based_off_lat_lon(lat, lon)
    elif str(waypoint_source_crs)[:-2] == '43':
        print("Waypoints are in Lat-Lon and need to be converted to Meters (UTM)")
        zone_number, zone_letter = select_utm_zone_based_off_lat_lon(centroid_xy[1], centroid_xy[0])
    else:
        message = 'unrecognised coordinate reference system. Please use epsg:4326 or epsg:326XX'
        show_error(message)

    waypoint_target_crs = {
        "source_crs_epsg_int": waypoint_source_crs,
        "source_crs_wp_centroid": centroid_xy,
        "target_crs_epsg_int": int('326' + str(zone_number)),
        "target_utm_num_int": int(zone_number),  # UTM zone number
        "target_utm_letter": zone_letter  # UTM zone letter
    }
    return waypoint_target_crs

def clear_directory(directory_path):
    """
    Removes all files and folders in the specified directory.

    Parameters:
    directory_path (str): The path to the directory to clear.
    """
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

def waypoints(waypoint_path, target_epsg=32609):
    # Identify file type based on extension
    file_ext = waypoint_path.split('.')[-1].lower()

    # qgis appends crap to the end of the file name, so we need to remove it
    file_ext = file_ext.split('|')[0]

    # Create a QGIS Vector Layer from the waypoint file
    wpt_layer = QgsVectorLayer(waypoint_path, "waypoints", "ogr")
    if not wpt_layer.isValid():
        err_message = f"Failed to open the file: \n\n {waypoint_path}"
        show_error(err_message)

    # Check the CRS of the layer
    crs = wpt_layer.crs()
    current_epsg = crs.postgisSrid()

    layer_reprojected = False
    # If the layer's EPSG doesn't match target_epsg, reproject the layer
    if current_epsg != target_epsg:

        # Determine the plugin's directory
        plugin_dir = os.path.dirname(os.path.realpath(__file__))

        # Ensure a 'temp' directory exists within the plugin directory
        temp_dir = os.path.join(plugin_dir, 'temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Define the path for the reprojected layer inside the temp directory
        temp_reprojected_path = os.path.join(temp_dir, f"temp_reprojected_{uuid.uuid4()}.shp")

        target_crs = QgsCoordinateReferenceSystem(f"EPSG:{target_epsg}")

        # Set up coordinate transformation
        transform = QgsCoordinateTransform(crs, target_crs, QgsProject.instance())

        # Reproject features and save to a new file
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.ct = transform
        error = QgsVectorFileWriter.writeAsVectorFormat(wpt_layer, temp_reprojected_path, options)

        if error[0] != QgsVectorFileWriter.NoError:
            err_message = f"Error reprojecting waypoints layer: {error[1]}"
            show_error(err_message)

        # Replace the original layer with the reprojected one
        wpt_layer = QgsVectorLayer(temp_reprojected_path, "reprojected_waypoints", "ogr")
        layer_reprojected = True

    # Extract waypoints
    wpts_xy = []
    for feature in wpt_layer.getFeatures():
        geom = feature.geometry()

        if file_ext in ['kml', 'shp'] and geom.type() == QgsWkbTypes.LineGeometry:
            if geom.isMultipart():
                # Handling multi-line strings
                lines = geom.asMultiPolyline()
                for line in lines:
                    for point in line:
                        wpts_xy.append((point.x(), point.y()))
            else:
                # Handling single line strings
                line = geom.asPolyline()
                for point in line:
                    wpts_xy.append((point.x(), point.y()))

        elif file_ext == 'shp' and geom.type() == QgsWkbTypes.PointGeometry:
            point = geom.asPoint()
            wpts_xy.append((point.x(), point.y()))

    if not wpts_xy:
        err_message = f"Error reprojecting waypoints layer"
        show_error(err_message)

    # After processing the layer
    wpt_layer = None

    if layer_reprojected:
        # clean the temp directory:
        clear_directory(temp_dir)

    # Return waypoints
    return wpts_xy

def raster(rast_path, target_epsg_int):
    # Open the GeoTIFF dataset
    dataset = gdal.Open(rast_path)

    # Ensure the dataset is opened properly
    if dataset is None:
        err_message = f"Input file: \n\n {rast_path} \n\n Failed to open the GeoTIFF file!"
        show_error(err_message)

    srs = osr.SpatialReference()
    srs.ImportFromWkt(dataset.GetProjection())
    # Get the EPSG code of the dataset's projection
    srs.AutoIdentifyEPSG()
    dataset_epsg = srs.GetAuthorityCode(None)

    if dataset_epsg == '4326':
        pix_size_xy = get_source_raster_pix_size_xy(dataset, target_epsg_int)
        use_pix_size = np.floor(min(pix_size_xy)/10)*10
        converted_file_path = os.path.splitext(rast_path)[0]+'_UTM'+os.path.splitext(rast_path)[1]
        success = raster_convert_to_meters_crs(rast_path,
                                                  converted_file_path,
                                                  target_epsg_int,
                                                  use_pix_size)
        if not success:
            show_error("error converting raster to UTM")
        rast_path = converted_file_path
        dataset = gdal.Open(rast_path)
        srs = osr.SpatialReference()
        srs.ImportFromWkt(dataset.GetProjection())
    elif dataset_epsg[:-2] == '326':
        pass
    else:
        show_error(f'Unknown Coordinate reference system: EPSG:{dataset_epsg}')

    # Check if units are meters
    if srs.GetLinearUnitsName() != 'metre':
        err_message = f"The units of the GeoTIFF: \n\n {rast_path} \n\n are not in meters."
        show_error(err_message)

    # Read the raster band
    band = dataset.GetRasterBand(1)

    # Read the data into a numpy array
    array = band.ReadAsArray()

    # Read the nodata value
    nodata_value = band.GetNoDataValue()

    # Check if nodata_value is None
    if nodata_value is None:
        err_message = f"Input file: \n\n {rast_path} \n\n is missing a 'nodata' value!\nGo to the Menu Bar and select Raster > Conversion > Translate (Convert format)."
        show_error(err_message)

    epsg_code = int(srs.GetAuthorityCode(None))

    # Get the geotransform
    gt = dataset.GetGeoTransform()

    # Width and height of the raster
    width = dataset.RasterXSize
    height = dataset.RasterYSize


    # Create 1D arrays for x and y coordinates
    x_coords = np.arange(0, width) * gt[1] + gt[0]
    y_coords = np.arange(0, height) * gt[5] + gt[3]

    assert gt[5] < 0, "The y-axis of the raster is different that whats expected!"

    # setting y coords acesding bottom left of pixel
    y_coords = np.flip(y_coords)
    y_coords += gt[5] # NEED THIS OFFSET TO GET THE CORRECT COORDINATES FOR BOTTOM LEFT OF PIXEL
    array = np.flip(array, axis=0)  # flip along the y-axis

    # Convert the array to float
    array = array.astype(float)

    # Close the dataset
    dataset = None
    
    return array, x_coords, y_coords, nodata_value, epsg_code


def sample_lat_lon_tiff(tif_path: str, epsg: int, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
    # Open the geotiff
    dataset = gdal.Open(tif_path)

    # Check if dataset is loaded
    if not dataset:
        show_error("Failed to open the TIFF file.")

    # Get geotransformation and the raster band
    geotransform = dataset.GetGeoTransform()
    raster_band = dataset.GetRasterBand(1)  # assuming single band geotiff for simplicity

    # Define source and destination spatial reference systems
    src_srs = osr.SpatialReference()
    src_srs.ImportFromEPSG(epsg)

    dest_srs = osr.SpatialReference()
    dest_srs.ImportFromWkt(dataset.GetProjection())

    # Initialize coordinate transformation
    transform = osr.CoordinateTransformation(src_srs, dest_srs)

    # Sample the geotiff for each coordinate
    z_data_sampled = []
    for x, y in zip(x_coords, y_coords):

        try:
            # Transform coordinates
            y_trans, x_trans, _ = transform.TransformPoint(x, y)

            # Convert transformed coordinates to pixel/line
            col = int((x_trans - geotransform[0]) / geotransform[1])
            row = int((y_trans - geotransform[3]) / geotransform[5])

            # Ensure the coordinates are within the image bounds
            if 0 <= col < raster_band.XSize and 0 <= row < raster_band.YSize:
                z_val = raster_band.ReadAsArray(col, row, 1, 1)
                z_data_sampled.append(z_val[0, 0])
            else:
                z_data_sampled.append(np.nan)

        except Exception as e:
            z_data_sampled.append(np.nan)

    return np.array(z_data_sampled)