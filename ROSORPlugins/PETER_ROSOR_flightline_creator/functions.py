import math
import os
import re
import xlwt
from PyQt5.QtCore import QVariant
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsField,
                       QgsGeometry, QgsLineString, QgsPoint, QgsPointXY,
                       QgsProject, QgsVectorFileWriter, QgsVectorLayer,
                       QgsWkbTypes, QgsLayerTreeGroup, QgsUnitTypes)
import numpy as np
from PyQt5.QtWidgets import QMessageBox
import shutil
import xml.etree.ElementTree as ET
from osgeo import osr

def show_error(mesage):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setText(mesage)
    msg.setWindowTitle("Error")
    msg.setStandardButtons(QMessageBox.Ok)
    retval = msg.exec_()

def show_information(message):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)  # Set icon to Information type
    msg.setText(message)
    msg.setWindowTitle("Information")
    msg.setStandardButtons(QMessageBox.Ok)
    retval = msg.exec_()

def extract_and_check_anchor_coordinates(anchor_coordinates_str, poly_layer) -> tuple[int, int]:
    # Step 1: Check for specific string values that lead to a return of None
    anchor_coordinates_str = str(anchor_coordinates_str)
    if anchor_coordinates_str in ['"0"', "'0'", "0", "0,0", '0.0']:
        return None

    # Step 2: Validate the string format
    if "," not in anchor_coordinates_str or "-" in anchor_coordinates_str:
        error_text = "Coordinates string for anchor coordinates must contain a comma and no negatives"
        show_error(error_text)
        raise ValueError(error_text)

    # Split the string and parse as floats, then convert to integers
    try:
        x_str, y_str = anchor_coordinates_str.split(",")
        x, y = int(float(x_str)), int(float(y_str))
    except ValueError as e:
        # This catches both split failure and int/float conversion failure
        error_text = "Invalid format for anchor coordinates"
        show_error(error_text)
        raise ValueError(error_text) from e

    # Step 4: Check if the coordinates are within the extent
    extent = poly_layer.sourceExtent()
    if not (extent.xMinimum() <= x <= extent.xMaximum() and extent.yMinimum() <= y <= extent.yMaximum()):
        error_text = "Coordinates are outside the polygon layer's extent"
        show_error(error_text)
        raise ValueError(error_text)

    # Step 5: Return the validated and converted coordinates
    return x, y

def get_wholest(start: float, end: float) -> float:
    # Ensure input is in integer form and within the range
    start, end = int(start), int(end)

    # Create a numpy array of all integers in the range
    numbers = np.arange(start, end + 1)

    # Find the largest power of 10 that is less than or equal to the end of the range
    max_divisor = 10 ** int(np.log10(end))

    while max_divisor >= 1:
        # Check if any number in the range is divisible by the current divisor
        divisible_numbers = numbers[numbers % max_divisor == 0]

        if divisible_numbers.size > 0:
            # If there are multiple choices, select one in the middle
            if divisible_numbers.size > 1:
                middle_index = len(divisible_numbers) // 2
                # Adjust the index slightly if there's an even number of choices to lean towards the middle
                return divisible_numbers[middle_index - (1 if len(divisible_numbers) % 2 == 0 else 0)]
            else:
                # If there's only one choice, return it
                return divisible_numbers[-1]

        # Decrease max_divisor to check the next lower power of 10
        max_divisor /= 10

    # In case there's no number found (which is unlikely with positive ranges),
    # return the start of the range or a sensible default
    return start


def get_anchor_xy(poly_layer) -> tuple[float, float]:
    extent = poly_layer.sourceExtent()

    # Use the `get_wholest` function for both dimensions
    x_anchor = get_wholest(extent.xMinimum(), extent.xMaximum())
    y_anchor = get_wholest(extent.yMinimum(), extent.yMaximum())

    return (x_anchor, y_anchor)

def get_pure_inpoly_name(path):
    # List of words to remove from the path
    words_to_remove = ["poly", "polygon", "area", "areas", "boundary", "utm", "polys", "polygons", "lidar"]
    separators = [' ', '_', '-']
    # Convert path to lowercase for case-insensitive comparison
    pure = os.path.basename(path).lower()
    # Remove file extension if exists
    if '.' in pure:
        pure = '.'.join(pure.split('.')[:-1])
    for word in words_to_remove:
        pure = pure.replace(word, "")

    # Remove leading/trailing spaces, underscores, dashes based on separators list
    for sep in separators:
        pure = pure.strip(sep)
        # Replace double occurrences of the separator
        while sep*2 in pure:
            pure = pure.replace(sep*2, sep)

    # Remove version number at the end if it exists
    pure = re.sub(r"_v\d+$", "", pure)

    return pure

