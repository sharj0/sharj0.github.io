from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsVectorLayer, QgsProject, QgsWkbTypes
import tempfile
import numpy as np
import os
import csv
import subprocess
from collections import defaultdict
import matplotlib.pyplot as plt


def run_lkm_calculations(layer_dict, names):
    # Ensure that there is at least one valid layer in the dictionary
    first_layer = next(iter(layer_dict.values()), None)

    if first_layer and first_layer.isValid():
        lines_source_and_target_crs = get_source_and_target_crs_from_layer(first_layer)
    else:
        show_error('selected layer not valid')
        return  # Exit the function if no valid layer is found

    utm_coords_list = []

    # Iterate over the layers in the dictionary
    for layer in layer_dict.values():
        if layer.isValid():
            utm_coords = reproject_vector_layer_coords(layer,
                                                       target_epsg=lines_source_and_target_crs['target_crs_epsg_int'])
            utm_coords_list.append(utm_coords)
        else:
            print(f"Layer associated with {layer} is not valid and will be skipped.")
            utm_coords_list.append(None)

    flight_distances = []

    for line in utm_coords_list:
        line_distance = 0
        for coords in line:
            if len(coords) < 2:
                continue  # Skip if there are not enough points to calculate a distance

            # Convert QgsPointXY objects to NumPy arrays
            points_array = np.array([(point.x(), point.y()) for point in coords])

            # Calculate differences between consecutive points
            diffs = np.diff(points_array, axis=0)

            # Calculate the Euclidean distance for each pair of points
            segment_distances = np.sqrt(np.sum(diffs ** 2, axis=1))

            # Sum the distances to get the total length of the line
            line_distance += np.sum(segment_distances)

        flight_distances.append(line_distance)

    assert len(names) == len(flight_distances), 'Some input files are empty'

    return utm_coords_list, flight_distances, lines_source_and_target_crs   # Return the list of reprojected coordinates

def find_common_path(paths):
    common_path = os.path.commonpath(paths)
    return common_path

def calculate_folder_distances(names, distances, production_dists, common_path):
    folder_tree = {"children": defaultdict(dict), "distance": 0.0, "production_distance": 0.0}
    common_path_parts = common_path.split(os.sep)

    for name, distance, prod_distance in zip(names, distances, production_dists):
        parts = name.split(os.sep)[len(common_path_parts):]  # Skip common path parts
        current_level = folder_tree
        current_level["distance"] += distance
        current_level["production_distance"] += prod_distance
        for part in parts[:-1]:
            if part not in current_level["children"]:
                current_level["children"][part] = {"children": defaultdict(dict), "distance": 0.0, "production_distance": 0.0}
            current_level = current_level["children"][part]
            current_level["distance"] += distance
            current_level["production_distance"] += prod_distance
        current_level["children"][parts[-1]] = {"distance": distance, "production_distance": prod_distance}

    return folder_tree


def write_tree_to_csv(folder_tree, common_path):
    #output_csv_path =  r"C:\Users\pyoty\Desktop\del me\temp_test.csv"
    #with open(output_csv_path, mode='w', newline='') as temp_file:
    #    writer = csv.writer(temp_file)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='w', newline='') as temp_file:
        writer = csv.writer(temp_file)

        # Calculate the maximum depth to set the appropriate number of columns
        max_depth = calculate_max_depth(folder_tree) + 1

        # Create dynamic headers based on the maximum depth, with "Depth" in header names
        headers = []
        for i in range(max_depth + 1):
            headers.extend(
                [f'Loaded Folder Depth {i + 1}', f'Flown LKM Distance {i + 1}', f'Production LKM Distance {i + 1}'])
        writer.writerow(headers)

        def write_level(level, depth=1):  # Start at depth 1 to properly align under the common path
            for name, data in level["children"].items():
                # Dynamically extend row size to accommodate the depth
                row = [''] * ((depth + 1) * 3)
                row[depth * 3] = name
                row[depth * 3 + 1] = f'{data["distance"]:.3f}' if isinstance(data["distance"], float) else ''
                row[depth * 3 + 2] = f'{data["production_distance"]:.3f}' if isinstance(data["production_distance"],
                                                                                        float) else ''
                writer.writerow(row)
                if "children" in data:
                    write_level(data, depth + 1)

        # Write the common path as the first row at depth 0
        writer.writerow([common_path, f'{folder_tree["distance"]:.3f}', f'{folder_tree["production_distance"]:.3f}'])
        # Write the tree starting from depth 1
        write_level(folder_tree, depth=1)

    # Launch the CSV with the default application
    csv_file = temp_file.name
    print('start:', csv_file)
    os.startfile(csv_file)
    #try:
    #    # Escape the file path with quotes
    #    quoted_csv_file = f'"{csv_file}"'
