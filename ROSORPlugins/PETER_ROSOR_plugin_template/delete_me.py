import os
import sys
import json
from PyQt5.QtWidgets import QWidget, QScrollArea, \
    QVBoxLayout, QHBoxLayout, QGridLayout, \
    QLabel, QLineEdit, QCheckBox, QFileDialog, \
    QGroupBox, QPushButton, QComboBox, QRadioButton, QSizePolicy, QButtonGroup
from PyQt5.QtGui import QFont, QIcon, QColor, QPixmap
from qgis.core import QgsProject
from PyQt5.QtCore import Qt, pyqtSignal, QSize
import subprocess

from . import plugin_tools
from . import plugin_settings_suffixes
from . import plugin_add_custom_buttons

# disable the mouse wheel scrolling through dropdown values. can lead to unintentional value changing
class NoScrollQComboBox(QComboBox):
    def wheelEvent(self, event):
        # Don't do anything on a wheel event to prevent scrolling
        pass

def run(next_app_stage, settings_folder, skip=False, windowtitle=plugin_tools.get_plugin_name()):
    # Get the directory containing the current Python file.
    # This would be the path to the 'PETER_ROSOR_QGIS_PLUGIN' folder.
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    newest_file = plugin_tools.get_newest_file_in(plugin_dir=plugin_dir, folder=settings_folder)
    print(f'loaded newest settings file: {newest_file}')
    change_settings(newest_file, next_app_stage, settings_folder, skip=skip, windowtitle=windowtitle)