def make_next_folder(directory, original_foldername):
    full_path = os.path.join(directory, original_foldername)
    version_number = ''  # Default version number is an empty string

    # Check if the original folder name doesn't exist and create it
    if not os.path.exists(full_path):
        os.makedirs(full_path)
        return full_path, version_number

    parts = original_foldername.split('_')
    if parts[-1].startswith('v') and parts[-1][1:].isdigit():
        # Increment the last part if it's a version number
        version = int(parts[-1][1:]) + 1
        version_number = f"_v{version}"
        parts[-1] = f"v{version}"
    else:
        # Append '_v2' if no version number found
        version = 2
        version_number = '_v2'
        parts.append('v2')

    # Construct the new folder name from parts
    new_foldername = '_'.join(parts)
    # Check for existence and adjust if necessary
    new_full_path = os.path.join(directory, new_foldername)
    while os.path.exists(new_full_path):
        version += 1
        version_number = f"_v{version}"
        parts[-1] = f"v{version}"
        new_foldername = '_'.join(parts)
        new_full_path = os.path.join(directory, new_foldername)

    # Create the new folder
    os.makedirs(new_full_path)
    return new_full_path, version_number

def save_excel_file(excel_path,
                    polygon_geometry,
                    output_lines,
                    crs,
                    utm_letter,
                    flight_line_spacing,
                    tie_line_spacing,
                    flight_line_angle):

    # Check if the geometry is a MultiPolygon
    if polygon_geometry.geom_type == 'MultiPolygon':
        polygons = list(polygon_geometry)
        if len(polygons) > 0:
            corners = list(polygons[0].exterior.coords)  # This is the first polygon
    elif polygon_geometry.geom_type == 'Polygon':
        corners = list(polygon_geometry.exterior.coords)  # This is the main ring of the polygon

    workbook = xlwt.Workbook()
    worksheet = workbook.add_sheet('Sheet1')

    # Write corner data
    worksheet.write(0, 0, 'Corner #')
    worksheet.write(0, 1, 'UTME')
    worksheet.write(0, 2, 'UTMN')
    for i, (x, y) in enumerate(corners, start=1):
        worksheet.write(i, 0, i)
        worksheet.write(i, 1, round(x,3))
        worksheet.write(i, 2, round(y,3))

    # Calculate the extent of the polygon
    bounds = polygon_geometry.bounds
    min_x, min_y, max_x, max_y = bounds
    worksheet.write(1, 4, 'Extent')
    worksheet.write(2, 4, 'min E')
    worksheet.write(2, 5, round(min_x,3))
    worksheet.write(3, 4, 'max E')
    worksheet.write(3, 5, round(max_x,3))
    worksheet.write(4, 4, 'min N')
    worksheet.write(4, 5, round(min_y,3))
    worksheet.write(5, 4, 'max N')
    worksheet.write(5, 5, round(max_y,3))

    # Calculate the center coordinates
    center_x = sum(x for x, y in corners) / len(corners)
    center_y = sum(y for x, y in corners) / len(corners)
    worksheet.write(1, 7, 'Centre coordinate')
    worksheet.write(2, 7, 'UTME')
    worksheet.write(2, 8, round(center_x,3))  # Rounded to the nearest meter
    worksheet.write(3, 7, 'UTMN')
    worksheet.write(3, 8, round(center_y,3))  # Rounded to the nearest meter

    # Calculate and write the area in square kilometers
    area_km2 = round(polygon_geometry.area / 1000000, 3)  # Converting and rounding to 2 decimals
    worksheet.write(5, 7, 'Area (sq km)')
    worksheet.write(5, 8, area_km2)

    # Calculate and write the sum of line lengths
    inline_kms = round(sum(line.length() / 1000 for line in output_lines), 3)  # Converting and rounding to 2 decimals
    worksheet.write(6, 7, 'In-Line km')
    worksheet.write(6, 8, inline_kms)

    # Write the UTM zone
    utm_zone = crs.split(':')[1][3:6]+" '"+utm_letter+"'"  # Assuming a standard EPSG code like "EPSG:32633"
    worksheet.write(7, 7, 'UTM Zone')
    worksheet.write(7, 8, utm_zone)

    # Write the line spacings
    worksheet.write(9, 7, "Line Spacing")
    worksheet.write(10, 7, "Traverse")
    worksheet.write(10, 8, flight_line_spacing)
    worksheet.write(11, 7, "Tie")
    worksheet.write(11, 8, tie_line_spacing)

    # Write flightline angle
    worksheet.write(13, 7, "Line Angles (degrees CW of North)")
    worksheet.write(14, 7, "Traverse")
    worksheet.write(14, 8, flight_line_angle)
    worksheet.write(15, 7, "Tie")
    worksheet.write(15, 8, flight_line_angle+90)


    try:
        workbook.save(excel_path)
        print(f"Excel successfully written. {excel_path}\n")
    except:
        print("EXCEL FILE NOT SAVED.")
        return {}

