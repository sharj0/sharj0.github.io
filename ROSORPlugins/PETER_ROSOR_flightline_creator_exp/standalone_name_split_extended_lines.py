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
import matplotlib.pyplot as plt

input_shapefile = r"I:\CONTRACT_Senoa\Ram\SHP\tof5_mag_tie_split_more_ext.shp"
spacing = 245
number_pre_fix = 'T'
output_shp = True
do_plot = True
strip_name_direction_reverse = True
line_name_direction_reverse = True


def get_name_of_non_existing_output_file(base_filepath, additional_suffix=''):
    # Function to create a unique file path by adding a version number
    base, ext = os.path.splitext(base_filepath)
    version = 1
    new_out_file_path = f"{base}{additional_suffix}_v{version}{ext}"

    while os.path.exists(new_out_file_path):
        version += 1
        new_out_file_path = f"{base}{additional_suffix}_v{version}{ext}"
    return new_out_file_path


# Function to calculate the angle of a line
def calculate_line_angle(start_point, end_point):
    dx = end_point.x() - start_point.x()
    dy = end_point.y() - start_point.y()
    angle = math.degrees(math.atan2(dy, dx))
    if angle < 0:
        angle += 360
    return angle


# Function to rotate a point around the origin by a given angle in degrees
def rotate_point(point, angle):
    rad_angle = math.radians(angle)
    cos_angle = math.cos(rad_angle)
    sin_angle = math.sin(rad_angle)
    x_new = point.x() * cos_angle - point.y() * sin_angle
    y_new = point.x() * sin_angle + point.y() * cos_angle
    return QgsPointXY(x_new, y_new)


# Function to rotate a line back to its original angle
def rotate_line_back(line, angle):
    return [rotate_point(point, -angle) for point in line]


