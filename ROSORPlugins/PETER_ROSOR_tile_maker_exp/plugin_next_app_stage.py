import os
import shutil
import string

from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsPointXY,
    QgsGeometry,
    QgsFeatureRequest,
    QgsRectangle,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
)
from qgis.PyQt.QtWidgets import QPushButton, QMessageBox, QProgressDialog
from PyQt5.QtCore import QVariant
from qgis.utils import iface

from . import plugin_load_settings
from . import plugin_tools
from . import plotting




def main(settings_path):
    """Entry point for the plugin."""
    settings_dict = plugin_load_settings.run(settings_path)

    # "First Time Setup"
    clipped_grid_path = settings_dict['Clipped Grid']
    do_copy_shp = settings_dict['Output a new file']
    settings_dict = None  # don't use settings_dict from here on

    if do_copy_shp:
        input_path = copy_shp(clipped_grid_path)
        hide_layer_by_path(clipped_grid_path)
    else:
        input_path = clipped_grid_path

    input_layer = get_or_load_layer(input_path)

    apply_style(input_layer)

    success = add_tile_name_attribute(input_layer)
    if not success:
        return

    canvas = iface.mapCanvas()

    # Create and set our custom map tool that handles both hover highlight and merging on click
    hover_merge_tool = HoverHighlightTool(canvas, input_layer)
    canvas.setMapTool(hover_merge_tool)

    # Optionally show a message to user
    #plugin_tools.show_information("Hover over polygons to highlight; click to select.\n"
    #                              "When you have one feature selected, click a *different* feature to merge.")

def hide_layer_by_path(shapefile_path):
    """
    Hides a layer in the QGIS Layers panel if it is already loaded.

    Parameters:
    - shapefile_path (str): The file path to the shapefile.

    Returns:
    - bool: True if the layer was found and hidden, False otherwise.
    """
    # Normalize the input path
    normalized_path = os.path.normpath(shapefile_path).lower()
    print(f"Checking if layer is loaded: {normalized_path}")

    # Iterate through loaded layers and find a matching one
    for layer in QgsProject.instance().mapLayers().values():
        if os.path.normpath(layer.source()).lower() == normalized_path:
            print(f"Layer found: {layer.name()} - Hiding it.")
            iface.layerTreeView().layerTreeModel().rootGroup().findLayer(layer.id()).setItemVisibilityChecked(False)
            return True

    print("Layer not found in the project.")
    return False


def get_or_load_layer(shapefile_path):
    """
    Checks if a layer with the same data source is already loaded,
    otherwise loads it and returns the layer.
    """
    # Normalize the input path
    normalized_path = os.path.normpath(shapefile_path).lower()
    print(f"Checking if layer is already loaded: {normalized_path}")

    # Get the normalized paths of all loaded layers
    loaded_layers = [os.path.normpath(layer.source()).lower() for layer in QgsProject.instance().mapLayers().values()]
    print(f"Loaded layers: {loaded_layers}")

    # Check if the normalized path matches any loaded layer
    for layer in QgsProject.instance().mapLayers().values():
        if os.path.normpath(layer.source()).lower() == normalized_path:
            print("Layer found in project.")
            return layer  # Already loaded

    # If not found, load it
    print("Layer not found. Attempting to load...")
    file_name = os.path.basename(os.path.splitext(shapefile_path)[0])
    layer = QgsVectorLayer(shapefile_path, file_name, "ogr")
    if not layer.isValid():
        raise Exception(f"Could not load layer from: {shapefile_path}")
    QgsProject.instance().addMapLayer(layer)
    print("Layer successfully loaded.")
    return layer

################################################################################
# ADD NAME
################################################################################


def apply_style(layer):
    """
    Applies a style from "style_file.qml" located in the same directory as this script
    to the specified layer. Copies the QML file to the directory of the layer's data source
    and renames it to match the layer's filename for future automatic style application.

    Parameters:
    - layer: QgsVectorLayer to which the style will be applied.
    """
    # Path to the style file in the same directory as this script
    script_dir = os.path.dirname(__file__)
    style_file_path = os.path.join(script_dir, "style_file.qml")

    if not os.path.exists(style_file_path):
        raise FileNotFoundError(f"Style file not found at {style_file_path}")

    # Apply the style to the input layer
    print(f"Applying style from {style_file_path} to layer {layer.name()}")
    layer.loadNamedStyle(style_file_path)
    layer.triggerRepaint()

    # Determine the layer's data source directory and name
    layer_source = layer.dataProvider().dataSourceUri()
    layer_dir, layer_filename = os.path.split(layer_source)
    if not os.path.isdir(layer_dir):
        raise ValueError(f"Could not determine a valid directory for layer source: {layer_source}")

    # Path to the copied QML file next to the input file
    new_style_file_path = os.path.join(layer_dir, f"{os.path.splitext(layer_filename)[0]}.qml")

    # Copy the QML file to the new location
    print(f"Copying style file to {new_style_file_path}")
    shutil.copy(style_file_path, new_style_file_path)

    print(f"Style applied and copied to {new_style_file_path}")

