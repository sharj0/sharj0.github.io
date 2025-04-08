#Node_display_tool_class.py

import numpy as np
import copy
from qgis.PyQt.QtCore import Qt, QVariant, QSizeF, QPointF, QRectF, QEvent
from qgis.PyQt.QtGui import QColor, QTextDocument, QFont, QFontMetrics
from qgis.gui import QgsMapTool
from qgis.core import (
    QgsWkbTypes,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsSymbolLayer,
    QgsField,
    QgsProject,
    QgsMarkerSymbol,
    QgsSimpleMarkerSymbolLayer,
    QgsMarkerLineSymbolLayer,
    QgsLineSymbol,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsProperty,
    QgsFeature,
    QgsUnitTypes,
    QgsTextAnnotation,
    QgsFillSymbol,
    QgsSimpleFillSymbolLayer,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)

class Node_display_tool(QgsMapTool):
    def __init__(self, canvas, root, dock_widget=None):
        super().__init__(canvas)
        self.root = root
        self.canvas = canvas
        self.dock_widget = dock_widget
        self.nodeLayer = None  # Shared in-memory layer for all nodes.
        # Dictionaries mapping a unique node id (node.global_count) to feature and annotation.
        self.nodeFeatures = {}     # {node_id: feature id}
        self.nodeAnnotations = {}  # {node_id: QgsTextAnnotation}
        self.nodes = {}            # {node_id: node object}
        self.currentHighlightedNodeId = None
        self.currentHighlightFeature = None
        self.currentHighlightAnnotation = None

        self.currentSelectedNodeId = None
        self.currentSelectedFeature = None
        self.currentSelectedAnnotation = None

        # Increase tolerance for hit detection.
        self.tolerance = 10  # base tolerance in map units
        self.hitFactor = 3   # multiplier for hit testing

        # Install an event filter on the canvas to capture when the mouse leaves the canvas.
        self.canvas.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.canvas and event.type() == QEvent.Leave:
            # When the mouse leaves the canvas, clear any highlights.
            if self.currentHighlightedNodeId is not None:
                self.remove_highlight()
                self.currentHighlightedNodeId = None
            return True
        return super().eventFilter(obj, event)

    def resetDisplay(self):
        """Clear all node features, annotations, highlighted and selected nodes without deactivating the tool."""
        # If the node layer exists, remove any highlighted or selected features first.
        if self.nodeLayer is not None:
            if self.currentHighlightFeature:
                self.nodeLayer.dataProvider().deleteFeatures([self.currentHighlightFeature.id()])
                self.currentHighlightFeature = None
            if self.currentHighlightAnnotation:
                QgsProject.instance().annotationManager().removeAnnotation(self.currentHighlightAnnotation)
                self.currentHighlightAnnotation = None
            if self.currentSelectedFeature:
                self.nodeLayer.dataProvider().deleteFeatures([self.currentSelectedFeature.id()])
                self.currentSelectedFeature = None
            if self.currentSelectedAnnotation:
                QgsProject.instance().annotationManager().removeAnnotation(self.currentSelectedAnnotation)
                self.currentSelectedAnnotation = None
        self.currentHighlightedNodeId = None
        self.currentSelectedNodeId = None

        # Remove the node layer from the project if it exists.
        if self.nodeLayer is not None:
            QgsProject.instance().removeMapLayer(self.nodeLayer.id())
            self.nodeLayer = None

        # Clear the dictionaries holding features, annotations, and nodes.
        self.nodeFeatures.clear()
        manager = QgsProject.instance().annotationManager()
        for ann in self.nodeAnnotations.values():
            manager.removeAnnotation(ann)
        self.nodeAnnotations.clear()
        self.nodes.clear()

        self.canvas.refresh()

    def deactivate(self):
        """Deactivate the tool and perform minimal cleanup."""
        if self.currentHighlightAnnotation or self.currentHighlightFeature:
            self.remove_highlight()
            self.currentHighlightedNodeId = None
        self.remove_selection()
        # If you want to fully clear everything on exit, you can call resetDisplay here.
        self.resetDisplay()
        self.canvas.refresh()
        self.canvas.unsetMapTool(self)
        if self.dock_widget:
            self.dock_widget.close()
        super().deactivate()

    def _ensure_nodeLayer(self, crs_root):
        """Ensure the shared node layer exists, creating it if necessary."""
        if self.nodeLayer is None:
            self.nodeLayer = QgsVectorLayer(f"LineString?crs={crs_root}", "Lines to flights Plugin", "memory")
            self.nodeLayer.dataProvider().addAttributes([
                QgsField("color", QVariant.String),
                QgsField("heading", QVariant.Double),
                QgsField("total_length", QVariant.Double),
                QgsField("efficiency_percent", QVariant.Double),
                QgsField("outline_color", QVariant.String),
                QgsField("node_id", QVariant.String)
            ])
            self.nodeLayer.updateFields()
            symbol = QgsLineSymbol()
            symbol.deleteSymbolLayer(0)
            outline_layer = QgsSimpleLineSymbolLayer()
            outline_layer.setWidth(1)
            outline_layer.setDataDefinedProperty(
                QgsSymbolLayer.PropertyStrokeColor,
                QgsProperty.fromExpression('"outline_color"')
            )
            symbol.appendSymbolLayer(outline_layer)
            inner_layer = QgsSimpleLineSymbolLayer()
            inner_layer.setColor(QColor(255, 0, 0))
            inner_layer.setWidth(0.5)
            inner_layer.setDataDefinedProperty(
                QgsSymbolLayer.PropertyStrokeColor,
                QgsProperty.fromExpression('"color"')
            )
            symbol.appendSymbolLayer(inner_layer)

            triangle_symbol = QgsMarkerSymbol.createSimple({
                'name': 'triangle',
                'size': '1',
                'outline_color': 'black'
            })
            triangle_layer = triangle_symbol.symbolLayer(0)
            triangle_layer.setSizeUnit(QgsUnitTypes.RenderMillimeters)
            size_expr = """
            CASE 
              WHEN @map_scale < 1000 THEN 5
              WHEN @map_scale < 10000 THEN 2
              ELSE 0.3
            END
            """
            triangle_layer.setDataDefinedProperty(
                QgsSymbolLayer.PropertySize,
                QgsProperty.fromExpression(size_expr)
            )
            triangle_symbol.symbolLayer(0).setDataDefinedProperty(
                QgsSimpleMarkerSymbolLayer.PropertyAngle,
                QgsProperty.fromExpression('"heading" + 90')
            )
            triangle_symbol.symbolLayer(0).setDataDefinedProperty(
                QgsSimpleMarkerSymbolLayer.PropertyFillColor,
                QgsProperty.fromExpression('"color"')
            )
            marker_line_layer = QgsMarkerLineSymbolLayer()
            marker_line_layer.setPlacement(QgsMarkerLineSymbolLayer.Vertex)
            marker_line_layer.setSubSymbol(triangle_symbol)
            symbol.appendSymbolLayer(marker_line_layer)
            renderer = QgsSingleSymbolRenderer(symbol)
            self.nodeLayer.setRenderer(renderer)
            QgsProject.instance().addMapLayer(self.nodeLayer)

    def create_node_line_feature(self, node, highlighted=False, selected=False):
        """
        Create and add the line feature for the given node.
        """
        crs_root = f"EPSG:{node.root.global_crs_target['target_crs_epsg_int']}"
        self._ensure_nodeLayer(crs_root)
        if selected:
            ocolor = "#ffffff"
        elif highlighted:
            ocolor = "#808080"
        else:
            ocolor = "#000000"
        coords = np.array(node.utm_fly_list)
        points = [QgsPointXY(x, y) for x, y in coords]
        geom = QgsGeometry.fromPolylineXY(points)
        feat = QgsFeature(self.nodeLayer.fields())
        feat.setGeometry(geom)
        color_str = node.color if node.color.startswith("#") else "#" + node.color
        feat.setAttribute("color", color_str)
        feat.setAttribute("heading", getattr(node, "heading", 0))
        feat.setAttribute("total_length", node.total_length)
        feat.setAttribute("efficiency_percent", node.efficiency_percent)
        feat.setAttribute("outline_color", ocolor)
        feat.setAttribute("node_id", str(node.global_count))
        self.nodeLayer.dataProvider().addFeature(feat)
        self.nodeLayer.updateExtents()
        self.nodeLayer.triggerRepaint()
        return feat

    def create_node_annotation(self, node, highlighted=False, selected=False):
        letter = node.__class__.__name__[0].upper()
        line1 = f'{letter}{node.global_count}'
        line2 = f'{round(node.total_length / 1000, 1)}km'
        line3 = f'{round(node.efficiency_percent)}%'
        label_text = f'{line1}<br>{line2}<br>{line3}'
        doc = QTextDocument()
        doc.setHtml(
            f'<div style="text-align:center; font-size:10pt; font-family:Arial; color:black;">{label_text}</div>')
        annotation = QgsTextAnnotation()
        annotation.setDocument(doc)
        end_points = [end_point.xy for end_point in node.end_point_list]
        end_point_centroid = tuple(np.mean(np.array(end_points), axis=0))
        crs_root = f"EPSG:{node.root.global_crs_target['target_crs_epsg_int']}"
        node_crs = QgsCoordinateReferenceSystem(crs_root)
        project_crs = QgsProject.instance().crs()
        transform = QgsCoordinateTransform(node_crs, project_crs, QgsProject.instance())
        project_point = transform.transform(QgsPointXY(*end_point_centroid))
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
        color_str = node.color if node.color.startswith("#") else "#" + node.color
        qcolor = QColor(color_str)
        qcolor.setAlpha(180)
        fill_color = f"{qcolor.red()},{qcolor.green()},{qcolor.blue()},{qcolor.alpha()}"
        fill_symbol = QgsFillSymbol.createSimple({
            'color': fill_color,
            'outline_color': a_outline,
            'outline_width': '0.5',
        })
        annotation.setFillSymbol(fill_symbol)
        annotation.setMapLayer(self.nodeLayer)
        annotation.customFrameSize = QSizeF(frame_width_px, frame_height_px)
        manager = QgsProject.instance().annotationManager()
        manager.addAnnotation(annotation)
        return annotation

    def canvasMoveEvent(self, event):
        widget_pos = event.pos()
        # If the mouse is not inside the canvas widget, clear highlight.
        if not self.canvas.rect().contains(widget_pos):
            if self.currentHighlightedNodeId is not None:
                self.remove_highlight()
                self.currentHighlightedNodeId = None
            return

        mouse_map_point = self.canvas.getCoordinateTransform().toMapCoordinates(widget_pos)
        if not hasattr(self, 'overallExtent') or self.overallExtent is None:
            self.updateOverallExtent()
        if self.overallExtent and not self.overallExtent.contains(mouse_map_point):
            if self.currentHighlightedNodeId is not None:
                self.remove_highlight()
                self.currentHighlightedNodeId = None
            return

        closest_node = None
        min_dist_sq = float('inf')
        for node_id, annotation in self.nodeAnnotations.items():
            centroid = getattr(annotation, 'centroid', annotation.mapPosition())
            dx = centroid.x() - mouse_map_point.x()
            dy = centroid.y() - mouse_map_point.y()
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_node = node_id

        # Do not highlight a node that is already selected.
        if closest_node and closest_node == self.currentSelectedNodeId:
            if self.currentHighlightedNodeId is not None:
                self.remove_highlight()
                self.currentHighlightedNodeId = None
            return

        if closest_node:
            if self.currentHighlightedNodeId != closest_node:
                if self.currentHighlightedNodeId is not None:
                    self.remove_highlight()
                node = self.nodes[closest_node]
                self.currentHighlightFeature = self.create_node_line_feature(node, highlighted=True, selected=False)
                self.currentHighlightAnnotation = self.create_node_annotation(node, highlighted=True, selected=False)
                self.currentHighlightedNodeId = closest_node
        else:
            if self.currentHighlightedNodeId is not None:
                self.remove_highlight()
                self.currentHighlightedNodeId = None

    def canvasReleaseEvent(self, event):
        """When the canvas is clicked, re-run the highlight logic and update selection accordingly."""
        if event.button() != Qt.LeftButton:
            return

        widget_pos = event.pos()
        mouse_map_point = self.canvas.getCoordinateTransform().toMapCoordinates(widget_pos)

        if not hasattr(self, 'overallExtent') or self.overallExtent is None:
            self.updateOverallExtent()

        candidate_node = None
        min_dist_sq = float('inf')
        for node_id, annotation in self.nodeAnnotations.items():
            centroid = getattr(annotation, 'centroid', annotation.mapPosition())
            dx = centroid.x() - mouse_map_point.x()
            dy = centroid.y() - mouse_map_point.y()
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                candidate_node = node_id

        # If the click is outside the overall extent, treat it as no node being clicked.
        if self.overallExtent and not self.overallExtent.contains(mouse_map_point):
            candidate_node = None

        if candidate_node is not None:
            # If the clicked node is not already selected, update the selection.
            if self.currentSelectedNodeId != candidate_node:
                self.remove_selection()
                # If the node is currently highlighted, remove its highlight so that selection replaces it.
                if self.currentHighlightedNodeId == candidate_node:
                    self.remove_highlight()
                    self.currentHighlightedNodeId = None
                node = self.nodes[candidate_node]
                self.currentSelectedFeature = self.create_node_line_feature(node, highlighted=False, selected=True)
                self.currentSelectedAnnotation = self.create_node_annotation(node, highlighted=False, selected=True)
                self.currentSelectedNodeId = candidate_node
        else:
            # If click is outside any node, unselect any selected node.
            self.remove_selection()

    def remove_highlight(self):
        """Remove the currently highlighted node (both line and annotation)."""
        if self.currentHighlightFeature:
            self.nodeLayer.dataProvider().deleteFeatures([self.currentHighlightFeature.id()])
            self.nodeLayer.triggerRepaint()
            self.currentHighlightFeature = None
        if self.currentHighlightAnnotation:
            QgsProject.instance().annotationManager().removeAnnotation(self.currentHighlightAnnotation)
            self.currentHighlightAnnotation = None
        self.canvas.refresh()

    def remove_selection(self):
        """Remove the currently selected node (both line and annotation)."""
        if self.currentSelectedFeature:
            self.nodeLayer.dataProvider().deleteFeatures([self.currentSelectedFeature.id()])
            self.nodeLayer.triggerRepaint()
            self.currentSelectedFeature = None
        if self.currentSelectedAnnotation:
            QgsProject.instance().annotationManager().removeAnnotation(self.currentSelectedAnnotation)
            self.currentSelectedAnnotation = None
        self.currentSelectedNodeId = None
        self.canvas.refresh()

    def updateOverallExtent(self):
        overall = None
        for node in self.nodes.values():
            if hasattr(node, 'utm_fly_list'):
                coords = np.array(node.utm_fly_list)
                xmin = np.min(coords[:, 0])
                xmax = np.max(coords[:, 0])
                ymin = np.min(coords[:, 1])
                ymax = np.max(coords[:, 1])
                node_extent = QgsRectangle(xmin, ymin, xmax, ymax)
                if overall is None:
                    overall = QgsRectangle(node_extent)
                else:
                    overall.combineExtentWith(node_extent)
        if overall:
            buffer_width = overall.width() * 0.25
            buffer_height = overall.height() * 0.25
            self.overallExtent = QgsRectangle(
                overall.xMinimum() - buffer_width,
                overall.yMinimum() - buffer_height,
                overall.xMaximum() + buffer_width,
                overall.yMaximum() + buffer_height
            )
        else:
            self.overallExtent = None

    def execute_action_on_selected_node(self, action):
        """
        Execute the specified action on the currently selected node.
        'action' should be one of: 'give_left', 'give_right', 'take_left', or 'take_right'.
        """
        if self.currentSelectedNodeId is not None:
            node = self.nodes.get(self.currentSelectedNodeId)
            # Save a deep copy of the current state of self.root for undo.
            new_state = copy.deepcopy(node.root)
            node.root.past_states.append(new_state)
            # If more than 100 states are stored, remove the oldest one.
            if len(node.root.past_states) > 100:
                node.root.past_states.pop(0)

            if node and hasattr(node, action):
                # Execute the node method
                getattr(node, action)()
                # Optionally, update the display if the node's state has changed.
                # For example, re-display the node or refresh annotations.
                # self.resetDisplay()
                # self.display_Node(node)
            else:
                print("Selected node does not have method:", action)
        else:
            print("No node is currently selected.")

    def undo(self):
        """
        Restore the previous state if available.
        """

        if self.root.past_states:
            # Pop the latest saved state.
            previous_state = self.root.past_states.pop()
            # Restore self.root to the previous state.
            self.root = previous_state

            # Clear current display (features, annotations, etc.)
            self.resetDisplay()

            # Re-display nodes based on the radio button state in the dock widget.
            if self.dock_widget and self.dock_widget.radio_edit_within_flights.isChecked():
                for flight in self.root.flight_list:
                    self.display_Node(flight)
            else:
                for TA in self.root.TA_list:
                    self.display_Node(TA)

            self.canvas.refresh()
            print('undone')
        else:
            print("No previous state to restore.")

    def display_Node(self, node):
        """
        Display a node (its line feature and annotation) in the default state.
        """
        node_id = str(node.global_count)
        self.nodes[node_id] = node
        feat = self.create_node_line_feature(node, highlighted=False, selected=False)
        ann = self.create_node_annotation(node, highlighted=False, selected=False)
        self.nodeFeatures[node_id] = feat.id()
        self.nodeAnnotations[node_id] = ann
        return feat