def name_split_extended_lines(input_shapefile, spacing, output_shp, do_plot, number_pre_fix='F',
                              strip_name_direction_reverse=False, line_name_direction_reverse=False):
    # Load the shapefile
    layer = QgsVectorLayer(input_shapefile, "lines", "ogr")
    if not layer.isValid():
        print("Failed to load layer!")
        exit()

    # Get the angle of the first line
    first_feature = next(layer.getFeatures())
    first_geom = first_feature.geometry()

    if first_geom.isMultipart():
        first_geom = first_geom.asMultiPolyline()[0]
    else:
        first_geom = first_geom.asPolyline()

    first_angle = calculate_line_angle(first_geom[0], first_geom[1])

    # Calculate rotation angle to make lines horizontal
    rotation_angle = -first_angle if first_angle < 180 else -(first_angle - 180)

    # Rotate all lines to become horizontal
    rotated_lines = []
    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom.type() == QgsWkbTypes.LineGeometry:
            if geom.isMultipart():
                line_strings = geom.asMultiPolyline()
            else:
                line_strings = [geom.asPolyline()]

            for line in line_strings:
                rotated_line = [rotate_point(point, rotation_angle) for point in line]
                rotated_lines.append((feature.id(), rotated_line))

    # Calculate strips
    all_y_coords = [point.y() for _, line in rotated_lines for point in line]
    min_y = min(all_y_coords)
    max_y = max(all_y_coords)
    num_strips = int((max_y - min_y) // spacing) + 1

    strip_borders = [min_y - spacing / 2 + i * spacing for i in range(num_strips + 1)]

    # Assign strips and sort within each strip
    strips = {i: [] for i in range(num_strips)}
    for feature_id, line in rotated_lines:
        y_coords = [point.y() for point in line]
        mean_y = sum(y_coords) / len(y_coords)
        for i in range(num_strips):
            if strip_borders[i] <= mean_y < strip_borders[i + 1]:
                strips[i].append((feature_id, line))
                break

    # Reverse strip order if flag is set
    strip_keys = sorted(strips.keys())

    # Sort lines within each strip and assign numbers for plotting
    line_numbers = {}
    for i, strip_index in enumerate(strip_keys):
        strip_lines = strips[strip_index]
        # Sort by the minimum x-coordinate
        strip_lines.sort(key=lambda item: min(point.x() for point in item[1]))
        # Reverse the list of lines if flag is set
        if line_name_direction_reverse:
            strip_lines.reverse()
        if len(strip_lines) > 99:
            raise ValueError("More than 99 lines in a strip")

        # Adjust strip number based on the direction
        strip_number = f"{len(strip_keys) - i:03d}" if strip_name_direction_reverse else f"{i + 1:03d}"

        for line_index, (feature_id, line) in enumerate(strip_lines):
            line_number = f"{line_index + 1:02d}"
            combined_number = number_pre_fix + strip_number + line_number
            line_numbers[feature_id] = combined_number

    # Output the line numbers
    for feature_id, combined_number in line_numbers.items():
        print(f"Line ID {feature_id} assigned number: {combined_number}")

    if do_plot:
        # Plotting
        fig, ax = plt.subplots()
        for i in range(num_strips):
            y0 = strip_borders[i]
            y1 = strip_borders[i + 1]
            ax.plot([min(point.x() for _, line in rotated_lines for point in line),
                     max(point.x() for _, line in rotated_lines for point in line)], [y0, y0], 'r--')
            ax.plot([min(point.x() for _, line in rotated_lines for point in line),
                     max(point.x() for _, line in rotated_lines for point in line)], [y1, y1], 'r--')

        for feature_id, line in rotated_lines:
            x_coords = [point.x() for point in line]
            y_coords = [point.y() for point in line]
            ax.plot(x_coords, y_coords, 'b-')
            # Display the assigned number in the plot
            if feature_id in line_numbers:
                mid_point = line[len(line) // 2]  # Get the middle point of the line
                ax.text(mid_point.x(), mid_point.y(), line_numbers[feature_id], fontsize=8, ha='center')
            else:
                print(f"Warning: Feature ID {feature_id} not found in line_numbers.")

        plt.xlabel('X')
        plt.ylabel('Y')
        plt.title('Rotated Lines and Strips with Assigned Numbers')
        plt.show()

    # Prepare the output layer for saving
    if output_shp:
        output_shapefile = get_name_of_non_existing_output_file(input_shapefile, '_named_lines')
        crs = layer.crs()
        fields = layer.fields()
        fields.append(QgsField("Grid_Fltln", QVariant.String))  # Add the new field
        output_layer = QgsVectorLayer(f"LineString?crs={crs.toWkt()}", "named_lines", "memory")
        output_layer.dataProvider().addAttributes(fields)
        output_layer.updateFields()

        # Add features to the output layer
        for i, strip_index in enumerate(strip_keys):
            strip_lines = strips[strip_index]
            # Sort by the same minimum x-coordinate for saving
            strip_lines.sort(key=lambda item: min(point.x() for point in item[1]))
            # Reverse the list of lines if flag is set
            if line_name_direction_reverse:
                strip_lines.reverse()

            # Adjust strip number based on the direction
            strip_number = f"{len(strip_keys) - i:03d}" if strip_name_direction_reverse else f"{i + 1:03d}"

            for line_index, (feature_id, line) in enumerate(strip_lines):
                original_line = rotate_line_back(line, rotation_angle)
                strip_geom = QgsGeometry.fromPolylineXY(original_line)
                new_feature = QgsFeature()
                new_feature.setGeometry(strip_geom)
                new_feature.setAttributes([None] * len(fields))  # Add empty attributes
                combined_number = number_pre_fix + strip_number + f"{line_index + 1:02d}"
                new_feature.setAttribute(fields.indexOf("Grid_Fltln"), combined_number)
                output_layer.dataProvider().addFeature(new_feature)

        # Save the output layer to a shapefile
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        QgsVectorFileWriter.writeAsVectorFormatV3(output_layer, output_shapefile,
                                                  QgsProject.instance().transformContext(), options)

        print("Filtered shapefile saved.")


name_split_extended_lines(input_shapefile, spacing, output_shp, do_plot, number_pre_fix,
                          strip_name_direction_reverse, line_name_direction_reverse)