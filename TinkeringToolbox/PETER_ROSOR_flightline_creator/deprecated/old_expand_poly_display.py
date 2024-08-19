from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QLabel
import matplotlib.pyplot as plt
import matplotlib
from PyQt5.QtGui import QIcon
import os
from shapely.geometry import Polygon, Point
import numpy as np

from PyQt5 import QtWidgets
from qgis.core import QgsGeometry, QgsWkbTypes, QgsVectorLayer, QgsUnitTypes

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

def gui(poly_layer, flt_lines, tie_lines, tie_line_spacing, tie_line_box_buffer, anchor_xy):
    matplotlib.use('Qt5Agg')
    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Waypoints")

    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)

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

    # Extracting coordinates for flight lines and tie lines
    flt_lines_coords = get_line_coords(flt_lines)
    tie_lines_coords = get_line_coords(tie_lines)

    # Plotting the polygon geometry
    polygon_feature = next(poly_layer.getFeatures())
    polygon_coords = extract_polygon_coords(polygon_feature.geometry())
    class bound_poly():
        def __init__(self, poly):
            self.poly = poly
    bounding_polygon = bound_poly(Polygon(polygon_coords[0]))

    def ploting_safe_space(flt_lines_coords, tie_lines_coords, polygon_coords, line_spacing, buffer):
        # Create the figure
        fig = plt.figure(figsize=(12, 10))
        ax = plt.subplot2grid((12, 12), (0, 0), rowspan=12, colspan=12)

        # Function to create quarter polygons
        def create_quartered_polygons(corners):
            midpoints = [
                ((corners[0][0] + corners[1][0]) / 2, (corners[0][1] + corners[1][1]) / 2),
                ((corners[1][0] + corners[2][0]) / 2, (corners[1][1] + corners[2][1]) / 2),
                ((corners[2][0] + corners[3][0]) / 2, (corners[2][1] + corners[3][1]) / 2),
                ((corners[3][0] + corners[0][0]) / 2, (corners[3][1] + corners[0][1]) / 2)
            ]
            center = (sum(x for x, _ in corners) / 4, sum(y for _, y in corners) / 4)

            return [
                Polygon([corners[0], midpoints[0], center, midpoints[3]]),
                Polygon([midpoints[0], corners[1], midpoints[1], center]),
                Polygon([center, midpoints[1], corners[2], midpoints[2]]),
                Polygon([midpoints[3], center, midpoints[2], corners[3]])
            ]

        for ring_coords in polygon_coords:
           x, y = zip(*ring_coords)
           #ax.plot(x, y, color='black', linestyle='-', linewidth=1.5)  # Adjust color, linestyle, and linewidth as needed# Assuming the first ring is the outer boundary

        #Plotting flight lines
        for line_coords in flt_lines_coords:
           x, y = zip(*line_coords)
           ax.plot(x, y, label='Flight Line', color='darkblue', linestyle='-', linewidth=0.3)

        # Store line objects in a list
        quarters_polygons = []
        expanded_polygons = []
        # Plotting tie lines
        for line_coords in tie_lines_coords:
            x, y = zip(*line_coords)
            ax.plot(x, y, label='Tie Line', color='red')
            dx, dy = np.diff(x), np.diff(y)
            angle = np.arctan2(dy, dx)

            narrow_box = line_spacing / 2
            corners = [
                (x[0] - np.sin(angle)[0] * narrow_box, y[0] + np.cos(angle)[0] * narrow_box),
                (x[1] - np.sin(angle)[0] * narrow_box, y[1] + np.cos(angle)[0] * narrow_box),
                (x[1] + np.sin(angle)[0] * narrow_box, y[1] - np.cos(angle)[0] * narrow_box),
                (x[0] + np.sin(angle)[0] * narrow_box, y[0] - np.cos(angle)[0] * narrow_box)
            ]
            wide_box = line_spacing + buffer
            expanded_corners = [
                (x[0] - np.sin(angle)[0] * wide_box, y[0] + np.cos(angle)[0] * wide_box),
                (x[1] - np.sin(angle)[0] * wide_box, y[1] + np.cos(angle)[0] * wide_box),
                (x[1] + np.sin(angle)[0] * wide_box, y[1] - np.cos(angle)[0] * wide_box),
                (x[0] + np.sin(angle)[0] * wide_box, y[0] - np.cos(angle)[0] * wide_box)
            ]

            quarters_polygons.extend(create_quartered_polygons(corners))
            expanded_polygons.extend(create_quartered_polygons(expanded_corners))

        def on_click(event):
            if toolbar._actions_disabled:
                return
            print('click')
            global current_union_polygon
            if not event.inaxes:
                return

            point = Point(event.xdata, event.ydata)
            if current_union_polygon and current_union_polygon.contains(point):
                bounding_polygon.poly = current_union_polygon

        # Event handler for mouse movement
        def on_move(event):
            if toolbar._actions_disabled:
                return
            global current_union_polygon
            if not event.inaxes:
                return
            for p in ax.patches:
                if p.get_edgecolor() == (0.0, 0.0, 0.0, 1.0):
                    p.remove()

            point = Point(event.xdata, event.ydata)  # Create a Shapely Point for the mouse location
            outside = True
            for original, expand in zip(quarters_polygons, expanded_polygons):
                if original.contains(point):  # Check if the point is within the Shapely polygon
                    # Clear previous union polygons
                    # Create and plot the union polygon
                    expanded_shape = Polygon(expand)
                    union_shape = expanded_shape.union(bounding_polygon.poly)
                    x, y = union_shape.exterior.xy
                    union_polygon = plt.Polygon(list(zip(x, y)), edgecolor='black', facecolor='none', linewidth=1.4)
                    ax.add_patch(union_polygon)
                    outside = False
                    current_union_polygon = Polygon(list(zip(x, y)))

            if outside:
                x, y = bounding_polygon.poly.exterior.xy
                curr_polygon = plt.Polygon(list(zip(x, y)), edgecolor='black', facecolor='none', linewidth=1.4)
                ax.add_patch(curr_polygon)

            fig.canvas.draw_idle()
        fig.canvas.mpl_connect('motion_notify_event', on_move)
        fig.canvas.mpl_connect('button_press_event', on_click)
        ax.set_aspect('equal', adjustable='box')
        return fig

    fig = ploting_safe_space(flt_lines_coords, tie_lines_coords, polygon_coords, tie_line_spacing, tie_line_box_buffer)
    canvas = FigureCanvas(fig)
    dialog_layout.addWidget(canvas)

    # Bottom bar layout
    bottom_bar_layout = QHBoxLayout()
    toolbar = CustomNavigationToolbar(canvas, dialog)
    btn_accept = QPushButton("Accept and Save", dialog)

    font = btn_accept.font()
    font.setPointSize(12)
    btn_accept.setFont(font)
    btn_accept.setFixedSize(300, 30)
    btn_accept.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    anchor_coords_label = QLabel("Anchor Coords: " + str(anchor_xy))
    font = anchor_coords_label.font()
    font.setPointSize(10)
    anchor_coords_label.setFont(font)
    bottom_bar_layout.addWidget(anchor_coords_label)

    bottom_bar_layout.addWidget(toolbar)
    bottom_bar_layout.addStretch(1)
    bottom_bar_layout.addWidget(btn_accept)

    dialog_layout.addLayout(bottom_bar_layout)

    btn_accept.clicked.connect(dialog.accept)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "Waypoint_Terrain_Follow.png")))

    result = dialog.exec_() == QDialog.Accepted
    plt.close(fig)

    del dialog
    return result, bounding_polygon.poly