def get_name(poly_file, name):
    return os.path.join(os.path.dirname(poly_file), name)

def get_crs(poly_layer):
    return poly_layer.sourceCrs().authid().lower()

def save_polygon(shapely_polygon, output_path, crs, poly_style_source):
    # Check if the directory exists, if not, create it
    directory = os.path.dirname(output_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Create a new vector layer with polygon geometry
    init_string = f"Polygon?crs={crs}&field=id:integer"
    vl = QgsVectorLayer(init_string, "Polygon Data", "memory")

    # Start editing the layer
    vl.startEditing()

    # Add attributes to the layer
    vl.dataProvider().addAttributes([QgsField("id", QVariant.Int)])
    vl.updateFields()  # Update to apply the fields

    # Add the Shapely polygon to the layer
    feat = QgsFeature(vl.fields())
    wkt_geom = shapely_polygon.wkt
    qgs_geom = QgsGeometry.fromWkt(wkt_geom)
    feat.setGeometry(qgs_geom)
    feat.setAttributes([1])  # Assuming a single feature with ID=1
    vl.dataProvider().addFeature(feat)

    # Commit changes to make them permanent
    vl.commitChanges()

    # coppy style file so that it automatically applies to the loaded layer
    name_no_ext = os.path.splitext(os.path.basename(output_path))[0]
    qml_path = os.path.join(os.path.dirname(output_path), name_no_ext+'.qml')
    shutil.copy(poly_style_source, qml_path)

    # Save the layer to a shapefile
    error = QgsVectorFileWriter.writeAsVectorFormat(vl, output_path, "UTF-8", vl.crs(), "ESRI Shapefile")

    # Check for errors during save
    if error[0] == QgsVectorFileWriter.NoError:
        print(f"Shapefile successfully written. {output_path}")
    else:
        print("Error writing shapefile:", error)



def save_lines(flt_lines, tie_lines, output_path, crs, lines_style_source):
    # Create a new vector layer with line geometry
    init_string = f"LineString?crs={crs}&field=id:integer&field=line_type:string(10)"
    vl = QgsVectorLayer(init_string, "Line Data", "memory")

    # Start editing the layer
    vl.startEditing()

    # Add attributes to the layer
    vl.dataProvider().addAttributes([
        QgsField("id", QVariant.Int),
        QgsField("line_type", QVariant.String, len=10)
    ])
    vl.updateFields()  # Update to apply the fields

    # Add flight lines and tie lines to the layer
    id = 1
    for line in flt_lines + tie_lines:
        feat = QgsFeature(vl.fields())
        # Check if the line is already a QgsGeometry, otherwise create one from polyline
        if isinstance(line, QgsGeometry):
            geom = line
        else:
            geom = QgsGeometry.fromPolyline(line)
        feat.setGeometry(geom)
        line_type = "Flight" if line in flt_lines else "Tie"
        feat.setAttributes([id, line_type])
        vl.dataProvider().addFeature(feat)
        id += 1

    # Commit changes to make them permanent
    vl.commitChanges()

    # coppy style file so that it automatically applies to the loaded layer
    name_no_ext = os.path.splitext(os.path.basename(output_path))[0]
    qml_path = os.path.join(os.path.dirname(output_path), name_no_ext+'.qml')
    shutil.copy(lines_style_source, qml_path)

    # Save the layer to a shapefile
    error = QgsVectorFileWriter.writeAsVectorFormat(vl, output_path, "UTF-8", vl.crs(), "ESRI Shapefile")

    # Check for errors during save
    if error[0] == QgsVectorFileWriter.NoError:
        print(f"Shapefile successfully written. {output_path}")
    else:
        print("Error writing shapefile:", error)

def load_vector_layer_into_qgis(output_path):
    # Load the saved shapefile into QGIS
    name_no_ext = os.path.splitext(os.path.basename(output_path))[0]
    loaded_layer = QgsVectorLayer(output_path, name_no_ext, "ogr")
    if not loaded_layer.isValid():
        print("Failed to load the shapefile into qgis.")
    else:
        QgsProject.instance().addMapLayer(loaded_layer)
        print(f"Shapefile {output_path} successfully loaded.")


def combine_kml_files(file_paths, output_path):
    # Define namespaces to ensure they are preserved in the output
    namespaces = {
        '': "http://www.opengis.net/kml/2.2",  # Default namespace
        'gx': "http://www.google.com/kml/ext/2.2",
        'kml': "http://www.opengis.net/kml/2.2",
        'atom': "http://www.w3.org/2005/Atom"
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    # Create a new KML root element
    kml_root = ET.Element("{http://www.opengis.net/kml/2.2}kml", nsmap=namespaces)

    # Create a Document element to hold all other elements, named after the output basename
    output_basename = os.path.splitext(os.path.basename(output_path))[0]
    document = ET.SubElement(kml_root, "{http://www.opengis.net/kml/2.2}Document")
    doc_name = ET.SubElement(document, "{http://www.opengis.net/kml/2.2}name")
    doc_name.text = output_basename

    # Iterate through each file and import its contents into separate folders
    for file_path in file_paths:
        if file_path == '':
            continue
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Extract the file basename to name the folder
        file_basename = os.path.splitext(os.path.basename(file_path))[0]
        folder = ET.SubElement(document, "{http://www.opengis.net/kml/2.2}Folder")
        folder_name = ET.SubElement(folder, "{http://www.opengis.net/kml/2.2}name")
        folder_name.text = file_basename

        # Find the Document element of the current KML and move its children to the new folder
        for element in root.findall("{http://www.opengis.net/kml/2.2}Document"):
            folder.extend(element.findall("./*"))

    # Write the combined KML to a new file
    tree = ET.ElementTree(kml_root)
    tree.write(output_path, encoding="UTF-8", xml_declaration=True)


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
        raise ValueError("Latitude must be between -80.0 and 84.0 degrees.")

    zone_number = int((longitude + 180) / 6) + 1

    # Determine the UTM zone letter based on latitude
    letters = 'CDEFGHJKLMNPQRSTUVWXX'
    zone_letter = letters[int((latitude + 80) / 8)]
    return zone_number, zone_letter


def reproject_and_save_layer(original_layer, epsg_code, output_file_path):
    """
    Reprojects a vector layer to a new CRS and saves it as a Shapefile, explicitly
    removing any existing file at the output path.

    Parameters:
    - original_layer (QgsVectorLayer): The layer to be re-projected.
    - epsg_code (str): The target CRS in EPSG code format (e.g., 'EPSG:32617').
    - output_file_path (str): The file path for the output Shapefile (without the file extension).

    Returns:
    - bool: True if successful, False otherwise.
    """
    crs = QgsCoordinateReferenceSystem(epsg_code)

    # Manually remove existing output files to ensure overwrite
    for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.qpj']:
        try:
            try_path = os.path.splitext(output_file_path)[0] + ext
            os.remove(try_path)
        except FileNotFoundError:
            pass  # If the file does not exist, move on
        except PermissionError:
            message = f"File {try_path} is being used by another app. Close the app or unload that file."
            show_error(message)
            raise message
            pass  # If the file exists but you don't have permission to delete it, move on


    error, _ = QgsVectorFileWriter.writeAsVectorFormat(
        layer=original_layer,
        fileName=output_file_path,
        fileEncoding="UTF-8",
        destCRS=crs,
        driverName="ESRI Shapefile"
    )

    if error == QgsVectorFileWriter.NoError:
        print(f"Layer re-projected and saved successfully to {output_file_path}.shp")
        return True
    else:
        message = f"Failed to re-project and save layer: {error}"
        show_error(message)
        raise message
        return False

def save_input_layer_as_utm_shapefile(poly_kml_layer, poly_file, convert_to_specific_UTM_zone):
    for indx, feature in enumerate(poly_kml_layer.getFeatures()):
        if indx > 0:
            continue
        centroid = feature.geometry().centroid().asPoint()

    if centroid.y() < 0:
        message = f"This app cannot handle southern hemisphere things yet sorry." \
                  f"\n latitude: {centroid.y()} "
        show_error(message)

    if convert_to_specific_UTM_zone in [0, '0', '0.0']:
        utm_zone, utm_letter = select_utm_zone_based_off_lat_lon(centroid.y(),centroid.x())
    else:
        utm_zone = convert_to_specific_UTM_zone

    # Pad the UTM zone to two digits
    utm_zone_padded = str(utm_zone).zfill(2)

    # Create the EPSG code
    epsg_code = 'EPSG:326' + utm_zone_padded



    output_shp_path = os.path.splitext(poly_file)[0] + "_UTM.shp"
    reproject_and_save_layer(poly_kml_layer, epsg_code, output_shp_path)

    return output_shp_path, utm_letter

def open_different_kinds_of_input_polys(poly_file, convert_to_specific_UTM_zone):
    if poly_file.endswith('.kml'):
        poly_kml_layer = QgsVectorLayer(poly_file, "poly", "ogr")
        if not poly_kml_layer.isValid():
            print("Layer is not valid!")
        poly_file, utm_letter = save_input_layer_as_utm_shapefile(poly_kml_layer, poly_file, convert_to_specific_UTM_zone)
        poly_layer = QgsVectorLayer(poly_file, "poly", "ogr")
    elif poly_file.endswith('.shp'):
        poly_layer = QgsVectorLayer(poly_file, "poly", "ogr")
    else:
        message = f"Unknown file type selected: " \
                  f"\n{poly_file} " \
                  f"\nOnly '.kml' and '.shp' are accepted."
        show_error(message)
        raise message

    crs_uses_meters = poly_layer.sourceCrs().mapUnits() == QgsUnitTypes.DistanceMeters

    crs_is_utm = '+proj=utm' in poly_layer.sourceCrs().toProj4()

    useable_crs = crs_uses_meters and crs_is_utm

    # Check if the CRS units are in meters
    if not useable_crs:
        try:
            if get_crs(poly_layer) in ['epsg:4326']:
                poly_file, utm_letter = save_input_layer_as_utm_shapefile(poly_layer, poly_file, convert_to_specific_UTM_zone)
                poly_layer = QgsVectorLayer(poly_file, "poly", "ogr")
            else:
                if convert_to_specific_UTM_zone in [0, '0', '0.0']:
                    error_text = "Input layer coordinates not recognised, try specifying a UTM zone to convert it to"
                    show_error(error_text)
                    raise error_text
                else:
                    output_shp_path = os.path.splitext(poly_file)[0] + "_UTM.shp"
                    reproject_and_save_layer(poly_layer, convert_to_specific_UTM_zone, output_shp_path)
                    poly_layer = QgsVectorLayer(output_shp_path, "poly", "ogr")
                    poly_file = output_shp_path
        except:
            error_text = "Cannot auto convert crs"
            show_error(error_text)
            raise error_text
    else:
        for indx, feature in enumerate(poly_layer.getFeatures()):
            if indx > 0:
                continue
            centroid = feature.geometry().centroid().asPoint()

        lat, lon = utm_to_lat_lon(centroid[0], centroid[1], get_crs(poly_layer))
        utm_zone, utm_letter = select_utm_zone_based_off_lat_lon(lat, lon)
    return poly_file, poly_layer, utm_letter

def utm_to_lat_lon(easting, northing, crs):
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
    utm_crs.ImportFromEPSG(int(crs.split(':')[1]))
    latlon_crs = osr.SpatialReference()
    latlon_crs.ImportFromEPSG(4326)  # EPSG code for WGS84

    # Create a transformer
    transformer = osr.CoordinateTransformation(utm_crs, latlon_crs)

    # Transform UTM coordinates to latitude and longitude
    lon, lat, _ = transformer.TransformPoint(easting, northing)

    return lon, lat
