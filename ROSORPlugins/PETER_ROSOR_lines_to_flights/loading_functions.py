import os
from typing import List, Tuple
from qgis.core import (QgsVectorLayer,
                       QgsProject,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsFeature,
                       QgsGeometry,
                       QgsVectorFileWriter,
                       QgsPointXY,
                       QgsWkbTypes)
from osgeo import gdal, osr, ogr
from .plugin_tools import show_error
import numpy as np
import subprocess

from .new_classes.IIIIII_line import Line
from .new_classes.IIIIIII_end_point import EndPoint

from .Take_off_Class import Take_off_Class
from .Global_Singleton import Global_Singleton
from .plugin_tools import show_information



#suppress warnings
gdal.DontUseExceptions()
os.environ['CPL_LOG'] = 'NUL'      # For Windows systems




def extract_line_obj_from_line_layer(flight_lines_layer, flight_lines_path):

    grid_fltlns = []
    strip_letters = []
    ids = []
    dont_use_line_list = []
    only_use_line_list = []
    for layer_ind, feature in enumerate(flight_lines_layer.getFeatures()):

        # Get the attributes, with checks for existence
        grid_fltln = feature['Grid_Fltln'] if 'Grid_Fltln' in feature.fields().names() else None
        grid_fltlns.append(grid_fltln)

        strip = feature['STRIP'] if 'STRIP' in feature.fields().names() else None
        strip_letters.append(strip)

        dont_use_line = feature['Dont_use'] if 'Dont_use' in feature.fields().names() else None
        dont_use_line_list.append(dont_use_line)

        only_use_line = feature['Only_use'] if 'Only_use' in feature.fields().names() else None
        only_use_line_list.append(only_use_line)

        id = feature['id'] if 'id' in feature.fields().names() else None
        id = id if isinstance(id, int) else None
        ids.append(id)

    plugin_global = Global_Singleton()
    plugin_global.has_grid_fltlns = False
    plugin_global.has_strips = False

    disp = ''
    use_name = 'layer_ind'
    if all(strip_letters):
        plugin_global.has_strips = True
        disp += f'\n✅ strip detected in input line layer'
    else:
        disp += f'\n❌ strips MISSING in input line layer'
    if all(ids):
        plugin_global.has_line_ids = True
        #print(f'ids detected in input line layer')
        use_name = 'id'
    if all(grid_fltlns):
        plugin_global.has_grid_fltlns = True
        disp += f'\n✅ grid flight-line names detected in input line layer'
        use_name = 'grid_fltln'
    else:
        disp += f'\n❌ grid flight-line names MISSING in input line layer'

    plugin_global.disp = disp

    lisst = []
    for layer_ind, feature in enumerate(flight_lines_layer.getFeatures()):
        # Get the geometry of the feature
        geom = feature.geometry()
        # Extract the coordinates from the geometry
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            lines = [geom.asPolyline()]

        for line in lines:
            start = EndPoint(f'EndPoint-{layer_ind}-start', line[0][0], line[0][1])
            end = EndPoint(f'EndPoint-{layer_ind}-end', line[1][0], line[1][1])

            if use_name == 'grid_fltln':
                line_name = grid_fltlns[layer_ind]
            elif use_name == 'id':
                line_name = ids[layer_ind]
            else:
                line_name = layer_ind

            line_obj = Line(line_name,
                            start,
                            end,
                            grid_fltlns[layer_ind],
                            strip_letters[layer_ind],
                            ids[layer_ind],
                            layer_ind,
                            flight_lines_path)

            line_obj.dont_use = bool(dont_use_line_list[layer_ind])
            line_obj.only_use = bool(only_use_line_list[layer_ind])

            lisst.append(line_obj)


    unique_strip_letters = np.unique([s for s in strip_letters if s is not None])

    return lisst, unique_strip_letters