def add_tile_name_attribute(layer):
    """
    Adds a `TILE_NAME` attribute to the input layer based on `row_index` and `col_index`.
    The naming follows an alphanumeric pattern (A1, A2, ..., AA1, AB1, ...).
    Detects and warns the user about duplicates in (row_index, col_index).
    """
    # Show a progress dialog while adding the TILE_NAME attribute
    progress_dialog = QProgressDialog("Adding TILE_NAME attribute, please wait...", None, 0, 0)
    progress_dialog.setWindowTitle("Processing")
    progress_dialog.setWindowModality(Qt.ApplicationModal)
    progress_dialog.setCancelButton(None)
    progress_dialog.show()

    # Check if layer is editable
    if not layer.isEditable():
        print("Starting edit session for the layer.")
        layer.startEditing()

    # Collect all row_index and col_index values
    row_indices = []
    col_indices = []
    row_col_pairs = []
    feature_map = {}

    for feature in layer.getFeatures():
        row_index = int(feature['row_index'])
        col_index = int(feature['col_index'])
        row_indices.append(row_index)
        col_indices.append(col_index)
        row_col_pairs.append((row_index, col_index))
        feature_map[(row_index, col_index)] = feature_map.get((row_index, col_index), []) + [feature.id()]

    # Check for duplicates in (row_index, col_index)
    seen = set()
    duplicates = set(x for x in row_col_pairs if x in seen or seen.add(x))

    if duplicates:
        progress_dialog.close()
        duplicate_pair = list(duplicates)[0]
        duplicate_ids = feature_map[duplicate_pair]
        layer.selectByIds(duplicate_ids)  # Select duplicates in the attribute table
        # Zoom to the extent of the duplicates
        extent = layer.boundingBoxOfSelected()
        iface.mapCanvas().setExtent(extent)
        iface.mapCanvas().refresh()
        iface.showAttributeTable(layer)  # Open the attribute table for the layer
        plugin_tools.show_information(
            f"Duplicate (row_index, col_index): {duplicate_pair}.\n 1 out of {len(duplicates)} duplicate(s)")
        return False

    # Normalize indices to start from 1
    min_row = min(row_indices)
    min_col = min(col_indices)
    row_shift = lambda x: x - min_row + 1
    col_shift = lambda x: x - min_col + 1

    # Generate alphanumeric names
    def row_to_letter(index):
        index = int(index)
        """Converts a 1-based row index to an alphanumeric string (A, B, ..., AA, AB, ..., BA, ...)."""
        letters = string.ascii_uppercase
        name = ""
        while index > 0:
            index -= 1
            name = letters[index % 26] + name
            index //= 26
        return name

    # Add the `TILE_NAME` field if it doesn't exist
    if 'TILE_NAME' not in [field.name() for field in layer.fields()]:
        print("Adding TILE_NAME field to the layer.")
        layer.dataProvider().addAttributes([QgsField('TILE_NAME', QVariant.String)])
        layer.updateFields()

    # Update each feature with the new `TILE_NAME`
    for feature in layer.getFeatures():
        row_index = feature['row_index']
        col_index = feature['col_index']
        shifted_row = row_shift(row_index)
        shifted_col = col_shift(col_index)
        tile_name = f"{row_to_letter(shifted_row)}{int(shifted_col)}"

        print(f"Feature ID {feature.id()}: row_index={row_index}, col_index={col_index}, TILE_NAME={tile_name}")

        # Update the feature
        feature['TILE_NAME'] = tile_name
        layer.updateFeature(feature)

    # Commit changes
    print("Committing changes to the layer.")
    layer.commitChanges()
    layer.triggerRepaint()
    progress_dialog.close()
    return True


