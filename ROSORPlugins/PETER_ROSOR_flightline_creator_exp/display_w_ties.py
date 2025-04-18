import os

from .my_class_definitions import (EndPoint, FltLine, TieLine)
from .functions import get_anchor_xy, show_information
from .display_functions import (convert_shapely_poly_to_layer, extract_polygon_coords,
                                get_line_coords, convert_lines_to_my_format, convert_and_list_polygons,
                                convert_to_0_180, wrap_around)
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
from PyQt5.QtWidgets import QMenu, QAction

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

        self.instruction_text = self.figure.text(
            0.99,  # x position (right-aligned)
            0.01,  # y position (bottom-aligned)
            "Right-click to add/remove vertices",  # Text content
            ha="right",  # Horizontal alignment
            va="bottom",  # Vertical alignment
            fontsize=9,  # Font size
            color="black",  # Text color
            alpha=1,  # Transparency
            bbox=dict(boxstyle="square,pad=0.5", facecolor="white", edgecolor="white", alpha=0.7)  # Background box
        )
        self.instruction_text.set_text("Move Vertex: Hover over point, left click and drag\nAdd Vertex: Hover over line and right click\nRemove Vertex: Hover over point and right click")

        #store the original poly_layer (this is for a reset button hopefully)
        self.initial_poly_layer = poly_layer
        self.initial_poly_coords = extract_polygon_coords(next(poly_layer.getFeatures()).geometry())[0]

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

        # Initialize variables for hover effects
        self.hovered_vertex = None
        self.hovered_line = None
        self.vertex_artists = []  # Store vertex artists for highlighting
        self.line_artists = []  # Store line artists for highlighting

        # Connect the motion_notify_event for hover effects
        self.cid_motion = self.canvas.mpl_connect('motion_notify_event', self.on_hover)

        # Initialize plot and interaction variables
        self.dragging_line = None
        self.start_point = None
        self.closest_vertex_index = None
        self.closest_line_index = None

    def restore_initial_polygon(self):

        """Restore the polygon to its initial state."""
        # Restore the initial polygon coordinates
        self.poly_layer = convert_shapely_poly_to_layer(MultiPolygon([Polygon(self.initial_poly_coords)]))

        # Redraw the plot with the initial polygon
        self.update_flight_lines()
        self.canvas.draw()

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

        intersection = Polygon(original_poly_coords[0]).intersection(Polygon(polygon_coords[0]))

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

    def get_scaled_threshold(self, event, pixel_threshold=20):
        """Convert a pixel threshold to data coordinates based on the current zoom level."""
        # Get the current axis limits
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()

        # Get the figure size in pixels
        fig_width, fig_height = self.canvas.get_width_height()

        # Calculate the scaling factors for x and y axes
        x_scale = (xlim[1] - xlim[0]) / fig_width
        y_scale = (ylim[1] - ylim[0]) / fig_height

        # Use the average scaling factor to convert the pixel threshold to data coordinates
        scale_factor = (x_scale + y_scale) / 2
        return pixel_threshold * scale_factor

    # This function checks to see if a click is near any of the vertices to set the dragging boolean on
    def on_press(self, event):

        # Adjust threshold as needed
        if event.inaxes != self.ax:
            return

        if self.is_near_vertex(event) is True and event.button == 1:
            self.dragging_line = True
            self.start_point = (event.xdata,  event.ydata)
        else:
            self.dragging_line = None

        if event.button == 3:  # Right-click
            if self.is_near_vertex(event) or self.is_near_line(event):
                self.show_context_menu(event)
                return

    #The on motion function moves a poly_layer vertex within the threshold from on_press along the mouse point data
    def on_motion(self, event):

        #checkes whether mouse is within the axes boolean and dragging line boolean limiters
        if event.inaxes != self.ax:
            return

        if self.dragging_line is not None:
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

            # Ensure the polygon remains closed by updating the last vertex if the first vertex is moved, and vice versa
            num_vertices = len(new_poly_layer_coords)
            if self.closest_vertex_index == 0:
                # If the first vertex is moved, update the last vertex to match
                new_poly_layer_coords[-1] = new_poly_layer_coords[0]
            elif self.closest_vertex_index == num_vertices - 1:
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

    def on_hover(self, event):
        """Handle mouse motion events for hover effects."""
        if event.inaxes != self.ax:
            return

        # Check if the mouse is near a vertex
        self.hovered_vertex = self.is_near_vertex(event)
        if self.hovered_vertex is True:
            # Highlight the vertex and clear any line highlights
            self.highlight_vertex(self.closest_vertex_index)
            self.clear_line_highlight()
        else:
            # If no vertex is near, check if the mouse is near a line
            self.hovered_line = self.is_near_line(event)
            if self.hovered_line is True:
                # Highlight the line and clear any vertex highlights
                self.highlight_line(self.closest_line_index)
                self.clear_vertex_highlight()
            else:
                # If neither is near, clear all highlights
                self.clear_vertex_highlight()
                self.clear_line_highlight()

        # Redraw the canvas
        self.canvas.draw()

    def is_near_vertex(self, event):
        """Find the closest vertex to the mouse position."""

        threshold = self.get_scaled_threshold(event)

        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Iterate over the polygon's vertices to find the closest one to the mouse
        closest_vertex_index = None
        min_dist = float('inf')

        for i, coord in enumerate(poly_layer_coords):
            x, y = coord[:2]
            dist = np.linalg.norm([event.xdata - x, event.ydata - y])
            if dist < min_dist:
                min_dist = dist
                closest_vertex_index = i

        # Return the closest vertex if it is within the threshold
        if min_dist < threshold:
            self.closest_vertex_index = closest_vertex_index
            return True
        else:
            self.closest_vertex_index = None
            return False

    def is_near_line(self, event):
        """Find the closest line to the mouse position."""

        threshold = self.get_scaled_threshold(event)

        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Iterate over the polygon's edges to find the closest one to the mouse
        closest_line_index = None
        min_dist = float('inf')
        for i in range(len(poly_layer_coords)):
            x1, y1 = poly_layer_coords[i]
            x2, y2 = poly_layer_coords[(i + 1) % len(poly_layer_coords)]

            # Calculate the distance from the mouse to the line
            edge_length = np.linalg.norm([x2 - x1, y2 - y1])
            if edge_length == 0:
                continue

            # Project the mouse point onto the line
            t = ((event.xdata - x1) * (x2 - x1) + (event.ydata - y1) * (y2 - y1)) / (edge_length ** 2)
            t = max(0, min(1, t))  # Clamp t to the edge
            proj_x = x1 + t * (x2 - x1)
            proj_y = y1 + t * (y2 - y1)

            dist = np.linalg.norm([event.xdata - proj_x, event.ydata - proj_y])
            if dist < min_dist:
                min_dist = dist
                closest_line_index = i

        # Return the closest line if it is within the threshold
        if min_dist < threshold:
            self.closest_line_index = closest_line_index
            return True
        else:
            self.closest_line_index = None
            return False

    def highlight_vertex(self, vertex_index):
        """Highlight the specified vertex."""
        # Clear previous vertex highlights
        self.clear_vertex_highlight()

        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Plot the highlighted vertex
        x, y = poly_layer_coords[vertex_index]
        artist = self.ax.plot(x, y, marker='o', markersize=10, color='red', alpha=0.8)[0]
        self.vertex_artists.append(artist)

    def highlight_line(self, line_index):
        """Highlight the specified line."""
        # Clear previous line highlights
        self.clear_line_highlight()

        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Plot the highlighted line
        x1, y1 = poly_layer_coords[line_index]
        x2, y2 = poly_layer_coords[(line_index + 1) % len(poly_layer_coords)]
        artist = self.ax.plot([x1, x2], [y1, y2], color='red', linewidth=3, alpha=0.8)[0]
        self.line_artists.append(artist)

    def clear_vertex_highlight(self):
        """Clear all vertex highlights."""
        for artist in self.vertex_artists:
            artist.remove()
        self.vertex_artists.clear()

    def clear_line_highlight(self):
        """Clear all line highlights."""
        for artist in self.line_artists:
            artist.remove()
        self.line_artists.clear()

    def show_context_menu(self, event):
        """Display a context menu"""
        # Create a QMenu
        context_menu = QMenu(self)

        # Add a conditional action to remove a vertex
        if self.is_near_vertex(event):
            remove_vertex_action = QAction("Remove Vertex", self)
            remove_vertex_action.triggered.connect(self.remove_vertex)
            context_menu.addAction(remove_vertex_action)
        else:
            # Add an action to add a vertex
            add_vertex_action = QAction("Add Vertex", self)
            add_vertex_action.triggered.connect(lambda: self.add_vertex(event))
            context_menu.addAction(add_vertex_action)

        # Get the global position of the mouse cursor
        global_pos = self.canvas.mapToGlobal(
            self.canvas.mapFromParent(event.guiEvent.pos())
        )
        # Show the context menu at the cursor position
        context_menu.exec_(global_pos)

    def add_vertex(self, event):
        """Add a vertex to the polygon at the clicked location."""
        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Find the closest edge to the click location
        min_dist = float('inf')
        insert_index = 0

        for i in range(len(poly_layer_coords)):
            # Get the current and next vertex (to form an edge)
            x1, y1 = poly_layer_coords[i]
            x2, y2 = poly_layer_coords[(i + 1) % len(poly_layer_coords)]

            # Calculate the distance from the click to the edge
            edge_length = np.linalg.norm([x2 - x1, y2 - y1])
            if edge_length == 0:
                continue

            # Project the click point onto the edge
            t = ((event.xdata - x1) * (x2 - x1) + (event.ydata - y1) * (y2 - y1)) / (edge_length ** 2)
            t = max(0, min(1, t))  # Clamp t to the edge
            proj_x = x1 + t * (x2 - x1)
            proj_y = y1 + t * (y2 - y1)

            dist = np.linalg.norm([event.xdata - proj_x, event.ydata - proj_y])
            if dist < min_dist:
                min_dist = dist
                insert_index = i + 1

        # Insert the new vertex at the closest edge
        new_vertex = (event.xdata, event.ydata)
        poly_layer_coords.insert(insert_index, new_vertex)

        # Update the polygon layer
        self.poly_layer = convert_shapely_poly_to_layer(MultiPolygon([Polygon(poly_layer_coords)]))

        # Redraw the plot
        self.update_flight_lines()
        self.canvas.draw()

    def remove_vertex(self):
        """Remove the closest vertex from the polygon."""
        if self.closest_vertex_index is None:
            return

        # Get the current polygon coordinates
        current_features = next(self.poly_layer.getFeatures())
        poly_layer_coords = extract_polygon_coords(current_features.geometry())[0]

        # Ensure the polygon has at least 4 vertices (3 unique vertices + closing vertex)
        if len(poly_layer_coords) > 4:  # Allow removing the start/end vertex
            # Remove the closest vertex
            poly_layer_coords.pop(self.closest_vertex_index)

            # If the start/end vertex was removed, update the last vertex to match the new start vertex
            if self.closest_vertex_index == 0 or self.closest_vertex_index == len(poly_layer_coords):
                poly_layer_coords[-1] = poly_layer_coords[0]

            # Update the polygon layer
            self.poly_layer = convert_shapely_poly_to_layer(MultiPolygon([Polygon(poly_layer_coords)]))

            # Redraw the plot
            self.update_flight_lines()
            self.canvas.draw()
        else:
            print("Cannot remove vertex: Polygon must have at least 3 vertices.")

    # this function reruns the update_flight_lines function in the out code
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
        # print(f"Total LKMs: {self.total_LKMs/1000:.3f} km")

    # this returns the desired output variables so that an outside function can access the desired values
    def get_results(self):
        self.update_flight_lines()
        return (self.new_flt_lines_qgis_format,
                self.new_tie_lines_qgis_format,
                self.new_poly,
                self.the_rest_of_the_flt_line_gen_params,
                self.the_rest_of_the_tie_line_gen_params)


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

