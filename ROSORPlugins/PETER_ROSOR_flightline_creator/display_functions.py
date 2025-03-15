
from qgis.core import (QgsFeature, QgsGeometry, QgsVectorLayer, QgsWkbTypes)
from .my_class_definitions import (EndPoint, TieLine)

def convert_shapely_poly_to_layer(shapely_poly):
    """
    Convert a Shapely Polygon to a QGIS layer without adding it to the Layers Panel.

    Parameters:
    - shapely_poly: A Shapely Polygon object.

    Returns:
    - A QGIS Vector Layer containing the given polygon, not added to the QGIS project.
    """
    # Convert the Shapely Polygon to WKT format
    poly_wkt = shapely_poly.wkt

    # Create a new memory layer, specify 'Polygon' for polygon geometries.
    # Replace 'EPSG:4326' with the correct CRS for your data
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "new_polygon_layer", "memory")

    # Get the layer's data provider and start editing the layer
    prov = layer.dataProvider()
    layer.startEditing()

    # Create a new feature and set its geometry from the WKT of the Shapely polygon
    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromWkt(poly_wkt))

    # Add the feature to the layer
    prov.addFeature(feat)

    # Commit changes to the layer. Do not add the layer to the QgsProject instance
    layer.commitChanges()

    return layer

def extract_polygon_coords(geom):
    # peter added chaange to fix "Polygon geometry cannot be converted to a multipolygon. Only multi polygon or curves are permitted."
    # Check if the geometry is multipart
    if geom.isMultipart():
        # If it's a multipolygon, use asMultiPolygon()
        polygons = geom.asMultiPolygon()
    else:
        # If it's a single polygon, wrap the asPolygon() output in a list
        polygons = [geom.asPolygon()]

    coords = []
    for polygon in polygons:
        # Each polygon is a list of rings (first ring is exterior, others are holes)
        for ring in polygon:
            # Extract (x, y) ignoring the z-coordinate
            ring_coords = [(pt.x(), pt.y()) for pt in ring]
            coords.append(ring_coords)
    return coords

def get_line_coords(lines):
    coords = []
    for qgs_geometry in lines:
        if QgsWkbTypes.isSingleType(qgs_geometry.wkbType()):
            geom = qgs_geometry.asPolyline()
            coords.append([(point.x(), point.y()) for point in geom])
        elif QgsWkbTypes.isMultiType(qgs_geometry.wkbType()):
            multi_geom = qgs_geometry.asMultiPolyline()
            for line in multi_geom:
                coords.append([(point.x(), point.y()) for point in line])
    return coords

def convert_lines_to_my_format(new_lines_qgis_format):
    new_lines = []
    for new_line in new_lines_qgis_format:
        start = EndPoint(x=new_line.asPolyline()[0].x(), y=new_line.asPolyline()[0].y())
        end = EndPoint(x=new_line.asPolyline()[1].x(), y=new_line.asPolyline()[1].y())
        new_lines.append(TieLine(start, end))
    return new_lines

def convert_and_list_polygons(geometry):
    polygons = [poly for poly in geometry.geoms]
    return polygons

def convert_to_0_180(degree):
    normalized_degree = (int(degree) + 360) % 360  # Normalize to the range [0, 360)
    if normalized_degree > 180:
        return normalized_degree - 180
    return normalized_degree

def wrap_around(value, min_val=0, max_val=100):
    range_width = max_val - min_val
    # Normalize value to be within the range [0, range_width)
    normalized_value = (value - min_val) % range_width
    return normalized_value + min_val