def extract_tof_obj_from_tof_layer(tof_points_layer, tof_points_path, show_feedback_popup):
    tof_names = []
    ids = []
    for layer_ind, feature in enumerate(tof_points_layer.getFeatures()):
        # First try 'NAME'
        fields = feature.fields().names()
        if 'NAME' in fields:
            tof_name = feature['NAME']
        else:
            tof_name = None

        # If still None, try 'Name'
        if tof_name is None:
            if 'Name' in fields:
                tof_name = feature['Name']

        # If still missing, popup
        if tof_name is None:
            show_feedback_popup(f"Feature at index {layer_ind} is missing a NAME/Name attribute")

        tof_names.append(tof_name)

        # ID logic unchanged
        fid = None
        if 'id' in fields:
            val = feature['id']
            if isinstance(val, int):
                fid = val
        ids.append(fid)

    plugin_global = Global_Singleton()
    plugin_global.has_tof_names = False

    disp = plugin_global.disp
    use_name = 'layer_ind'
    if all(tof_names):
        plugin_global.has_tof_names = True
        use_name = 'tof_name'
        disp += f'\n✅ take-off names detected in input take-off layer'
    else:
        disp += f'\n❌ take-off names Missing in input take-off layer'
    if all(ids):
        plugin_global.has_tof_ids = True
        #print(f'ids detected in input take-off layer')
        use_name = 'id'

    plugin_global.disp = disp
    print(disp)
    if show_feedback_popup:
        show_information(disp)

    lisst = []
    for layer_ind, feature in enumerate(tof_points_layer.getFeatures()):
        geometry = feature.geometry()
        if geometry is None or geometry.isNull():
            continue
        if geometry.type() == QgsWkbTypes.PointGeometry:
            if QgsWkbTypes.isSingleType(geometry.wkbType()):
                point = geometry.asPoint()
                tof_obj = Take_off_Class(point[0],
                                         point[1],
                                         tof_names[layer_ind],
                                         ids[layer_ind],
                                         use_name,
                                         layer_ind, tof_points_path)
                lisst.append(tof_obj)
            else:  # Multipoint
                raise ValueError("cannot do multi-points")
        else:
            raise ValueError("The layer does not contain point or multipoint geometries")
    return lisst

def load_vector_path_into_qgis(output_path):
    # Load the saved shapefile into QGIS
    name_no_ext = os.path.splitext(os.path.basename(output_path))[0]
    loaded_layer = QgsVectorLayer(output_path, name_no_ext, "ogr")
    if not loaded_layer.isValid():
        print("Failed to load the shapefile into qgis.")
    else:
        QgsProject.instance().addMapLayer(loaded_layer)
        print(f"Shapefile {output_path} successfully loaded.")


def get_layer_extent_and_centroid(layer):
    if not layer.isValid():
        return None
    else:
        # Get the extent of the layer
        extent = layer.extent()

        # Calculate the centroid of the extent
        x = (extent.xMinimum() + extent.xMaximum()) / 2
        y = (extent.yMinimum() + extent.yMaximum()) / 2
        extent_dict =  {
            "x_min": extent.xMinimum(),
            "x_max": extent.xMaximum(),
            "y_min": extent.yMinimum(),
            "y_max": extent.yMaximum()
        }
        centroid = (x, y)

    return extent_dict, centroid


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
    lat, lon, _ = transformer.TransformPoint(easting, northing)

    return lat, lon

def get_source_and_target_crs_from_layer(wpt_layer):
    waypoint_source_crs: int = int(wpt_layer.crs().authid().split(':')[-1])
    extent, centroid_xy = get_layer_extent_and_centroid(wpt_layer)

    if str(waypoint_source_crs)[:-2] == '326':
        lat, lon = utm_point_to_lat_lon(centroid_xy[0], centroid_xy[1], waypoint_source_crs)
        zone_number, zone_letter = select_utm_zone_based_off_lat_lon(lat, lon)
        target_crs_epsg_int = int(waypoint_source_crs)
    elif str(waypoint_source_crs)[:-2] == '327':
        lat, lon = utm_point_to_lat_lon(centroid_xy[0], centroid_xy[1], waypoint_source_crs)
        zone_number, zone_letter = select_utm_zone_based_off_lat_lon(lat, lon)
        target_crs_epsg_int = int(waypoint_source_crs)
    elif str(waypoint_source_crs) == '4326':
        print("Waypoints are in Lat-Lon and need to be converted to Meters (UTM)")
        zone_number, zone_letter = select_utm_zone_based_off_lat_lon(centroid_xy[1], centroid_xy[0])
        if centroid_xy[1] < 0:
            target_crs_epsg_int = int('327' + str(zone_number))
        else:
            target_crs_epsg_int = int('326' + str(zone_number))
    else:
        message = 'unrecognised coordinate reference system. Please use epsg:4326 or epsg:326XX, or epsg:327XX'
        show_error(message)

    waypoint_target_crs = {
        "source_crs_epsg_int": waypoint_source_crs,
        "source_crs_centroid_xy": centroid_xy,
        "source_crs_extent": extent,
        "target_crs_epsg_int": target_crs_epsg_int,
        "target_utm_num_int": int(zone_number),  # UTM zone number
        "target_utm_letter": zone_letter  # UTM zone letter
    }
    return waypoint_target_crs

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
    point_x, point_y, _ = coord_trans.TransformPoint(src_gt[3], src_gt[0])
    point_x_1, point_y_1, _ = coord_trans.TransformPoint(src_gt[3] - src_pixel_size_y, src_gt[0] + src_pixel_size_x)

    # Calculate the pixel size in the target CRS
    target_pixel_size_x = abs(point_x_1 - point_x)
    target_pixel_size_y = abs(point_y_1 - point_y)

    return target_pixel_size_x,target_pixel_size_y