# This function regenerates flight and tie lines using all the input parameters that are passed through it
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

    # Create a layout for the Undo button
    reset_button_layout = QHBoxLayout()
    reset_button_layout.addStretch(1)  # Push the button to the right

    # Bottom bar layout
    bottom_bar_layout = QHBoxLayout()

    toolbar = CustomNavigationToolbar(interactive_plot_widget.canvas, dialog)
    bottom_bar_layout.addWidget(toolbar)

    # Add a stretch first to push everything after it to the right
    bottom_bar_layout.addStretch(1)

    # Add the Undo button
    undo_button = QPushButton("Reset", dialog)
    font = undo_button.font()
    font.setPointSize(12)  # Adjust font size as needed
    undo_button.setFont(font)
    undo_button.setFixedSize(100, 30)
    undo_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    undo_button.clicked.connect(interactive_plot_widget.restore_initial_polygon)
    reset_button_layout.addWidget(undo_button)

    dialog_layout.addLayout(reset_button_layout)


    # angle_label = QLabel("Flight Line Angle:", dialog)
    # angle_label.setFixedSize(150, 20)
    # dialog_layout.addWidget(angle_label)

    flight_line_spacing = the_rest_of_the_flt_line_gen_params[0]
    flight_line_angle = the_rest_of_the_flt_line_gen_params[1]
    flight_line_shift_sideways = the_rest_of_the_flt_line_gen_params[2]

    angle_slider = QSlider(Qt.Horizontal, dialog)
    angle_slider.setMinimum(0)
    angle_slider.setMaximum(180)

    normalized_degree = convert_to_0_180(flight_line_angle)

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
    flt_line_translation_slider.setMaximum(int(flight_line_spacing))

    flt_translation_value = wrap_around(int(flight_line_shift_sideways),0,int(flight_line_spacing))

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

    bottom_bar_layout.addWidget(btn_accept)

    dialog_layout.addLayout(bottom_bar_layout)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "plugin_icon.png")))

    btn_accept.clicked.connect(lambda: dialog.accept())

    result = dialog.exec_() == QDialog.Accepted

    outputs = []

    # runs the get_results function of the class to return the final output
    if result:
        outputs = interactive_plot_widget.get_results()

    del dialog
    return result, *outputs
