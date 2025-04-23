# qgis_gui.py


from qgis.core import QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QButtonGroup, QDockWidget, QHBoxLayout, QPushButton,
    QRadioButton, QSizePolicy, QVBoxLayout, QWidget
)
from .Plugin_Canvas_Gui_Class import PluginCanvasGui
from . import plugin_tools

# Global variables to track the current instances.
current_dock_widget = None
plugin_canvas_gui = None


# ---------------------------------------------------------------------------
# Dock Widget with Buttons
# ---------------------------------------------------------------------------
class MyDockableWidget(QDockWidget):
    def __init__(self, canvas, survey_area, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.survey_area = survey_area  # Save the survey area for use in updateVisibility
        self.mapTool = None
        self.setWindowTitle("Lines to Flights Controls")

        # Main container
        main_widget = QWidget()
        self.setWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
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

        # Removed row for Previous strip, Next strip

        # Row 3: Radio buttons for mode selection
        row3_layout = QHBoxLayout()
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(2)
        self.radio_edit_within_flights = QRadioButton("Edit lines per flight\n●─●🛩️")
        self.radio_edit_within_TOFs = QRadioButton("Edit flights per TOF\n🛩️🅷")
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.radio_edit_within_flights)
        self.radio_group.addButton(self.radio_edit_within_TOFs)
        self.radio_edit_within_flights.setChecked(True)
        row3_layout.addWidget(self.radio_edit_within_flights)
        row3_layout.addWidget(self.radio_edit_within_TOFs)
        main_layout.addLayout(row3_layout)

        # Mode-specific containers
        self.lines_container = QWidget()
        self.flights_container = QWidget()
        self.lines_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.flights_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Layout for lines container
        lines_layout = QVBoxLayout()
        lines_layout.setContentsMargins(2, 2, 2, 2)
        lines_layout.setSpacing(2)
        self.lines_container.setLayout(lines_layout)

        # Layout for flights container
        flights_layout = QVBoxLayout()
        flights_layout.setContentsMargins(2, 2, 2, 2)
        flights_layout.setSpacing(2)
        self.flights_container.setLayout(flights_layout)

        main_layout.addWidget(self.lines_container, alignment=Qt.AlignTop)
        main_layout.addWidget(self.flights_container, alignment=Qt.AlignTop)

        # LINES mode controls
        row4_layout = QHBoxLayout()
        self.btn_take_left = QPushButton("Take Line from Left\n 🢀🫴●─●")
        self.btn_take_right = QPushButton("Take Line from Right\n ●─●🫴🢂 ")
        row4_layout.addWidget(self.btn_take_left)
        row4_layout.addWidget(self.btn_take_right)
        lines_layout.addLayout(row4_layout)

        row5_layout = QHBoxLayout()
        self.btn_give_left = QPushButton("Give Line to Left\n 🢀🎁●─● ")
        self.btn_give_right = QPushButton("Give Line to Right\n●─●🎁🢂 ")
        row5_layout.addWidget(self.btn_give_left)
        row5_layout.addWidget(self.btn_give_right)
        lines_layout.addLayout(row5_layout)

        # Removed row for Flip line direction in LINES mode

        # FLIGHTS mode controls (kept for completeness)
        row4_flights_layout = QHBoxLayout()
        self.btn_take_flight_left = QPushButton("Take Flight from Left\n 🢀🫴🛩️")
        self.btn_take_flight_right = QPushButton("Take Flight from Right\n 🛩️🫴🢂 ")
        row4_flights_layout.addWidget(self.btn_take_flight_left)
        row4_flights_layout.addWidget(self.btn_take_flight_right)
        flights_layout.addLayout(row4_flights_layout)

        row5_flights_layout = QHBoxLayout()
        self.btn_give_flight_left = QPushButton("Give Flight to Left\n 🢀🎁🛩️ ")
        self.btn_give_flight_right = QPushButton("Give Flight to Right\n🛩️🎁🢂 ")
        row5_flights_layout.addWidget(self.btn_give_flight_left)
        row5_flights_layout.addWidget(self.btn_give_flight_right)
        flights_layout.addLayout(row5_flights_layout)

        row6_layout = QHBoxLayout()
        self.btn_flip_direction = QPushButton("Flip line direction\n🔄 ●─● 🔄")
        row6_layout.addWidget(self.btn_flip_direction)
        lines_layout.addLayout(row6_layout)
        # Removed row for Flip line direction in FLIGHTS mode

        self.radio_edit_within_flights.toggled.connect(self.updateVisibility)
        self.radio_edit_within_TOFs.toggled.connect(self.updateVisibility)
        self.updateVisibility()  # Initialize display based on default selection

        self.btn_exit.clicked.connect(self.exitApplication)

    def linkActionButtons(self):
        """Connect the action buttons to the map tool's action executor."""
        if self.mapTool:
            self.btn_give_left.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("give_left"))
            self.btn_give_right.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("give_right"))
            self.btn_take_left.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("take_left"))
            self.btn_take_right.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("take_right"))

            self.btn_flip_direction.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("flip_lines"))

            self.btn_give_flight_left.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("give_left"))
            self.btn_give_flight_right.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("give_right"))
            self.btn_take_flight_left.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("take_left"))
            self.btn_take_flight_right.clicked.connect(lambda: self.mapTool.execute_action_on_selected_node("take_right"))

    def updateVisibility(self):
        # Only clear the display if mapTool is set.
        if self.mapTool is not None:
            self.mapTool.clear()

        if self.radio_edit_within_flights.isChecked():
            self.flights_container.setVisible(False)
            self.lines_container.setVisible(True)
            if self.mapTool is not None:
                self.mapTool.display_level("Flight")
        else:
            self.lines_container.setVisible(False)
            self.flights_container.setVisible(True)
            if self.mapTool is not None:
                self.mapTool.display_level("Quadrant")
                #self.mapTool.display_level("TOFAssignment")

    def exitApplication(self):
        if self.mapTool:
            self.mapTool.deactivate()
        self.close()

    def closeEvent(self, event):
        if self.mapTool:
            self.mapTool.deactivate()
        super().closeEvent(event)


