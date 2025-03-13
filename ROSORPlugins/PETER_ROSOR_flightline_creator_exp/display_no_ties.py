import os

from .my_class_definitions import (EndPoint, FltLine, TieLine)
from .functions import get_anchor_xy, show_information, convert_shapely_poly_to_layer, extract_polygon_coords, \
    get_line_coords, convert_lines_to_my_format, convert_and_list_polygons
from .generate_lines import generate_lines
from .generate_lines import generate_lines

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
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

from qgis.core import QgsGeometry, QgsWkbTypes, QgsVectorLayer, QgsUnitTypes, QgsProject, QgsFeature

class InteractivePlotWidget(QWidget):

    updated_LKM = pyqtSignal(float)

    def __init__(self,
                 poly_layer,
                 anchor_xy,
                 flt_line_buffer_distance,
                 the_rest_of_the_flt_line_gen_params,
                 unbuffered_poly,
                 parent = None
                 ):
        super().__init__(parent)

        # Set up the layout for the widget
        self.layout = QVBoxLayout(self)

        # Create a Matplotlib figure and canvas
        self.figure = Figure(figsize=(12, 10))
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        # Add axes to the figure
        self.ax = self.figure.add_subplot(111)

        # store the original poly_layer (this is for a reset button hopefully)
        self.initial_poly_layer = poly_layer
        self.initial_poly_coords = extract_polygon_coords(next(poly_layer.getFeatures()).geometry())[0]

        # Initialization parameters
        self.the_rest_of_the_flt_line_gen_params = the_rest_of_the_flt_line_gen_params
        self.anchor_xy = anchor_xy
        self.poly_layer = poly_layer
        self.flt_line_buffer_distance = flt_line_buffer_distance
        self.unbuffered_poly = unbuffered_poly

        self.flt_lines = []
        self.LKMs = 0.0
        self.total_LKMs = 0.0

        # These are the output variables that need to be finalized
        self.bounding_poly = None

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

    def plot(self, flt_lines, anchor_xy, poly_layer):

        self.poly_layer = poly_layer

        # Extract the first feature from the polygon layer
        polygon_feature = next(poly_layer.getFeatures())
        polygon_geometry = polygon_feature.geometry()

        # Extract the coordinates from the polygon geometry
        polygon_coords = [(point.x(), point.y()) for point in polygon_geometry.vertices()]

        # Convert the coordinates to a Shapely Polygon
        shapely_polygon = Polygon(polygon_coords)

        self.flt_lines = flt_lines
        self.anchor_xy = anchor_xy

        if isinstance(flt_lines[0], QgsGeometry):
            flt_lines = convert_lines_to_my_format(flt_lines)

        self.ax.clear()

        if self.plot_x_lims:
            self.ax.set_xlim(self.plot_x_lims)

        if self.plot_y_lims:
            self.ax.set_ylim(self.plot_y_lims)

        # Plot the polygon using the Shapely Polygon's exterior coordinates
        self.ax.plot(*shapely_polygon.exterior.xy, '-')
        for flt_line in flt_lines:
            flt_line.plot(self.ax, color='blue', linestyle='-', linewidth=0.5)

        polygon_coords = extract_polygon_coords(polygon_feature.geometry())
        x, y = Polygon(polygon_coords[0]).exterior.xy
        self.ax.plot(x, y, color='darkgreen', linestyle='-', marker=".", linewidth=2, markersize=10, alpha=1,
                     label="Buffered")

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
            self.start_point = (event.xdata, event.ydata)
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

    def update_flight_lines(self):

        self.plot_x_lims = self.ax.get_xlim()
        self.plot_y_lims = self.ax.get_ylim()

        null, self.flt_lines, self.poly_layer, self.bounding_poly = \
            update_flight_lines(
                the_rest_of_the_flt_line_gen_params=self.the_rest_of_the_flt_line_gen_params,
                anchor_xy=self.anchor_xy,
                poly_layer=self.poly_layer,
                flt_line_buffer_distance=self.flt_line_buffer_distance,
                interactive_plot_widget=self,
                flt_lines=None
            )

    def compute_LKM_from_lines(self, flt_lines):
        self.LKMs = 0.0

        for flt_line in flt_lines:
            self.LKMs += flt_line.length()

        self.total_LKMs = self.LKMs
        self.updated_LKM.emit(self.total_LKMs)
        # print(f"Total LKMs: {self.total_LKMs/1000:.3f} km")

    def get_results(self):
        self.update_flight_lines()
        return self.flt_lines, self.bounding_poly

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

