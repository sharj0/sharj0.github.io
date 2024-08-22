'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

import os
import sys
import json
from PyQt5.QtWidgets import QWidget, QScrollArea, \
    QVBoxLayout, QHBoxLayout, QGridLayout, \
    QLabel, QLineEdit, QCheckBox, QFileDialog, \
    QGroupBox, QPushButton, QComboBox, QRadioButton, QSizePolicy, QButtonGroup, QMenu
from PyQt5.QtGui import QFont, QIcon, QColor, QPixmap
from qgis.core import QgsProject, QgsLayerTreeLayer
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QUrl
from PyQt5.Qt import QDesktopServices
import subprocess

from qgis.utils import iface

from . import plugin_tools
from . import plugin_add_custom_buttons
from .plugin_settings_suffixes import get_suffixes

import re

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


class Setting():
    def __init__(self, key, attributes=None):
        self.key = key
        self.attributes = attributes if attributes else {}

    def __repr__(self):
        return f"Setting: {self.key}, Attributes: {self.attributes}"


class Group:
    def __init__(self, key, children):
        self.key = key
        self.children = children

    def __repr__(self):
        return f"Group: {self.key}, Children: {self.children}"


def get_suffixes():
    return ['_SELECT_FOLDER', '_SELECT_FILE', '_SELECT_LAYER', '_COMMENT', '_TOOLTIP', '_RADIO', '_VIDEO']


def parse_dict(d, suffixes):
    settings = []

    def add_setting(key, value, suffix):
        existing_setting = next((s for s in settings if s.key == key), None)
        if existing_setting:
            existing_setting.attributes[suffix] = value
        else:
            settings.append(Setting(key, {suffix: value}))

    for key, value in d.items():
        if any(key.endswith(suffix) for suffix in suffixes):
            base_key = key
            for suffix in suffixes:
                if key.endswith(suffix):
                    base_key = key[:-len(suffix)]
                    add_setting(base_key, value, suffix)
                    break
        elif isinstance(value, dict):
            children = parse_dict(value, suffixes)
            if any(c.key == key for c in children):
                settings.append(Setting(key, value))
            else:
                settings.append(Group(key, children))
        else:
            settings.append(Setting(key, {'value': value}))

    return settings


def reverse_parse(settings):
    result = {}

    for item in settings:
        if isinstance(item, Group):
            result[item.key] = reverse_parse(item.children)
        elif isinstance(item, Setting):
            for suffix, value in item.attributes.items():
                key = item.key + suffix
                if suffix == 'value':
                    result[item.key] = value
                else:
                    result[key] = value

    return result


def save_as_json(data, file_path):
    with open(file_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)


def get_settings(data):
    suffixes = get_suffixes()
    settings = parse_dict(data, suffixes)

    return settings


