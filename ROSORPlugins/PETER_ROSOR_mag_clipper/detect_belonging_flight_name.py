
'''IMPORTS NEED CLEANING'''

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
from .plugin_tools import show_message
'''IMPORTS NEED CLEANING'''

class Kml2D_flight():
    def __init__(self, path, buffer_kml_by):
        self.path = path
        self.buffer = buffer_kml_by
        self.basic_name = "_".join(os.path.basename(path).split('_')[:4])
        self.layer = self.load_kml_as_layer(path)
        self.centroidPoint, self.centroid_xy = self.get_layer_centroid(self.layer)
        self.line_x = []
        self.line_y = []

    def __repr__(self):
        return self.basic_name

    def load_kml_as_layer(self, path):
        layer = QgsVectorLayer(path, self.basic_name, "ogr")
        if not layer.isValid():
            print(f"Failed to load layer: {self.basic_name}")
            return None
        return layer

    def buffer_layer(self):
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
            buffered_geometry = feature.geometry().buffer(self.buffer, 5)
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

        for feature in transformed_layer.getFeatures():
            geometry = feature.geometry()
            if geometry.isMultipart():
                linestrings = geometry.asMultiPolyline()
            else:
                linestrings = [geometry.asPolyline()]
            for linestring in linestrings:
                self.line_x.extend([point.x() for point in linestring])
                self.line_y.extend([point.y() for point in linestring])

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

def get_all_files_in_folder_recursive(folder_path, ext):
    out_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(ext):
                out_files.append(os.path.join(root, file))
    return out_files

def get_points_within_buffer(points, buffered_poly_layer):
    mask = np.zeros(len(points), dtype=bool)
    for feature in buffered_poly_layer.getFeatures():
        polygon = feature.geometry()
        for i, point in enumerate(points):
            if polygon.contains(QgsGeometry.fromPointXY(point)):
                mask[i] = True

    return mask

def get_best_kml_for_mag_data(mag_data, flights_list, match_thresh_percent):
    best_kml = None
    mag_data_centroid = np.array(mag_data.centroid_xy)

    def calculate_distance(flight):
        flight_centroid = np.array(flight.utm_centroid_xy)
        return np.linalg.norm(mag_data_centroid - flight_centroid)

    if len(flights_list) == 0:
        show_message("cannot use the provided 2D flights to name things")
        return
    sorted_flights = sorted(flights_list, key=calculate_distance)
    points = [QgsPointXY(x, y) for x, y in zip(mag_data.utme, mag_data.utmn)]
    percent_of_points_inside_list = []
    for flight in sorted_flights:
        found = False
        mask = get_points_within_buffer(points, flight.buffer_layer())
        percent_of_points_inside = np.count_nonzero(mask) / mask.shape[0] * 100
        percent_of_points_inside_list.append(percent_of_points_inside)
        if percent_of_points_inside == 100:
            best_kml = flight
            best_percent = 100
            found = True
            break
    if not found:
        indx = np.argmax(percent_of_points_inside_list)
        best_percent = percent_of_points_inside_list[indx]
        if best_percent < match_thresh_percent:
            best_kml = None
        else:
            best_kml = sorted_flights[indx]

    return best_kml

class Mag_Data():
    def __init__(self, df):
        self.utme = df['UTME'].to_numpy()
        self.utmn = df['UTMN'].to_numpy()
        self.centroid_xy = np.mean(df['UTME']), np.mean(df['UTMN'])

def clean_name(name):
    # Remove specific substrings
    substrings_to_remove = ['SRVY0-', '_10Hz', 'SRVY0', '10Hz']
    for substring in substrings_to_remove:
        name = name.replace(substring, '')
    return name

def sub_samp_this_df(df, sub_samp_df=30):
    subsampled_df = df.iloc[::sub_samp_df, :]
    # Include the last row
    if len(df) % sub_samp_df != 0:
        last_row = df.iloc[[-1]]
        subsampled_df = pd.concat([subsampled_df, last_row])
    return subsampled_df

def detect_belonging_flight_name(df,
                                 path_to_2d_flights,
                                 epsg_target,
                                 og_export_file_path,
                                 buffer_kml_by=20,
                                 match_thresh_percent=70):
    kmls_to_run = get_all_files_in_folder_recursive(path_to_2d_flights, ".kml")
    flights_list = [Kml2D_flight(file, buffer_kml_by) for file in kmls_to_run]
    for flight in flights_list:
        flight.utm_layer = flight.convert_layer_to_epsg(epsg_target)
        flight.utm_centroidPoint, flight.utm_centroid_xy = flight.get_layer_centroid(flight.utm_layer)

    subsampled_df = sub_samp_this_df(df)
    mag_data = Mag_Data(subsampled_df)
    mag_data.best_kml = get_best_kml_for_mag_data(mag_data, flights_list, match_thresh_percent)


    if mag_data.best_kml:
        clean_basename = clean_name(os.path.splitext(os.path.basename(og_export_file_path))[0])
        new_basename = mag_data.best_kml.basic_name + '_' + clean_basename + '.csv'
        new_export_file_path = os.path.join(os.path.dirname(og_export_file_path),new_basename)
        flt_coords = mag_data.best_kml.line_x, mag_data.best_kml.line_y
        run_flightline_splitter = None
    else:
        new_export_file_path = og_export_file_path
        flt_coords = None
        run_flightline_splitter = (get_best_kml_for_mag_data, sub_samp_this_df,
                                   Mag_Data, flights_list, match_thresh_percent)

    return new_export_file_path, flt_coords, run_flightline_splitter