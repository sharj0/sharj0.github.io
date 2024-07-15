import os

from PETER_ROSOR_flightline_creator.my_class_definitions import (EndPoint, FltLine, TieLine)
from PETER_ROSOR_flightline_creator.functions import get_anchor_xy, show_information
from PETER_ROSOR_flightline_creator.generate_lines import generate_lines

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import matplotlib

from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
import shapely.wkt

import numpy as np

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QLabel, QApplication
from PyQt5.QtGui import QIcon
from PyQt5 import QtWidgets

from qgis.core import QgsGeometry, QgsWkbTypes, QgsVectorLayer, QgsUnitTypes, QgsProject, QgsFeature

class CustomNavigationToolbar(NavigationToolbar):
    def __init__(self, canvas, parent, coordinates=True):
        super().__init__(canvas, parent, coordinates)
        self._actions_disabled = False

        # Loop through actions and remove specified ones
        actions = self.findChildren(QtWidgets.QAction)
        for action in actions:
            if 'Subplots' in action.text() or 'Save' in action.text() or 'Customize' in action.text():
                self.removeAction(action)
                # No break here as we want to check all actions, not just the first match

    def pan(self, *args):
        super().pan(*args)
        self._toggle_click_handler()

    def zoom(self, *args):
        super().zoom(*args)
        self._toggle_click_handler()

    def _toggle_click_handler(self):
        if self.mode in ['pan/zoom', 'zoom rect']:
            self._actions_disabled = True
        else:
            self._actions_disabled = False

def get_closest_tie_intersection(flt_line, tie_line_list, from_line_start_perspective=True):
    closest_distance = float('inf')  # Initialize with infinity
    closest_intersection = None
    closest_tie_line = None
    distance = None

    for ind, tie_line in enumerate(tie_line_list):
        intersection_arr = flt_line.calculate_intersection(tie_line)
        if intersection_arr is not None:  # If there's an intersection
            # Calculate distance from the flt_line's start or end point to the intersection
            intersection = EndPoint(*intersection_arr)
            if from_line_start_perspective:
                distance = flt_line.start_point.calculate_distance(intersection)
            else:
                distance = flt_line.end_point.calculate_distance(intersection)

            # Update closest intersection if this one is closer
            if distance < closest_distance:
                closest_distance = distance
                closest_intersection = intersection
                closest_tie_line = tie_line

    return closest_intersection, closest_tie_line, closest_distance

def plotting(flt_lines, tie_lines, polygon_coords, new_flt_lines, debug_working_flt_line_list, new_tie_lines, new_poly, anchor_xy):
    # Create the figure
    fig = plt.figure(figsize=(12, 10))
    ax = plt.subplot2grid((12, 12), (0, 0), rowspan=12, colspan=12)

    #for extended_flt_line in debug_working_flt_line_list[:10]:
    #    extended_flt_line.intersections[0].plot(ax, 'bx')
    #    extended_flt_line.intersections[1].plot(ax, 'rx')

    # plot the new data
    ax.plot(*new_poly.exterior.xy, '-')
    for new_flt_line in new_flt_lines:
        new_flt_line.plot(ax, color='blue', linestyle='-', linewidth=0.5)
    for new_tie_line in new_tie_lines:
        new_tie_line.plot(ax, color='red', linestyle='-', linewidth=0.5)

    #plot the old data
    for ring_coords in polygon_coords:
        x, y = zip(*ring_coords)
        ax.plot(x, y, color='black', linestyle='-', linewidth=2, alpha=0.3)
    for flt_line in flt_lines:
        flt_line.plot(ax, color='black', linestyle='-', linewidth=2, alpha=0.3)
    for tie_line in tie_lines:
        tie_line.plot(ax, color='black', linestyle='-', linewidth=2, alpha=0.3)

    ax.text(*anchor_xy, '⚓', fontsize=15, ha='center', va='center')
    ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.set_aspect('equal', adjustable='box')
    return fig

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

