import os
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsFeature,
    QgsWkbTypes,
    QgsPointXY
)
import numpy as np
import pandas as pd
import shutil
import matplotlib.pyplot as plt
from qgis.PyQt.QtWidgets import QProgressDialog
from qgis.PyQt.QtCore import Qt

from .load_csv import create_subbed

def get_utm_epsg_info_from_lat_lon(latitude, longitude):
    dict = {}
    if not -80.0 <= latitude <= 84.0:
        raise ValueError("Latitude must be between -80.0 and 84.0 degrees.")

    dict["zone_number"] = int((longitude + 180) / 6) + 1

    # Determine EPSG code
    if latitude >= 0:
        dict["hemisphere"] = 'N'
        dict["epsg_code"] = 32600 + dict["zone_number"]  # Northern Hemisphere
    else:
        dict["hemisphere"] = 'S'
        dict["epsg_code"] = 32700 + dict["zone_number"]  # Southern Hemisphere

    # Determine the UTM zone letter based on latitude
    letters = 'CDEFGHJKLMNPQRSTUVWXX'
    dict["zone_letter"] = letters[int((latitude + 80) / 8)]
    return dict


def get_all_files_in_folder_recursive(folder_path, ext):
    out_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(ext):
                out_files.append(os.path.join(root, file))
    return out_files


class Kml2D_flight():
    def __init__(self, path):
        self.path = path
        self.basic_name = "_".join(os.path.basename(path).split('_')[:4])
        self.layer = self.load_kml_as_layer(path)
        self.centroidPoint, self.centroid_xy = self.get_layer_centroid(self.layer)

    def __repr__(self):
        return self.basic_name

    def load_kml_as_layer(self, path):
        layer = QgsVectorLayer(path, self.basic_name, "ogr")
        if not layer.isValid():
            print(f"Failed to load layer: {self.basic_name}")
            return None
        return layer

    def buffer_layer(self, distance):
        if not self.utm_layer:
            print("UTM layer is not available.")
            return None

        # Create a new polygon layer for the buffer
        buffer_layer = QgsVectorLayer("Polygon?crs=" + self.utm_layer.crs().authid(), self.basic_name + "_buffered", "memory")
        buffer_layer_data_provider = buffer_layer.dataProvider()

        # Add fields from the original layer
        buffer_layer_data_provider.addAttributes(self.utm_layer.fields())
        buffer_layer.updateFields()

        # Buffer and add features
        for feature in self.utm_layer.getFeatures():
            buffered_geometry = feature.geometry().buffer(distance, 5)
            buffered_feature = QgsFeature(feature)
            buffered_feature.setGeometry(buffered_geometry)
            buffer_layer_data_provider.addFeature(buffered_feature)

        return buffer_layer

    def get_layer_centroid(self, layer):
        if not layer:
            return None

        features = layer.getFeatures()
        geometries = [feature.geometry() for feature in features]
        if not geometries:
            return None

        # Combine geometries and calculate the centroid
        combined_geometry = QgsGeometry.unaryUnion(geometries)
        if not combined_geometry:
            return None

        centroid = combined_geometry.centroid()
        return centroid.asPoint(), (centroid.asPoint().x(),centroid.asPoint().y())

    def convert_layer_to_epsg(self, epsg_code):
        if not self.layer:
            print("Layer is not loaded.")
            return None

        # Define the source CRS (assuming the layer has a valid CRS)
        source_crs = self.layer.crs()

        # Define the destination CRS
        dest_crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg_code}")

        # Set up the coordinate transform
        transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())

        # Create a new layer with the same properties as the original one
        geometry_type = self.layer.geometryType()
        geometry_type_str = self.geometry_type_to_str(geometry_type)
        transformed_layer = QgsVectorLayer(geometry_type_str, self.basic_name + "_transformed", "memory")
        transformed_layer.setCrs(dest_crs)

        # Add fields from the original layer
        transformed_layer_data_provider = transformed_layer.dataProvider()
        transformed_layer_data_provider.addAttributes(self.layer.fields())
        transformed_layer.updateFields()

        # Transform and add features
        for feature in self.layer.getFeatures():
            transformed_feature = QgsFeature(feature)
            transformed_geometry = feature.geometry()
            transformed_geometry.transform(transform)  # Transform the geometry in place
            transformed_feature.setGeometry(transformed_geometry)
            transformed_layer_data_provider.addFeature(transformed_feature)

        return transformed_layer

    def geometry_type_to_str(self, geometry_type):
        if geometry_type == QgsWkbTypes.PointGeometry:
            return "Point"
        elif geometry_type == QgsWkbTypes.LineGeometry:
            return "LineString"
        elif geometry_type == QgsWkbTypes.PolygonGeometry:
            return "Polygon"
        else:
            raise ValueError("Unsupported geometry type")