################################################################################
# Map Tool: Highlight on Hover, Merge on Second Click
################################################################################
def exit_edit_mode(layer):
    """
    Exit edit mode for the given layer by prompting the user
    to save or discard changes.
    """
    if layer.isEditable():
        # Prompt the user
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Exit Edit Mode")
        msg_box.setText("Do you want to save changes to the layer?")
        msg_box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        response = msg_box.exec()
        if response == QMessageBox.Save:
            # Commit changes
            print("Saving changes...")
            layer.commitChanges()
            add_tile_name_attribute(layer)

        elif response == QMessageBox.Discard:
            # Rollback changes
            print("Discarding changes...")
            layer.rollBack()
        else:
            # Cancel exit
            print("Exit canceled.")
            return False
    return True

from qgis.PyQt.QtWidgets import QMessageBox

class HoverHighlightTool(QgsMapTool):
    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer

        # Track the current highlighted feature (hover)
        self.highlighted_feature_id = None

        # Track selection for merging
        self.selected_ids = []

        # Add an exit button
        self.exit_button = QPushButton("Exit Tool", self.canvas)
        self.exit_button.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.exit_button.setFixedSize(100, 30)
        self.exit_button.move(10, 10)
        self.exit_button.clicked.connect(self.exitTool)

        # Listen for layer removal
        QgsProject.instance().layersWillBeRemoved.connect(self.onLayerRemoved)

    def activate(self):
        super().activate()
        self.canvas.setCursor(Qt.CrossCursor)
        self.exit_button.show()
        print("HoverHighlightTool activated. Hover to highlight; click to select or merge.")

        # Start editing mode if not already active
        if not self.layer.isEditable():
            print("Entering edit mode.")
            self.layer.startEditing()

    def deactivate(self):
        super().deactivate()
        self.clearHighlight()
        self.layer.removeSelection()
        self.selected_ids.clear()
        self.canvas.unsetCursor()
        self.exit_button.hide()

        # Stop editing mode without committing changes
        if self.layer.isEditable():
            print("Exiting edit mode without saving changes.")
            self.layer.rollBack()

        print("HoverHighlightTool deactivated.")

    def onLayerRemoved(self, layer_ids):
        """
        Handle the removal of layers. If the tool's layer is removed, deactivate the tool.
        """
        if self.layer.id() in layer_ids:
            print("Layer removed. Exiting tool.")
            self.layer = None  # Remove reference to the deleted layer
            self.deactivate()
            self.canvas.unsetMapTool(self)
            iface.actionPan().trigger()  # Switch back to the Pan tool
            QMessageBox.warning(None, "Layer Removed", "The layer being edited was removed. Exiting the tool.")

    def canvasMoveEvent(self, event):
        """
        Highlight the feature under the mouse cursor.
        """
        if not self.layer.isValid():
            print("Layer is no longer valid.")
            self.exitTool()
            return

        point = self.toMapCoordinates(event.pos())
        tolerance = 5
        search_rect = QgsRectangle(point.x() - tolerance, point.y() - tolerance,
                                   point.x() + tolerance, point.y() + tolerance)
        request = QgsFeatureRequest().setFilterRect(search_rect).setLimit(1)

        found_feature = None
        for feature in self.layer.getFeatures(request):
            found_feature = feature
            break

        if found_feature:
            print(f"Hovered over feature ID: {found_feature.id()}")
            if self.highlighted_feature_id != found_feature.id():
                self.highlightFeature(found_feature)
        else:
            self.clearHighlight()

    def canvasReleaseEvent(self, event):
        """
        Handle clicks: toggle selection or merge selected features.
        """
        if not self.layer.isValid():
            print("Layer is no longer valid.")
            self.exitTool()
            return

        if event.button() == Qt.LeftButton:
            point = self.toMapCoordinates(event.pos())
            tolerance = 5
            search_rect = QgsRectangle(point.x() - tolerance, point.y() - tolerance,
                                       point.x() + tolerance, point.y() + tolerance)
            request = QgsFeatureRequest().setFilterRect(search_rect).setLimit(1)

            clicked_feature = None
            for f in self.layer.getFeatures(request):
                clicked_feature = f
                break

            if clicked_feature:
                clicked_id = clicked_feature.id()
                print(f"Clicked feature ID: {clicked_id}")

                if clicked_id in self.selected_ids:
                    print(f"Feature ID {clicked_id} unselected.")
                    self.selected_ids.remove(clicked_id)
                    self.layer.selectByIds(self.selected_ids)
                else:
                    print(f"Feature ID {clicked_id} selected.")
                    self.selected_ids.append(clicked_id)
                    self.layer.selectByIds(self.selected_ids)

                    if len(self.selected_ids) == 2:
                        print("Two features selected. Attempting merge...")
                        self.perform_merge()
            else:
                print("Clicked outside any feature.")

        elif event.button() == Qt.RightButton:
            print("Right click detected. Clearing selection.")
            self.selected_ids.clear()
            self.layer.removeSelection()

    def perform_merge(self):
        """
        Merge the two selected polygons in the layer.
        """
        feats = []
        for f in self.layer.getFeatures():
            if f.id() in self.selected_ids:
                feats.append(f)
                if len(feats) == 2:
                    break

        if len(feats) < 2:
            print("Error: Less than two features available for merge.")
            return

        feat1, feat2 = feats
        geom1 = feat1.geometry()
        geom2 = feat2.geometry()

        union_geom = geom1.combine(geom2)

        area1 = geom1.area()
        area2 = geom2.area()
        new_attrs = feat1.attributes() if area1 >= area2 else feat2.attributes()

        print(f"Deleting original features: {feat1.id()} and {feat2.id()}")
        self.layer.deleteFeature(feat1.id())
        self.layer.deleteFeature(feat2.id())

        new_feat = QgsFeature(self.layer.fields())
        new_feat.setAttributes(new_attrs)
        new_feat.setGeometry(union_geom)

        success = self.layer.addFeature(new_feat)
        if success:
            print("Merge successful. New feature added.")
        else:
            print("Merge failed. Could not add new feature.")

        self.layer.triggerRepaint()
        self.selected_ids.clear()
        self.layer.removeSelection()
        print("Merge complete. Selection cleared.")

    def keyPressEvent(self, event):
        """
        Exit the tool when Escape is pressed.
        """
        if event.key() == Qt.Key_Escape:
            print("Escape key pressed. Exiting tool.")
            self.exitTool()

    def highlightFeature(self, feature):
        """
        Highlight a new feature by selecting it temporarily.
        """
        self.clearHighlight()
        self.highlighted_feature_id = feature.id()
        self.layer.selectByIds([self.highlighted_feature_id])
        print(f"Feature ID {self.highlighted_feature_id} highlighted.")

    def clearHighlight(self):
        """
        Clear any existing highlight.
        """
        if self.highlighted_feature_id is not None:
            if self.highlighted_feature_id not in self.selected_ids:
                self.layer.removeSelection()
            print(f"Cleared highlight for feature ID {self.highlighted_feature_id}.")
            self.highlighted_feature_id = None

    def exitTool(self):
        """
        Exit the tool, prompting to save or discard changes, and deactivate the tool.
        """
        print("Exiting HoverHighlightTool.")

        if not exit_edit_mode(self.layer):
            print("User canceled exiting edit mode.")
            return

        self.deactivate()
        self.canvas.unsetMapTool(self)
        iface.actionPan().trigger()  # Switch back to the Pan tool

