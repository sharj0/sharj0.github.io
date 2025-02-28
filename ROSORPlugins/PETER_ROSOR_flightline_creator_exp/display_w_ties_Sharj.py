import os

from .my_class_definitions import (EndPoint, FltLine, TieLine)
from .functions import get_anchor_xy, show_information
from .generate_lines import generate_lines

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backend_bases import MouseButton
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib

from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
import shapely.wkt

import numpy as np

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QLabel, QApplication, QWidget, \
    QSlider
from PyQt5.QtGui import QIcon, QFont
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal

from qgis.core import QgsGeometry, QgsWkbTypes, QgsPointXY, QgsPoint, QgsVectorLayer, QgsUnitTypes, QgsProject, \
    QgsFeature


# THIS IS A CUSTOM INTERACTIVE PLOT WIDGET CLASS THAT REQUIRES AN ARRAY OF INPUTS TO INITIALIZE
class InteractivePlotWidget(QWidget):

    updated_LKM = pyqtSignal(float)

    def __init__(self,
                 the_rest_of_the_flt_line_gen_params,
                 the_rest_of_the_tie_line_gen_params,
                 anchor_xy,
                 poly_layer,
                 flt_line_buffer_distance,
                 tie_line_buffer_distance,
                 tie_line_box_buffer,
                 flt_line_spacing,
                 tie_line_spacing,
                 unbuffered_poly,
                 parent=None):

        super().__init__(parent)
        # Set up the layout for the widget
        self.layout = QVBoxLayout(self)

        # Create a Matplotlib figure and canvas
        self.figure = Figure(figsize=(12, 10))
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        # Add axes to the figure
        self.ax = self.figure.add_subplot(111)


        # Panning variables
        self.panning = False
        self.pan_start = None
        self.plot_x_lims = None
        self.plot_y_lims = None

        # Initialize plot and interaction variables
        self.dragging_line = None
        self.start_point = None
        self.closest_vertex_index = None

        #store the original poly_layer (this is for a reset button hopefully)
        self.initial_poly_layer = poly_layer

        # Initialization parameters
        self.the_rest_of_the_flt_line_gen_params = the_rest_of_the_flt_line_gen_params
        self.the_rest_of_the_tie_line_gen_params = the_rest_of_the_tie_line_gen_params
        self.anchor_xy = anchor_xy
        self.poly_layer = poly_layer
        self.flt_line_buffer_distance = flt_line_buffer_distance
        self.tie_line_buffer_distance = tie_line_buffer_distance
        self.tie_line_box_buffer = tie_line_box_buffer
        self.flt_line_spacing = flt_line_spacing
        self.tie_line_spacing = tie_line_spacing
        self.unbuffered_poly = unbuffered_poly

        # These are regeneration parameters (everytime a change happens, these are regenerated using generate_lines function)
        self.flt_lines = []
        self.tie_lines = []
        self.new_flt_lines = []
        self.new_tie_lines = []
        self.LKMs = 0.0
        self.total_LKMs = 0.0


        # These are the output variables that need to be finalized
        self.new_flt_lines_qgis_format = None
        self.new_tie_lines_qgis_format = None
        self.new_poly = None

        self.plot_x_lims = None
        self.plot_y_lims = None

        # Connect event handlers
        self.cid_press = self.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_release = self.canvas.mpl_connect('button_release_event', self.on_release)
        self.cid_motion = self.canvas.mpl_connect('motion_notify_event', self.on_motion)


    def plot(self, flt_lines, tie_lines, new_flt_lines, new_tie_lines, new_poly, anchor_xy, poly_layer):

        # store the current poly layer into the class for use in on_motion and on_press
        self.poly_layer = poly_layer

        # Instead of passing down polygon_coords, it is regenerated everyime poly_layer is tampered with
        #Uses gets the MultipolygonZ feature from the polygon layer and uses the custom function to extract coords (idk why multipolygonZ with 0 alt)
        polygon_feature = next(poly_layer.getFeatures())
        polygon_coords = extract_polygon_coords(polygon_feature.geometry())

        # Store these for later use in the on_motion event
        self.flt_lines = flt_lines
        self.tie_lines = tie_lines
        self.new_flt_lines = new_flt_lines
        self.new_tie_lines = new_tie_lines
        self.new_poly = new_poly
        self.anchor_xy = anchor_xy

        self.compute_LKM_from_lines(flt_lines=new_flt_lines,tie_lines=new_tie_lines)

        # Example plotting logic
        self.ax.clear()  # Clear previous plot

        if self.plot_x_lims:
            self.ax.set_xlim(self.plot_x_lims)

        if self.plot_y_lims:
            self.ax.set_ylim(self.plot_y_lims)

        # Plotting the new data
        self.ax.plot(*new_poly.exterior.xy, '-')
        for new_flt_line in new_flt_lines:
            new_flt_line.plot(self.ax, color='blue', linestyle='-', linewidth=0.5)
        for new_tie_line in new_tie_lines:
            new_tie_line.plot(self.ax, color='red', linestyle='-', linewidth=0.5)

        x, y = Polygon(polygon_coords[0]).exterior.xy
        self.ax.plot(x, y, color='darkgreen', linestyle='-', marker=".", linewidth=2, markersize=10, alpha=1, label = "Buffered")

        original_poly_coords = extract_polygon_coords(next(self.unbuffered_poly.getFeatures()).geometry())

        x, y = Polygon(original_poly_coords[0]).exterior.xy
        self.ax.plot(x, y, color='coral', linestyle='-', linewidth=2, alpha=1, label="Unbuffered")
        self.ax.fill(x, y, color="red", alpha=1)

        intersection = Polygon(original_poly_coords[0]).intersection(new_poly)

        if not intersection.is_empty:
            # If the intersection is a MultiPolygon, iterate over each Polygon
            if isinstance(intersection, MultiPolygon):
                for polygon in intersection.geoms:
                    x_int, y_int = polygon.exterior.xy
                    self.ax.fill(x_int, y_int, color="white", alpha=1)
            else:  # If the intersection is a single Polygon
                x_int, y_int = intersection.exterior.xy
                self.ax.fill(x_int, y_int, color="white", alpha=1)
        else:
            pass


        self.ax.text(*anchor_xy, '⚓', fontsize=15, ha='center', va='center')
        self.ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:,.0f}'))
        self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:,.0f}'))
        self.ax.set_aspect('equal', adjustable='box')

        self.ax.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize='small', title='Legend', title_fontsize='medium')

        # Draw the canvas to update the plot
        self.canvas.draw()

    # This function checks to see if a click is near any of the vertices to set the dragging boolean on
    def on_press(self, event, threshold=25):


        # Adjust threshold as needed
        if event.inaxes != self.ax:
            return

        # Initialize variables to find the closest vertex
        closest_vertex_index = None
        min_dist = float('inf')

        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Iterate over the polygon's vertices to find the closest one to the click
        for i, coord in enumerate(poly_layer_coords):

            #skip the first vertex since its the same as the last
            if i == 0:
                continue

            x, y = coord[:2]
            dist = np.linalg.norm([event.xdata - x, event.ydata - y])
            if dist < min_dist:
                min_dist = dist
                closest_vertex_index = i

        # If the closest vertex is within a reasonable distance, enable dragging, get the closest vertex and store starting click point value
        if min_dist < threshold:
            self.dragging_line = True
            self.start_point = (event.xdata, event.ydata)
            self.closest_vertex_index = closest_vertex_index
        else:
            self.dragging_line = None

    #The on motion function moves a poly_layer vertex within the threshold from on_press along the mouse point data
    def on_motion(self, event):

        #checkes whether mouse is within the axes boolean and dragging line boolean limiters
        if event.inaxes != self.ax or self.dragging_line is None:
            return

        # takes the mouse movement and subtracts from the starting click in the on_press function to get the x and y deltas
        dx = event.xdata - self.start_point[0]
        dy = event.ydata - self.start_point[1]
        self.start_point = (event.xdata, event.ydata)

        # Get the original polygon coordinates
        updated_features = next(self.poly_layer.getFeatures())
        new_poly_layer_coords = extract_polygon_coords(updated_features.geometry())[0]

        # Update only the closest vertex coordinates
        new_poly_layer_coords[self.closest_vertex_index] = (
            new_poly_layer_coords[self.closest_vertex_index][0] + dx,
            new_poly_layer_coords[self.closest_vertex_index][1] + dy
        )

        # Ensure the polygon remains closed
        num_vertices = len(new_poly_layer_coords)
        if self.closest_vertex_index == num_vertices - 1:
            # If the last vertex is moved, update the first vertex to match
            new_poly_layer_coords[0] = new_poly_layer_coords[-1]

        #remake the poly_layer using coordinate list
        self.poly_layer = convert_shapely_poly_to_layer(MultiPolygon([Polygon(new_poly_layer_coords)]))

        # Update the flight lines and tie lines live
        self.update_flight_lines()

    #Release function to set the dragging line booleans false/None when mouse drag is let go
    def on_release(self, event):


        if self.dragging_line is None:
            return
        self.dragging_line = None

    # this function reruns the update_flight_lines function in the out code (it is called in other functions everytime a change is made)
    # It stores the desired output variables back into the class as they were initialized as None
    def update_flight_lines(self):
        """Calls the update_flight_lines function with current parameters."""

        self.plot_x_lims = self.ax.get_xlim()
        self.plot_y_lims = self.ax.get_ylim()

        null, self.new_flt_lines_qgis_format, self.new_tie_lines_qgis_format, self.new_poly = \
            update_flight_lines(
                the_rest_of_the_flt_line_gen_params=self.the_rest_of_the_flt_line_gen_params,
                the_rest_of_the_tie_line_gen_params=self.the_rest_of_the_tie_line_gen_params,
                anchor_xy=self.anchor_xy,
                poly_layer=self.poly_layer,
                flt_line_buffer_distance=self.flt_line_buffer_distance,
                tie_line_buffer_distance=self.tie_line_buffer_distance,
                tie_line_box_buffer=self.tie_line_box_buffer,
                flt_line_spacing=self.flt_line_spacing,
                tie_line_spacing=self.tie_line_spacing,
                interactive_plot_widget=self,
                flt_lines=None,
                tie_lines=None
            )

    #modifies the input parameters for update flight lines and reruns said function with newly stored values in the class
    def update_params_through_sliders(self, new_flt_line_angle, new_flt_line_translation, new_tie_line_translation):
        self.the_rest_of_the_flt_line_gen_params = (
            self.the_rest_of_the_flt_line_gen_params[0],
            new_flt_line_angle,
            new_flt_line_translation,
            self.the_rest_of_the_flt_line_gen_params[3],
            self.the_rest_of_the_flt_line_gen_params[4],
            self.the_rest_of_the_flt_line_gen_params[5]
        )
        self.the_rest_of_the_tie_line_gen_params = (
            self.the_rest_of_the_tie_line_gen_params[0],
            new_flt_line_angle + 90,
            new_tie_line_translation,
            self.the_rest_of_the_tie_line_gen_params[3],
            self.the_rest_of_the_tie_line_gen_params[4],
            self.the_rest_of_the_tie_line_gen_params[5]
        )
        self.update_flight_lines()

    def compute_LKM_from_lines(self, flt_lines, tie_lines):
        self.LKMs = 0.0

        for flt_line in flt_lines:
            self.LKMs += flt_line.length()

        for tie_line in tie_lines:
            self.LKMs += tie_line.length()

        self.total_LKMs = self.LKMs
        self.updated_LKM.emit(self.total_LKMs)
        print(f"Total LKMs: {self.total_LKMs/1000:.3f} km")


    # this returns the desired output variables so that an outside function can access the desired values
    def get_results(self):
        self.update_flight_lines()
        return self.new_flt_lines_qgis_format, self.new_tie_lines_qgis_format, self.new_poly


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