class Csv_Mag_Data():
    def __init__(self, path):
        self.path = path
        self.basic_name = os.path.basename(path).split(".")[0]
        self.utme = None
        self.utmn = None
        self.read_csv_and_add_attrs()
        self.centroid_xy = self.compute_centroid()

    def __repr__(self):
        return self.basic_name

    def read_csv_and_add_attrs(self):
        df = pd.read_csv(self.path)
        if 'UTME' in df.columns and 'UTMN' in df.columns:
            self.utme = df['UTME'].to_numpy()
            self.utmn = df['UTMN'].to_numpy()
        else:
            raise ValueError("CSV file does not contain 'UTME' and 'UTMN' columns")

    def compute_centroid(self):
        centroid_utme = np.mean(self.utme)
        centroid_utmn = np.mean(self.utmn)
        return centroid_utme, centroid_utmn

    def copy_files(self):
        for src, dst in self.in_out_tups:
            # Ensure the destination directory exists
            dst_dir = os.path.dirname(dst)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)

            base, extension = os.path.splitext(dst)
            version = 2
            while os.path.exists(dst):
                dst = f"{base}_v{version}{extension}"
                version += 1

            shutil.copy(src, dst)
            print(f"Copied from {src} to {dst}")

def get_points_within_buffer(points, buffered_poly_layer):
    mask = np.zeros(len(points), dtype=bool)
    for feature in buffered_poly_layer.getFeatures():
        polygon = feature.geometry()
        for i, point in enumerate(points):
            if polygon.contains(QgsGeometry.fromPointXY(point)):
                mask[i] = True

    return mask


def get_best_kml_for_csv(csv, flights_list, match_thresh_percent):
    best_kml = None
    csv_centroid = np.array(csv.centroid_xy)

    def calculate_distance(flight):
        flight_centroid = np.array(flight.utm_centroid_xy)
        return np.linalg.norm(csv_centroid - flight_centroid)

    sorted_flights = sorted(flights_list, key=calculate_distance)
    points = [QgsPointXY(x, y) for x, y in zip(csv.utme, csv.utmn)]
    percent_of_points_inside_list = []
    for flight in sorted_flights:
        found = False
        mask = get_points_within_buffer(points, flight.bufferd_poly)
        percent_of_points_inside = np.count_nonzero(mask) / mask.shape[0] * 100
        percent_of_points_inside_list.append(percent_of_points_inside)
        if percent_of_points_inside == 100:
            best_kml = flight
            found = True
            break
    if not found:
        indx = np.argmax(percent_of_points_inside_list)
        best_percent = percent_of_points_inside_list[indx]
        if best_percent < match_thresh_percent:
            '''
            DEBUG
            '''
            debug = False
            if debug:
                print(best_percent)

                # Plot points and the buffered polygon for debugging
                fig, ax = plt.subplots()
                x_coords = [point.x() for point in points]
                y_coords = [point.y() for point in points]
                ax.scatter(x_coords, y_coords, c='blue', label='CSV Points')
                for feature in sorted_flights[indx].bufferd_poly.getFeatures():
                    polygon = feature.geometry().asPolygon()
                    if polygon:
                        polygon_coords = polygon[0]  # Get the outer ring of the polygon
                        poly_x = [point.x() for point in polygon_coords]
                        poly_y = [point.y() for point in polygon_coords]
                        ax.plot(poly_x, poly_y, c='red', label='Buffered Polygon')
                # Plot the sorted_flights[indx].utm_layer
                for feature in sorted_flights[indx].utm_layer.getFeatures():
                    geometry = feature.geometry()
                    if geometry.isMultipart():
                        linestrings = geometry.asMultiPolyline()
                    else:
                        linestrings = [geometry.asPolyline()]
                    for linestring in linestrings:
                        line_x = [point.x() for point in linestring]
                        line_y = [point.y() for point in linestring]
                        ax.plot(line_x, line_y, c='green', label='UTM Layer')
                ax.axis("equal")
                ax.set_xlabel('UTME')
                ax.set_ylabel('UTMN')
                ax.set_title(f'{csv} {sorted_flights[indx]} {best_percent}%')
                ax.legend()
                plt.show()
                '''
                DEBUG
                '''
            best_kml = None
        else:
            best_kml = sorted_flights[indx]

    return best_kml

