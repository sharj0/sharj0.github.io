import os
from osgeo import gdal
import numpy as np
import math
from qgis.core import QgsWkbTypes
from qgis.core import QgsGeometry, QgsRectangle

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsWkbTypes
)
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtWidgets import QPushButton
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from qgis.utils import iface

# Your existing helpers:
from . import plugin_load_settings
from . import plugin_tools



DEBUG = True

def debug_print(msg):
    if DEBUG:
        print(msg)


################################################################################
# Safety check: Must be in QGIS Desktop
################################################################################
if QgsApplication.instance().platform() != 'desktop':
    plugin_tools.show_error("Must be running in QGIS Desktop.")
    raise Exception("Not running in QGIS Desktop. Aborting script.")


################################################################################
# check_if_layer_loaded
################################################################################
def check_if_layer_loaded(raster_path):
    debug_print("check_if_layer_loaded() called.")
    normalized_path = os.path.normpath(raster_path).lower()
    debug_print(f"Normalized path: {normalized_path}")

    for layer in QgsProject.instance().mapLayers().values():
        if os.path.normpath(layer.source()).lower() == normalized_path:
            debug_print("Raster is already loaded.")
            return layer

    # If not found, try to load it
    err_txt = f'Provided Input Geotiff Layer:\n{os.path.basename(raster_path)}\nis not loaded into QGIS.\nFull path:\n{raster_path}'
    plugin_tools.show_error(err_txt)
    raise ValueError(err_txt)
    return rlayer


################################################################################
# Convert map coords -> (row, col)
################################################################################
def world_to_pixel(x, y, geotransform):
    """Given map coords (x, y) and a GDAL geotransform, return (row, col)."""
    originX, pixelWidth, _, originY, _, pixelHeight = geotransform
    col = int((x - originX) / pixelWidth)
    row = int((originY - y) / abs(pixelHeight))
    return row, col


def get_line_pixels(row1, col1, row2, col2):
    """
    Return all (row, col) pixels along the line from (row1, col1) to (row2, col2)
    using only 4-connected moves (up, down, left, right). This function first computes
    the standard Bresenham (8-connected) line and then post-processes it so that any
    diagonal move is replaced by a horizontal move followed by a vertical move.
    """
    # --- First, compute the standard 8-connected Bresenham line ---
    points = []
    d_row = abs(row2 - row1)
    d_col = abs(col2 - col1)
    s_row = 1 if row2 > row1 else -1
    s_col = 1 if col2 > col1 else -1
    err = d_row - d_col

    r, c = row1, col1
    points.append((r, c))
    while (r, c) != (row2, col2):
        e2 = 2 * err
        if e2 > -d_col:
            err -= d_col
            r += s_row
        if e2 < d_row:
            err += d_row
            c += s_col
        points.append((r, c))

    # --- Now, post-process to force 4-connected moves ---
    new_points = [points[0]]
    for pt in points[1:]:
        prev = new_points[-1]
        dr = pt[0] - prev[0]
        dc = pt[1] - prev[1]
        # If both row and col change, it's a diagonal move.
        if abs(dr) == 1 and abs(dc) == 1:
            # Insert an intermediate pixel that moves horizontally first.
            intermediate = (prev[0], prev[1] + dc)
            new_points.append(intermediate)
        new_points.append(pt)
    return new_points


############################################################################
# Helpers for angle + side extension
############################################################################
def angle_between_pixels(r1, c1, r2, c2):
    """
    Return the angle in [0,180) degrees of the line (r1,c1)->(r2,c2).
    We'll treat row as 'y' and col as 'x', but remember row grows downward.
    """
    dx = c2 - c1
    dy = r2 - r1
    # atan2 is (y, x). This returns angle in radians in [-pi, pi).
    angle_radians = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_radians)  # [-180, 180)

    # We only want [0, 180).
    if angle_deg < 0:
        angle_deg += 180.0
    if angle_deg >= 180:
        # e.g. 180.0 exactly could happen with negative dx
        angle_deg -= 180.0

    return angle_deg


