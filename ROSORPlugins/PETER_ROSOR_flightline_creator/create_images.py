from pathlib import Path
from typing import Optional
import os

from qgis.PyQt.QtCore import QRectF
from qgis.PyQt.QtGui import QFont, QColor
from qgis.utils import iface
from qgis.core import (
    QgsProject,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsUnitTypes,
    QgsLayoutSize,
    QgsLayoutPoint,
    QgsLayoutExporter,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsLayoutItemPicture,
    QgsVectorLayer,
)

def create_print_layout(iface, layout_name, extent):

    project = QgsProject.instance()
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()

    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(297, 149, QgsUnitTypes.LayoutMillimeters))

    map = QgsLayoutItemMap(layout)
    map.attemptResize(QgsLayoutSize(297,149, QgsUnitTypes.LayoutMillimeters))

    # Add buffer to extent
    width  = extent.xMaximum() - extent.xMinimum()
    height = extent.yMaximum() - extent.yMinimum()
    buffer = max(width, height) * 0.2
    extent.grow(buffer)
    extent = adjust_extent_to_aspect_ratio(extent, 297, 149)

    map.setExtent(extent)
    map.refresh()
    layout.addLayoutItem(map)

    # North Arrow
    plugin_dir = os.path.dirname(__file__)
    arrow_path = os.path.join(plugin_dir, 'north_arrow.png')
    arrow = QgsLayoutItemPicture(layout)
    arrow.setPicturePath(arrow_path)

    arrow_size = QgsLayoutSize(15, 25, QgsUnitTypes.LayoutMillimeters)
    arrow.attemptResize(arrow_size)

    margin = 4
    page_size = page.pageSize()
    x = margin
    y = page_size.height() - arrow_size.height() - margin
    arrow.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    arrow.setRotation(-map.rotation())
    layout.addLayoutItem(arrow)

    # Scale Bar
    sb = QgsLayoutItemScaleBar(layout)
    sb.setStyle('Line Ticks Up')
    sb.setLinkedMap(map)
    sb.applyDefaultSize()
    
    sb.guessUnits()

    sb.attemptMove(QgsLayoutPoint(4, 4, QgsUnitTypes.LayoutMillimeters))

    font = sb.font()
    font.setBold(True)
    sb.setFont(font) 
    sb.setFillColor   (QColor("white"))
    sb.setFillColor2  (QColor("white"))
    sb.setLineColor   (QColor("white"))
    sb.setFontColor   (QColor("white"))
    sb.setBackgroundEnabled(True)
    bg = QColor(0, 0, 0, 127)
    sb.setBackgroundColor(bg)
    layout.addLayoutItem(sb)

    margin = 4
    page_size = page.pageSize()
    sb_rect = sb.rectWithFrame()
    sb.attemptMove(QgsLayoutPoint(page_size.width() - sb_rect.width() - margin, page_size.height() - sb_rect.height() - margin,QgsUnitTypes.LayoutMillimeters))

    return layout


def export_as_image(layout: QgsPrintLayout, output_path: str | Path, dpi: int = 300) -> Path:
    output_path = Path(output_path).expanduser().resolve()
    exporter = QgsLayoutExporter(layout)
    settings = exporter.ImageExportSettings()
    settings.dpi = dpi
    settings.rasterizeWholeImage = False
    exporter.exportToImage(str(output_path), settings)
    return output_path


def show_only(layer_path, keep_always_visible):
    root = iface.layerTreeView().layerTreeModel().rootGroup()
    base_name = os.path.splitext(os.path.basename(layer_path))[0]

    for layer in QgsProject.instance().mapLayers().values():
        node = root.findLayer(layer.id())
        if not node:
            continue
        name = layer.name()
        if name in keep_always_visible or name == base_name:
            node.setItemVisibilityChecked(True)
        else:
            node.setItemVisibilityChecked(False)

    target_layer = QgsProject.instance().mapLayersByName(base_name)[0]
    return target_layer

