import os
from qgis.core import (
    QgsApplication,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsVectorFileWriter,
    QgsProject
)
from PyQt5.QtCore import QVariant
import math

input_shapefile = r"I:\CONTRACT_Senoa\Ram\SHP\split_more_ext_flt_lines.shp"


output_filename = "split_extended_mag_flt_lines.shp"

flight_line_angle_cwN = 0



def get_name_of_non_existing_output_file(base_filepath, additional_suffix=''):
    # Function to create a unique file path by adding a version number
    base, ext = os.path.splitext(base_filepath)
    new_out_file_path = f"{base}{additional_suffix}{ext}"

    if not os.path.exists(new_out_file_path):
        return new_out_file_path

    version = 2
    while os.path.exists(f"{base}{additional_suffix}_v{version}{ext}"):
        version += 1
    return f"{base}{additional_suffix}_v{version}{ext}"

# Function to calculate the angle of a line
def calculate_line_angle(start_point, end_point):
    dx = end_point.x() - start_point.x()
    dy = end_point.y() - start_point.y()
    angle = math.degrees(math.atan2(dy, dx))
    if angle < 0:
        angle += 360
    return angle


def split_shp_into_flt_and_tie_lines(input_shapefile, output_filename, flight_line_angle_cwN, tolerance=5):
    output_shapefile = os.path.join(os.path.dirname(input_shapefile),output_filename)
    output_shapefile = get_name_of_non_existing_output_file(output_shapefile)

    flight_line_angle = - flight_line_angle_cwN + 90

    # Load the shapefile
    layer = QgsVectorLayer(input_shapefile, "lines", "ogr")
    if not layer.isValid():
        print("Failed to load layer!")
        exit()


    # Prepare the output layer
    crs = layer.crs()
    fields = layer.fields()
    output_layer = QgsVectorLayer(f"LineString?crs={crs.toWkt()}", "filtered_lines", "memory")
    output_layer.dataProvider().addAttributes(fields)
    output_layer.updateFields()

    # Process each feature
    for feature in layer.getFeatures():
        geom = feature.geometry()
        line_strings = []

        if geom.type() == QgsWkbTypes.LineGeometry:
            if geom.isMultipart():
                # Split MultiLineString into individual LineStrings
                line_strings = geom.asMultiPolyline()
            else:
                # Single LineString
                line_strings = [geom.asPolyline()]

            for line in line_strings:
                if len(line) != 2:
                    print("Warning: LineString does not have exactly two coordinates, skipping.")
                    continue

                start_point = line[0]
                end_point = line[1]
                angle = calculate_line_angle(start_point, end_point)

                if 180 <= angle <= 360:
                    angle -= 180

                if (flight_line_angle - tolerance <= angle <= flight_line_angle + tolerance) or (170 <= angle <= 180):
                    new_feature = QgsFeature()
                    new_feature.setGeometry(QgsGeometry.fromPolylineXY([start_point, end_point]))
                    new_feature.setAttributes(feature.attributes())
                    output_layer.dataProvider().addFeature(new_feature)

    # Save the output layer to a shapefile
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    QgsVectorFileWriter.writeAsVectorFormatV3(output_layer, output_shapefile, QgsProject.instance().transformContext(),
                                              options)

    print("Filtered shapefile saved.")

split_shp_into_flt_and_tie_lines(input_shapefile, output_filename, flight_line_angle_cwN)