def copy_shp(input_file_path):
    """
    Copies a shapefile to a new location, ensuring all attributes are preserved.
    The new file name is generated using get_name_of_non_existing_output_file.

    Parameters:
    - input_file_path (str): Path to the input shapefile.

    Returns:
    - str: Path to the copied shapefile.
    """
    def get_name_of_non_existing_output_file(base_filepath, additional_suffix='', new_extension=''):
        """
        Generate a unique file path by adding a version number if needed.
        """
        base, ext = os.path.splitext(base_filepath)
        if new_extension:
            ext = new_extension
        new_out_file_path = f"{base}{additional_suffix}{ext}"

        if not os.path.exists(new_out_file_path):
            return new_out_file_path

        version = 2
        while os.path.exists(f"{base}{additional_suffix}_v{version}{ext}"):
            version += 1
        return f"{base}{additional_suffix}_v{version}{ext}"

    # Ensure the input file exists
    if not os.path.exists(input_file_path):
        raise FileNotFoundError(f"Input file not found: {input_file_path}")

    # Load the input shapefile
    input_layer = QgsVectorLayer(input_file_path, "Input Layer", "ogr")
    if not input_layer.isValid():
        raise ValueError(f"Failed to load the input shapefile: {input_file_path}")

    # Generate a new output file path
    output_file_path = get_name_of_non_existing_output_file(input_file_path)

    # Prepare options for saving
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    options.fileEncoding = "UTF-8"

    # Save the copied shapefile
    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        input_layer,
        output_file_path,
        QgsCoordinateTransformContext(),
        options
    )

    if error[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Failed to save the shapefile: {error[1]}")

    print(f"Shapefile copied to: {output_file_path}")
    return output_file_path