def change_settings(set_curr_file, next_app_stage, settings_folder, skip=False, windowtitle='Change Settings'):
    plugin_dir = os.path.dirname(os.path.abspath(__file__))

    if skip:
        next_app_stage(set_curr_file)
        sys.exit()

    with open(set_curr_file) as data:
        parsed_data = json.loads(data.read())

    class DynamicGui(QWidget):
        # Add this line to create a new signal
        settings_updated = pyqtSignal(str)

        def __init__(self, data, iface):
            super().__init__()
            self.data = data
            self.header_font_size = 13  # Font size for sections like "Files" and "Settings"
            self.field_font_size = 12  # Font size for field names
            self.field_font = QFont()
            self.field_font.setPointSize(self.field_font_size)
            self.ellipsis_font = QFont()
            self.ellipsis_font.setPointSize(14)
            self.ellipsis_font.setBold(True)
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
            self.changes_made = False

            """Sharj"""
            self.iface = iface
            """Sharj"""

            self.initUI()

        def set_icon(self, icon_path):
            self.setWindowIcon(QIcon(icon_path))

        def show_context_menu(self, position):
            context_menu = QMenu()
            open_plugin_dir_action = context_menu.addAction("Open Debug File")
            open_plugin_dir_action.triggered.connect(self.open_debug_file)
            open_plugin_dir_action = context_menu.addAction("Open Plugin Directory")
            open_plugin_dir_action.triggered.connect(self.open_plugin_dir)
            context_menu.exec_(self.mapToGlobal(position))

        def open_debug_file(self):
            plug_dir = os.path.dirname(self.settings_folder_path)
            debug_file = os.path.join(plug_dir, '__debug__.txt')
            plug_base_name = os.path.basename(plug_dir)
            output_file = f'debug_{plug_base_name}.py'
            output_dir = os.path.dirname(plug_dir)
            output_path = os.path.join(output_dir, output_file)

            # Read the content of the __debug__.txt file
            with open(debug_file, 'r') as file:
                content = file.read()

            # Replace the placeholder with the plugin base name
            new_content = content.replace('>>>PLUGIN_BASE_NAME<<<', plug_base_name)

            # Write the new content to the output file
            with open(output_path, 'w') as file:
                file.write(new_content)

            # Launch the new .py file using the default OS application
            os.startfile(output_path)

        def open_plugin_dir(self):
            plug_dir = os.path.dirname(self.settings_folder_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(plug_dir))

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

            # Add context menu to the browse button
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self.show_context_menu)

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

            self.settings = get_settings(self.data)

            self._create_widgets_recursive(self.settings, self.mainLayout)

            # Create an Accept button and connect it to an action
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

        def get_available_qgis_layers(self):
            """Retrieve a list of available layer names from the current QGIS project."""
            return [layer.name() for layer in QgsProject.instance().mapLayers().values()]

        def _reset_combobox_style(self, text):
            sender = self.sender()
            if text != "previous input":
                sender.setStyleSheet("NoScrollQComboBox { color: black; font-style: normal; }")

        def get_init_dir(self, setting):
            current_path = setting.attributes['value']
            if current_path:
                initial_dir = os.path.dirname(current_path)
            else:
                # Default to the user's home directory if the current path is empty
                initial_dir = os.path.expanduser("~")

            return initial_dir

        """Sharj Modified"""

        def update_textfield_from_dropdown(self, setting, selected_value):

            #The path delimiters are any garbage QGIS adds in for metadata, having this might break things if the plugins NEED the metadata.
            #Hopefully any and all plugins don't require the metadata in the path
            path_delimiters = r"[|?]"
            if selected_value == "Original selection":
                path_from_json = plugin_tools.find_key_in_nested_dict(self.data,
                                                                      setting.key.replace("_SELECT_LAYER", ""))
                setting.line_edit.setText(path_from_json)

            #Checks for the highlighted layer denoted by QGIS API as "activeLayer()"
            #Note that it only updates when changing settings (it does not live update as you are click a different layer to highlight, you need to swap to another selection and swap back to update)
            elif selected_value == "Highlighted Layer":
                layer = self.iface.activeLayer()
                if layer:

                    #cleans the path to only return the file path and no garbage metadata that might be useful to QGIS
                    cleaned_path = re.split(path_delimiters,layer.source(),1)[0]
                    setting.line_edit.setText(cleaned_path)

            else:
                # Assuming layers have an attribute 'source' for full path; adjust if needed
                layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == selected_value),
                             None)
                if layer:

                    # cleans the path to only return the file path and no garbage metadata that might be useful to QGIS
                    cleaned_path = re.split(path_delimiters, layer.source(), 1)[0]
                    setting.line_edit.setText(cleaned_path)


        """Sharj Modified"""

        def update_textfield_from_file_dialog(self, setting):

            initial_dir = self.get_init_dir(setting)

            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(self, "Select File", initial_dir,
                                                       "All Files (*);;Text Files (*.txt)", options=options)
            if file_path:  # Only update if filePath is not empty
                setting.line_edit.setText(file_path)

        def update_textfield_from_layer_file_dialog(self, setting):
            initial_dir = self.get_init_dir(setting)

            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(self, "Select File", initial_dir,
                                                       "All Files (*);;Text Files (*.txt)", options=options)
            if file_path:  # Only update if filePath is not empty
                setting.line_edit.setText(file_path)

        def update_textfield_from_folder_dialog(self, setting):
            initial_dir = self.get_init_dir(setting)
            # Open folder dialog
            folderPath = QFileDialog.getExistingDirectory(self, "Select Folder", initial_dir)
            if folderPath:  # Only update if folderPath is not empty
                setting.line_edit.setText(folderPath)

        def get_key_of_true(self, original_group):
            return next((key for key, value in original_group.items() if isinstance(value, bool) and value), None)

        def on_accept(self):
            newest_file = plugin_tools.get_newest_file_in(plugin_dir=plugin_dir, folder=settings_folder)
            if os.path.normpath(set_curr_file) == os.path.normpath(newest_file):
                using_newest = True
            else:
                using_newest = False

            new_file = plugin_tools.get_next_filename(os.path.dirname(set_curr_file),
                                                      os.path.basename(set_curr_file))

            if self.changes_made:
                reversed_data = reverse_parse(self.settings)
                save_as_json(reversed_data, new_file)
                print(f"Saved new settings file to {new_file}")
                self.output_settings_file_path = new_file
            elif not using_newest:
                reversed_data = reverse_parse(self.settings)
                save_as_json(reversed_data, new_file)
                print(f"Copying old settings file to new file {new_file}")
                self.close()
                change_settings(new_file, next_app_stage, settings_folder, skip=skip, windowtitle=windowtitle)
                self.output_settings_file_path = new_file
            else:
                print("No changes to settings made")
                self.output_settings_file_path = set_curr_file
            if self.settings[-1].attributes['value']:
                self.close()
            next_app_stage(self.output_settings_file_path)

        def _create_widgets_recursive(self, settings, parent_layout):
            for item in settings:
                if isinstance(item, Group):
                    groupbox = QGroupBox(item.key)
                    font = groupbox.font()
                    font.setPointSize(self.header_font_size)
                    groupbox.setFont(font)
                    group_layout = QVBoxLayout()
                    groupbox.setLayout(group_layout)
                    parent_layout.addWidget(groupbox)
                    self._create_widgets_recursive(item.children, group_layout)
                elif isinstance(item, Setting):
                    self._create_setting_widget_area(item, parent_layout)

        def _add_radio_buttons(self, setting, parent_layout):
            key = setting.key
            value = setting.attributes['_RADIO']

            groupbox = QGroupBox(key)
            font = groupbox.font()
            font.setPointSize(self.header_font_size)
            groupbox.setFont(font)
            group_layout = QVBoxLayout()
            groupbox.setLayout(group_layout)
            parent_layout.addWidget(groupbox)

            button_group = QButtonGroup(self)
            v_layout = QVBoxLayout()
            v_layout.setContentsMargins(0, 0, 0, 0)

            for _keya, _valuea in value.items():
                self._add_radio_button(setting, key, _keya, _valuea, button_group, v_layout)

            self.radio_buttons[key] = button_group  # Store the button group
            group_layout.addLayout(v_layout)

        def _add_radio_button(self, setting, key, _keya, _valuea, button_group, v_layout):
            #special case when there is a comment under the radio button:
            if '_COMMENT' in _keya:
                self._add_comment(v_layout, _valuea)
                return

            radioButton = QRadioButton(self)
            radioButton.setText(f"{_keya}")  # Set the text for the radio button
            radioButton.setChecked(bool(_valuea))  # Set the checked state based on _valuea
            radioButton.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Set size policy
            radioButton.setMinimumHeight(20)  # Adjust minimum height
            radioButton.setMaximumHeight(20)  # Adjust maximum height
            radioButton.setObjectName(f"{key}_{_keya}")  # Set the object name for later lookup
            button_group.addButton(radioButton)
            v_layout.addWidget(radioButton)
            radioButton.toggled.connect(lambda checked, s=setting, k=_keya: self.update_radio_setting(s, k, checked))

        def update_radio_setting(self, setting, key, checked):
            if checked:
                for k in setting.attributes['_RADIO']:
                    if not '_COMMENT' in k:
                        setting.attributes['_RADIO'][k] = (k == key)
                self.changes_made = True
                print(f"Setting: {setting.key} changed to {setting.attributes['_RADIO']}")

        def _add_comment(self, layout, comment):
            # Display comments as QLabel
            comment_layout = QHBoxLayout()
            spacer_label = QLabel()  # This label will simulate the tabbing
            spacer_label.setFixedWidth(self.spacer)  # Adjust this value for your desired amount of spacing
            comment_label = QLabel(comment)
            comment_font = QFont()
            comment_font.setPointSize(self.comment_font_size)
            comment_label.setFont(comment_font)
            # Make the comment appear in grey
            comment_label.setStyleSheet("color: grey;")
            comment_layout.addWidget(spacer_label)
            comment_layout.addWidget(comment_label)
            layout.addLayout(comment_layout)

        def update_bool_setting(self, setting, state):
            setting.attributes['value'] = (state == Qt.Checked)
            self.changes_made = True
            print(f'Setting: {setting.key} changed to {setting.attributes["value"]}')

        def update_text_setting(self, setting, text):
            update_text = False
            if text.startswith("'") and text.endswith("'"):
                text = text[1:-1]
                update_text = True

            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
                update_text = True

            """Sharj"""
            # Gets rid of the "file:///" when someone does copy-paste on a file
            if text.startswith("file:///"):
                text = text[8:]
                update_text = True

            if '/' in text:
                text = text.replace('/', os.sep)
                update_text = True

            if update_text:
                setting.line_edit.setText(text)
                return

            try:
                # Try converting the text to float
                text = int(text)
            except ValueError:
                try:
                    # Try converting the text to float
                    text = float(text)
                except ValueError:
                    # If conversion fails, keep it as a string
                    pass
                pass

            if not setting.attributes['value'] == text or type(setting.attributes['value']) != type(text):
                setting.attributes['value'] = text
                self.changes_made = True
                print(f"Setting: {setting.key} changed to {setting.attributes['value']}")

        def _add_setting_to_setting_area(self, setting, top_layout):
            suffix_list = list(setting.attributes.keys())
            if '_RADIO' in suffix_list:
                if 'value' in suffix_list:
                    raise ValueError(f'.json settings made improperly, cannot have "_RADIO" and "value"')
                self._add_radio_buttons(setting, top_layout)
                return

            # boolean setting
            if isinstance(setting.attributes['value'], bool):
                checkbox = QCheckBox(setting.key)
                checkbox.setFont(self.field_font)
                checkbox.setChecked(setting.attributes['value'])
                checkbox.stateChanged.connect(lambda state, s=setting: self.update_bool_setting(s, state))
                top_layout.addWidget(checkbox)
                return

            text_entry_layout = QVBoxLayout()
            line_edit = plugin_tools.CustomLineEdit(str(setting.attributes['value']))
            line_edit.setFont(self.field_font)
            line_edit.setAcceptDrops(True)
            line_edit.textChanged.connect(lambda text, s=setting: self.update_text_setting(s, text))
            line_edit_label = QLabel(setting.key)
            line_edit_label.setFont(self.field_font)
            setting.line_edit = line_edit
            h_layout = QHBoxLayout()
            h_layout.setObjectName(f"layout_{setting.key}")
            h_layout.addWidget(line_edit_label)
            h_layout.addWidget(line_edit)
            text_entry_layout.addLayout(h_layout)
            top_layout.addLayout(text_entry_layout)

            if '_SELECT_LAYER' in suffix_list:
                h_layout = QHBoxLayout()
                combobox = NoScrollQComboBox()
                italic_font = QFont()
                italic_font.setItalic(True)
                special_buttons = ["Select Layer:", "Original selection", "Highlighted Layer"]
                for index, special_button in enumerate(special_buttons):
                    combobox.addItem(special_button)
                    combobox.setItemData(index, italic_font, Qt.FontRole)
                    combobox.setItemData(index, QColor("grey"), Qt.ForegroundRole)

                for layer_name in self.get_available_qgis_layers():
                    combobox.addItem(layer_name)
                combobox.currentTextChanged.connect(
                    lambda text, k=setting: self.update_textfield_from_dropdown(k, text))

                h_layout.addWidget(combobox, 1)
                # Adding a "..." button after the dropdown
                ellipsis_button = QPushButton("...")
                ellipsis_button.setFont(self.ellipsis_font)
                ellipsis_button.clicked.connect(lambda text, k=setting: self.update_textfield_from_layer_file_dialog(k))
                h_layout.addWidget(ellipsis_button)
                text_entry_layout.addLayout(h_layout)
                return

            if '_SELECT_FILE' in suffix_list:
                h_layout = QHBoxLayout()
                folder_button = QPushButton("...")
                folder_button.setFont(self.ellipsis_font)
                folder_button.clicked.connect(lambda text, k=setting: self.update_textfield_from_file_dialog(k))
                h_layout.addWidget(folder_button)
                text_entry_layout.addLayout(h_layout)
                return

            if '_SELECT_FOLDER' in suffix_list:
                h_layout = QHBoxLayout()
                folder_button = QPushButton("...")
                folder_button.setFont(self.ellipsis_font)
                folder_button.clicked.connect(lambda text, k=setting: self.update_textfield_from_folder_dialog(k))
                h_layout.addWidget(folder_button)
                text_entry_layout.addLayout(h_layout)
                return

        def _add_video_to_setting_area(self, top_layout, vid_name):
            vid_button = QPushButton()
            vid_icon_path = os.path.join(plugin_dir, "vid_icon.png")
            vid_button.setIcon(QIcon(vid_icon_path))
            vid_button.setIconSize(QSize(24, 24))
            vid_button.setFixedSize(QSize(24, 24))  # Set fixed size to make it square
            vid_button.clicked.connect(lambda: self.play_vid(os.path.join(self.video_folder_path, vid_name)))
            top_layout.addWidget(vid_button)

        def _create_setting_widget_area(self, setting, parent_layout):
            '''
            |---------|------|
            | SETTING | VID  |
            |---------|------|
            | COMMENT |      |
            |---------|------|
            '''

            suffix_list = list(setting.attributes.keys())

            # Main layout for the setting widget
            setting_area_layout = QVBoxLayout()

            # Horizontal layout for setting and video
            top_layout = QHBoxLayout()

            self._add_setting_to_setting_area(setting, top_layout)

            if '_VIDEO' in suffix_list:
                self._add_video_to_setting_area(top_layout, setting.attributes['_VIDEO'])

            setting_area_layout.addLayout(top_layout)

            if '_COMMENT' in suffix_list:
                self._add_comment(setting_area_layout, setting.attributes['_COMMENT'])

            parent_layout.addLayout(setting_area_layout)

    return DynamicGui(parsed_data, iface)