def extract_polygon_coords(multi_polygon_geom):
    coords = []
    for polygon in multi_polygon_geom.asMultiPolygon():
        # Each polygon is a list of rings (first ring is exterior, others are holes)
        for ring in polygon:
            # Extract (x, y) ignoring z-coordinate
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

def gui(poly_layer,
        flt_lines,
        tie_lines,
        flt_line_spacing,
        tie_line_spacing,
        tie_line_box_buffer,
        anchor_xy,
        generated_anchor_coordinates,
        flt_line_buffer_distance,
        tie_line_buffer_distance,
        the_rest_of_the_flt_line_gen_params,
        the_rest_of_the_tie_line_gen_params):
    matplotlib.use('Qt5Agg')
    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Flight Lines")


    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)

    # Extracting coordinates for flight lines and tie lines
    flt_lines_coords = get_line_coords(flt_lines)
    tie_lines_coords = get_line_coords(tie_lines)

    # Plotting the polygon geometry
    polygon_feature = next(poly_layer.getFeatures())
    polygon_coords = extract_polygon_coords(polygon_feature.geometry())

    flt_lines = [FltLine(EndPoint(*coord[0]),EndPoint(*coord[1])) for coord in flt_lines_coords]
    tie_lines = [TieLine(EndPoint(*coord[0]), EndPoint(*coord[1])) for coord in tie_lines_coords]

    extended_flt_lines = []
    buffer_polys = []
    debug_working_flt_line_list = []
    for flt_line_idx_for_debug, flt_line in enumerate(flt_lines):
        flt_line.intersections = [None, None]
        for direction in [0, 1]:  # looks at the start and end of lines
            result = get_closest_tie_intersection(flt_line,
                                                  tie_lines,
                                                  from_line_start_perspective=bool(direction))
            intersection, intersec_tie_line, dist = result
            if intersection == None:
                print()
                pass
                ''' not implemented. look for nearest tie line endpoint and extend it out until it does intersect with  
                    with the flight line. dont know how to deal with the new tie lines though. maybe this has to be 
                    done outside first
                '''

            if not intersection == None:
                flt_line.intersections[direction] = intersection
                # intersection.plot(ax, 'r.')
                if dist < tie_line_box_buffer:
                    extend_dist = tie_line_box_buffer - 0.1
                    flt_line.intersections[direction].is_short = True
                else:
                    extend_dist = tie_line_box_buffer + tie_line_spacing - 0.1
                    flt_line.intersections[direction].is_short = False
                ext_end_point = intersection.point_at_distance_and_angle(extend_dist, flt_line.angle + 180 * direction)

                # create or modify a new extended flight line
                if not bool(direction):  # 0, looking back, goes first
                    if not hasattr(flt_line, 'extended_flt_line'):
                        flt_line.extended_flt_line = FltLine(ext_end_point, EndPoint(*flt_line.end_point.xy))
                    else:
                        flt_line.extended_flt_line.start_point.x = ext_end_point.x
                        flt_line.extended_flt_line.start_point.y = ext_end_point.y

                else:  # 1, looking forwards, goes next
                    if not hasattr(flt_line, 'extended_flt_line'):
                        flt_line.extended_flt_line = FltLine(EndPoint(*flt_line.end_point.xy), ext_end_point)
                    else:
                        flt_line.extended_flt_line.end_point.x = ext_end_point.x
                        flt_line.extended_flt_line.end_point.y = ext_end_point.y

        # check if the intersections have the same coords.
        # if they do that means the flt line is intercected by only one tie line and should not be used
        flt_line.has_more_than_one_tie_intersection = True
        if flt_line.intersections[0] is None or flt_line.intersections[0] is None:
            flt_line.has_more_than_one_tie_intersection = False
        else:
            if flt_line.intersections[0].x == flt_line.intersections[1].x and \
                    flt_line.intersections[0].y == flt_line.intersections[1].y:
                if flt_line.intersections[0].is_short and flt_line.intersections[1].is_short:
                    flt_line.has_more_than_one_tie_intersection = False

        if hasattr(flt_line, 'extended_flt_line') and flt_line.has_more_than_one_tie_intersection:
            buffer_poly = flt_line.extended_flt_line.get_buffer_poly(flt_line_spacing / 2 + 0.01)
            buffer_polys.append(buffer_poly)
            debug_working_flt_line_list.append(flt_line)
            extended_flt_lines.append(flt_line.extended_flt_line)

    new_poly = unary_union(buffer_polys)

    if isinstance(new_poly, MultiPolygon):
        all_polys = convert_and_list_polygons(new_poly)
        new_poly = max(all_polys, key=lambda poly: poly.area)

    # get rid of redundant verticies
    new_poly = new_poly.simplify(tolerance=0.001)

    # the following allows for the simplification of the first point in the ring ('simplify' code above may not do it)
    # Shift the points by removing the first point and adding it to the end
    exterior_coords = list(new_poly.exterior.coords)
    shifted_coords = exterior_coords[1:] + [exterior_coords[0]]
    shifted_polygon = Polygon(shifted_coords)
    new_poly = shifted_polygon.simplify(tolerance=0.001)

    # new_poly is in the wrong format
    new_poly_layer = convert_shapely_poly_to_layer(new_poly)

    new_flt_lines_qgis_format = generate_lines(new_poly_layer,
                                               flt_line_buffer_distance,
                                               *the_rest_of_the_flt_line_gen_params)
    new_flt_lines = convert_lines_to_my_format(new_flt_lines_qgis_format)

    # re-generate the tielines to fit in the new polygon
    new_tie_lines_qgis_format = generate_lines(new_poly_layer,
                                               tie_line_buffer_distance,
                                               *the_rest_of_the_tie_line_gen_params)
    new_tie_lines = convert_lines_to_my_format(new_tie_lines_qgis_format)

    # plot on the matplotlib canvas
    fig = plotting(flt_lines, tie_lines, polygon_coords, new_flt_lines, debug_working_flt_line_list, new_tie_lines, new_poly, anchor_xy)

    canvas = FigureCanvas(fig)
    dialog_layout.addWidget(canvas)

    # Bottom bar layout
    bottom_bar_layout = QHBoxLayout()

    toolbar = CustomNavigationToolbar(canvas, dialog)
    bottom_bar_layout.addWidget(toolbar)

    # Add a stretch first to push everything after it to the right
    bottom_bar_layout.addStretch(1)

    # i need this class to be able to pass anchor_xy to the function below
    class G():
        def __init__(self):
            pass
    g = G()
    g.anchor_xy = anchor_xy
    def copy_anchor_coords_to_clipboard():
        clipboard = QApplication.clipboard()
        if not generated_anchor_coordinates:
            g.anchor_xy = get_anchor_xy(poly_layer)
        clipboard.setText(f"{g.anchor_xy[0]}, {g.anchor_xy[1]}")
        message = f'Copied anchor coords {g.anchor_xy} to clipboard'
        show_information(message)
        print(message)

    copy_coords_btn = QPushButton("Copy Generated Anchor Coordinates to Clipboard")
    font = copy_coords_btn.font()
    font.setPointSize(12)  # Adjust font size as needed
    copy_coords_btn.setFont(font)
    copy_coords_btn.setFixedSize(400, 30)
    copy_coords_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    # Connect the button's 'clicked' signal to the 'copy_anchor_coords_to_clipboard' slot
    copy_coords_btn.clicked.connect(copy_anchor_coords_to_clipboard)
    bottom_bar_layout.addWidget(copy_coords_btn)

    btn_accept = QPushButton("Accept and Save", dialog)
    font = btn_accept.font()
    font.setPointSize(12)
    btn_accept.setFont(font)
    btn_accept.setFixedSize(400, 30)
    btn_accept.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    btn_accept.clicked.connect(dialog.accept)
    bottom_bar_layout.addWidget(btn_accept)

    dialog_layout.addLayout(bottom_bar_layout)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "plugin_icon.png")))

    result = dialog.exec_() == QDialog.Accepted
    plt.close(fig)

    del dialog
    return result, new_flt_lines_qgis_format, new_tie_lines_qgis_format, new_poly