def load_raster(rast_path: str, target_extent: dict[str, float], target_epsg: int):
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
        pix_size_xy = get_source_raster_pix_size_xy(dataset, target_epsg)
        use_pix_size = np.floor(min(pix_size_xy)/10)*10
        converted_file_path = os.path.splitext(rast_path)[0]+'_UTM'+os.path.splitext(rast_path)[1]
        success = reproject_and_crop_raster(rast_path,
                                            converted_file_path,
                                            target_epsg,
                                            use_pix_size,
                                            target_extent)
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
    y_coords += gt[5]  # NEED THIS OFFSET TO GET THE CORRECT COORDINATES FOR BOTTOM LEFT OF PIXEL
    array = np.flip(array, axis=0)  # flip along the y-axis

    # Convert the array to float
    array = array.astype(float)

    # Close the dataset
    dataset = None

    pix_size = x_coords[1] - x_coords[0]

    return array, x_coords, y_coords, nodata_value, pix_size

def reproject_and_crop_raster(src_filename, converted_file_path, target_epsg_int, use_pix_size, target_extent):
    # Define the gdalwarp command as a list of arguments
    te_values = [
        str(target_extent['x_min']),
        str(target_extent['y_min']),
        str(target_extent['x_max']),
        str(target_extent['y_max'])
    ]

    # Create the -te argument for gdalwarp
    te_argument = ['-te'] + te_values

    cmd = [
        'gdalwarp', '-overwrite', '-t_srs', f'EPSG:{target_epsg_int}',
        '-dstnodata', '0.0', '-tr', f'{use_pix_size}', f'{use_pix_size}',
        '-r', 'bilinear',
        *te_argument,
        '-of', 'GTiff',
        src_filename,
        converted_file_path
    ]

    # Run the command
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # return if the command was successful
    return not bool(process.returncode)

def reproject_vector_layer(layer: QgsVectorLayer, reprojected_path: str, target_epsg: int) -> None:
    """
    Reprojects a vector layer to a specified CRS and saves the result to a new file.

    Parameters:
        layer (QgsVectorLayer): The input vector layer to reproject.
        reprojected_path (str): The file path where the reprojected layer will be saved.
        target_epsg (int): The EPSG code of the target coordinate reference system.

    Returns:
        None
    """
    if not layer.isValid():
        print("Input layer is not valid.")
        return

    # Create a CRS object for the target CRS
    target_crs = QgsCoordinateReferenceSystem(target_epsg)

    # Set up the coordinate transformation
    transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())

    # Create a new memory layer to store the reprojected features
    reprojected_layer = QgsVectorLayer(f"LineString?crs=epsg:{target_epsg}", "reprojected_layer", "memory")
    reprojected_layer_data = reprojected_layer.dataProvider()

    # Copy attributes from the original layer to the new layer
    reprojected_layer_data.addAttributes(layer.fields())
    reprojected_layer.updateFields()

    # Iterate through original layer's features, transform, and add to new layer
    for feature in layer.getFeatures():
        new_feature = QgsFeature(feature)
        new_geometry = feature.geometry()
        new_geometry.transform(transform)
        new_feature.setGeometry(new_geometry)
        reprojected_layer_data.addFeature(new_feature)

    # Save the reprojected memory layer to the specified path
    QgsVectorFileWriter.writeAsVectorFormat(reprojected_layer, reprojected_path, "UTF-8", target_crs, "ESRI Shapefile")

    print(f"Layer reprojected and saved to {reprojected_path}")

# UN-USED
def reproject_coords(coords_xy: List[Tuple[float, float]], source_crs: int, target_crs: int) -> List[Tuple[float, float]]:
    """
    Reprojects a list of coordinate tuples from one CRS to another.

    Parameters:
        coords_xy (List[Tuple[float, float]]): List of tuples, where each tuple contains X (longitude) and Y (latitude) coordinates.
        source_crs (int): The EPSG code of the source coordinate reference system.
        target_crs (int): The EPSG code of the target coordinate reference system.

    Returns:
        List[Tuple[float, float]]: A list of tuples containing the reprojected X and Y coordinates.
    """
    # Create CRS objects for the source and target CRS
    source = QgsCoordinateReferenceSystem(source_crs)
    target = QgsCoordinateReferenceSystem(target_crs)

    # Set up the coordinate transformation
    transform = QgsCoordinateTransform(source, target, QgsProject.instance())

    # Reproject each coordinate
    coords_reprojected_xy = []
    for x, y in coords_xy:
        point = QgsPointXY(x, y)
        reprojected_point = transform.transform(point)
        coords_reprojected_xy.append((reprojected_point.x(), reprojected_point.y()))

    return coords_reprojected_xy