def run_qgis_gui(iface, survey_area):
    global current_dock_widget, plugin_canvas_gui

    # Check survey area CRS versus project CRS.
    target_epsg = survey_area.global_crs_target['target_crs_epsg_int']
    survey_crs = QgsCoordinateReferenceSystem("EPSG:" + str(target_epsg))
    project_crs = QgsProject.instance().crs()

    if project_crs.authid() != survey_crs.authid():
        message = (f"CRS mismatch: Project CRS is {project_crs.authid()}, "
                   f"but survey area CRS is {survey_crs.authid()}. \n\nSwitching project CRS "
                   f"to {survey_crs.authid()}!")
        plugin_tools.show_information(message)
        QgsProject.instance().setCrs(survey_crs)
        iface.mapCanvas().setDestinationCrs(survey_crs)
        iface.mapCanvas().refresh()

    if current_dock_widget is not None:
        current_dock_widget.close()
        current_dock_widget = None
        plugin_canvas_gui = None

    canvas = iface.mapCanvas()
    current_dock_widget = MyDockableWidget(canvas, survey_area)
    plugin_canvas_gui = PluginCanvasGui(canvas, survey_area, current_dock_widget)
    current_dock_widget.mapTool = plugin_canvas_gui

    current_dock_widget.btn_undo.clicked.connect(plugin_canvas_gui.undo)
    current_dock_widget.btn_save.clicked.connect(plugin_canvas_gui.save)

    iface.addDockWidget(Qt.RightDockWidgetArea, current_dock_widget)
    canvas.setMapTool(plugin_canvas_gui)

    # Now that mapTool is assigned, update the display and link the node action buttons.
    current_dock_widget.updateVisibility()
    current_dock_widget.linkActionButtons()

    return current_dock_widget, plugin_canvas_gui


