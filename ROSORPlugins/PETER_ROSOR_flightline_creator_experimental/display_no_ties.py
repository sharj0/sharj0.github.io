import os

from PETER_ROSOR_flightline_creator.my_class_definitions import (EndPoint, FltLine, TieLine)
from PETER_ROSOR_flightline_creator.functions import get_anchor_xy, show_information
from PETER_ROSOR_flightline_creator.generate_lines import generate_lines

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import matplotlib

from shapely.geometry import Polygon
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

def plotting(flt_lines, polygon_coords, anchor_xy):
    # Create the figure
    fig = plt.figure(figsize=(12, 10))
    ax = plt.subplot2grid((12, 12), (0, 0), rowspan=12, colspan=12)

    #plot the old data
    for ring_coords in polygon_coords:
        x, y = zip(*ring_coords)
        ax.plot(x, y, color='black', linestyle='-', linewidth=0.7)
    for flt_line in flt_lines:
        flt_line.plot(ax, color='blue', linestyle='-', linewidth=0.5)

    ax.text(*anchor_xy, '⚓', fontsize=15, ha='center', va='center')
    ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.set_aspect('equal', adjustable='box')
    return fig

def gui(poly_layer,
        flt_lines,
        anchor_xy,
        generated_anchor_coordinates):
    matplotlib.use('Qt5Agg')
    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Flight Lines")

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

    # Plotting the polygon geometry
    polygon_feature = next(poly_layer.getFeatures())
    polygon_coords = extract_polygon_coords(polygon_feature.geometry())
    class bound_poly():
        def __init__(self, poly):
            self.poly = poly
    bounding_polygon = bound_poly(Polygon(polygon_coords[0]))

    flt_lines = [FltLine(EndPoint(*coord[0]),EndPoint(*coord[1])) for coord in flt_lines_coords]

    # plot on the matplotlib canvas
    fig = plotting(flt_lines, polygon_coords, anchor_xy)

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
    return result, bounding_polygon.poly