from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorLayer, QgsCoordinateReferenceSystem, QgsProject,
    QgsCoordinateTransformContext, QgsCoordinateTransform, QgsVectorFileWriter,
    QgsSingleSymbolRenderer, QgsFillSymbol
)
import numpy as np
import math
import os
import shutil


# Function to calculate the angle between two points
def calculate_angle(start_point, end_point):
   dx = end_point.x() - start_point.x()
   dy = end_point.y() - start_point.y()
   return math.degrees(math.atan2(dy, dx))

# Function to transform geometry to the target CRS
def transform_geometry(geometry, source_crs, target_crs):
    transform = QgsCoordinateTransform(source_crs, target_crs, QgsCoordinateTransformContext())
    new_geom = QgsGeometry(geometry)
    new_geom.transform(transform)
    return new_geom

# Function to calculate rectangle coordinates
def calculate_rectangle_coords(start_point, end_point, width):
    angle = calculate_angle(start_point, end_point)
    dx = width / 2 * np.cos(np.radians(angle + 90))
    dy = width / 2 * np.sin(np.radians(angle + 90))
    coords = [
        QgsPointXY(start_point.x() + dx, start_point.y() + dy),
        QgsPointXY(start_point.x() - dx, start_point.y() - dy),
        QgsPointXY(end_point.x() - dx, end_point.y() - dy),
        QgsPointXY(end_point.x() + dx, end_point.y() + dy),
        QgsPointXY(start_point.x() + dx, start_point.y() + dy)  # Close the polygon
    ]
    return coords

def make_swaths(input_file, output_file, swath_width, crs, swath_style_source):
    # Load the layer
    layer_path = input_file
    line_layer = QgsVectorLayer(layer_path, "lines", "ogr")
    if not line_layer.isValid():
        raise Exception("Layer failed to load!")

    target_crs = QgsCoordinateReferenceSystem(crs)

    # Create a new memory layer for rectangles
    rect_layer = QgsVectorLayer("Polygon?crs="+crs, "Swath Rectangles", "memory")
    rect_layer_provider = rect_layer.dataProvider()

    # Iterate over each line in the layer and create rectangles
    for feature in line_layer.getFeatures():
        geom = feature.geometry()
        # Assuming transform_geometry is a function you have defined elsewhere
        transformed_geom = transform_geometry(geom, line_layer.crs(), target_crs)
        if transformed_geom.isMultipart():
            lines = transformed_geom.asMultiPolyline()
        else:
            lines = [transformed_geom.asPolyline()]

        for line in lines:
            if len(line) >= 2:  # Check if the line has at least two points
                start_point = QgsPointXY(line[0])
                end_point = QgsPointXY(line[-1])
                # Assuming calculate_rectangle_coords is a function you have defined
                rectangle_coords = calculate_rectangle_coords(start_point, end_point, swath_width)
                rect_feat = QgsFeature()
                rect_feat.setGeometry(QgsGeometry.fromPolygonXY([rectangle_coords]))
                rect_layer_provider.addFeature(rect_feat)

    # coppy style file so that it automatically applies to the loaded layer
    name_no_ext = os.path.splitext(os.path.basename(output_file))[0]
    qml_path = os.path.join(os.path.dirname(output_file),name_no_ext+'.qml')
    shutil.copy(swath_style_source, qml_path)

    # Save the rectangles layer to a Shapefile
    error = QgsVectorFileWriter.writeAsVectorFormat(rect_layer, output_file, "UTF-8", target_crs, "ESRI Shapefile")

    if error[0] == QgsVectorFileWriter.NoError:
        print(f"Success! Shapefile written at: {output_file}")
    else:
        print(f"Error writing Shapefile: {error}")



if __name__ == '__main__':
    input_file = r"I:\QGIS_PLUGINS\TEST_LINE_MAKER\lines_out_v2.shp"
    output_file = r"I:\QGIS_PLUGINS\TEST_LINE_MAKER\swaths_out_v2.shp"
    swath_width = 20  # replace with your desired width
    crs = "EPSG:32617"
    make_swaths(input_file, output_file, swath_width, crs)