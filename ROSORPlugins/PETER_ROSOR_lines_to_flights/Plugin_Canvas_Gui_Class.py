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
from xml.dom import minidom
import json
from qgis.core import (
    QgsVectorFileWriter,
    QgsFeature,
    QgsCoordinateTransformContext,

)

from qgis.PyQt.QtCore import Qt, QEvent, QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QColor, QFont
from qgis.gui import QgsMapTool
from .Node_Graphic_Class import NodeGraphic
from .functions import (get_name_of_non_existing_output_file)
from .import_kmls import process_folder



class PluginCanvasGui(QgsMapTool):
    def __init__(self, canvas, root, dock_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.root = root
        self.dock_widget = dock_widget
        self.current_selection = None  # A NodeGraphic currently selected
        self.current_highlight = None  # A NodeGraphic currently highlighted
        self.current_highlights = []
        self.nodeLayer = self.create_nodeLayer()  # Create the shared node layer once
        self._level = None  # Backing variable for level; not set until display_level() is called
        self.overallExtent = None
        self.past_states = []
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

    def preview_target_node(self, action_type):
        self.remove_highlight()
        if not self.current_selection:
            return
        src = self.current_selection.node
        tgt = None

        if action_type == "take_left":
            if hasattr(src, "_take_left_node_specific"):
                tgt = src._immediate_left_neighbour()
            if tgt and hasattr(tgt, "graphic") and tgt.graphic:
                self.set_highlight(tgt.graphic)
            return
        elif action_type == "take_right":
            if hasattr(src, "_take_right_node_specific"):
                tgt = src._immediate_right_neighbour()
            if tgt and hasattr(tgt, "graphic") and tgt.graphic:
                self.set_highlight(tgt.graphic)
            return
        elif action_type == "give_left":
            if hasattr(src, "_give_left_node_specific"):
                tgt = src._immediate_left_neighbour()
            if tgt and hasattr(tgt, "graphic") and tgt.graphic:
                self.set_highlight(tgt.graphic)
            return
        elif action_type == "give_right":
            if hasattr(src, "_give_right_node_specific"):
                tgt = src._immediate_right_neighbour()
            if tgt and hasattr(tgt, "graphic") and tgt.graphic:
                self.set_highlight(tgt.graphic)
            return
        elif action_type == "take_left_cascade":
            # Highlight all nodes to the left in the strip
            node = src
            while node is not None:
                if hasattr(node, "graphic") and node.graphic:
                    self.set_highlight(node.graphic)
                node = getattr(node, "left_neighbour", None)
            return
        elif action_type == "take_right_cascade":
            # Highlight all nodes to the right in the strip
            node = src
            while node is not None:
                if hasattr(node, "graphic") and node.graphic:
                    self.set_highlight(node.graphic)
                node = getattr(node, "right_neighbour", None)
            return

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
        project = QgsProject.instance()  # grab the project
        project.addMapLayer(nodeLayer, False)  # add layer (but NOT to the legend)
        project.layerTreeRoot().insertLayer(0, nodeLayer)  # insert it at index 0 → top of list
        return nodeLayer

    def save_kml(self, geom, out_path, flight, main_epsg_int):
        """
        Saves the provided geometry to a KML file, then injects a CDATA-wrapped
        JSON description containing flight metadata (neighbours, children, etc.).

        Parameters:
          geom: QgsGeometry object.
          out_path: Full path (including filename) for the output KML.
          flight: flight object with attributes long_output_name, color,
                  left_neighbour, right_neighbour, and children list.
          main_epsg_int: CRS integer (e.g. 32613).
        """
        # build the CRS string
        main_crs = f"EPSG:{main_epsg_int}"

        # 1) ensure the output folder exists
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # 2) write a basic single-feature KML
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "KML"
        options.fileEncoding = "UTF-8"

        layer = QgsVectorLayer(f"LineString?crs={main_crs}", flight.long_output_name, "memory")
        dp = layer.dataProvider()
        layer.startEditing()
        feat = QgsFeature()
        feat.setGeometry(geom)
        dp.addFeatures([feat])
        layer.commitChanges()

        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            out_path,
            QgsCoordinateTransformContext(),
            options
        )

        coords = []
        if geom.isMultipart():
            multi = geom.asMultiPolyline()
            for part in multi:
                for pt in part:
                    coords.append({"x": pt.x(), "y": pt.y()})
        else:
            line_pts = geom.asPolyline()
            for pt in line_pts:
                coords.append({"x": pt.x(), "y": pt.y()})

        # 3) assemble the metadata dict
        meta = {
            "flight_name": flight.long_output_name,
            "epsg": main_epsg_int,
            "left_neighbor": getattr(flight.left_neighbour, "long_output_name", None),
            "right_neighbor": getattr(flight.right_neighbour, "long_output_name", None),
            "tof": {
                "name": str(flight.tof_assignment.tof),
                "x":    flight.tof_assignment.tof.x,
                "y":    flight.tof_assignment.tof.y
            },
            "flight_coords": coords,
            "children": []
        }

        for line in flight.children:
            geom_line = {
                "start_x": line.start.x,
                "start_y": line.start.y,
                "end_x": line.end.x,
                "end_y": line.end.y
            }
            neigh = {
                "left": getattr(line.left_neighbour, "grid_name", None),
                "right": getattr(line.right_neighbour, "grid_name", None),
                "up": getattr(line.up_neighbour, "grid_name", None),
                "down": getattr(line.down_neighbour, "grid_name", None),
            }
            meta["children"].append({
                "line_name": str(line.grid_name),
                "neighbors": neigh,
                "geometry": geom_line
            })

        # 4) parse + inject CDATA-JSON + update color tags
        try:
            doc = minidom.parse(out_path)
            placemarks = doc.getElementsByTagName("Placemark")

            for pm in placemarks:
                # remove any existing <description>
                for old in pm.getElementsByTagName("description"):
                    pm.removeChild(old)

                # new <description><![CDATA[ ...json... ]]></description>
                desc = doc.createElement("description")
                cdata = doc.createCDATASection(json.dumps(meta, indent=2))
                desc.appendChild(cdata)

                # try to insert it right before the geometry node
                geom_node = None
                for tag in ("LineString", "Polygon", "Point", "MultiGeometry"):
                    elems = pm.getElementsByTagName(tag)
                    if elems:
                        geom_node = elems[0]
                        break
                if geom_node:
                    pm.insertBefore(desc, geom_node)
                else:
                    pm.appendChild(desc)

                # update any <color> child
                for color_elem in pm.getElementsByTagName("color"):
                    if color_elem.firstChild:
                        color_elem.firstChild.nodeValue = flight.color
                    else:
                        color_elem.appendChild(doc.createTextNode(flight.color))

                # -- **reformat coordinates** so each coord-triplet is on its own line
                for coord_elem in pm.getElementsByTagName("coordinates"):
                    txt = coord_elem.firstChild.nodeValue or ""
                    parts = txt.strip().split()
                    # add a leading and trailing newline
                    new_txt = "\n" + "\n".join(parts) + "\n"
                    coord_elem.firstChild.nodeValue = new_txt

            # write back out (toxml with encoding returns bytes)
            xml_bytes = doc.toxml(encoding="utf-8")
            with open(out_path, "wb") as f:
                f.write(xml_bytes)

            print("KML metadata and color elements updated.")
        except Exception as e:
            print(f"Error injecting JSON CDATA into KML: {e}")


    def save_kml_old(self, geom, out_path, flight, main_epsg_int):
        """
        Saves the provided geomety to a KML file.

        Parameters:
          geom: QgsGeometry object.
          out_path: Full path (including filename) for the output.
          flight obj
        """
        '''
        FOR CHAT GPT
        long output name examples. these are the names of the flights and also the names of the kml files
        
        survey_area.flight_list[15].long_output_name
        Out[20]: 'tof_6_flt_1_2.97km.kml'
        survey_area.flight_list[16].long_output_name
        Out[21]: 'tof_6_flt_2_3.01km.kml'
        survey_area.flight_list[17].long_output_name
        Out[22]: 'tof_6_flt_3_3.05km.kml'
        survey_area.flight_list[18].long_output_name
        Out[23]: 'tof_8_flt_16_2.97km.kml'
        survey_area.flight_list[19].long_output_name
        Out[24]: 'tof_8_flt_17_2.92km.kml'
        survey_area.flight_list[20].long_output_name
        Out[25]: 'tof_8_flt_18_2.88km.kml'
        ^this is for other time this func is called
        
        flight.long_output_name
        Out[33]: 'tof_8_flt_16_2.97km.kml'
        flight.left_neighbour.long_output_name
        Out[34]: 'tof_6_flt_3_3.05km.kml'
        flight.right_neighbour.long_output_name
        Out[35]: 'tof_8_flt_17_2.92km.kml'
        
        main_crs
        Out[50]: 'EPSG:32613'
        
        flight.children
        Out[36]: [Line-33] # there are usually more than one
        
        flight.children[0].start.x
        Out[42]: 320525.98457968136
        flight.children[0].start.y
        Out[43]: 4235527.165916944
        flight.children[0].end.x
        Out[44]: 319455.5989698029
        flight.children[0].end.y
        Out[45]: 4234884.013356795
        
        
        # what follows is the unique line name you should use. 
        right now its an integer, but you should save it as string in case we change how we use it in the future
        flight.children[0].grid_name 
        400101
        flight.right_neighbour.children[0].grid_name 
        400301
        
        I'm using simple default line names here but make sure to use line.up_neighbour.grid_name ....grid_name ..grid_name
        line = flight.children[0]
        line.up_neighbour
        Out[4]: Line-6
        line.down_neighbour # in this case it does not have a down_neighbour so leave empty, or what ever kml uses as "None"
        line.right_neighbour
        Out[6]: Line-34
        line.left_neighbour
        Out[7]: Line-32
        '''
        main_crs = f"EPSG:{main_epsg_int}"
        out_layer_name = flight.long_output_name
        flight_color = flight.color

        # Ensure the directory exists.
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "KML"
        options.fileEncoding = "UTF-8"

        # Create an in-memory layer for LineStrings.
        layer = QgsVectorLayer(f"LineString?crs={main_crs}", out_layer_name, "memory")
        dp = layer.dataProvider()
        layer.startEditing()
        feat = QgsFeature()
        feat.setGeometry(geom)
        dp.addFeatures([feat])
        layer.commitChanges()

        QgsVectorFileWriter.writeAsVectorFormatV3(layer, out_path, QgsCoordinateTransformContext(), options)

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


    def save(self):
        '''---- FLIGHT LENGTH CHECK ----'''
        max_flt_size = self.root.flight_settings.get("max_flight_size", None)
        if max_flt_size is not None:
            over_limit = []
            for tof in self.root.TOF_list:
                for flight in tof.flight_list:
                    total_length = getattr(flight, "total_length", None)
                    if total_length is None and hasattr(flight, "utm_fly_list"):
                        pts = getattr(flight, "utm_fly_list", [])
                        if len(pts) > 1:
                            total_length = sum(
                                (( (pts[i][0] - pts[i-1][0])**2 + (pts[i][1] - pts[i-1][1])**2 )**0.5)
                                for i in range(1, len(pts))
                            )
                        else:
                            total_length = 0
                    if total_length is not None and total_length > max_flt_size:
                        over_limit.append(f"{getattr(flight, 'short_output_name', str(flight))} (length: {total_length:.1f} m)")

            if over_limit:
                msg = (
                    "The following flights exceed the max_flt_size setting ({} m):\n\n".format(max_flt_size) +
                    "\n".join(over_limit) +
                    "\n\nPlease adjust your settings or split these flights before saving."
                )
                QMessageBox.critical(None, "Flight Length Limit Exceeded", msg)
                return

        '''---- CREATING THE OUTPUT PACKAGE FOLDER ----'''
        name = self.root.main_input_name+'_OUTPUT_PACKAGE'
        save_folder = os.path.join(self.root.save_folder_dir_path,name)
        output_package_folder = get_name_of_non_existing_output_file(save_folder)
        os.makedirs(output_package_folder, exist_ok=True)
        print(f"save_folder:{output_package_folder}")

        '''---- SAVING THE PICKLE ----'''
        # NOT IMPLEMENTED
        pickle_file_path = os.path.join(output_package_folder,
                                        self.root.main_input_name+self.root.pickle_ext)

        pickle_file_path = get_name_of_non_existing_output_file(pickle_file_path)
        # NOT IMPLEMENTED ^^^

        '''---- SAVING THE LINES ----'''
        lines_file_path = os.path.join(output_package_folder,
                                        self.root.main_input_name+'_named.shp')
        lines_file_path = get_name_of_non_existing_output_file(lines_file_path)
        self.save_lines_to_file(lines_file_path)

        '''---- SAVING THE 2D KML FLIGHTS ----'''
        if self.root.flight_settings['name_tie_not_flt']:
            tie_or_flt_string = 'tie'
        else:
            tie_or_flt_string = 'flt'
        flights_2D_folder = os.path.join(output_package_folder,
                                        f'2D_kml_{tie_or_flt_string}s_for_'+self.root.main_input_name)
        os.makedirs(flights_2D_folder, exist_ok=True)
        main_epsg_int = self.root.global_crs_target.get('target_crs_epsg_int')
        file_ext = ".kml"
        for tof in self.root.TOF_list:
            # ---------- 1) Collect exportable flights first -------------
            flights_to_save = []
            for flight in tof.flight_list:
                # build geometry from utm_fly_list
                pts = [
                    QgsPointXY(x, y)
                    for x, y in getattr(flight, "utm_fly_list", [])
                    if isinstance(x, (int, float)) and isinstance(y, (int, float))
                ]
                if pts:  # skip empty / bad flights
                    flights_to_save.append(
                        (flight, QgsGeometry.fromPolylineXY(pts))
                    )

            # ---------- 2) Skip empty TOFs (=> no folder is created) ----
            if not flights_to_save:
                continue

            # ---------- 3) Now it is safe to create the TOF folder ------
            tof_folder = os.path.join(flights_2D_folder, str(tof))
            os.makedirs(tof_folder, exist_ok=True)

            # ---------- 4) Write each flight ----------------------------
            for flight, geom in flights_to_save:
                out_path = os.path.join(tof_folder, flight.long_output_name)
                if not out_path.lower().endswith(file_ext):
                    out_path += file_ext

                self.save_kml(
                    geom,
                    out_path,
                    flight,
                    main_epsg_int,
                )

            '''---- COPY OUTPUT_STYLE.QML ----'''
            lines_basename = os.path.splitext(os.path.basename(lines_file_path))[0]
            try:
                # Path to the template QML style file (in your plugin folder)
                plugin_dir = os.path.dirname(__file__)
                template_qml_path = os.path.join(plugin_dir, "output_style.qml")

                # Destination QML name: match the lines file base name
                if not lines_basename.endswith("_named"):
                    lines_basename += "_named"
                qml_copy_path = os.path.join(output_package_folder, lines_basename + ".qml")

                # Copy the file
                import shutil
                shutil.copyfile(template_qml_path, qml_copy_path)
                print(f"Copied output_style.qml to: {qml_copy_path}")
            except Exception as e:
                print(f"Failed to copy output_style.qml: {e}")

        '''---- CLEANUP INTERMEDIATE _split_extended FILES FROM PARENT FOLDER ----'''
        parent_dir = os.path.dirname(output_package_folder)
        delete_intermediate_files(parent_dir)

        self.dock_widget.exitApplication()
        # NOT IMPLEMENTED
        #self.save_state_to_file(pickle_file_path)
        # NOT IMPLEMENTED ^^^
        '''---- IMPORTING THE 2D KML INTO QGIS ----'''
        process_folder(flights_2D_folder)

    def save_state_to_file(self, file_path):
        # NOT IMPLEMENTED
        self.root.plugin_canvas_gui.clear()
        self.root.past_states = []  # remove the list
        root_copy = copy.deepcopy(self.root) # this coppy omits the PluginCanvasGui obj that cant be piclkled
        with open(file_path, 'wb') as file:
            pickle.dump(root_copy, file)
        # NOT IMPLEMENTED ^^^

    def save_lines_to_file(self, lines_file_path: str) -> None:
        """
        Export every Line in self.root.line_groups to a shapefile that contains
            • Grid_Fltln – text (6-char) unique ID for each line
            • Only_use   – boolean, default False
            • Dont_use   – boolean, default False
            • Strip      – text, name of the parent Strip
        The ID is built like:
            4/7  +  line-group index (001-999)  +  line index in group (01-99)
            ► ‘4’ = flight lines   ► ‘7’ = tie lines
        """
        # ------------------------------------------------------------------ #
        # 1)  Basic set-up
        # ------------------------------------------------------------------ #
        os.makedirs(os.path.dirname(lines_file_path), exist_ok=True)
        target_epsg = self.root.global_crs_target.get('target_crs_epsg_int', 4326)
        mem_layer = QgsVectorLayer(
            f"LineString?crs=EPSG:{target_epsg}", "export_lines", "memory"
        )
        dp = mem_layer.dataProvider()

        dp.addAttributes(
            [
                QgsField("Grid_Fltln", QVariant.String, len=6),
                QgsField("Only_use", QVariant.Bool),
                QgsField("Dont_use", QVariant.Bool),
                #QgsField("Strip", QVariant.String, len=80),
            ]
        )
        mem_layer.updateFields()

        # Decide prefix once
        prefix = "7" if self.root.flight_settings.get("name_tie_not_flt") else "4"

        # ------------------------------------------------------------------ #
        # 2)  Build one feature per line
        # ------------------------------------------------------------------ #
        features = []
        for g_idx, group in enumerate(self.root.line_groups, start=1):
            for l_idx, line in enumerate(group.children, start=1):
                # ---- 2a) Geometry ------------------------------------------------
                start_pt = line.start
                end_pt = line.end
                # Accept either (x, y) tuples or objects with .x / .y
                p1 = QgsPointXY(start_pt[0], start_pt[1]) if hasattr(start_pt, "__getitem__") else QgsPointXY(
                    start_pt.x, start_pt.y)
                p2 = QgsPointXY(end_pt[0], end_pt[1]) if hasattr(end_pt, "__getitem__") else QgsPointXY(end_pt.x,
                                                                                                        end_pt.y)
                geom = QgsGeometry.fromPolylineXY([p1, p2])

                # ---- 2b) Attribute values ---------------------------------------
                grid_id = f"{prefix}{g_idx:03d}{l_idx:02d}"  # e.g. 400101
                line.grid_name = grid_id  # keep for later use
                #strip_name = line.get_parent_at_level("STRIP").strip_letter

                feat = QgsFeature(mem_layer.fields())
                feat.setGeometry(geom)
                #feat.setAttributes([grid_id, False, False, strip_name])
                feat.setAttributes([grid_id, False, False])
                features.append(feat)

        dp.addFeatures(features)
        mem_layer.updateExtents()

        # ------------------------------------------------------------------ #
        # --- 3) Write the shapefile to disk ------------------------------- #
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"

        QgsVectorFileWriter.writeAsVectorFormatV3(
            mem_layer,
            lines_file_path,
            QgsCoordinateTransformContext(),
            options,
        )


    def execute_action_on_selected_node(self, command):
        #self.root.plugin_canvas_gui.clear()
        #if len(self.root.past_states) >= 100:
        #    self.root.past_states.pop(0)
        ## Separate the past_states list from self.root
        #past_states = self.root.past_states
        #self.root.past_states = []  # Temporarily remove the list
        #root_copy = copy.deepcopy(self.root)
        ## Reattach the past_states list to both self.root and the copy
        #root_copy.past_states = past_states
        #self.root.past_states = past_states
        #self.root.past_states.append(root_copy)

        if not self.current_selection:
            return
        if command == "give_left":
            self.current_selection.node.give_left()
        if command == "give_right":
            self.current_selection.node.give_right()
        if command == "take_left":
            self.current_selection.node.take_left()
        if command == "take_right":
            self.current_selection.node.take_right()
        if command == "flip_lines":
            self.current_selection.node.flip_lines()

        # Cascade logic
        if command == "take_left_cascade":
            node = self.current_selection.node
            while node is not None:
                node.take_left()
                node = getattr(node, "left_neighbour", None)
        if command == "take_right_cascade":
            node = self.current_selection.node
            while node is not None:
                node.take_right()
                node = getattr(node, "right_neighbour", None)

        self.current_selection.node.display_and_select()

    def remove_highlight(self):
        for node_graphic in self.current_highlights:
            node_graphic.un_highlight()
        self.current_highlights = []

    def remove_selection(self):
        if self.current_selection:
           self.current_selection.un_select()
           self.current_selection = None

    def set_highlight(self, node_graphic):
        if node_graphic not in self.current_highlights:
            self.current_highlights.append(node_graphic)
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

def delete_intermediate_files(folder_path: str, patterns=('split', 'split_extended',)):

    extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.qml']

    try:
        for filename in os.listdir(folder_path):
            for pattern in patterns:
                if filename.endswith(f"_{pattern}.shp"):
                    base_name = os.path.splitext(filename)[0]
                    shp_path = os.path.join(folder_path, filename)

                    try:
                        os.remove(shp_path)
                        print(f"Deleted .shp: {shp_path}")

                        for ext in extensions:
                            other_path = os.path.join(folder_path, base_name + ext)
                            if os.path.exists(other_path):
                                os.remove(other_path)
                                print(f"Deleted: {other_path}")
                    except Exception as e:
                        print(f"Could not delete {shp_path}; skipped associated files. Error: {e}")
    except Exception as outer_e:
        print(f"Failed scanning for split file cleanup in {folder_path}: {outer_e}")