def round_angle_to_45(angle_deg):
    """
    Round angle to the nearest multiple of 45 from {0, 45, 90, 135}.
    If rounding hits 180, we treat that as 0.
    """
    # Step 1: normal rounding to nearest 45
    nearest_45 = round(angle_deg / 45.0) * 45
    # Because we only want [0, 135], if we got 180 => 0:
    if nearest_45 == 180:
        nearest_45 = 0
    return nearest_45


def perpendicular_direction(angle_rounded):
    """
    Return the (dr, dc) that is perpendicular to the line
    whose angle is angle_rounded in {0,45,90,135}.

    - If the main line is horizontal (0 deg), perpendicular = vertical => (±1,0).
    - If the main line is vertical (90 deg), perpendicular = horizontal => (0,±1).
    - If the main line is 45, perpendicular = 135 => (±1, ∓1).
    - If the main line is 135, perpendicular = 45 => (±1, ±1).

    We'll just pick the "forward" direction. We'll call the negative direction
    separately when extending in both directions.
    """
    if angle_rounded == 0:
        # line is horizontal => perpendicular is vertical => (dr,dc) = (1,0)
        return (1, 0)
    elif angle_rounded == 90:
        # line is vertical => perpendicular is horizontal => (0,1)
        return (0, 1)
    elif angle_rounded == 45:
        # line is 45 => slope= +1 => perpendicular is slope= -1 => (1, -1)
        return (1, -1)
    elif angle_rounded == 135:
        # line is 135 => slope= -1 => perpendicular is slope= +1 => (1, 1)
        return (1, 1)
    # default fallback
    return (0, 0)


