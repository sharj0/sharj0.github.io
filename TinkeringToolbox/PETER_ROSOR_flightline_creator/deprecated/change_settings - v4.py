import os
import sys
import json
import re
from PyQt5.QtWidgets import QWidget, QScrollArea, \
    QSizePolicy, QVBoxLayout, QHBoxLayout, \
    QLabel, QLineEdit, QCheckBox, \
    QFormLayout, QGroupBox, QPushButton, QComboBox
from PyQt5.QtGui import QFont, QIcon, QColor
from qgis.core import QgsProject
from PyQt5.QtCore import Qt

from PETER_ROSOR_QGIS_PLUGIN import gui_tools

def find_key_in_nested_dict(nested_dict, search_key):
    if search_key in nested_dict:
        return nested_dict[search_key]

    for key, value in nested_dict.items():
        if isinstance(value, dict):
            result = find_key_in_nested_dict(value, search_key)
            if result is not None:
                return result
    return None


def get_next_filename(directory, original_filename):
    base, ext = os.path.splitext(original_filename)

    parts = base.split('_')

    if parts[-1].startswith('v') and parts[-1][1:].isdigit():
        # Increment the last part if it's a version number
        version = int(parts[-1][1:])
        parts[-1] = f"v{version + 1}"
    else:
        # Append '_v2' if no version number found
        parts.append('v2')

    # Construct the new base name from parts
    new_base = '_'.join(parts)

    new_filename = f"{new_base}{ext}"

    # Check for existence and adjust if necessary
    while os.path.exists(os.path.join(directory, new_filename)):
        version = int(parts[-1][1:])
        parts[-1] = f"v{version + 1}"
        new_base = '_'.join(parts)
        new_filename = f"{new_base}{ext}"

    return os.path.join(directory, new_filename)

