import numpy as np
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QSizePolicy
)
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsGeometry, QgsPointXY
from PyQt5.QtGui import QColor

# Global variables to track the current instances.
current_dock_widget = None
current_map_tool = None

# ---------------------------------------------------------------------------
# Dock Widget with Buttons
# ---------------------------------------------------------------------------
class MyDockableWidget(QDockWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setWindowTitle("Lines to Flights Controls")

        # Main container
        main_widget = QWidget()
        self.setWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # After creating main_layout in __init__:
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(5)

        # Row 1: Exit, Undo, Save
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(2)
        self.btn_exit = QPushButton("Exit\n❌")
        self.btn_undo = QPushButton("Undo\n🔄")
        self.btn_save = QPushButton("Save\n✅")
        self.btn_exit.setStyleSheet("QPushButton { background-color: red; color: white; }")
        self.btn_undo.setStyleSheet("QPushButton { background-color: blue; color: white; }")
        self.btn_save.setStyleSheet("QPushButton { background-color: green; color: white; }")
        row1_layout.addWidget(self.btn_exit)
        row1_layout.addWidget(self.btn_undo)
        row1_layout.addWidget(self.btn_save)
        main_layout.addLayout(row1_layout)

        # Row 2: Previous strip, Next strip
        row2_layout = QHBoxLayout()
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(2)
        self.btn_prev_strip = QPushButton("Previous strip\n⏮️☰")
        self.btn_next_strip = QPushButton("Next strip\n☰⏭️")
        row2_layout.addWidget(self.btn_prev_strip)
        row2_layout.addWidget(self.btn_next_strip)
        main_layout.addLayout(row2_layout)

        # Row 3: Radio buttons for mode selection
        row3_layout = QHBoxLayout()
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(2)
        self.radio_edit_lines = QRadioButton("Edit lines per flight\n●─●🛩️")
        self.radio_edit_flights = QRadioButton("Edit flights per TOF\n🛩️🅷")
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.radio_edit_lines)
        self.radio_group.addButton(self.radio_edit_flights)
        self.radio_edit_lines.setChecked(True)
        row3_layout.addWidget(self.radio_edit_lines)
        row3_layout.addWidget(self.radio_edit_flights)
        main_layout.addLayout(row3_layout)

        # Mode-specific containers
        self.lines_container = QWidget()
        self.flights_container = QWidget()

        # Prevent the containers from expanding vertically
        self.lines_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.flights_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Set tight layout for lines container
        lines_layout = QVBoxLayout()
        lines_layout.setContentsMargins(2, 2, 2, 2)
        lines_layout.setSpacing(2)
        self.lines_container.setLayout(lines_layout)

        # Set tight layout for flights container
        flights_layout = QVBoxLayout()
        flights_layout.setContentsMargins(2, 2, 2, 2)
        flights_layout.setSpacing(2)
        self.flights_container.setLayout(flights_layout)

        # Add the containers to the main layout with alignment to the top
        main_layout.addWidget(self.lines_container, alignment=Qt.AlignTop)
        main_layout.addWidget(self.flights_container, alignment=Qt.AlignTop)

        # LINES mode controls
        row4_layout = QHBoxLayout()
        self.btn_give_left = QPushButton("Give Line to Left\n 🢀🎁●─● ")
        self.btn_give_right = QPushButton("Give Line to Right\n●─●🎁🢂 ")
        row4_layout.addWidget(self.btn_give_left)
        row4_layout.addWidget(self.btn_give_right)
        lines_layout.addLayout(row4_layout)

        row5_layout = QHBoxLayout()
        self.btn_take_left = QPushButton("Take Line from Left\n 🢀🫴●─●")
        self.btn_take_right = QPushButton("Take Line from Right\n ●─●🫴🢂 ")
        row5_layout.addWidget(self.btn_take_left)
        row5_layout.addWidget(self.btn_take_right)
        lines_layout.addLayout(row5_layout)

        row6_layout = QHBoxLayout()
        self.btn_flip_direction = QPushButton("Flip line direction\n🔄 ●─● 🔄")
        row6_layout.addWidget(self.btn_flip_direction)
        lines_layout.addLayout(row6_layout)

        # FLIGHTS mode controls
        row4_flights_layout = QHBoxLayout()
        self.btn_give_flight_left = QPushButton("Give Flight to Left\n 🢀🎁🛩️ ")
        self.btn_give_flight_right = QPushButton("Give Flight to Right\n🛩️🎁🢂 ")
        row4_flights_layout.addWidget(self.btn_give_flight_left)
        row4_flights_layout.addWidget(self.btn_give_flight_right)
        flights_layout.addLayout(row4_flights_layout)

        row5_flights_layout = QHBoxLayout()
        self.btn_take_flight_left = QPushButton("Take Flight from Left\n 🢀🫴🛩️")
        self.btn_take_flight_right = QPushButton("Take Flight from Right\n 🛩️🫴🢂 ")
        row5_flights_layout.addWidget(self.btn_take_flight_left)
        row5_flights_layout.addWidget(self.btn_take_flight_right)
        flights_layout.addLayout(row5_flights_layout)

        row6_flights_layout = QHBoxLayout()
        self.btn_flip_flight_direction = QPushButton("Flip line direction per TOF\n🔄 🛩️ 🔄")
        row6_flights_layout.addWidget(self.btn_flip_flight_direction)
        flights_layout.addLayout(row6_flights_layout)

        # Connect radio button toggling to update visibility of mode containers.
        self.radio_edit_lines.toggled.connect(self.updateVisibility)
        self.radio_edit_flights.toggled.connect(self.updateVisibility)
        self.updateVisibility()

        # A reference to the map tool (to be set externally)
        self.mapTool = None

        # Connect the exit button so that closing the dock widget also deactivates the map tool.
        self.btn_exit.clicked.connect(self.exitApplication)

    def updateVisibility(self):
        """Toggle visibility of the mode-specific containers."""
        if self.radio_edit_lines.isChecked():
            self.flights_container.setVisible(False)
            self.lines_container.setVisible(True)
        else:
            self.lines_container.setVisible(False)
            self.flights_container.setVisible(True)

    def exitApplication(self):
        """Exit by deactivating the map tool and closing the dock widget."""
        if self.mapTool:
            self.mapTool.deactivate()
        self.close()

    def closeEvent(self, event):
        """Ensure that if the dock widget is closed, the map tool is also deactivated."""
        if self.mapTool:
            self.mapTool.deactivate()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Map Tool for Line Drawing (Without its own buttons)
