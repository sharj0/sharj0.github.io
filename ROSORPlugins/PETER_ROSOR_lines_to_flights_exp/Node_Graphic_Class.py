import numpy as np
from qgis.PyQt.QtCore import QSizeF, QPointF, QVariant
from qgis.PyQt.QtGui import QColor, QTextDocument, QFont, QFontMetrics
from qgis.core import (
    QgsPointXY,
    QgsGeometry,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    QgsProject,
    QgsSimpleLineSymbolLayer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsSimpleMarkerSymbolLayer,
    QgsMarkerLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsProperty,
    QgsTextAnnotation,
    QgsFillSymbol,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsUnitTypes,
    QgsSymbolLayer,
)


class NodeGraphic:
    def __init__(self, node, plugin_canvas_gui, highlighted=False, selected=False):
        """
        Initialize the NodeGraphic with a node and a reference to the PluginCanvasGui.
        Creates the graphics for the node (line feature and annotation).
        """
        self.plugin_canvas_gui = plugin_canvas_gui
        self.node = node
        self.drone_path = self.create_node_line_feature(highlighted=highlighted, selected=selected)
        self.label = self.create_node_annotation(highlighted=highlighted, selected=selected)
        self.highlight_graphic = None
        self.selection_graphic = None

    def create_node_line_feature(self, highlighted=False, selected=False):
        """
        Create and add the line feature for this node.
        Styling (e.g. outline color) is determined by the highlighted/selected state.
        """
        layer = self.plugin_canvas_gui.nodeLayer
        if selected:
            ocolor = "#ffffff"
        elif highlighted:
            ocolor = "#808080"
        else:
            ocolor = "#000000"
        coords = np.array(self.node.utm_fly_list)
        points = [QgsPointXY(x, y) for x, y in coords]
        geom = QgsGeometry.fromPolylineXY(points)
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        if not self.node.color:
            self.node.color = next(self.node.root.color_cycle)
        color_str = self.node.color if self.node.color.startswith("#") else "#" + self.node.color
        feat.setAttribute("color", color_str)
        feat.setAttribute("heading", getattr(self.node, "heading", 0))
        feat.setAttribute("total_length", self.node.total_length)
        feat.setAttribute("efficiency_percent", self.node.efficiency_percent)
        feat.setAttribute("outline_color", ocolor)
        layer.dataProvider().addFeature(feat)
        layer.updateExtents()
        layer.triggerRepaint()
        return feat

    def create_node_annotation(self, highlighted=False, selected=False):
        """
        Create and add the annotation for this node.
        The label displays a letter (from the node's class name) plus metrics from the node.
        """
        line1 = f'{self.node.short_name}'
        line2 = f'{round(self.node.total_length / 1000, 1)}km'
        line3 = f'{round(self.node.efficiency_percent)}%'
        label_text = f'{line1}<br>{line2}<br>{line3}'
        doc = QTextDocument()
        doc.setHtml(
            f'<div style="text-align:center; font-size:10pt; font-family:Arial; color:black;">{label_text}</div>')
        annotation = QgsTextAnnotation()
        annotation.setDocument(doc)
        # Calculate the centroid from the node's endpoints.
        crs_root = f"EPSG:{self.node.root.global_crs_target['target_crs_epsg_int']}"
        node_crs = QgsCoordinateReferenceSystem(crs_root)
        project_crs = QgsProject.instance().crs()
        transform = QgsCoordinateTransform(node_crs, project_crs, QgsProject.instance())
        project_point = transform.transform(QgsPointXY(*self.node.end_point_centroid))
        annotation.centroid = project_point
        annotation.setMapPosition(project_point)
        annotation.setMapPositionCrs(project_crs)
        font = QFont("Arial", 10)
        metrics = QFontMetrics(font)
        max_width_px = max(
            metrics.horizontalAdvance(line1),
            metrics.horizontalAdvance(line2),
            metrics.horizontalAdvance(line3)
        )
        padding_px = 10
        frame_width_px = max_width_px + padding_px
        frame_height_px = 53
        annotation.setFrameSize(QSizeF(frame_width_px, frame_height_px))
        annotation.setFrameOffsetFromReferencePoint(QPointF(-frame_width_px / 2, -frame_height_px / 2))
        annotation.setMarkerSymbol(None)
        if selected:
            a_outline = "255,255,255,255"
        elif highlighted:
            a_outline = "128,128,128,255"
        else:
            a_outline = "0,0,0,128"
        qcolor = QColor(color_str) if (
            color_str := (self.node.color if self.node.color.startswith("#") else "#" + self.node.color)) \
            else QColor(0,0,0)
        qcolor.setAlpha(180)
        fill_color = f"{qcolor.red()},{qcolor.green()},{qcolor.blue()},{qcolor.alpha()}"
        fill_symbol = QgsFillSymbol.createSimple({
            'color': fill_color,
            'outline_color': a_outline,
            'outline_width': '0.5',
        })
        annotation.setFillSymbol(fill_symbol)
        annotation.setMapLayer(self.plugin_canvas_gui.nodeLayer)
        annotation.customFrameSize = QSizeF(frame_width_px, frame_height_px)
        QgsProject.instance().annotationManager().addAnnotation(annotation)
        return annotation

    def un_highlight(self):
        if self.highlight_graphic:
            self.highlight_graphic.clear()
            self.highlight_graphic = None

    def un_select(self):
        if self.selection_graphic:
            self.selection_graphic.clear()
            self.selection_graphic = None

    def highlight(self):
        """
        Apply highlight styling to this node.
        If a highlighted version already exists, clear it before re-creating.
        """
        if self.highlight_graphic is not None:
            self.highlight_graphic.clear()
        self.highlight_graphic = NodeGraphic(self.node, self.plugin_canvas_gui, highlighted=True, selected=False)
        self.plugin_canvas_gui.current_highlight = self

    def select(self):
        """
        Apply selection styling to this node.
        If a selected version already exists, clear it before re-creating.
        """
        print(f'Selected {self.node}')
        if self.selection_graphic is not None:
            self.selection_graphic.clear()
        self.selection_graphic = NodeGraphic(self.node, self.plugin_canvas_gui, highlighted=False, selected=True)
        self.plugin_canvas_gui.current_selection = self

    def _clear_node_line_feature(self):
        """
        Clear the node's line feature from the canvas.
        Removes only this node's line feature.
        """
        if self.drone_path is not None:
            layer = self.plugin_canvas_gui.nodeLayer
            layer.dataProvider().deleteFeatures([self.drone_path.id()])
            layer.triggerRepaint()
            self.drone_path = None

    def _clear_node_annotation(self):
        """
        Clear the node's annotation from the canvas.
        Removes only this node's annotation.
        """
        if self.label is not None:
            QgsProject.instance().annotationManager().removeAnnotation(self.label)
            self.label = None

    def clear(self):
        """
        Clear both the line feature and annotation for this node.
        """
        self._clear_node_annotation()
        self._clear_node_line_feature()

        if self.highlight_graphic:
            self.highlight_graphic.clear()

        if self.selection_graphic:
            self.selection_graphic.clear()