def run():
    # Get the directory containing the current Python file.
    # This would be the path to the 'PETER_ROSOR_QGIS_PLUGIN' folder.
    plugin_dir = os.path.dirname(os.path.abspath(__file__))

    def get_newest_file_in(folder='settings', filter='.json'):
        # Construct the path to the 'settings_folder'
        settings_folder_path = os.path.join(plugin_dir, folder)

        files = os.listdir(settings_folder_path)
        paths = [os.path.join(settings_folder_path, basename) for basename in files if basename[-5:] == filter]
        return max(paths, key=os.path.getmtime)

    newest_file = get_newest_file_in(folder='settings')
    print(f'loaded most recent settings file: {newest_file}')

    with open(newest_file) as data:
        parsed_data = json.loads(data.read())

    class DynamicGui(QWidget):
        def __init__(self, data):
            super().__init__()
            self.data = data
            self.header_font_size = 13  # Font size for sections like "Files" and "Settings"
            self.field_font_size = 12  # Font size for field names
            self.comment_font_size = 10  # Font size for comments
            self.spacer = 40
            self.width_cm = 20
            self.height_cm = 15
            self.offset_from_corner = 50
            self.set_icon(os.path.join(plugin_dir, "rosor_icon.png")) # Set window icon
            self.scrollArea = QScrollArea(self)
            self.scrollArea.setWidgetResizable(True)
            self.mainWidget = QWidget(self.scrollArea)
            self.scrollArea.setWidget(self.mainWidget)
            self.mainLayout = QVBoxLayout(self.mainWidget)
            self.mainWidget.setLayout(self.mainLayout)
            self.initUI()

        def set_icon(self, icon_path):
            self.setWindowIcon(QIcon(icon_path))

        def initUI(self):
            self._create_widgets_recursive(self.data, self.mainLayout)

            # Create an Accept button and connect it to an action (to be defined)
            accept_button = QPushButton("Accept")
            accept_button.clicked.connect(self.on_accept)

            # Main layout for the window which will contain the scrollArea and the Accept button
            main_window_layout = QVBoxLayout(self)
            main_window_layout.addWidget(self.scrollArea)
            main_window_layout.addWidget(accept_button)

            self.setLayout(main_window_layout)
            self.setWindowTitle('Settings')

            width_px, height_px = gui_tools.convert_app_cm_to_px\
                (self.width_cm, self.height_cm)
            self.resize(width_px, height_px)
            self.move(self.offset_from_corner, self.offset_from_corner)
            self.show()

        def recursive_update(self, data_dict, key, new_value):
            if key in data_dict:
                data_dict[key] = new_value
            else:
                for k, v in data_dict.items():
                    if isinstance(v, dict):
                        self.recursive_update(v, key, new_value)

        def _update_nested_dict_value(self, nested_dict, search_key, new_value):
            if search_key in nested_dict:
                nested_dict[search_key] = new_value
                return True

            for key, value in nested_dict.items():
                if isinstance(value, dict):
                    if self._update_nested_dict_value(value, search_key, new_value):
                        return True

            return False

        def on_accept(self):
            changes_made = False
            changes = {}
            for child in self.findChildren((QLineEdit, QCheckBox)):
                key = child.objectName()
                original_value = find_key_in_nested_dict(self.data, key)
                if isinstance(child, QLineEdit):
                    new_value = child.text()
                    try:
                        # Try converting the text to float
                        new_value = float(new_value)
                    except ValueError:
                        # If conversion fails, keep it as a string
                        pass
                    if original_value != new_value:
                        changes_made = True
                        changes[key] = (original_value, new_value)
                elif isinstance(child, QCheckBox):
                    new_value = child.isChecked()
                    if original_value != new_value:
                        changes_made = True
                        changes[key] = (original_value, new_value)

            if changes_made:
                # If there are changes, print them and save to a new settings file
                for k, (orig, new) in changes.items():
                    print(f"Setting: {k} was originally: {orig}, now changed to: {new}")

                newest_file = get_newest_file_in(folder='settings')
                directory = os.path.dirname(newest_file)
                new_file_path = get_next_filename(directory, "settings.json")

                with open(new_file_path, 'w') as f:
                    updated_data = self.data  # Copy the original data
                    for k, (_, new) in changes.items():
                        # This recursive function will update 'updated_data' in-place
                        self.recursive_update(updated_data, k, new)
                    json.dump(updated_data, f, indent=4)

                print(f"Saved new settings file to {new_file_path}")
            else:
                print("No changes to settings made")
            self.close()

        def _create_widgets_recursive(self, data_dict, parent_layout):
            for key, value in data_dict.items():
                if isinstance(value, dict):
                    groupbox = QGroupBox(key)
                    font = groupbox.font()
                    font.setPointSize(self.header_font_size)
                    groupbox.setFont(font)

                    group_layout = QVBoxLayout()
                    groupbox.setLayout(group_layout)
                    parent_layout.addWidget(groupbox)
                    self._create_widgets_recursive(value, group_layout)
                else:
                    self._add_widget_for_value(key, value, parent_layout)

        def _add_widget_for_value(self, key, value, layout):
            field_font = QFont()
            field_font.setPointSize(self.field_font_size)

            if "_comment" in key:
                # Display comments as QLabel
                comment_layout = QHBoxLayout()
                spacer_label = QLabel()  # This label will simulate the tabbing
                spacer_label.setFixedWidth(self.spacer)  # Adjust this value for your desired amount of spacing

                comment_label = QLabel(value)

                comment_font = QFont()
                comment_font.setPointSize(self.comment_font_size)
                comment_label.setFont(comment_font)

                # Make the comment appear in grey
                comment_label.setStyleSheet("color: grey;")

                comment_layout.addWidget(spacer_label)
                comment_layout.addWidget(comment_label)

                layout.addLayout(comment_layout)
            elif "_SELECT_LAYER" in key:
                # Handle _SELECT_LAYER keys to create a dropdown
                combobox = QComboBox()

                # Add "previous input" and style it
                combobox.addItem("previous input")
                index = combobox.findText("previous input")

                italic_font = QFont()  # Default font
                italic_font.setItalic(True)
                combobox.setItemData(index, italic_font, Qt.FontRole)
                combobox.setItemData(index, QColor("grey"), Qt.ForegroundRole)


                for layer_name in self.get_available_qgis_layers():
                    combobox.addItem(layer_name)

                # Connect the dropdown's signal to the update function
                combobox.currentTextChanged.connect(lambda text, k=key: self.update_textfield_from_dropdown(k, text))

                h_layout = QHBoxLayout()
                label = QLabel(key.replace("_SELECT_LAYER", ""))
                h_layout.addWidget(label)
                h_layout.addWidget(combobox)
                layout.addLayout(h_layout)
            else:
                if isinstance(value, bool):
                    # Use QCheckBox for boolean values
                    checkbox = QCheckBox(key)
                    checkbox.setFont(field_font)
                    checkbox.setChecked(value)
                    checkbox.setObjectName(key)
                    layout.addWidget(checkbox)
                else:
                    # Use QLineEdit for other types
                    line_edit = QLineEdit(str(value))
                    line_edit.setFont(field_font)
                    line_edit.setObjectName(key)  # Set the object name for later lookup
                    line_edit_label = QLabel(key)
                    line_edit_label.setFont(field_font)
                    h_layout = QHBoxLayout()
                    h_layout.addWidget(line_edit_label)
                    h_layout.addWidget(line_edit)
                    layout.addLayout(h_layout)

        def get_available_qgis_layers(self):
            """Retrieve a list of available layer names from the current QGIS project."""
            return [layer.name() for layer in QgsProject.instance().mapLayers().values()]

        def update_textfield_from_dropdown(self, key, selected_value):
            line_edit = self.findChild(QLineEdit, key.replace("_SELECT_LAYER", ""))
            if selected_value == "previous input":
                path_from_json = find_key_in_nested_dict(self.data, key.replace("_SELECT_LAYER", ""))
                line_edit.setText(path_from_json)
            else:
                # Assuming layers have an attribute 'source' for full path; adjust if needed
                layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == selected_value),
                             None)
                if layer:
                    line_edit.setText(layer.source())

    return DynamicGui(parsed_data)