# ---------------------------------------------------------------------------
class LineDrawingTool(QgsMapTool):
    def __init__(self, canvas, dock_widget=None):
        super().__init__(canvas)
        self.canvas = canvas
        # Keep a reference to the controlling dock widget.
        self.dock_widget = dock_widget

        # Set up rubber bands for drawing lines.
        self.rubberBands = []
        self.lineRubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.lineRubberBand.setColor(QColor(255, 0, 0))  # Red
        self.lineRubberBand.setWidth(2)
        self.rubberBands.append((self.lineRubberBand, QgsWkbTypes.LineGeometry))

    def clearRubberBands(self):
        """Clear all drawing rubber bands."""
        for rb, geom_type in self.rubberBands:
            rb.hide()
            rb.reset(geom_type)

    def deactivate(self):
        """
        When deactivated, clear drawings, unset the map tool,
        and close the controlling dock widget.
        """
        self.clearRubberBands()
        self.canvas.unsetMapTool(self)
        if self.dock_widget:
            self.dock_widget.close()
        super().deactivate()

    def display_Flight(self, flight):
        """
        Display a flight's line using its coordinates. Creates a black outline
        and a colored line (using flight.color) for better visibility.
        """
        import numpy as np
        coords = np.array(flight.utm_fly_list)
        points = list(map(QgsPointXY, coords[:, 0], coords[:, 1]))
        geom = QgsGeometry.fromPolylineXY(points)

        # Create black outline rubberband (thicker)
        outline_rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        outline_rb.setColor(QColor(0, 0, 0))  # Black outline
        outline_rb.setWidth(4)  # Slightly thicker for outline
        outline_rb.setToGeometry(geom, self.canvas.mapSettings().destinationCrs())
        outline_rb.show()

        # Create colored rubberband (on top of the outline)
        # Ensure flight.color is in proper hex format
        color_str = flight.color if flight.color.startswith("#") else "#" + flight.color
        color_rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        color_rb.setColor(QColor(color_str))
        color_rb.setWidth(2)  # Thinner line on top
        color_rb.setToGeometry(geom, self.canvas.mapSettings().destinationCrs())
        color_rb.show()

        # Track both rubber bands for later removal
        self.rubberBands.append((outline_rb, QgsWkbTypes.LineGeometry))
        self.rubberBands.append((color_rb, QgsWkbTypes.LineGeometry))
        return (outline_rb, color_rb)


# ---------------------------------------------------------------------------
# Setup Function to Initialize and Link Both Components
# ---------------------------------------------------------------------------
def initialize_combined_tool(canvas, iface):
    """
    Sets up the dock widget and map tool, links them together,
    and adds the dock widget to the QGIS interface.
    """
    dock_widget = MyDockableWidget(canvas)
    map_tool = LineDrawingTool(canvas, dock_widget=dock_widget)

    # Link the dock widget to the map tool.
    dock_widget.mapTool = map_tool

    # Example connection: Undo button clears the rubber bands.
    dock_widget.btn_undo.clicked.connect(map_tool.clearRubberBands)

    iface.addDockWidget(Qt.RightDockWidgetArea, dock_widget)
    canvas.setMapTool(map_tool)

    return dock_widget, map_tool


def run_qgis_gui(iface, pickle_obj):
    global current_dock_widget, current_map_tool

    if current_dock_widget is not None:
        current_dock_widget.close()
        current_dock_widget = None
        current_map_tool = None

    flights = pickle_obj.flight_list

    canvas = iface.mapCanvas()
    current_dock_widget, current_map_tool = initialize_combined_tool(canvas, iface)

    for flight in flights:
        flight.utm_fly_list
        current_map_tool.display_Flight(flight)

    return current_dock_widget, current_map_tool