def clean_name(name):
    # Remove specific substrings
    substrings_to_remove = ['SRVY0-', '_10Hz', 'SRVY0', '10Hz']
    for substring in substrings_to_remove:
        name = name.replace(substring, '')
    return name

def org_csvs_by_kml_flight(input_folder,
                           reorganise_by_kml_flights_path,
                           csv_load_dict,
                           buffer_kml_by=10,
                           match_thresh_percent=80,
                           ):
    csvs_paths_to_run_nosubb = get_all_files_in_folder_recursive(input_folder, ".csv")

    csv_file_ext = csv_load_dict['csv_file_ext']
    for csv_nosubb in csvs_paths_to_run_nosubb:
        create_subbed(csv_nosubb, csv_load_dict)

    csvs_paths_to_run = get_all_files_in_folder_recursive(input_folder, csv_file_ext)

    # Initialize the progress dialog
    progress = QProgressDialog("Re-naming and Re-organising...", "Cancel", 0, len(csvs_paths_to_run))
    progress.setWindowTitle("Loading")
    progress.setWindowModality(Qt.WindowModal)

    csvs_list = [Csv_Mag_Data(csv) for csv in csvs_paths_to_run]
    kmls_to_run = get_all_files_in_folder_recursive(reorganise_by_kml_flights_path, ".kml")
    flights_list = [Kml2D_flight(file) for file in kmls_to_run]
    centroid_arr = np.array([flt.centroid_xy for flt in flights_list])
    mean_centroid_xy = (np.mean(centroid_arr[:,0]),np.mean(centroid_arr[:,1]))
    utm_epsg_info = get_utm_epsg_info_from_lat_lon(mean_centroid_xy[1], mean_centroid_xy[0])
    for flight in flights_list:
        flight.utm_layer = flight.convert_layer_to_epsg(utm_epsg_info["epsg_code"])
        flight.bufferd_poly = flight.buffer_layer(buffer_kml_by)
        flight.utm_centroidPoint, flight.utm_centroid_xy = flight.get_layer_centroid(flight.utm_layer)

    new_output_dir = input_folder + '_re_organised'
    v = 2

    # Check if the directory already exists and increment the version number if it does
    while os.path.exists(new_output_dir):
        new_output_dir = f"{input_folder}_re_organised_v{v}"
        v += 1

    for csv in csvs_list:
        if progress.wasCanceled():
            break
        csv.best_kml = get_best_kml_for_csv(csv, flights_list, match_thresh_percent)
        if csv.best_kml is None:
            path_temp = os.path.join(new_output_dir, 'No_Matches',
                                        os.path.relpath(csv.path, input_folder))
            path_no_ext = os.path.splitext(path_temp)[0]
        else:
             path_temp = os.path.join(new_output_dir,
                                        os.path.relpath(csv.best_kml.path, reorganise_by_kml_flights_path))
             path_no_ext = os.path.splitext(path_temp)[0]
             _dir = os.path.dirname(path_no_ext)
             _cleaner_name = '_'.join(os.path.basename(path_no_ext).split('_')[:-1])
             path_no_ext = os.path.join(_dir, _cleaner_name)
             if csv.basic_name.startswith(_cleaner_name):
                path_no_ext = os.path.join(os.path.dirname(path_no_ext),clean_name(csv.basic_name))
             else:
                path_no_ext += '_' + clean_name(csv.basic_name)

        csv.out_path = path_no_ext + '.csv'
        csv.in_out_tups = []
        if "subed" in csv_file_ext:
            csv.subed_out_path = path_no_ext + csv_file_ext
            csv.in_out_tups.append((csv.path, csv.subed_out_path))
            csv.in_out_tups.append((os.path.splitext(csv.path)[0]+'.csv', csv.out_path))
        else:
            csv.subed_out_path = None
            csv.in_out_tups.append((csv.path, csv.out_path))
        csv.copy_files()
        progress.setValue(progress.value() + 1)
    progress.close()
    return new_output_dir, (Csv_Mag_Data, flights_list, get_best_kml_for_csv, match_thresh_percent)