class RasterInterpolationMapTool(QgsMapTool):
    """
    Map tool that:
    - Highlights hovered pixel in a rubber band.
    - Waits for two clicks to interpolate between them.
    - Writes changes via QGIS's raster provider (edit blocks).
    - Supports Undo of the last line.
    - Has "Undo" & "Exit" buttons on the map canvas.
    """

    # In RasterInterpolationMapTool class:

    # In the RasterInterpolationMapTool class:
    def __init__(self, canvas, raster_layer, geotransform, multiply_mode, addition_mode, assignment_mode,
                 blocking_value, do_extend_perpendicularly):
        super().__init__(canvas)
        self.canvas = canvas
        self.rlayer = raster_layer
        self.geotransform = geotransform
        self.multiply_mode = multiply_mode
        self.addition_mode = addition_mode
        self.assignment_mode = assignment_mode
        self.blocking_value = blocking_value
        self.do_extend_perpendicularly = do_extend_perpendicularly
        self.provider = self.rlayer.dataProvider()
        self.first_click_info = None  # (row, col, old_val)
        self.last_line_pixel_values = []

        # Setup rubber bands and buttons (unchanged) ...
        self.hover_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.hover_rubber.setWidth(2)
        self.hover_rubber.hide()
        self.first_click_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.first_click_rubber.setWidth(2)
        self.first_click_rubber.setColor(QColor(255, 0, 0, 150))
        self.first_click_rubber.setFillColor(QColor(255, 0, 0, 60))
        self.first_click_rubber.hide()
        self.undo_button = self._make_button("Undo", (10, 10), self.on_undo_clicked, bg="#444")
        self.exit_button = self._make_button("Exit", (90, 10), self.exitTool, bg="red")
        QgsProject.instance().layersWillBeRemoved.connect(self.onLayerRemoved)

    def activate(self):
        super().activate()
        self.canvas.setCursor(Qt.CrossCursor)
        self.undo_button.show()
        self.exit_button.show()
        debug_print("RasterInterpolationMapTool activated.")

    def deactivate(self):
        super().deactivate()
        self.canvas.unsetCursor()
        self.hover_rubber.hide()
        self.hover_rubber.reset(QgsWkbTypes.PolygonGeometry)
        # Hide and reset the persistent red highlight.
        self.first_click_rubber.hide()
        self.first_click_rubber.reset(QgsWkbTypes.PolygonGeometry)
        self.undo_button.hide()
        self.exit_button.hide()
        debug_print("RasterInterpolationMapTool deactivated.")

    def canvasMoveEvent(self, event):
        """
        Highlight the pixel under the mouse.
        """
        if not self.provider.isValid():
            return

        # Convert to map coords
        point = self.toMapCoordinates(event.pos())
        layer_crs = self.rlayer.crs()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if layer_crs != canvas_crs:
            xform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            point = xform.transform(point)

        row, col = world_to_pixel(point.x(), point.y(), self.geotransform)

        # Choose highlight color
        if self.first_click_info is None:
            self.hover_rubber.setColor(QColor(255, 0, 0, 150))
            self.hover_rubber.setFillColor(QColor(255, 0, 0, 60))
        else:
            self.hover_rubber.setColor(QColor(0, 0, 255, 150))
            self.hover_rubber.setFillColor(QColor(0, 0, 255, 60))

        rect_geom = self.pixel_as_map_rect(row, col)
        if rect_geom:

            self.hover_rubber.reset(QgsWkbTypes.PolygonGeometry)
            self.hover_rubber.setToGeometry(rect_geom, layer_crs)
            self.hover_rubber.show()
        else:
            self.hover_rubber.hide()

    def canvasReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.provider.isValid():
            return

        # Convert screen coords -> layer coords.
        point = self.toMapCoordinates(event.pos())
        layer_crs = self.rlayer.crs()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if layer_crs != canvas_crs:
            xform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            point = xform.transform(point)

        row, col = world_to_pixel(point.x(), point.y(), self.geotransform)
        current_val = self.get_pixel_value(row, col)

        if self.first_click_info is None:
            # First click: store the location and value and show persistent red highlight.
            self.first_click_info = (row, col, current_val)
            debug_print(f"First click at row={row}, col={col}, value={current_val}")
            rect_geom = self.pixel_as_map_rect(row, col)
            if rect_geom:
                self.first_click_rubber.reset(QgsWkbTypes.PolygonGeometry)
                self.first_click_rubber.setToGeometry(rect_geom, layer_crs)
                self.first_click_rubber.show()
            return
        else:
            # Second click: process interpolation and apply updates.
            (r1, c1, v1) = self.first_click_info
            (r2, c2, v2) = (row, col, current_val)
            debug_print(f"Second click at row={r2}, col={c2}, value={v2}")

            updated_rows, updated_cols, updated_vals = self.compute_updated_pixels(r1, c1, v1, r2, c2, v2)
            self.apply_updates(updated_rows, updated_cols, updated_vals)

            # Hide the persistent red highlight and reset for next operation.
            self.first_click_rubber.hide()
            self.first_click_info = None

    def compute_updated_pixels(self, r1, c1, v1, r2, c2, v2):
        """
        Compute the updated pixel coordinates and interpolated values along the line.
        If self.do_extend_perpendicularly is True, also extend perpendicularly until a blocking_value
        is encountered; otherwise, only the straight-line interpolation is returned.
        """
        line_pixels = np.array(get_line_pixels(r1, c1, r2, c2))
        n = len(line_pixels)
        fractions = np.linspace(0, 1, n)
        new_vals_line = v1 + fractions * (v2 - v1)

        updated_rows = line_pixels[:, 0].tolist()
        updated_cols = line_pixels[:, 1].tolist()
        updated_vals = new_vals_line.tolist()

        if self.do_extend_perpendicularly:
            raw_angle = angle_between_pixels(r1, c1, r2, c2)
            rounded_angle = round_angle_to_45(raw_angle)
            (pdr, pdc) = perpendicular_direction(rounded_angle)
            for idx in range(n):
                base_r = line_pixels[idx, 0]
                base_c = line_pixels[idx, 1]
                val_to_extend = new_vals_line[idx]

                # Extend in the positive perpendicular direction.
                rX, cX = base_r + pdr, base_c + pdc
                while 0 <= rX < self.rlayer.height() and 0 <= cX < self.rlayer.width():
                    if self.get_pixel_value(rX, cX) == self.blocking_value:
                        break
                    updated_rows.append(rX)
                    updated_cols.append(cX)
                    updated_vals.append(val_to_extend)
                    rX += pdr
                    cX += pdc

                # Extend in the negative perpendicular direction.
                rX, cX = base_r - pdr, base_c - pdc
                while 0 <= rX < self.rlayer.height() and 0 <= cX < self.rlayer.width():
                    if self.get_pixel_value(rX, cX) == self.blocking_value:
                        break
                    updated_rows.append(rX)
                    updated_cols.append(cX)
                    updated_vals.append(val_to_extend)
                    rX -= pdr
                    cX -= pdc

        return np.array(updated_rows), np.array(updated_cols), np.array(updated_vals, dtype=np.float32)

    def apply_updates(self, updated_rows, updated_cols, updated_vals):
        """
        Applies the computed updates to the raster layer using the selected mode,
        regardless of whether perpendicular extension is enabled.
        """
        min_row = int(updated_rows.min())
        max_row = int(updated_rows.max())
        min_col = int(updated_cols.min())
        max_col = int(updated_cols.max())
        block_height = max_row - min_row + 1
        block_width = max_col - min_col + 1

        rel_rows = updated_rows - min_row
        rel_cols = updated_cols - min_col

        dataset = gdal.Open(self.rlayer.source(), gdal.GA_Update)
        band = dataset.GetRasterBand(1)

        undo_block = band.ReadAsArray(min_col, min_row, block_width, block_height).copy()
        self.last_block_info = (min_row, min_col, undo_block)
        block_array = undo_block.copy()

        if self.multiply_mode:
            block_array[rel_rows, rel_cols] = undo_block[rel_rows, rel_cols] * updated_vals
        elif self.addition_mode:
            block_array[rel_rows, rel_cols] = undo_block[rel_rows, rel_cols] + updated_vals
        elif self.assignment_mode:
            block_array[rel_rows, rel_cols] = updated_vals

        band.WriteArray(block_array, min_col, min_row)
        dataset.FlushCache()
        self.rlayer.reload()

    def on_undo_clicked(self):

        if not hasattr(self, 'last_block_info') or self.last_block_info is None:
            debug_print("No undo information available.")
            return

        min_row, min_col, undo_block = self.last_block_info

        dataset = gdal.Open(self.rlayer.source(), gdal.GA_Update)
        band = dataset.GetRasterBand(1)

        # Restore the old block in one vectorized write.
        band.WriteArray(undo_block, min_col, min_row)
        dataset.FlushCache()

        # Reload the layer to update the display.
        self.rlayer.reload()

        # Clear the undo info.
        self.last_block_info = None
        debug_print("Undo completed.")


    def exitTool(self):
        """
        Deactivate the tool and disconnect signals.
        """
        debug_print("Exiting RasterInterpolationMapTool...")
        self.deactivate()
        self.canvas.unsetMapTool(self)
        QgsProject.instance().layersWillBeRemoved.disconnect(self.onLayerRemoved)

    def onLayerRemoved(self, removed_ids):
        """
        If our layer is removed, exit the tool automatically.
        """
        if self.rlayer.id() in removed_ids:
            debug_print("Layer removed. Exiting tool.")
            self.exitTool()

    # --------------------------------------------------------------------------
    # Methods to read/write pixels via QGIS raster provider
    # --------------------------------------------------------------------------
    def get_pixel_value(self, row, col):
        """
        Reads a single pixel from the raster provider by requesting a 1x1 block.
        """
        # Build a 1×1 pixel rectangle in map coords
        left, top = self.upper_left_of_pixel(row, col)
        pixel_width = abs(self.geotransform[1])
        pixel_height = abs(self.geotransform[5])
        rect = QgsRectangle(left, top - pixel_height, left + pixel_width, top)

        block = self.provider.block(1, rect, 1, 1)  # band=1, extent=rect, 1x1
        if block is None:
            debug_print(f"block() returned None for (row={row}, col={col})")
            return 0.0

        val = block.value(0, 0)
        return val if val is not None else 0.0

    # --------------------------------------------------------------------------
    # Helper geometry methods
    # --------------------------------------------------------------------------
    def pixel_as_map_rect(self, row, col):
        """
        Return a small square (QgsGeometry) for the pixel in map coords.
        """

        try:
            left, top = self.upper_left_of_pixel(row, col)
            pixel_width = abs(self.geotransform[1])
            pixel_height = abs(self.geotransform[5])
            rect = QgsRectangle(left, top - pixel_height, left + pixel_width, top)
            return QgsGeometry.fromRect(rect)
        except Exception as e:
            debug_print(f"pixel_as_map_rect error: {e}")
            return None

    def upper_left_of_pixel(self, row, col):
        """
        Returns the (x, y) map coords of the *upper left* corner of pixel (row, col).
        geotransform = [originX, pixelWidth, 0, originY, 0, -pixelHeight].
        """
        originX, pixelWidth, _, originY, _, pixelHeight = self.geotransform
        x = originX + col * pixelWidth
        y = originY + row * pixelHeight  # pixelHeight is negative
        return (x, y)

    def keyPressEvent(self, event):
        """
        If user presses Escape, exit the tool.
        """
        if event.key() == Qt.Key_Escape:
            debug_print("ESC pressed, exiting tool.")
            self.exitTool()

    def _make_button(self, text, pos, callback, bg="#555"):
        """
        Helper to create a styled QPushButton on the canvas.
        """
        btn = QPushButton(text, self.canvas)
        btn.setStyleSheet(f"background-color: {bg}; color: white; font-weight: bold;")
        btn.setFixedSize(70, 30)
        btn.move(*pos)
        btn.clicked.connect(callback)
        return btn