def change_settings(set_curr_file, next_app_stage, settings_folder, skip=False, windowtitle='Change Settings'):
    suffixes = plugin_settings_suffixes.get()
    plugin_dir = os.path.dirname(os.path.abspath(__file__))

    if skip:
        next_app_stage(set_curr_file)
        sys.exit()

    with open(set_curr_file) as data:
        parsed_data = json.loads(data.read())

    class DynamicGui(QWidget):
        # Add this line to create a new signal
        settings_updated = pyqtSignal(str)

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
            self.set_icon(os.path.join(plugin_dir, "plugin_icon.png"))  # Set window icon
            self.windowtitle = windowtitle
            self.scrollArea = QScrollArea(self)
            self.scrollArea.setWidgetResizable(True)
            self.mainWidget = QWidget(self.scrollArea)
            self.scrollArea.setWidget(self.mainWidget)
            self.mainLayout = QVBoxLayout(self.mainWidget)
            self.mainWidget.setLayout(self.mainLayout)
            self.radio_buttons = {}  # Store radio buttons groups
            self.initUI()

        def set_icon(self, icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Define the browse_for_json method
        def browse_for_json(self):
            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(self, "Select JSON File", self.settings_folder_path,
                                                       "JSON Files (*.json);;All Files (*)", options=options)
            if file_path:
                print(f'Selected file: {file_path}')
                self.close()
                change_settings(file_path, next_app_stage, settings_folder, skip=skip, windowtitle=windowtitle)

        def play_vid(self, vid_path):
            if os.path.exists(vid_path):
                if os.name == 'nt':  # For Windows
                    os.startfile(vid_path)
                elif os.name == 'posix':  # For macOS and Linux
                    subprocess.call(
                        ('open', vid_path) if sys.platform == 'darwin' else ('xdg-open', vid_path))

        def initUI(self):
            # Create a grid layout for the icon and button
            top_layout = QGridLayout()

            # Create a button for browsing .json files
            self.settings_folder_path = os.path.join(plugin_dir, settings_folder)
            self.video_folder_path = os.path.join(plugin_dir, 'tutorial_vids')
            browse_button = QPushButton("📁 Load previous settings")
            browse_button_font = QFont()
            browse_button_font.setPointSize(12)  # Set the font size
            browse_button.setFont(browse_button_font)  # Apply the font to the button
            browse_button.clicked.connect(self.browse_for_json)
            top_layout.addWidget(browse_button, 0, 0, Qt.AlignTop)  # Add the button to the top left corner

            # Load and set the plugin icon at the top
            icon_path = os.path.join(plugin_dir, "plugin_icon.png")
            icon_label = QLabel(self)
            width_px, height_px = plugin_tools.convert_app_cm_to_px(3, 3)
            icon_pixmap = QPixmap(icon_path).scaled(width_px, height_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_pixmap)
            top_layout.addWidget(icon_label, 0, 1, Qt.AlignCenter)  # Add the icon label to the center

            # Create a button with an image icon
            vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
            vid_button = QPushButton()
            vid_button.setIcon(QIcon(vid_icon_path))
            vid_button.setIconSize(QSize(41, 41))
            vid_button.clicked.connect(lambda: self.play_vid(os.path.join(self.video_folder_path, 'intro.mp4')))
            top_layout.addWidget(vid_button, 0, 2,
                                 Qt.AlignTop | Qt.AlignRight)  # Add the video button to the top right corner

            # Add a stretch to push the icon to the center
            top_layout.setColumnStretch(0, 1)
            top_layout.setColumnStretch(1, 2)
            top_layout.setColumnStretch(2, 1)

            # Add the top layout to the main layout
            self.mainLayout.addLayout(top_layout)

            plugin_add_custom_buttons.add_custom_buttons(self, plugin_dir)

            # Extract all tooltips from the parsed_data
            self.tooltips = {}
            self._extract_tooltips(self.data, self.tooltips)
            self._create_widgets_recursive(self.data, self.mainLayout)

            # Create an Accept button and connect it to an action (to be defined)
            accept_button = QPushButton("Accept")
            accept_button.clicked.connect(self.on_accept)

            # Main layout for the window which will contain the scrollArea and the Accept button
            main_window_layout = QVBoxLayout(self)
            main_window_layout.addWidget(self.scrollArea)
            main_window_layout.addWidget(accept_button)

            self.setLayout(main_window_layout)
            self.setWindowTitle(self.windowtitle)

            width_px, height_px = plugin_tools.convert_app_cm_to_px \
                (self.width_cm, self.height_cm)
            self.resize(width_px, height_px)
            self.move(self.offset_from_corner, self.offset_from_corner)
            self.show()

        def get_key_of_true(self, original_group):
            return next((key for key, value in original_group.items() if value), None)

        def _extract_tooltips(self, data_dict, tooltips):
            for key, value in data_dict.items():
                if "_TOOLTIP" in key:
                    base_key = key.replace("_TOOLTIP", "")
                    tooltips[base_key] = value
                elif isinstance(value, dict):
                    self._extract_tooltips(value, tooltips)  # Recursive call for nested dictionaries

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
            for child in self.findChildren((QLineEdit, QCheckBox, QRadioButton)):
                key = child.objectName()
                original_value = plugin_tools.find_key_in_nested_dict(self.data, key)
                if isinstance(child, QLineEdit):
                    new_value = child.text()
                    # drop quote marks from string. makes file expr ctrl+shift+C easy
                    if new_value.startswith(("'", '"')) and new_value.endswith(("'", '"')):
                        new_value = new_value[1:-1]
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
                elif isinstance(child, QRadioButton):
                    radio_group_key = key.rsplit('_', 1)[0]
                    original_group = plugin_tools.find_key_in_nested_dict(self.data, radio_group_key)
                    original_checked = self.get_key_of_true(original_group)
                    if child.isChecked():
                        new_checked = child.text()
                        if original_checked != new_checked:
                            changes_made = True
                            new_group = original_group.copy()
                            new_group[original_checked] = False
                            new_group[new_checked] = True
                            changes[radio_group_key] = (original_group, new_group)


            newest_file = plugin_tools.get_newest_file_in(plugin_dir=plugin_dir, folder=settings_folder)
            if os.path.normpath(set_curr_file) == os.path.normpath(newest_file):
                using_newest = True
            else:
                using_newest = False

            new_file = plugin_tools.get_next_filename(os.path.dirname(set_curr_file),
                                                      os.path.basename(set_curr_file))

            if changes_made:
                # If there are changes, print them and save to a new settings file
                for k, (orig, new) in changes.items():
                    print(f"Setting: {k} was originally: {orig}, now changed to: {new}")

                with open(new_file, 'w') as f:
                    updated_data = self.data  # Copy the original data
                    for k, (_, new) in changes.items():
                        # This recursive function will update 'updated_data' in-place
                        self.recursive_update(updated_data, k, new)
                    json.dump(updated_data, f, indent=4)

                print(f"Saved new settings file to {new_file}")
                self.output_settings_file_path = new_file
            elif not using_newest:
                with open(new_file, 'w') as f:
                    updated_data = self.data  # Copy the original data
                    for k, (_, new) in changes.items():
                        # This recursive function will update 'updated_data' in-place
                        self.recursive_update(updated_data, k, new)
                    json.dump(updated_data, f, indent=4)
                print(f"Copying old settings file to new file {new_file}")
                self.close()
                change_settings(new_file, next_app_stage, settings_folder, skip=skip, windowtitle=windowtitle)
                self.output_settings_file_path = new_file
            else:
                print("No changes to settings made")
                self.output_settings_file_path = set_curr_file
            #self.close()
            next_app_stage(self.output_settings_file_path)

        def _add_radio_buttons(self, key, value, layout):
            button_group = QButtonGroup(self)
            v_layout = QVBoxLayout()
            v_layout.setContentsMargins(0, 0, 0, 0)

            first = True

            for _keya, _valuea in value.items():
                if first:
                    h_layout = QHBoxLayout()
                    radioButton = QRadioButton(self)
                    radioButton.setText(f"{_keya}")  # Set the text for the radio button
                    radioButton.setChecked(_valuea)  # Set the checked state based on _valuea
                    radioButton.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Set size policy
                    radioButton.setMinimumHeight(20)  # Adjust minimum height
                    radioButton.setMaximumHeight(20)  # Adjust maximum height
                    radioButton.setObjectName(f"{key}_{_keya}")  # Set the object name for later lookup
                    button_group.addButton(radioButton)
                    h_layout.addWidget(radioButton)

                    # Check if there is a corresponding video key
                    video_key = key.replace("_RADIO", "_VIDEO")
                    if video_key in self.data:
                        vid_button = QPushButton()
                        vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
                        vid_button.setIcon(QIcon(vid_icon_path))
                        vid_button.setIconSize(QSize(24, 24))
                        vid_button.setFixedSize(QSize(24, 24))  # Set fixed size to make it square
                        vid_button.clicked.connect(
                            lambda: self.play_vid(os.path.join(self.video_folder_path, self.data[video_key])))
                        h_layout.addWidget(vid_button, alignment=Qt.AlignRight)
                    else:
                        h_layout.addStretch()  # Add spacer to align radio button to the left

                    v_layout.addLayout(h_layout)
                    first = False
                else:
                    radioButton = QRadioButton(self)
                    radioButton.setText(f"{_keya}")  # Set the text for the radio button
                    radioButton.setChecked(_valuea)  # Set the checked state based on _valuea
                    radioButton.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Set size policy
                    radioButton.setMinimumHeight(20)  # Adjust minimum height
                    radioButton.setMaximumHeight(20)  # Adjust maximum height
                    radioButton.setObjectName(f"{key}_{_keya}")  # Set the object name for later lookup
                    button_group.addButton(radioButton)
                    v_layout.addWidget(radioButton)

            self.radio_buttons[key] = button_group  # Store the button group
            layout.addLayout(v_layout)

        def _create_widgets_recursive(self, data_dict, parent_layout):
            for key, value in data_dict.items():
                if "_TOOLTIP" in key:
                    continue
                if isinstance(value, dict):
                    # this is a group or a radio button #if implemented
                    if key.endswith('_RADIO'):
                        groupbox = QGroupBox(key[:-6])
                    else:
                        groupbox = QGroupBox(key)
                    font = groupbox.font()
                    font.setPointSize(self.header_font_size)
                    groupbox.setFont(font)
                    group_layout = QVBoxLayout()
                    groupbox.setLayout(group_layout)
                    parent_layout.addWidget(groupbox)
                    if key.endswith('_RADIO'):
                        self._add_radio_buttons(key, value, group_layout)
                    else:
                        self._create_widgets_recursive(value, group_layout)
                elif not key.endswith('_VIDEO'):
                    self._add_widget_for_value(key, value, parent_layout)

        def _add_widget_for_value(self, key, value, layout):
            ellipsis_font = QFont()
            ellipsis_font.setPointSize(14)
            ellipsis_font.setBold(True)

            # get base key
            base_key = key
            for suffix in suffixes:
                if key.endswith(suffix):
                    base_key = key[:-len(suffix)]
                    break

            field_font = QFont()
            field_font.setPointSize(self.field_font_size)

            tooltip = self.tooltips.get(base_key)

            if "_COMMENT" in key:
                # Display comments as QLabel
                comment_layout = QHBoxLayout()
                spacer_label = QLabel()  # This label will simulate the tabbing
                spacer_label.setFixedWidth(self.spacer)  # Adjust this value for your desired amount of spacing
                comment_label = QLabel(value)
                comment_font = QFont()
                comment_font.setPointSize(self.comment_font_size)
                comment_label.setFont(comment_font)
                if tooltip:
                    comment_label.setToolTip(tooltip)
                # Make the comment appear in grey
                comment_label.setStyleSheet("color: grey;")
                comment_layout.addWidget(spacer_label)
                comment_layout.addWidget(comment_label)
                layout.addLayout(comment_layout)


            elif "_SELECT_LAYER" in key:
                h_layout = QHBoxLayout()
                combobox = NoScrollQComboBox()
                combobox.addItem("previous input")
                index = combobox.findText("previous input")
                italic_font = QFont()
                italic_font.setItalic(True)
                combobox.setItemData(index, italic_font, Qt.FontRole)
                combobox.setItemData(index, QColor("grey"), Qt.ForegroundRole)
                for layer_name in self.get_available_qgis_layers():
                    combobox.addItem(layer_name)
                combobox.currentTextChanged.connect(lambda text, k=key: self.update_textfield_from_dropdown(k, text))

                if tooltip:
                    combobox.setToolTip(tooltip)
                h_layout.addWidget(combobox, 1)
                # Adding a "..." button after the dropdown
                ellipsis_button = QPushButton("...")
                ellipsis_button.setFont(ellipsis_font)
                ellipsis_button.clicked.connect(lambda text, k=key: self.update_textfield_from_layer_file_dialog(k))
                if tooltip:
                    ellipsis_button.setToolTip(tooltip)
                h_layout.addWidget(ellipsis_button)
                layout.addLayout(h_layout)


            elif "_SELECT_FILE" in key:
                h_layout = QHBoxLayout()
                folder_button = QPushButton("...")
                folder_button.setFont(ellipsis_font)
                folder_button.clicked.connect(lambda text, k=key: self.update_textfield_from_file_dialog(k))

                if tooltip:
                    folder_button.setToolTip(tooltip)
                h_layout.addWidget(folder_button)
                layout.addLayout(h_layout)


            elif "_SELECT_FOLDER" in key:
                h_layout = QHBoxLayout()
                folder_button = QPushButton("...")
                folder_button.setFont(ellipsis_font)
                folder_button.clicked.connect(lambda text, k=key: self.update_textfield_from_folder_dialog(k))
                if tooltip:
                    folder_button.setToolTip(tooltip)
                h_layout.addWidget(folder_button)
                layout.addLayout(h_layout)

            elif "_VIDEO" in key:
                # Add a button to play the video next to the existing QLineEdit
                base_key = key.replace("_VIDEO", "")
                line_edit = self.findChild(QLineEdit, base_key)
                if not line_edit:
                    checkbox = self.findChild(QCheckBox, base_key)
                    if checkbox:
                        h_layout = self.findChild(QHBoxLayout, f"layout_{base_key}")
                        if not h_layout:
                            h_layout = QHBoxLayout()
                            h_layout.setObjectName(f"layout_{base_key}")
                            field_font = QFont()
                            field_font.setPointSize(self.field_font_size)
                            checkbox.setFont(field_font)
                            h_layout.addWidget(checkbox)
                            layout.addLayout(h_layout)
                    else:
                        line_edit = QLineEdit(str(value))
                        line_edit.setFont(field_font)
                        line_edit.setObjectName(base_key)  # Set the object name for later lookup
                        line_edit_label = QLabel(base_key)
                        line_edit_label.setFont(field_font)
                        if tooltip:
                            line_edit.setToolTip(tooltip)
                            line_edit_label.setToolTip(tooltip)
                        h_layout = QHBoxLayout()
                        h_layout.setObjectName(f"layout_{base_key}")
                        h_layout.addWidget(line_edit_label)
                        h_layout.addWidget(line_edit)
                        layout.addLayout(h_layout)
                else:
                    h_layout = self.findChild(QHBoxLayout, f"layout_{base_key}")
                vid_button = QPushButton()
                vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
                vid_button.setIcon(QIcon(vid_icon_path))
                vid_button.setIconSize(QSize(24, 24))
                vid_button.setFixedSize(QSize(24, 24))  # Set fixed size to make it square
                vid_button.clicked.connect(lambda: self.play_vid(os.path.join(self.video_folder_path, value)))
                h_layout.addWidget(vid_button)


            else:
                if isinstance(value, bool):
                    # Use QCheckBox for boolean values
                    checkbox = QCheckBox(key)
                    checkbox.setFont(field_font)
                    checkbox.setChecked(value)
                    checkbox.setObjectName(key)
                    if tooltip:
                        checkbox.setToolTip(tooltip)
                    h_layout = QHBoxLayout()
                    h_layout.setObjectName(f"layout_{key}")
                    h_layout.addWidget(checkbox)
                    layout.addLayout(h_layout)
                    if key + "_VIDEO" in self.data:
                        vid_button = QPushButton()
                        vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
                        vid_button.setIcon(QIcon(vid_icon_path))
                        vid_button.setIconSize(QSize(24, 24))
                        vid_button.setFixedSize(QSize(24, 24))  # Set fixed size to make it square
                        vid_button.clicked.connect(
                            lambda: self.play_vid(os.path.join(self.video_folder_path, self.data[key + "_VIDEO"])))
                        h_layout.addWidget(vid_button)
                else:
                    # Use QLineEdit for other types
                    line_edit = QLineEdit(str(value))
                    line_edit.setFont(field_font)
                    line_edit.setObjectName(key)  # Set the object name for later lookup
                    line_edit_label = QLabel(key)
                    line_edit_label.setFont(field_font)
                    if tooltip:
                        line_edit.setToolTip(tooltip)
                        line_edit_label.setToolTip(tooltip)
                    h_layout = QHBoxLayout()
                    h_layout.setObjectName(f"layout_{key}")
                    h_layout.addWidget(line_edit_label)
                    h_layout.addWidget(line_edit)
                    layout.addLayout(h_layout)

        def update_textfield_from_folder_dialog(self, key):
            line_edit = self.findChild(QLineEdit, key.replace("_SELECT_FOLDER", ""))
            current_path = line_edit.text()
            if current_path:
                initial_dir = os.path.dirname(current_path)
            else:
                initial_dir = os.path.expanduser(
                    "~")  # Default to the user's home directory if the current path is empty
            # Open folder dialog
            folderPath = QFileDialog.getExistingDirectory(self, "Select Folder", initial_dir)
            folderPath = folderPath.replace('/', os.sep)
            if folderPath:  # Only update if folderPath is not empty
                line_edit.setText(folderPath)

        def update_textfield_from_layer_file_dialog(self, key):
            line_edit = self.findChild(QLineEdit, key.replace("_SELECT_LAYER", ""))
            current_path = line_edit.text()
            if current_path:
                initial_dir = os.path.dirname(current_path)
            else:
                initial_dir = os.path.expanduser(
                    "~")  # Default to the user's home directory if the current path is empty

            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(self, "Select File", initial_dir,
                                                       "All Files (*);;Text Files (*.txt)", options=options)
            file_path = file_path.replace('/', os.sep)
            if file_path:  # Only update if filePath is not empty
                line_edit.setText(file_path)

        def update_textfield_from_file_dialog(self, key):
            line_edit = self.findChild(QLineEdit, key.replace("_SELECT_FILE", ""))
            current_path = line_edit.text()
            if current_path:
                initial_dir = os.path.dirname(current_path)
            else:
                initial_dir = os.path.expanduser(
                    "~")  # Default to the user's home directory if the current path is empty

            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(self, "Select File", initial_dir,
                                                       "All Files (*);;Text Files (*.txt)", options=options)
            file_path = file_path.replace('/', os.sep)
            if file_path:  # Only update if filePath is not empty
                line_edit.setText(file_path)

        def _reset_combobox_style(self, text):
            sender = self.sender()
            if text != "previous input":
                sender.setStyleSheet("NoScrollQComboBox { color: black; font-style: normal; }")

        def get_available_qgis_layers(self):
            """Retrieve a list of available layer names from the current QGIS project."""
            return [layer.name() for layer in QgsProject.instance().mapLayers().values()]

        def update_textfield_from_dropdown(self, key, selected_value):
            line_edit = self.findChild(QLineEdit, key.replace("_SELECT_LAYER", ""))
            if selected_value == "previous input":
                path_from_json = plugin_tools.find_key_in_nested_dict(self.data, key.replace("_SELECT_LAYER", ""))
                line_edit.setText(path_from_json)
            else:
                # Assuming layers have an attribute 'source' for full path; adjust if needed
                layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == selected_value),
                             None)
                if layer:
                    line_edit.setText(layer.source())

    return DynamicGui(parsed_data)
