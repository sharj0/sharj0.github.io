
import xlwt
import os

import numpy as np
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsPointXY,
    QgsVectorFileWriter)
from PyQt5.QtCore import QVariant
from osgeo import osr, ogr

def save_shapefile_lines_where_steep(coord_lat_lon_list, shapefile_path):
    # Define the type of geometry that the shapefile will contain
    layer = QgsVectorLayer('LineString?crs=epsg:4326', 'steep_lines', 'memory')

    # Start editing the layer
    layer.startEditing()

    # Define the fields for the shapefile and add them to the layer
    layer.dataProvider().addAttributes([
        QgsField('id', QVariant.Int),
        QgsField('slope', QVariant.Double)
    ])
    layer.updateFields()

    # Create features for each line and add them to the layer
    for idx, coords_lat_lon in enumerate(coord_lat_lon_list):
        # Define the line geometry
        line_geom = QgsGeometry.fromPolylineXY([
            QgsPointXY(coords_lat_lon[0][1], coords_lat_lon[0][0]),
            QgsPointXY(coords_lat_lon[1][1], coords_lat_lon[1][0])
        ])

        # Create a feature
        feature = QgsFeature()
        feature.setGeometry(line_geom)
        feature.setAttributes([idx, 0.0])  # Assuming 0.0 for slope here, replace with actual data if needed

        # Add the feature to the layer
        layer.addFeature(feature)

    # Commit changes and save the shapefile
    layer.commitChanges()
    error = QgsVectorFileWriter.writeAsVectorFormat(layer, shapefile_path, "UTF-8", layer.crs(), "ESRI Shapefile")

    if error[0] == QgsVectorFileWriter.NoError:
        print("Shapefile successfully written.")
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

def save_kml_lines_where_steep(coord_lat_lon_list, kml_file_path):
    kml_text = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <Style id="redLine">
        <LineStyle>
            <color>ff5555ff</color>
            <width>6</width>
        </LineStyle>
    </Style>'''

    for coords_lat_lon in coord_lat_lon_list:
        kml_text += f'''
    <Placemark>
        <styleUrl>#redLine</styleUrl>
        <LineString>
            <coordinates>
                {coords_lat_lon[0][1]},{coords_lat_lon[0][0]} {coords_lat_lon[1][1]},{coords_lat_lon[1][0]}
            </coordinates>
        </LineString>
    </Placemark>'''
    kml_text += f'''
</Document>
</kml>'''
    # Writing to file, 'w' mode overwrites the file if it exists
    with open(kml_file_path, 'w', encoding='utf-8') as file:
        file.write(kml_text)
    print(f'Done saving "{kml_file_path}"')


def save_excel_file(segment_len, average_slope_per_segment, total_x_distance_above_thresh_per_segment, excel_file_path):
    # Create a new Excel workbook and add a worksheet
    workbook = xlwt.Workbook()
    worksheet = workbook.add_sheet('Flight Line Slope Analysis')

    # Define cell style for numbers with two decimal places
    style = xlwt.XFStyle()
    style.num_format_str = '0.00'  # Two decimal places format

    whole_flight_columns = ['For whole Flight', 'Average Slope [%]', 'Flight Total in-Line [km]', 'Total Steep Distance [km]', 'Distance Steep %']


    # Define column titles
    line_columns = ['Per Flight line #', 'Average Slope [%]', 'Line Length [km]', 'Total Steep Distance [km]', 'Distance Steep %']

    # Write column titles to the second row to leave a space for 'For whole flight'
    for col_index, (whole_flight_column, col) in enumerate(zip(whole_flight_columns, line_columns)):
        worksheet.write(0, col_index, whole_flight_column)
        worksheet.write(3, col_index, col)
        worksheet.col(col_index).width = 256 * (len(whole_flight_column) + 3)  # Set column width

    # Write data to the worksheet starting from the third row
    for index, (length, slope, x_dist) in enumerate(
            zip(segment_len, average_slope_per_segment, total_x_distance_above_thresh_per_segment)):
        worksheet.write(index + 4, 0, index + 1, style)  # Flight line numbers start at row 3
        worksheet.write(index + 4, 1, slope, style)
        worksheet.write(index + 4, 2, length/1000, style)
        worksheet.write(index + 4, 3, x_dist/1000, style)
        worksheet.write(index + 4, 4, xlwt.Formula(f"D{index + 5}/C{index + 5}*100"), style)

    num_rows = len(segment_len) + 4
    # Add average and sum for 'For whole flight' at the first row
    worksheet.write(1, 1, xlwt.Formula(f"AVERAGE(B5:B{num_rows})"), style)
    worksheet.write(1, 2, xlwt.Formula(f"SUM(C5:C{num_rows})"), style)
    worksheet.write(1, 3, xlwt.Formula(f"SUM(D5:D{num_rows})"), style)
    worksheet.write(1, 4, xlwt.Formula(f"D2/C2*100"), style)

    # Save the workbook to a file
    try:
        workbook.save(excel_file_path)
        print(f"Excel successfully written. {excel_file_path}\n")
    except Exception as e:
        print("EXCEL FILE NOT SAVED. Error:", e)