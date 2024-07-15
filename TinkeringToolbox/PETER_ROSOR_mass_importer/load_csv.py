import os

import numpy as np
import xml.etree.ElementTree as ET

# for apply_style func
from qgis.core import QgsSymbolLayer, QgsProperty
from qgis.core import QgsVectorLayer, QgsProject, QgsFeature, QgsGeometry, QgsPointXY, QgsFields, QgsField
from qgis.PyQt.QtCore import QVariant
from PyQt5.QtGui import QColor
from qgis.utils import iface

import csv
import re

"""↓↓ Sharj's Additions ↓↓"""
from .Global_Singleton import Global_Singleton #THE MOST SINGLEST POINT OF SUCCESS AND FAILURE
from . import output_lkm_distance_calculation_Sharj
"""↑↑ Sharj's Additions ↑↑"""

def clean_subbed_csvs(folder):
    pattern = re.compile(r'subed\d+csv$')
    for root, dirs, files in os.walk(folder):
        for file in files:
            if pattern.search(file):
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")


# Function to check if required columns are present in the CSV
def check_csv_columns(filename):
    required_columns = ['Flightline', 'r', 'g', 'b', 'a', 'size', 'range_noise', 'noise_bad']
    with open(filename, mode='r', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        headers = next(reader)  # This reads the first line of the CSV which should be the headers
        # Check if all required columns are present in the headers
        return all(column in headers for column in required_columns)


def update_and_apply_style(layer, min_val, max_val, attr, number_of_ranges, style_file):
    # Read the QML file
    tree = ET.parse(style_file)
    root = tree.getroot()

    # Find the renderer-v2 element and update its attribute
    renderer = root.find('.//renderer-v2[@attr]')
    if renderer is not None:
        renderer.set('attr', attr)
    else:
        raise ValueError("Could not find the renderer-v2 element in the QML file.")

    # Update the ranges
    ranges = renderer.find('ranges')
    if ranges is not None:
        # Remove existing ranges
        for range_elem in list(ranges):
            ranges.remove(range_elem)

        # Calculate new ranges and add them
        interval = (max_val - min_val) / number_of_ranges
        for i in range(number_of_ranges):
            lower = min_val + i * interval
            upper = lower + interval
            range_elem = ET.SubElement(ranges, 'range')
            range_elem.set('symbol', str(i))
            range_elem.set('render', 'true')
            range_elem.set('lower', f"{lower}")
            range_elem.set('upper', f"{upper}")
            range_elem.set('label', f"{lower} - {upper}")
    else:
        raise ValueError("Could not find the ranges element in the QML file.")

    # Write the modified QML to a temporary file
    temp_style_file = style_file.replace('.qml', f'_{layer.name()}.qml')
    tree.write(temp_style_file)

    # Apply the updated style to the layer
    layer.loadNamedStyle(temp_style_file)
    layer.triggerRepaint()

    # Delete the temporary QML file
    os.remove(temp_style_file)  # Add this line to delete the temp file after use

def is_qgis_desktop_running():
    from qgis.core import QgsApplication
    if QgsApplication.instance().platform() == 'desktop':
        return True
    else:
        return False

def apply_style(layer, point_size_multiplier):
    # print("The CSV file contains all the required columns.")
    # Set the data-defined properties for symbol layer
    # This example assumes a single-symbol point layer; adjust as necessary for your layer type and structure
    symbol = layer.renderer().symbol()
    symbol_layer = symbol.symbolLayer(0)  # Get the first (or only) symbol layer

    # Correctly set color based on attributes, scaling RGB values up to 0-255 range
    symbol_layer.setDataDefinedProperty(QgsSymbolLayer.PropertyFillColor,
                                        QgsProperty.fromExpression('color_rgb("r"*255, "g"*255, "b"*255)'))

    # Set the size of the symbols based on an attribute, adjust "size_attribute" with your actual field name
    # and adjust scaling as needed

    if point_size_multiplier == 1:
        symbol_layer.setDataDefinedProperty(QgsSymbolLayer.PropertySize,
                                            QgsProperty.fromExpression('if("size" > 10, "size" / 15, "size" / 5)'))
    else:
        multiplier = point_size_multiplier
        symbol_layer.setDataDefinedProperty(QgsSymbolLayer.PropertySize,
                                            QgsProperty.fromExpression(f'if("size" > 10, '
                                                                       f'"size" / {15 / multiplier}, '
                                                                       f'"size" / {5 / multiplier})'))

    # Remove the outline by setting its color to transparent
    symbol_layer.setStrokeColor(QColor(0, 0, 0, 0))  # RGBA where A (alpha) is 0 for transparency

    # Apply the changes to the layer
    layer.triggerRepaint()

    if is_qgis_desktop_running():
        iface.layerTreeView().refreshLayerSymbology(layer.id())


def create_subbed(csv_file, csv_load_dict):
    sub_sample_csv_displayed_points = int(csv_load_dict['sub_sample_csv_displayed_points'])
    load_existing_subed = csv_load_dict['load_existing_subed']
    #csv_load_dict['']

    base_name, ext = os.path.splitext(csv_file)
    temp_csv_file = f"{base_name}{csv_load_dict['csv_file_ext']}"

    if os.path.exists(temp_csv_file) and load_existing_subed:
        skip_creation = True
    else:
        skip_creation = False

    if not skip_creation:
        # Read and subsample the CSV data
        with open(csv_file, newline='') as f:
            reader = csv.reader(f)
            header = next(reader)  # Read the header
            rows = list(reader)  # Read all the rows into a list

        if len(rows) == 0:
            print(f"No data rows in {csv_file}")
            return False

        subsampled_rows = [rows[0]]  # Always keep the first row

        for idx, row in enumerate(rows[1:], start=1):
            if idx % sub_sample_csv_displayed_points == 0:
                subsampled_rows.append(row)

        if rows[-1] not in subsampled_rows:
            subsampled_rows.append(rows[-1])  # Always keep the last row

        # Write the subsampled data to the temporary CSV file
        with open(temp_csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(subsampled_rows)
        print(f'sub sampled: {os.path.basename(csv_file)}')

    return temp_csv_file


def load_csv_as_layer(csv_file, layer_name, group, csv_load_dict):
    if int(csv_load_dict['sub_sample_csv_displayed_points']) in [0, 1]:
        layer_file = csv_file
    else:
        layer_file = create_subbed(csv_file, csv_load_dict)

    uri = f"file:///{layer_file}?delimiter=,&xField=Longitude&yField=Latitude&crs=epsg:4326"
    layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
    if not layer.isValid():
        print(f"Failed to load {layer_name}")
        return False

    QgsProject.instance().addMapLayer(layer, False)
    group.addLayer(layer)

    if check_csv_columns(csv_file):
        point_size_multiplier = csv_load_dict['point_size_multiplier']
        apply_style(layer, point_size_multiplier)

        """↓↓ Sharj's Additions ↓↓"""
        #Creates a singleton object
        everything_everywhere_all_at_once = Global_Singleton()

        if everything_everywhere_all_at_once.output_lkm:

            #Checks singleton for attribute existing
            try:
                #Proceeds to calculate the summed lkm distance and stores it into another singleton attribute for later use
                everything_everywhere_all_at_once.total_point_lkm += output_lkm_distance_calculation_Sharj.calculation_setup(csv_file)
            except AttributeError:
                print("There seems to be an issue with the singleton attributes")
        """↑↑ Sharj's Additions ↑↑"""

    else:
        print("The CSV file is missing one or more required columns. Cannot apply color/style")