#
    #    # Define the path to PowerShell executable
    #    powershell_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"  # Adjust this path if needed
#
    #    # Define the PowerShell command
    #    powershell_command = f"Import-Csv {quoted_csv_file} | Out-GridView"
#
    #    # Run the PowerShell command using subprocess
    #    subprocess.run([powershell_path, "-NoExit", "-Command", powershell_command], shell=True)
    #except:
    #    os.startfile(csv_file)


def calculate_max_depth(level, current_depth=0):
    max_depth = current_depth
    for _, data in level["children"].items():
        if "children" in data:
            child_depth = calculate_max_depth(data, current_depth + 1)
            if child_depth > max_depth:
                max_depth = child_depth
    return max_depth

def create_flight_dist_csv(names, flight_distances, production_dists):
    common_path = find_common_path(names)
    folder_tree = calculate_folder_distances(names, flight_distances, production_dists, common_path)
    write_tree_to_csv(folder_tree, common_path)

def get_line_coords(path: str, target_epsg: int)-> list:
    layer = QgsVectorLayer(path, 'Lines', "ogr")
    if layer.isValid():
        utm_coords = reproject_vector_layer_coords(layer, target_epsg=target_epsg)
    else:
        print(f"Lines Layer is not valid.")

    return utm_coords

def get_what_line_belongs_to_what_flight_dists(flight_paths, flight_coords, line_coords_qgis):
    line_coords = np.array(line_coords_qgis)
    # extra dimension for some reason
    line_coords = line_coords[:, 0, :]

    # Calculate the difference between the start and end points
    diffs = line_coords[:, 1, :] - line_coords[:, 0, :]

    # Calculate the Euclidean distance (length) for each segment
    line_lengths = np.sqrt(np.sum(diffs ** 2, axis=1))

    flight_prod_dists = []
    for path, flt_coord in zip(flight_paths, flight_coords):
        flight_prod_dist = 0

        # Step 1: Flatten the array to make it a 1D array of QgsPointXY objects
        start_coords = np.array(flt_coord[0][:-1])
        end_coords = np.array(flt_coord[0][1:])

        flt_segment_lines = np.stack((start_coords, end_coords), axis=1)

        flt_seg_middle_coords = np.mean(flt_segment_lines, axis=1)

        flt_seg_middle_coord = np.mean(flt_seg_middle_coords, axis=0)

        # Calculate the difference between the start and end points
        diffs = flt_segment_lines[:, 1, :] - flt_segment_lines[:, 0, :]

        # Calculate the Euclidean distance (length) for each segment
        flt_seg_lengths = np.sqrt(np.sum(diffs ** 2, axis=1))

        flt_seg_length_order = np.argsort(flt_seg_lengths)[::-1]

        lines_middle_coord = np.mean(line_coords, axis=1)

        # Calculate the Euclidean distance between each point in lines_middle_coord and flt_seg_middle_coord
        distances = np.sqrt(np.sum((lines_middle_coord - flt_seg_middle_coord) ** 2, axis=1))

        lines_closest_order = np.argsort(distances)

        # Loop through each line segment starting from the longest
        for seg_index in flt_seg_length_order:
            longest_flt_seg = flt_segment_lines[seg_index]

            for line_index in lines_closest_order:
                closest_line_coord = line_coords[line_index]

                # check to make sure that longest_flt_seg is longer than closest_line_coord length to avoid doing extra math
                if not flt_seg_lengths[seg_index] > line_lengths[line_index]:
                    continue

                direction_vector = longest_flt_seg[1] - longest_flt_seg[0]
                direction_unit_vector = direction_vector / np.linalg.norm(direction_vector)

                perpendicular_vector = np.array([-direction_unit_vector[1], direction_unit_vector[0]])
                buffer_distance = 2.0

                corner1 = longest_flt_seg[0] + buffer_distance * perpendicular_vector
                corner2 = longest_flt_seg[0] - buffer_distance * perpendicular_vector
                corner3 = longest_flt_seg[1] + buffer_distance * perpendicular_vector
                corner4 = longest_flt_seg[1] - buffer_distance * perpendicular_vector

                rectangle_corners = np.array([corner1, corner3, corner4, corner2, corner1])

                def point_in_rectangle(point, rect):
                    def sign(p1, p2, p3):
                        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

                    b1 = sign(point, rect[0], rect[1]) <= 0.0
                    b2 = sign(point, rect[1], rect[2]) <= 0.0
                    b3 = sign(point, rect[2], rect[3]) <= 0.0
                    b4 = sign(point, rect[3], rect[0]) <= 0.0

                    return (b1 == b2) and (b2 == b3) and (b3 == b4)

                inside1 = point_in_rectangle(closest_line_coord[0], rectangle_corners)
                inside2 = point_in_rectangle(closest_line_coord[1], rectangle_corners)

                #print(f"line_index: {line_index}, seg_index: {seg_index}, inside1: {inside1}, inside2: {inside2}")

                plot = False
                if inside1 and inside2 and plot:
                    plt.figure(figsize=(8, 8))
                    plt.plot(rectangle_corners[:, 0], rectangle_corners[:, 1], 'b-', label="Buffered Rectangle")
                    plt.scatter(closest_line_coord[:, 0], closest_line_coord[:, 1], c='r', label="Closest Line Points")
                    plt.plot(longest_flt_seg[:, 0], longest_flt_seg[:, 1], 'g-', label="Longest Line")

                    for i, (x, y) in enumerate(closest_line_coord):
                        plt.text(x, y, f"Point {i + 1}", fontsize=12, ha='right')

                    text = f"Comparing segment {seg_index} (longest) with line {line_index} (closest)."
                    plt.title(text)
                    plt.xlabel("X Coordinate")
                    plt.ylabel("Y Coordinate")
                    plt.legend()
                    plt.grid(True)
                    plt.show()

                if inside1 and inside2:
                    ...
                    flight_prod_dist += line_lengths[line_index]
                    # accosiate flight_prod_dist with path

        flight_prod_dists.append(flight_prod_dist)
    return flight_prod_dists



def reproject_vector_layer_coords(layer: QgsVectorLayer, target_epsg: int) -> list:
    """
    Reprojects the coordinates of a vector layer to a specified CRS and returns them as a list.

    Parameters:
        layer (QgsVectorLayer): The input vector layer to reproject.
        target_epsg (int): The EPSG code of the target coordinate reference system.

    Returns:
        list: A list of reprojected coordinates.
    """
    if not layer.isValid():
        print("Input layer is not valid.")
        return []

    # Create a CRS object for the target CRS
    target_crs = QgsCoordinateReferenceSystem.fromEpsgId(target_epsg)

    # Set up the coordinate transformation
    transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())

    # List to store the reprojected coordinates
    reprojected_coords = []

    # Iterate through original layer's features, transform, and collect coordinates
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if geometry:
            geometry.transform(transform)
            if geometry.isMultipart():
                coords = geometry.asMultiPolyline()  # For multipart geometries
            else:
                coords = geometry.asPolyline()  # For singlepart geometries
            reprojected_coords.append(coords)

    return reprojected_coords


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
            target_crs_epsg_int = int('327' + str(zone_number).zfill(2))
        else:
            target_crs_epsg_int = int('326' + str(zone_number).zfill(2))
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