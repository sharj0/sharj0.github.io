import copy
import pickle
import os

from qgis.core import (
    QgsProject, QgsRectangle, QgsPointXY, QgsVectorLayer, QgsField,
    QgsGeometry, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsUnitTypes, QgsSimpleLineSymbolLayer, QgsLineSymbol, QgsMarkerSymbol,
    QgsMarkerLineSymbolLayer, QgsSingleSymbolRenderer, QgsProperty, QgsTextAnnotation,
    QgsFillSymbol, QgsSymbolLayer, QgsSimpleMarkerSymbolLayer
)

import os
import xml.etree.ElementTree as ET

from qgis.core import (
    QgsVectorFileWriter,
    QgsFeature,
    QgsCoordinateTransformContext,

)

from qgis.PyQt.QtCore import Qt, QEvent, QVariant
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt.QtGui import QColor, QFont
from qgis.gui import QgsMapTool
from .Node_Graphic_Class import NodeGraphic
from .functions import (get_name_of_non_existing_output_file)

class PluginCanvasGui(QgsMapTool):
    def __init__(self, canvas, root, dock_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.root = root
        self.dock_widget = dock_widget
        self.current_selection = None  # A NodeGraphic currently selected
        self.current_highlight = None  # A NodeGraphic currently highlighted
        self.nodeLayer = self.create_nodeLayer()  # Create the shared node layer once
        self._level = None  # Backing variable for level; not set until display_level() is called
        self.overallExtent = None
        self.past_states = []
        self.root.action_counter = 0
        root.plugin_canvas_gui = self

    def __deepcopy__(self, memo):
        # Exclude deep copying for PluginCanvasGui objects.
        return None

    @property
    def level(self):
        if self._level:
            return self._level
        else:
            return None

    @property
    def displayed_nodes(self):
        """Dynamically returns the list of nodes to be displayed at this level.
           Returns None if display_level hasn't been called yet.
        """
        if self._level is None:
            return None
        return self.root.get_list_of_all_children_at_level(self._level)

    def display_level(self, level):
        self.clear()
        self._level = level
        # Instantiate a NodeGraphic for each displayed node.
        #print(f'{len(self.displayed_nodes) = }')
        if self.displayed_nodes is not None:
            for node in self.displayed_nodes:
                if not node.deleted:
                    node.graphic = NodeGraphic(node, self)

    def create_nodeLayer(self):
        """
        Create and configure the shared node layer used for all node graphics.
        This method replicates the functionality of _ensure_nodeLayer.
        """
        crs_root = f"EPSG:{self.root.global_crs_target['target_crs_epsg_int']}"
        nodeLayer = QgsVectorLayer(f"LineString?crs={crs_root}", "Plugin Graphics", "memory")
        nodeLayer.dataProvider().addAttributes([
            QgsField("color", QVariant.String),
            QgsField("heading", QVariant.Double),
            QgsField("total_length", QVariant.Double),
            QgsField("efficiency_percent", QVariant.Double),
            QgsField("outline_color", QVariant.String),
            QgsField("node_id", QVariant.String)
        ])
        nodeLayer.updateFields()
        symbol = QgsLineSymbol()
        symbol.deleteSymbolLayer(0)
        # Outline layer
        outline_layer = QgsSimpleLineSymbolLayer()
        outline_layer.setWidth(1)
        outline_layer.setDataDefinedProperty(
            QgsSimpleLineSymbolLayer.PropertyStrokeColor,
            QgsProperty.fromExpression('"outline_color"')
        )
        symbol.appendSymbolLayer(outline_layer)
        # Inner layer
        inner_layer = QgsSimpleLineSymbolLayer()
        inner_layer.setColor(QColor(255, 0, 0))
        inner_layer.setWidth(0.5)
        inner_layer.setDataDefinedProperty(
            QgsSimpleLineSymbolLayer.PropertyStrokeColor,
            QgsProperty.fromExpression('"color"')
        )
        symbol.appendSymbolLayer(inner_layer)
        # Marker (triangle) layer
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
        nodeLayer.setRenderer(renderer)
        QgsProject.instance().addMapLayer(nodeLayer)
        return nodeLayer


    def save_shp_or_kml(self, geoms, out_path, out_layer_name, target_epsg_code, flight_color, save_shp=True):
        """
        Saves the provided geometries to either a shapefile or a KML file.

        Parameters:
          geoms: List of QgsGeometry objects.
          out_path: Full path (including filename) for the output.
          out_layer_name: Name of the output layer.
          target_epsg_code: The CRS as a string (e.g. "EPSG:4326").
          flight_color: A color string in KML format (aabbggrr, e.g., "fff0a1d0").
          save_shp: If True, saves as shapefile; otherwise as KML.
        """
        # Ensure the directory exists.
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile" if save_shp else "KML"
        options.fileEncoding = "UTF-8"

        # Create an in-memory layer for LineStrings.
        layer = QgsVectorLayer(f"LineString?crs={target_epsg_code}", out_layer_name, "memory")
        dp = layer.dataProvider()
        layer.startEditing()
        for geom in geoms:
            feat = QgsFeature()
            feat.setGeometry(geom)
            dp.addFeatures([feat])
        layer.commitChanges()

        QgsVectorFileWriter.writeAsVectorFormatV3(layer, out_path, QgsCoordinateTransformContext(), options)
        print(f"File saved to {out_path}")

        if not save_shp:
            # For KML: Update the color in the KML file to match flight_color.
            try:
                tree = ET.parse(out_path)
                root = tree.getroot()
                namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}

                for color_elem in root.findall(".//kml:color", namespaces):
                    color_elem.text = flight_color

                # Write the modified KML.
                ET.register_namespace('', "http://www.opengis.net/kml/2.2")
                tree.write(out_path, xml_declaration=True, encoding='utf-8', method='xml')
                print("KML color elements updated.")
            except Exception as e:
                print(f"Error updating KML colors: {e}")
        else:
            # For shapefiles, create a companion QML style file so that QGIS shows the correct color.
            # Convert the KML color (aabbggrr) into a QML color (#RRGGBB).
            if len(flight_color) == 8:
                red = flight_color[6:8]
                green = flight_color[4:6]
                blue = flight_color[2:4]
                qml_color = f"#{red}{green}{blue}"
            else:
                qml_color = "#000000"

            qml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
    <qgis styleCategories="AllStyleCategories" version="3.0">
      <renderer-v2 type="singleSymbol">
        <symbols>
          <symbol alpha="1" type="line" name="line">
            <layer pass="0" class="SimpleLine" locked="0">
              <prop k="color" v="{qml_color}"/>
              <prop k="width" v="0.26"/>
            </layer>
          </symbol>
        </symbols>
      </renderer-v2>
      <labeling/>
    </qgis>
    '''
            qml_path = os.path.splitext(out_path)[0] + ".qml"
            with open(qml_path, "w", encoding="utf-8") as f:
                f.write(qml_content)
            print(f"QML style file saved to {qml_path}")

    def save(self, save_as_shp=False):
        """
        Creates a top-level folder and a subfolder for each TOF, then saves each flight
        as a KML or SHP file (with the flight's color). Each flight is expected to have:
          - long_output_name (a filename),
          - color (in aabbggrr format), and
          - utm_fly_list (a list of coordinate pairs).

        The target CRS is extracted from self.root.global_crs_target['target_crs_epsg_int'].
        """
        save_in_folder = os.path.dirname(self.root.current_pickle_path_out)
        top_save_folder_basename = "flights_2D"
        top_save_folder_path = os.path.join(save_in_folder, top_save_folder_basename)

        # Ensure a unique folder name if needed.
        top_save_folder_path = get_name_of_non_existing_output_file(top_save_folder_path)
        print(f'top_save_folder_path')
        print(top_save_folder_path)
        os.makedirs(top_save_folder_path, exist_ok=True)
        print(f"{self.root.global_crs_target = }")

        # Extract the EPSG code from self.root.global_crs_target.
        target_epsg_int = self.root.global_crs_target.get('target_crs_epsg_int', 4326)
        target_epsg_code = f"EPSG:{target_epsg_int}"

        for tof in self.root.TOF_list:
            tof_folder_name = str(tof)
            tof_folder_path = os.path.join(top_save_folder_path, tof_folder_name)
            os.makedirs(tof_folder_path, exist_ok=True)
            print(f'    {tof}:')

            for flight in tof.flight_list:
                print(f'        {flight.long_output_name = }')
                print(f'        {flight.color = }')
                print(f'        {flight.utm_fly_list = }')

                file_ext = ".shp" if save_as_shp else ".kml"
                out_path = os.path.join(tof_folder_path, flight.long_output_name)
                if not out_path.lower().endswith(file_ext):
                    out_path += file_ext

                # Create geometry from utm_fly_list since flight.geometry does not exist.
                geoms = []
                if hasattr(flight, 'utm_fly_list'):
                    try:
                        points = []
                        for pt in flight.utm_fly_list:
                            if isinstance(pt, (list, tuple)) and len(pt) == 2:
                                points.append(QgsPointXY(pt[0], pt[1]))
                        if points:
                            geom = QgsGeometry.fromPolylineXY(points)
                            geoms = [geom]
                        else:
                            print(f"No valid coordinates found for flight {flight.long_output_name}")
                            continue
                    except Exception as e:
                        print(f"Error converting utm_fly_list for flight {flight.long_output_name}: {e}")
                        continue
                else:
                    print(f"Flight {flight.long_output_name} has no geometry or utm_fly_list")
                    continue

                self.save_shp_or_kml(geoms, out_path, flight.long_output_name, target_epsg_code, flight.color,
                                save_shp=save_as_shp)

    def execute_action_on_selected_node(self, command):
        self.root.action_counter += 1

        if not self.current_selection:
            return
        if len(self.root.past_states) >= 100:
            self.root.past_states.pop(0)
        self.root.plugin_canvas_gui.clear()
        # Separate the past_states list from self.root
        past_states = self.root.past_states
        self.root.past_states = []  # Temporarily remove the list
        root_copy = copy.deepcopy(self.root)
        # Reattach the past_states list to both self.root and the copy
        root_copy.past_states = past_states
        self.root.past_states = past_states
        self.root.past_states.append(root_copy)

        if command == "give_left":
            self.current_selection.node.give_left()
        if command == "give_right":
            self.current_selection.node.give_right()
        if command == "take_left":
            self.current_selection.node.take_left()
        if command == "take_right":
            self.current_selection.node.take_right()

    def remove_highlight(self):
        if self.current_highlight:
            self.current_highlight.un_highlight()
            self.current_highlight = None

    def remove_selection(self):
        if self.current_selection:
           self.current_selection.un_select()
           self.current_selection = None

    def set_highlight(self, node_graphic):
        if self.current_selection == node_graphic:
            return
        node_graphic.highlight()

    def set_selection(self, node_graphic):
        node_graphic.select()

    def getClosestNode(self, mouse_map_point):
        """
        Given a mouse map point, iterate through displayed_nodes and return
        the node that is closest to the mouse coordinates.
        """
        closest_node = None
        min_dist_sq = float('inf')
        for node in self.displayed_nodes:
            if not hasattr(node, "graphic") or node.graphic is None:
                continue
            centroid = node.end_point_centroid
            dx = centroid[0] - mouse_map_point.x()
            dy = centroid[1] - mouse_map_point.y()
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_node = node
        return closest_node

    def updateOverallExtent(self):
        if self.overallExtent:
            return self.overallExtent
        overall = None
        for node in self.displayed_nodes:
            if hasattr(node, 'utm_fly_list') and node.utm_fly_list:
                xs = [pt[0] for pt in node.utm_fly_list]
                ys = [pt[1] for pt in node.utm_fly_list]
                node_extent = QgsRectangle(min(xs), min(ys), max(xs), max(ys))
                if overall is None:
                    overall = QgsRectangle(node_extent)
                else:
                    overall.combineExtentWith(node_extent)
        if overall:
            buffer_width = overall.width() * 0.25
            buffer_height = overall.height() * 0.25
            overall = QgsRectangle(
                overall.xMinimum() - buffer_width,
                overall.yMinimum() - buffer_height,
                overall.xMaximum() + buffer_width,
                overall.yMaximum() + buffer_height
            )
        self.overallExtent = overall
        return overall

    def canvasMoveEvent(self, event):
        """Determine which node should be highlighted based on mouse movement."""
        if not self.displayed_nodes:
            return
        widget_pos = event.pos()
        mouse_map_point = self.canvas.getCoordinateTransform().toMapCoordinates(widget_pos)
        overallExtent = self.updateOverallExtent()
        # If the mouse position is outside the overall extent, remove highlighting and exit.
        if overallExtent and not overallExtent.contains(mouse_map_point):
            self.remove_highlight()
            return

        closest_node = self.getClosestNode(mouse_map_point)
        if closest_node:
            # If the closest node is already highlighted, do nothing.
            if self.current_highlight and self.current_highlight.node == closest_node:
                return
            # Otherwise, remove the current highlight and set the new one.
            self.remove_highlight()
            self.set_highlight(closest_node.graphic)
        else:
            self.remove_highlight()

    def canvasReleaseEvent(self, event):
        """Determine which node is selected on mouse release and delegate selection."""
        if event.button() != Qt.LeftButton:
            return
        widget_pos = event.pos()
        mouse_map_point = self.canvas.getCoordinateTransform().toMapCoordinates(widget_pos)
        overallExtent = self.updateOverallExtent()
        # If the click is outside the overall extent, remove selection and exit.
        if overallExtent and not overallExtent.contains(mouse_map_point):
            self.remove_selection()
            return

        candidate = self.getClosestNode(mouse_map_point)
        if candidate:
            # If the candidate is already selected, do nothing.
            if self.current_selection and self.current_selection.node == candidate:
                return
            # Otherwise, remove the current selection and set the new one.
            self.remove_selection()
            self.set_selection(candidate.graphic)
        else:
            self.remove_selection()

    def undo(self):
        """Restore the previous state and reinitialize NodeGraphic instances."""
        if self.root.past_states:
            self.clear()
            previous_state = self.root.past_states.pop()
            old_level = self.level
            self.root = previous_state
            self.root.plugin_canvas_gui = self
            self.root.plugin_canvas_gui.display_level(old_level)
            self.canvas.refresh()
            print("undone")
        else:
            print("No previous state to restore.")

    def deactivate(self):
        self.clear()
        if self.nodeLayer is not None:
            QgsProject.instance().removeMapLayer(self.nodeLayer.id())
            self.nodeLayer = None
        self.canvas.unsetMapTool(self)
        if self.dock_widget:
            self.dock_widget.close()
        super().deactivate()

    def eventFilter(self, obj, event):
        if obj == self.canvas and event.type() == QEvent.Leave:
            self.remove_highlight()
            return True
        return False

    def clear(self):
        """Clear the visuals for all displayed nodes."""

        if not self.displayed_nodes:
            return
        for node in self.displayed_nodes:
            if hasattr(node, "graphic") and node.graphic is not None:
                node.graphic.clear()
                node.graphic = None
        self.canvas.refresh()
