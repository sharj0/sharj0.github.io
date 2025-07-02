# qgis_gui.py


from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle
from qgis.PyQt.QtCore import Qt, QEvent
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
        #row1_layout.addWidget(self.btn_undo)
        row1_layout.addWidget(self.btn_save)
        main_layout.addLayout(row1_layout)

        # Removed row for Previous strip, Next strip

        # Row 3: Radio buttons for mode selection
        row3_layout = QHBoxLayout()
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(2)
        self.radio_edit_within_flights = QRadioButton("Edit lines per flight\n●─●🛩️")
        self.radio_edit_within_TOFs = QRadioButton("Edit flights per TOF\n🛩️🅷")
        self.radio_view_survey_area = QRadioButton("View survey area\n🗺️")
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.radio_edit_within_flights)
        self.radio_group.addButton(self.radio_edit_within_TOFs)
        self.radio_group.addButton(self.radio_view_survey_area)
        self.radio_edit_within_flights.setChecked(True)
        row3_layout.addWidget(self.radio_edit_within_flights)
        row3_layout.addWidget(self.radio_edit_within_TOFs)
        row3_layout.addWidget(self.radio_view_survey_area)
        main_layout.addLayout(row3_layout)

        # Mode-specific containers
        self.lines_container = QWidget()
        self.flights_container = QWidget()
        self.survey_container = QWidget()
        self.lines_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.flights_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.survey_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

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

        # Layout for survey container
        survey_layout = QVBoxLayout()
        survey_layout.setContentsMargins(2, 2, 2, 2)
        survey_layout.setSpacing(2)
        self.survey_container.setLayout(survey_layout)

        main_layout.addWidget(self.lines_container, alignment=Qt.AlignTop)
        main_layout.addWidget(self.flights_container, alignment=Qt.AlignTop)
        main_layout.addWidget(self.survey_container, alignment=Qt.AlignTop)

        # LINES mode controls
        row4_layout = QHBoxLayout()
        self.btn_take_left = QPushButton("Take Line from Left\n 🢀🫴●─●")
        self.btn_take_right = QPushButton("Take Line from Right\n ●─●🫴🢂 ")
        for btn in (self.btn_take_left, self.btn_take_right):
            btn.setMouseTracking(True)
            btn.installEventFilter(self)
        row4_layout.addWidget(self.btn_take_left)
        row4_layout.addWidget(self.btn_take_right)
        lines_layout.addLayout(row4_layout)

        row5_layout = QHBoxLayout()
        self.btn_give_left = QPushButton("Give Line to Left\n 🢀🎁●─● ")
        self.btn_give_right = QPushButton("Give Line to Right\n●─●🎁🢂 ")
        for btn in (self.btn_give_left, self.btn_give_right):
            btn.setMouseTracking(True)
            btn.installEventFilter(self)
        row5_layout.addWidget(self.btn_give_left)
        row5_layout.addWidget(self.btn_give_right)
        lines_layout.addLayout(row5_layout)

        row6_layout = QHBoxLayout()
        self.btn_take_left_cascade = QPushButton("Take Line from Left Cascade\n🢀")
        self.btn_take_right_cascade = QPushButton("Take Line from Right Cascade\n🢂 ")
        for btn in (self.btn_take_left_cascade, self.btn_take_right_cascade):
            btn.setMouseTracking(True)
            btn.installEventFilter(self)
        row6_layout.addWidget(self.btn_take_left_cascade)
        row6_layout.addWidget(self.btn_take_right_cascade)
        lines_layout.addLayout(row6_layout)

        # Removed row for Flip line direction in LINES mode

        # FLIGHTS mode controls (kept for completeness)
        row4_flights_layout = QHBoxLayout()
        self.btn_take_flight_left = QPushButton("Take Flight from Left\n 🢀🫴🛩️")
        self.btn_take_flight_right = QPushButton("Take Flight from Right\n 🛩️🫴🢂 ")
        for btn in (self.btn_take_flight_right, self.btn_take_flight_left):
            btn.setMouseTracking(True)
            btn.installEventFilter(self)
        row4_flights_layout.addWidget(self.btn_take_flight_left)
        row4_flights_layout.addWidget(self.btn_take_flight_right)
        flights_layout.addLayout(row4_flights_layout)

        row5_flights_layout = QHBoxLayout()
        self.btn_give_flight_left = QPushButton("Give Flight to Left\n 🢀🎁🛩️ ")
        self.btn_give_flight_right = QPushButton("Give Flight to Right\n🛩️🎁🢂 ")
        for btn in (self.btn_give_flight_right, self.btn_give_flight_left):
            btn.setMouseTracking(True)
            btn.installEventFilter(self)
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
        self.radio_view_survey_area.toggled.connect(self.viewSurveyArea)
        self.updateVisibility()  # Initialize display based on default selection

        self.btn_exit.clicked.connect(self.exitApplication)

    def eventFilter(self, obj, event):
        # 1) Handle canvas-leave
        if obj == self.canvas and event.type() == QEvent.Leave:
            self.mapTool.remove_highlight()
            return True

        # 2) Catch hover-enter on our two buttons
        if event.type() == QEvent.Enter:
            if obj is self.btn_take_left:
                self.mapTool.preview_target_node("take_left")
                return True
            if obj is self.btn_take_right:
                self.mapTool.preview_target_node("take_right")
                return True
            if obj is self.btn_give_left:
                self.mapTool.preview_target_node("give_left")
                return True
            if obj is self.btn_give_right:
                self.mapTool.preview_target_node("give_right")
                return True
            if obj is self.btn_take_flight_left:
                self.mapTool.preview_target_node("take_left")
                return True
            if obj is self.btn_take_flight_right:
                self.mapTool.preview_target_node("take_right")
                return True
            if obj is self.btn_give_flight_left:
                self.mapTool.preview_target_node("give_left")
                return True
            if obj is self.btn_give_flight_right:
                self.mapTool.preview_target_node("give_right")
                return True
            if obj is self.btn_take_left_cascade:
                self.mapTool.preview_target_node("take_left_cascade")
                return True
            if obj is self.btn_take_right_cascade:
                self.mapTool.preview_target_node("take_right_cascade")
                return True

        # 3) Catch hover-leave on those buttons
        if event.type() == QEvent.Leave:
            if obj in (
                self.btn_take_left, self.btn_take_right, self.btn_give_left, self.btn_give_right,
                self.btn_take_flight_left, self.btn_take_flight_right, self.btn_give_flight_left, 
                self.btn_give_flight_right,
                self.btn_take_left_cascade, self.btn_take_right_cascade
            ):
                self.mapTool.remove_highlight()
                return True

        # 4) Fallback to default
        return super().eventFilter(obj, event)

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

            self.btn_take_left_cascade.clicked.connect(
                lambda: self.mapTool.execute_action_on_selected_node("take_left_cascade")
            )
            self.btn_take_right_cascade.clicked.connect(
                lambda: self.mapTool.execute_action_on_selected_node("take_right_cascade")
            )

    def updateVisibility(self):
        if self.mapTool is not None:
            self.mapTool.clear()
            self.mapTool.remove_selection()
            self.mapTool.remove_highlight()

        if self.radio_edit_within_flights.isChecked():
            self.flights_container.setVisible(False)
            self.lines_container.setVisible(True)
            self.survey_container.setVisible(False)
            self.survey_area.restore_colors()
            if self.mapTool is not None:
                self.mapTool.display_level("Flight")

        elif self.radio_edit_within_TOFs.isChecked():
            self.lines_container.setVisible(False)
            self.flights_container.setVisible(True)
            self.survey_container.setVisible(False)
            self.survey_area.color_by_tof()
            if self.mapTool is not None:
                self.mapTool.display_level("TOFAssignment")

        elif self.radio_view_survey_area.isChecked():
            self.lines_container.setVisible(False)
            self.flights_container.setVisible(False)
            self.survey_container.setVisible(True)
            self.survey_area.restore_colors()
            if self.mapTool is not None:
                self.mapTool.display_level("SurveyArea")
            self.zoomToSurveyExtent()
    
    def viewSurveyArea(self):
        if self.radio_view_survey_area.isChecked():
            self.updateVisibility()

    def zoomToSurveyExtent(self):
        lines = self.survey_area.line_list
        if not lines:
            print("No lines found in survey area.")
            return

        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')

        for line in lines:
            for pt in [line.start.xy, line.end.xy]:
                x, y = pt
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

        # Slight padding
        padding = 10
        extent = QgsRectangle(min_x - padding, min_y - padding, max_x + padding, max_y + padding)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

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

    ''' \\\ TEST /// '''
    flight = survey_area.flight_list[18]
    print(flight)


    ''' /// TEST \\\ '''

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