def set_project_crs_to_layer(layer):
    """Set the QGIS project CRS to match the given layer's CRS."""
    project = QgsProject.instance()
    layer_crs = layer.crs()
    project.setCrs(layer_crs)
    
def adjust_extent_to_aspect_ratio(extent: QgsRectangle, target_width: float, target_height: float) -> QgsRectangle:
    """Expand extent to match the target aspect ratio, keeping it centered."""
    cx = (extent.xMinimum() + extent.xMaximum()) / 2
    cy = (extent.yMinimum() + extent.yMaximum()) / 2
    width = extent.xMaximum() - extent.xMinimum()
    height = extent.yMaximum() - extent.yMinimum()
    current_ratio = width / height
    target_ratio = target_width / target_height

    if current_ratio > target_ratio:
        # Need to expand height
        new_height = width / target_ratio
        dh = (new_height - height) / 2
        return QgsRectangle(extent.xMinimum(), cy - new_height/2, extent.xMaximum(), cy + new_height/2)
    else:
        # Need to expand width
        new_width = height * target_ratio
        dw = (new_width - width) / 2
        return QgsRectangle(cx - new_width/2, extent.yMinimum(), cx + new_width/2, extent.yMaximum())
    
def get_polygon_vertex(layer, which="bottom-left"):
    """
    Return the coordinates of a vertex of the polygon or multilinestring:
    'bottom-left', 'bottom-right', 'top-left', 'top-right'.
    """
    geom = next(layer.getFeatures()).geometry()
    points = []

    if geom.type() == 2:  # Polygon
        if geom.isMultipart():
            points = geom.asMultiPolygon()[0][0]
        else:
            points = geom.asPolygon()[0]
        if points and points[0] == points[-1]:
            points = points[:-1]
    elif geom.type() == 1:  # Line (MultiLineString or LineString)
        if geom.isMultipart():
            for line in geom.asMultiPolyline():
                points.extend(line)
        else:
            points = geom.asPolyline()
    else:
        raise ValueError("Layer geometry must be Polygon or LineString/MultiLineString.")

    if not points:
        raise ValueError("No points found in geometry.")

    if which == "bottom-left":
        corner = min(points, key=lambda pt: (pt.y(), pt.x()))
    elif which == "bottom-right":
        corner = min(points, key=lambda pt: (pt.y(), -pt.x()))
    elif which == "top-left":
        corner = max(points, key=lambda pt: (pt.y(), -pt.x()))
    else:  # "top-right"
        corner = max(points, key=lambda pt: (pt.y(), pt.x()))

    centroid = geom.centroid().asPoint()
    dx = (centroid.x() - corner.x()) * 0.08
    dy = (centroid.y() - corner.y()) * 0.10
    moved_corner = corner.__class__(corner.x() + dx, corner.y() + dy)

    return moved_corner
    
def make_zoom_extent_around_point(center, full_ext: QgsRectangle, factor: float = 0.1, margin_frac: float = 0.04) -> QgsRectangle:
    w = full_ext.width() * factor
    h = full_ext.height() * factor
    margin_x = full_ext.width() * margin_frac
    margin_y = full_ext.height() * margin_frac
    return QgsRectangle(
        center.x() - w/2 + margin_x,
        center.y() - h/2 + margin_y,
        center.x() + w/2 - margin_x,
        center.y() + h/2 - margin_y
    )

def compute_zoom_factor_from_spacing(flight_line_spacing, min_spacing=50, max_spacing=200, min_zoom=0.2, max_zoom=0.4):
    """
    - spacing <= min_spacing: zoom = min_zoom
    - spacing >= max_spacing: zoom = max_zoom
    - in between: linear interpolation
    """
    if flight_line_spacing <= min_spacing:
        return min_zoom
    elif flight_line_spacing >= max_spacing:
        return max_zoom
    else:
        t = (flight_line_spacing - min_spacing) / (max_spacing - min_spacing)
        return min_zoom + (max_zoom - min_zoom) * t