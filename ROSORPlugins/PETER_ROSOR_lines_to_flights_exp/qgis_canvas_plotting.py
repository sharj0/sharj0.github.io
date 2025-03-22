from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsGeometry, QgsPointXY
from qgis.PyQt.QtWidgets import QPushButton
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

class LineDrawingTool(QgsMapTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

        # Create a list to store rubber bands.
        # Store tuples of (rubberBand, geometryType)
        self.rubberBands = []

        # Create a rubber band for a line geometry.
        self.lineRubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.lineRubberBand.setColor(QColor(255, 0, 0))  # Red color
        self.lineRubberBand.setWidth(2)
        self.rubberBands.append((self.lineRubberBand, QgsWkbTypes.LineGeometry))

        # Create a Clear button at the top left of the canvas.
        self.clearButton = self._make_button("Clear", (10, 10), self.clearRubberBands, bg="#444")
        # Create an Exit button to the right of the Clear button.
        self.exitButton = self._make_button("Exit", (90, 10), self.exitTool, bg="red")

    def _make_button(self, text, pos, callback, bg="#555"):
        """
        Create a styled QPushButton on the canvas.
        """
        btn = QPushButton(text, self.canvas)
        btn.setStyleSheet(f"background-color: {bg}; color: white; font-weight: bold;")
        btn.setFixedSize(70, 30)
        btn.move(*pos)
        btn.clicked.connect(callback)
        btn.show()  # Ensure the button is visible
        return btn

    def clearRubberBands(self):
        """
        Hide and reset all rubber bands managed by this tool.
        """
        for rb, geom_type in self.rubberBands:
            rb.hide()
            rb.reset(geom_type)

    def deactivate(self):
        """
        When the tool is deactivated, clean up the rubber bands, hide the buttons,
        and unset the map tool.
        """
        self.clearRubberBands()
        self.clearButton.hide()
        self.exitButton.hide()
        self.canvas.unsetMapTool(self)
        super().deactivate()

    def exitTool(self):
        """
        Exiting the tool gracefully.
        """
        self.deactivate()

    def setLineFromCoordinates(self, coords):
        """
        Set the line rubber band from a numpy array of coordinates.
        Expects coords to be a numpy array of shape (n, 2) where each row is [x, y].
        """
        # Create a list of QgsPointXY objects from the numpy array.
        points = list(map(QgsPointXY, coords[:, 0], coords[:, 1]))
        # Create a polyline geometry from the list of points.
        geom = QgsGeometry.fromPolylineXY(points)
        # Set the geometry of the rubber band using the canvas's destination CRS.
        self.lineRubberBand.setToGeometry(geom, self.canvas.mapSettings().destinationCrs())
        self.lineRubberBand.show()