# def plotting(flt_lines, polygon_coords, anchor_xy):
#     # Create the figure
#     fig = plt.figure(figsize=(12, 10))
#     ax = plt.subplot2grid((12, 12), (0, 0), rowspan=12, colspan=12)
#
#     #plot the old data
#     for ring_coords in polygon_coords:
#         x, y = zip(*ring_coords)
#         ax.plot(x, y, color='black', linestyle='-', linewidth=0.7)
#     for flt_line in flt_lines:
#         flt_line.plot(ax, color='blue', linestyle='-', linewidth=0.5)
#
#     ax.text(*anchor_xy, '⚓', fontsize=15, ha='center', va='center')
#     ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
#     ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
#     ax.set_aspect('equal', adjustable='box')
#     return fig


def update_flight_lines(the_rest_of_the_flt_line_gen_params,
                        anchor_xy,
                        poly_layer,
                        flt_line_buffer_distance,
                        interactive_plot_widget,
                        flt_lines=None
):
    if flt_lines is None:
        flt_lines = generate_lines(poly_layer,
                                   flt_line_buffer_distance,
                                   *the_rest_of_the_flt_line_gen_params)

    # Extracting coordinates for flight lines and tie lines
    flt_lines_coords = get_line_coords(flt_lines)

    # Plotting the polygon geometry
    polygon_feature = next(poly_layer.getFeatures())
    polygon_coords = extract_polygon_coords(polygon_feature.geometry())
    class bound_poly():
        def __init__(self, poly):
            self.poly = poly
    bounding_polygon = bound_poly(Polygon(polygon_coords[0]))

    flt_lines = generate_lines(poly_layer,
                               flt_line_buffer_distance,
                               *the_rest_of_the_flt_line_gen_params)

    # flt_lines = [FltLine(EndPoint(*coord[0]),EndPoint(*coord[1])) for coord in flt_lines_coords]

    interactive_plot_widget.plot(flt_lines, anchor_xy, poly_layer)

    return interactive_plot_widget, flt_lines, poly_layer, bounding_polygon

def gui(poly_layer,
        flt_lines,
        anchor_xy,
        generated_anchor_coordinates,
        flt_line_buffer_distance,
        the_rest_of_the_flt_line_gen_params,
        unbuffered_poly = None
        ):

    matplotlib.use('Qt5Agg')

    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Flight Lines")

    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)

    flt_lines_coords = get_line_coords(flt_lines)

    # flt_lines = [FltLine(EndPoint(*coord[0]), EndPoint(*coord[1])) for coord in flt_lines_coords]

    interactive_plot_widget = InteractivePlotWidget(
        poly_layer,
        anchor_xy,
        flt_line_buffer_distance,
        the_rest_of_the_flt_line_gen_params,
        unbuffered_poly
    )

    interactive_plot_widget, flt_lines, poly_layer, bounding_polygon = \
        (
            update_flight_lines
                (
                the_rest_of_the_flt_line_gen_params=the_rest_of_the_flt_line_gen_params,
                anchor_xy=anchor_xy,
                poly_layer=poly_layer,
                flt_line_buffer_distance=flt_line_buffer_distance,
                interactive_plot_widget=interactive_plot_widget,
                flt_lines=flt_lines
                )
        )

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

    new_flt_lines = flt_lines

    if result:
        new_flt_lines, bounding_polygon = interactive_plot_widget.get_results()

    del dialog
    return result, new_flt_lines, bounding_polygon.poly