def compute_geotransform(rlayer):
    """
    Compute geotransform directly from a QgsRasterLayer.
    Returns (originX, pixelWidth, 0, originY, 0, -pixelHeight).
    """
    extent = rlayer.extent()
    width = rlayer.width()
    height = rlayer.height()

    # Compute pixel size
    pixel_width = extent.width() / width
    pixel_height = extent.height() / height  # Normally negative

    return (
        extent.xMinimum(),  # originX (top-left X)
        pixel_width,  # pixelWidth
        0,  # rotation/skew (usually 0)
        extent.yMaximum(),  # originY (top-left Y)
        0,  # rotation/skew (usually 0)
        -pixel_height  # pixelHeight (negative)
    )


def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)
    raster_path = settings_dict['GeoTiff Layer']
    do_extend_perpendicularly = settings_dict["Extend perpendicularly"]
    blocking_value = float(settings_dict["Blocking Value"])  # NEW: get the blocking value from settings
    assignment_mode = settings_dict["Assignment"]
    addition_mode = settings_dict["Addition"]
    multiply_mode = settings_dict["Multiplication"]
    settings_dict = None

    rlayer = check_if_layer_loaded(raster_path)
    if not rlayer:
        plugin_tools.show_error("Could not load the specified raster layer.")
        return

    provider = rlayer.dataProvider()
    if not provider.isValid():
        debug_print("Provider is invalid, cannot edit raster.")
        return

    if provider.dataType(1) != 6:
        debug_print("Warning: the raster is NOT float32. Continuing anyway...")

    geotransform = compute_geotransform(rlayer)
    debug_print(f"Computed geotransform: {geotransform}")

    interpolation_tool = RasterInterpolationMapTool(
        iface.mapCanvas(),
        rlayer,
        geotransform,
        multiply_mode,
        addition_mode,
        assignment_mode,
        blocking_value,
        do_extend_perpendicularly,
    )
    iface.mapCanvas().setMapTool(interpolation_tool)