# This function regenerates flight and tie lines using all the input parameters that are passed through it
# It does not require flt_lines and tie_lines input as it will generate them if they don't exist
# I just took peters old code and made it into a singular function
def update_flight_lines(the_rest_of_the_flt_line_gen_params,
                        the_rest_of_the_tie_line_gen_params,
                        anchor_xy,
                        poly_layer,
                        flt_line_buffer_distance,
                        tie_line_buffer_distance,
                        tie_line_box_buffer,
                        flt_line_spacing,
                        tie_line_spacing,
                        interactive_plot_widget,
                        flt_lines=None,
                        tie_lines=None,
                        ):
    if flt_lines is None:
        flt_lines = generate_lines(poly_layer,
                                   tie_line_box_buffer,  # this is set to buffer the shape differently
                                   *the_rest_of_the_flt_line_gen_params)
        flt_lines_coords = get_line_coords(flt_lines)
        flt_lines = [FltLine(EndPoint(*coord[0]), EndPoint(*coord[1])) for coord in flt_lines_coords]

    if tie_lines is None:
        tie_lines = generate_lines(poly_layer,
                                   tie_line_box_buffer,  # this is set to buffer the shape differently
                                   *the_rest_of_the_tie_line_gen_params)
        tie_lines_coords = get_line_coords(tie_lines)
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
            if intersection is None:
                print()
                pass
                ''' not implemented. look for nearest tie line endpoint and extend it out until it does intersect with  
                        with the flight line. dont know how to deal with the new tie lines though. maybe this has to be 
                        done outside first
                    '''

            if intersection is not None:
                flt_line.intersections[direction] = intersection
                # intersection.plot(ax, 'r.')
                if dist < tie_line_box_buffer:
                    extend_dist = tie_line_box_buffer - 0.1
                    flt_line.intersections[direction].is_short = True
                else:
                    extend_dist = tie_line_box_buffer + tie_line_spacing - 0.1
                    flt_line.intersections[direction].is_short = False
                ext_end_point = intersection.point_at_distance_and_angle(extend_dist,
                                                                         flt_line.angle + 180 * direction)

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

    # Re-generate flight lines with the updated angle
    new_flt_lines_qgis_format = generate_lines(new_poly_layer,
                                               flt_line_buffer_distance,
                                               *the_rest_of_the_flt_line_gen_params)

    new_tie_lines_qgis_format = generate_lines(new_poly_layer,
                                               tie_line_buffer_distance,
                                               *the_rest_of_the_tie_line_gen_params)

    new_flt_lines = convert_lines_to_my_format(new_flt_lines_qgis_format)

    new_tie_lines = convert_lines_to_my_format(new_tie_lines_qgis_format)

    # Re-plot the updated lines
    interactive_plot_widget.plot(flt_lines, tie_lines, new_flt_lines, new_tie_lines, new_poly,
                                 anchor_xy, poly_layer)

    # Return the desired outputs, the plot widget class, and output data
    return interactive_plot_widget, new_flt_lines_qgis_format, new_tie_lines_qgis_format, new_poly


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
        the_rest_of_the_tie_line_gen_params,
        unbuffered_poly = None):
    matplotlib.use('Qt5Agg')

    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Flight Lines")

    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)

    # Extracting coordinates for flight lines and tie lines
    flt_lines_coords = get_line_coords(flt_lines)
    tie_lines_coords = get_line_coords(tie_lines)

    flt_lines = [FltLine(EndPoint(*coord[0]), EndPoint(*coord[1])) for coord in flt_lines_coords]
    tie_lines = [TieLine(EndPoint(*coord[0]), EndPoint(*coord[1])) for coord in tie_lines_coords]

    # plot on the matplotlib canvas
    # fig, ax = plotting(flt_lines, tie_lines, polygon_coords, new_flt_lines, debug_working_flt_line_list, new_tie_lines,
    #                new_poly, anchor_xy)

    # Creating an instance of the class for the interactive plot using the class inputs
    interactive_plot_widget = InteractivePlotWidget(
        the_rest_of_the_flt_line_gen_params=the_rest_of_the_flt_line_gen_params,
        the_rest_of_the_tie_line_gen_params=the_rest_of_the_tie_line_gen_params,
        anchor_xy=anchor_xy,
        poly_layer=poly_layer,
        flt_line_buffer_distance=flt_line_buffer_distance,
        tie_line_buffer_distance=tie_line_buffer_distance,
        tie_line_box_buffer=tie_line_box_buffer,
        flt_line_spacing=flt_line_spacing,
        tie_line_spacing=tie_line_spacing,
        unbuffered_poly=unbuffered_poly
    )

    #the plot needs to start somewhere, and that is here as update_flight_lines plots at the end
    interactive_plot_widget, new_flt_lines_qgis_format, new_tie_lines_qgis_format, new_poly = \
        (
            update_flight_lines
                (
                the_rest_of_the_flt_line_gen_params=the_rest_of_the_flt_line_gen_params,
                the_rest_of_the_tie_line_gen_params=the_rest_of_the_tie_line_gen_params,
                anchor_xy=anchor_xy,
                poly_layer=poly_layer,
                flt_line_buffer_distance=flt_line_buffer_distance,
                tie_line_buffer_distance=tie_line_buffer_distance,
                tie_line_box_buffer=tie_line_box_buffer,
                flt_line_spacing=flt_line_spacing,
                tie_line_spacing=tie_line_spacing,
                interactive_plot_widget=interactive_plot_widget,
                flt_lines=flt_lines,
                tie_lines=tie_lines
            )
        )

    # adding the interactive widget
    dialog_layout.addWidget(interactive_plot_widget)

    # Bottom bar layout
    bottom_bar_layout = QHBoxLayout()

    toolbar = CustomNavigationToolbar(interactive_plot_widget.canvas, dialog)
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

    """Sharj"""
    # Creating slider widgets for translation (I could change this to a input box but I find it more intuitive to slide and translate)
    # The slider has a set range (I'm thinking of changing it to the min and max distance from anchor but that is beyond my pay grade)
    # The slider DOES NOT WORK with floating point values, so I have to use integers (damn you QWidgets)
    # Live readings of the value are shown to the user (I might change that to an input box later)

    # angle_label = QLabel("Flight Line Angle:", dialog)
    # angle_label.setFixedSize(150, 20)
    # dialog_layout.addWidget(angle_label)

    angle_slider = QSlider(Qt.Horizontal, dialog)
    angle_slider.setMinimum(0)
    angle_slider.setMaximum(180)

    def convert_to_0_180(degree):
        normalized_degree = (int(degree) + 360) % 360  # Normalize to the range [0, 360)
        if normalized_degree > 180:
            return normalized_degree - 180
        return normalized_degree

    normalized_degree = convert_to_0_180(the_rest_of_the_flt_line_gen_params[1])

    angle_slider.setValue(int(normalized_degree))  # Assuming flight_line_angle is the second element
    angle_slider.setFixedSize(400, 20)

    angle_value_label = QLabel(f"Flight Line Angle: {angle_slider.value()} degrees", dialog)
    angle_value_label.setFixedSize(150, 20)

    dialog_layout.addWidget(angle_value_label)
    dialog_layout.addWidget(angle_slider)

    # flt_line_translation_label = QLabel("Flight Line Translation:", dialog)
    # flt_line_translation_label.setFixedSize(150, 20)
    # dialog_layout.addWidget(flt_line_translation_label)

    flt_line_translation_slider = QSlider(Qt.Horizontal, dialog)
    flt_line_translation_slider.setMinimum(0)
    flt_line_translation_slider.setMaximum(int(flt_line_spacing))

    def wrap_around(value, min_val=0, max_val=100):
        range_width = max_val - min_val
        # Normalize value to be within the range [0, range_width)
        normalized_value = (value - min_val) % range_width
        return normalized_value + min_val

    flt_translation_value = wrap_around(int(the_rest_of_the_flt_line_gen_params[2]),0,int(flt_line_spacing))

    flt_line_translation_slider.setValue(int(flt_translation_value))  # Assuming flt_shift is third element
    flt_line_translation_slider.setFixedSize(400, 20)
    flt_line_translation_value_label = QLabel(f"Flight Line Translation: {flt_line_translation_slider.value()} m",
                                              dialog)
    flt_line_translation_value_label.setFixedSize(150, 20)

    dialog_layout.addWidget(flt_line_translation_value_label)
    dialog_layout.addWidget(flt_line_translation_slider)

    # tie_line_translation_label = QLabel("Tie Line Translation:", dialog)
    # tie_line_translation_label.setFixedSize(150, 20)
    # dialog_layout.addWidget(tie_line_translation_label)

    tie_line_translation_slider = QSlider(Qt.Horizontal, dialog)
    tie_line_translation_slider.setMinimum(0)
    tie_line_translation_slider.setMaximum(int(tie_line_spacing))

    tie_translation_value = wrap_around(int(the_rest_of_the_tie_line_gen_params[2]),0,int(tie_line_spacing))

    tie_line_translation_slider.setValue(int(tie_translation_value))  # Assuming tie_shift is the third element
    tie_line_translation_slider.setFixedSize(400, 20)

    tie_line_translation_value_label = QLabel(f"Tie Line Translation: {tie_line_translation_slider.value()} m",
                                              dialog)
    tie_line_translation_value_label.setFixedSize(150, 20)

    dialog_layout.addWidget(tie_line_translation_value_label)
    dialog_layout.addWidget(tie_line_translation_slider)

    # The sliders are connected to the parameter change function in the class for live changes
    angle_slider.valueChanged.connect(
        lambda value: interactive_plot_widget.update_params_through_sliders(
            new_flt_line_angle=value,
            new_flt_line_translation=flt_line_translation_slider.value(),
            new_tie_line_translation=tie_line_translation_slider.value()
        )
    )

    flt_line_translation_slider.valueChanged.connect(
        lambda value: interactive_plot_widget.update_params_through_sliders(
            new_flt_line_angle=angle_slider.value(),
            new_flt_line_translation=value,
            new_tie_line_translation=tie_line_translation_slider.value()
            # Assuming you want to use the current tie line slider value
        )
    )

    tie_line_translation_slider.valueChanged.connect(
        lambda value: interactive_plot_widget.update_params_through_sliders(
            new_flt_line_angle=angle_slider.value(),
            new_flt_line_translation=flt_line_translation_slider.value(),
            # Assuming you want to use the current flight line slider value
            new_tie_line_translation=value
        )
    )

    #Live monitoring of the values
    def update_angle_label(value):
        angle_value_label.setText(f"Flight Line Angle: {value} degrees")

    def update_flt_label(value):
        flt_line_translation_value_label.setText(f"Flight Line Translation: {value} m")

    def update_tie_label(value):
        tie_line_translation_value_label.setText(f"Tie Line Translation: {value} m")

    angle_slider.valueChanged.connect(update_angle_label)
    flt_line_translation_slider.valueChanged.connect(update_flt_label)
    tie_line_translation_slider.valueChanged.connect(update_tie_label)

    display_LKMs_live_label = QLabel(f"Total LKMs: {interactive_plot_widget.total_LKMs/1000:.3f} km")
    display_LKMs_live_label.setFixedSize(400,20)
    display_LKMs_live_label_font_size = QFont()
    display_LKMs_live_label_font_size.setPointSize(12)
    display_LKMs_live_label.setFont(display_LKMs_live_label_font_size)
    dialog_layout.addWidget(display_LKMs_live_label)


    def update_LKMs_live_label(value):
        display_LKMs_live_label.setText(f"Total LKMs: {value/1000:.3f} km")

    interactive_plot_widget.updated_LKM.connect(update_LKMs_live_label)

    """Sharj"""

    btn_accept = QPushButton("Accept and Save", dialog)
    font = btn_accept.font()
    font.setPointSize(12)
    btn_accept.setFont(font)
    btn_accept.setFixedSize(400, 30)
    btn_accept.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    bottom_bar_layout.addWidget(btn_accept)

    dialog_layout.addLayout(bottom_bar_layout)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "plugin_icon.png")))

    btn_accept.clicked.connect(lambda: dialog.accept())

    result = dialog.exec_() == QDialog.Accepted

    # runs the get_results function of the class to return the final output
    # maybe add a button to reset to initial condition (but too much work rn)
    if result:
        new_flt_lines_qgis_format, new_tie_lines_qgis_format, new_poly = interactive_plot_widget.get_results()

    del dialog
    return result, new_flt_lines_qgis_format, new_tie_lines_qgis_format, new_poly
