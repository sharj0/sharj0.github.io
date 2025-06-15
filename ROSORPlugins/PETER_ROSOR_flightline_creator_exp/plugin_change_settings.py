'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

'''UPDATED: 2025-06-14 By: Sharj'''

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


def run(next_app_stage, settings_folder, skip=False, windowtitle=plugin_tools.get_plugin_name()+'       v'+plugin_tools.get_plugin_version()):
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
        # Class Constants
        HEADER_FONT_SIZE = 13
        FIELD_FONT_SIZE = 12
        COMMENT_FONT_SIZE = 10
        ELLIPSIS_FONT_SIZE = 14
        SPACER_WIDTH = 40
        WINDOW_WIDTH_CM = 20
        WINDOW_HEIGHT_CM = 15
        WINDOW_OFFSET_FROM_CORNER = 50
        PLUGIN_ICON_PATH = "plugin_icon.png"
        VIDEO_ICON_PATH = "vid_icon.png"
        INTRO_VIDEO_FILE = "intro.mp4"
        DEBUG_FILENAME = "__debug__.txt"


        # Add this line to create a new signal
        settings_updated = pyqtSignal(str)

        def __init__(self, data, iface):
            super().__init__()
            self.data = data
            self.header_font_size = DynamicGui.HEADER_FONT_SIZE  # Font size for sections like "Files" and "Settings"
            self.field_font = QFont()
            self.field_font.setPointSize(DynamicGui.FIELD_FONT_SIZE)
            self.ellipsis_font = QFont()
            self.ellipsis_font.setPointSize(DynamicGui.ELLIPSIS_FONT_SIZE)
            self.ellipsis_font.setBold(True)
            self.comment_font_size = DynamicGui.COMMENT_FONT_SIZE  # Font size for comments
            self.spacer = DynamicGui.SPACER_WIDTH
            self.width_cm = DynamicGui.WINDOW_WIDTH_CM
            self.height_cm = DynamicGui.WINDOW_HEIGHT_CM
            self.offset_from_corner = DynamicGui.WINDOW_OFFSET_FROM_CORNER
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
            self.child_visibility_controllers = {}  # New: To track all controllers for each child
            self.initialized_visibility = False  # New: Flag to manage initial application
            self.iface = iface

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

            # Setup paths for settings and videos
            self.settings_folder_path = os.path.join(plugin_dir, settings_folder)
            self.video_folder_path = os.path.join(plugin_dir, 'tutorial_vids')

            self._setup_top_panel_widgets()
            plugin_add_custom_buttons.add_custom_buttons(self, plugin_dir)  # External call

            self.settings = get_settings(self.data)
            self._create_widgets_recursive(self.settings, self.mainLayout)

            self._setup_main_window_layout()
            self._apply_initial_visibilities(self.settings)  # Important for initial state

            self.show()

        def _setup_top_panel_widgets(self):
            """Sets up the top panel with browse button, plugin icon, and intro video button."""
            top_grid_layout = QGridLayout()

            # Browse button
            browse_button = QPushButton("📁 Load previous settings")
            browse_button_font = QFont()
            browse_button_font.setPointSize(12)
            browse_button.setFont(browse_button_font)
            browse_button.clicked.connect(self.browse_for_json)
            top_grid_layout.addWidget(browse_button, 0, 0, Qt.AlignTop)

            # Context menu for the window itself, triggered by right-click anywhere on the window
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self.show_context_menu)

            # Plugin icon
            icon_label = QLabel(self)
            width_px, height_px = plugin_tools.convert_app_cm_to_px(3, 3)
            icon_pixmap = QPixmap(os.path.join(plugin_dir, DynamicGui.PLUGIN_ICON_PATH)).scaled(
                width_px, height_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_pixmap)
            top_grid_layout.addWidget(icon_label, 0, 1, Qt.AlignCenter)

            # Video button
            vid_button = QPushButton()
            vid_button.setIcon(QIcon(os.path.join(plugin_dir, DynamicGui.VIDEO_ICON_PATH)))
            vid_button.setIconSize(QSize(41, 41))
            vid_button.clicked.connect(
                lambda: self.play_vid(os.path.join(self.video_folder_path, DynamicGui.INTRO_VIDEO_FILE)))
            top_grid_layout.addWidget(vid_button, 0, 2, Qt.AlignTop | Qt.AlignRight)

            # Stretch to center the icon
            top_grid_layout.setColumnStretch(0, 1)
            top_grid_layout.setColumnStretch(1, 2)
            top_grid_layout.setColumnStretch(2, 1)

            self.mainLayout.addLayout(top_grid_layout)


        def _setup_main_window_layout(self):
            """Sets up the main window layout including scroll area and accept button."""
            main_window_layout = QVBoxLayout(self)
            main_window_layout.addWidget(self.scrollArea)

            accept_button = QPushButton("Accept")
            accept_button.clicked.connect(self.on_accept)
            main_window_layout.addWidget(accept_button)

            self.setLayout(main_window_layout)
            self.setWindowTitle(self.windowtitle)
            width_px, height_px = plugin_tools.convert_app_cm_to_px(
                DynamicGui.WINDOW_WIDTH_CM, DynamicGui.WINDOW_HEIGHT_CM)
            self.resize(width_px, height_px)
            self.move(DynamicGui.WINDOW_OFFSET_FROM_CORNER, DynamicGui.WINDOW_OFFSET_FROM_CORNER)

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



        def update_textfield_from_dropdown(self, setting, selected_value):

            path_delimiters = r"[|?]"
            if selected_value == "Original selection":
                path_from_json = plugin_tools.find_key_in_nested_dict(self.data,
                                                                      setting.key.replace("_SELECT_LAYER", ""))
                setting.line_edit.setText(path_from_json)

            elif selected_value == "Highlighted Layer":
                layer = self.iface.activeLayer()
                if layer:

                    cleaned_path = re.split(path_delimiters,layer.source(),1)[0]
                    setting.line_edit.setText(cleaned_path)

            else:

                layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == selected_value),
                             None)
                if layer:


                    cleaned_path = re.split(path_delimiters, layer.source(), 1)[0]
                    setting.line_edit.setText(cleaned_path)



        def _open_file_dialog(self, setting, dialog_type):
            """
            Opens a QFileDialog (file or directory) and updates the line edit.
            :param setting: The Setting object associated with the line edit.
            :param dialog_type: 'file', 'layer_file', or 'folder'.
            """
            initial_dir = self.get_init_dir(setting)
            options = QFileDialog.Options()
            selected_path = ""

            if dialog_type == 'file' or dialog_type == 'layer_file':
                selected_path, _ = QFileDialog.getOpenFileName(
                    self, "Select File", initial_dir, "All Files (*);;Text Files (*.txt)", options=options)
            elif dialog_type == 'folder':
                selected_path = QFileDialog.getExistingDirectory(
                    self, "Select Folder", initial_dir, options=options)

            if selected_path:
                setting.line_edit.setText(selected_path)

        def update_textfield_from_file_dialog(self, setting):
            self._open_file_dialog(setting, 'file')

        def update_textfield_from_layer_file_dialog(self, setting):
            self._open_file_dialog(setting, 'layer_file')

        def update_textfield_from_folder_dialog(self, setting):
            self._open_file_dialog(setting, 'folder')

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

        def update_checkbox_setting_with_visibility(self, setting, state, controlled_settings, current_group_key=""):
            # First update the checkbox setting
            self.update_bool_setting(setting, state)

            # Then handle visibility of controlled settings
            should_show = (state == Qt.Checked)
            controlling_parent_identifier = f"checkbox_{current_group_key}_{setting.key}" if current_group_key else f"checkbox_{setting.key}"
            for path in controlled_settings:
                self._set_widget_visibility_by_path(path, controlling_parent_identifier, should_show)


        def _apply_initial_visibilities(self, settings_list,  current_group_key=""):
            """Recursively apply initial visibility states based on _CHILDREN and _RADIO controls."""
            for item in settings_list:
                if isinstance(item, Setting):
                    # Checkbox controls
                    if isinstance(item.attributes.get('value'), bool) and '_CHILDREN' in item.attributes:
                        controlled_settings = item.attributes['_CHILDREN']
                        should_show = item.attributes['value']
                        for path in controlled_settings:
                            # Pass a unique identifier for this controlling parent
                            controlling_parent_identifier = f"checkbox_{current_group_key}_{item.key}" if current_group_key else f"checkbox_{item.key}"
                            self._set_widget_visibility_by_path(path, controlling_parent_identifier, should_show)

                    # Radio button controls
                    if '_RADIO' in item.attributes:
                        radio_options = item.attributes['_RADIO']
                        for option_key, option_value in radio_options.items():
                            if option_key.endswith('_CHILDREN'):
                                base_option_key = option_key.replace('_CHILDREN', '')
                                controlled_settings = option_value
                                is_active_radio_option = radio_options.get(base_option_key, False)
                                for path in controlled_settings:
                                    # Pass a unique identifier for this controlling parent
                                    controlling_parent_identifier = f"radio_{current_group_key}_{item.key}_{base_option_key}" if current_group_key else f"radio_{item.key}_{base_option_key}"
                                    self._set_widget_visibility_by_path(path, controlling_parent_identifier, is_active_radio_option)

                elif isinstance(item, Group):
                    # Pass the group's key for correct path identification
                    self._apply_initial_visibilities(item.children, item.key)

            # After all initial visibilities are processed, apply them.
            # This ensures that all controlling parents have registered their state
            # before any widget's visibility is set.
            if not self.initialized_visibility and current_group_key == "": # Only run once at the very top level
                for child_obj_name, controllers in self.child_visibility_controllers.items():
                    any_parent_is_true = any(controllers.values())
                    target_widget = self.findChild(QGroupBox, child_obj_name)
                    if not target_widget:
                        target_widget = self.findChild(QWidget, child_obj_name)
                    if target_widget:
                        target_widget.setVisible(any_parent_is_true)
                self.initialized_visibility = True # Set the flag after initial application

        def _set_widget_visibility_by_path(self, setting_path, controlling_parent_key, should_show):
            """
            Updates the internal visibility state for a widget or groupbox identified by its path,
            considering all controlling parents.
            """
            object_name_to_find = setting_path.replace(" ", "_").replace("/", "_")

            if object_name_to_find not in self.child_visibility_controllers:
                self.child_visibility_controllers[object_name_to_find] = {}

            # Store the state from the specific controlling parent
            self.child_visibility_controllers[object_name_to_find][controlling_parent_key] = should_show

            # Check if any of the controlling parents are true
            any_parent_is_true = any(self.child_visibility_controllers[object_name_to_find].values())

            target_widget = self.findChild(QGroupBox, object_name_to_find)
            if not target_widget:
                target_widget = self.findChild(QWidget, object_name_to_find)

            if target_widget:
                # Apply visibility only during initialization or when live updates
                # This prevents initial visibility from being overridden before all parents are processed
                if self.initialized_visibility or controlling_parent_key != "initial": # Use "initial" as a placeholder for initial calls
                    target_widget.setVisible(any_parent_is_true)
                    # print(f"Set visibility of '{object_name_to_find}' to {any_parent_is_true} (controlled by {controlling_parent_key})")


        def _create_widgets_recursive(self, settings, parent_layout, current_group_key=""):
            """Recursively creates QWidgets for settings and groups."""
            for item in settings:
                if isinstance(item, Group):
                    full_key = f"{current_group_key}/{item.key}" if current_group_key else item.key
                    groupbox = QGroupBox(item.key)
                    groupbox.setObjectName(full_key.replace(" ", "_").replace("/", "_"))  # Ensure valid object name
                    font = groupbox.font()
                    font.setPointSize(DynamicGui.HEADER_FONT_SIZE)  # Use class constant
                    groupbox.setFont(font)
                    group_layout = QVBoxLayout()
                    groupbox.setLayout(group_layout)
                    parent_layout.addWidget(groupbox)
                    self._create_widgets_recursive(item.children, group_layout, full_key)

                elif isinstance(item, Setting):
                    self._create_setting_widget_area(item, parent_layout, current_group_key)

        def _add_radio_buttons(self, setting, parent_layout, current_group_key=""):
            """Adds a group of radio buttons for a setting."""
            group_key = setting.key
            radio_options_data = setting.attributes['_RADIO']

            groupbox = QGroupBox(group_key)
            font = groupbox.font()
            font.setPointSize(DynamicGui.HEADER_FONT_SIZE)  # Use class constant
            groupbox.setFont(font)
            group_layout = QVBoxLayout()
            groupbox.setLayout(group_layout)
            parent_layout.addWidget(groupbox)

            button_group = QButtonGroup(self)
            v_layout = QVBoxLayout()
            v_layout.setContentsMargins(0, 0, 0, 0)

            visibility_controls = {
                base_name: option_value
                for option_name, option_value in radio_options_data.items()
                if option_name.endswith('_CHILDREN')
                   and (base_name := option_name.replace('_CHILDREN', ''))
            }

            for option_label, option_value in radio_options_data.items():
                if option_label.endswith('_COMMENT'):
                    self._add_comment(v_layout, option_value)
                    continue
                if option_label.endswith('_CHILDREN'):  # Handled by visibility_controls, no widget needed
                    continue

                # Create and add radio button
                radio_button = QRadioButton(option_label)
                radio_button.setChecked(bool(option_value))
                button_group.addButton(radio_button)
                v_layout.addWidget(radio_button)

                if option_label in visibility_controls:
                    controlled_settings = visibility_controls[option_label]
                    radio_button.toggled.connect(
                        lambda checked, s=setting, k=option_label, ctrl=controlled_settings,
                               cgk=current_group_key:  # Pass cgk
                        self.update_radio_setting_with_visibility(s, k, checked, ctrl, cgk))  # Pass cgk
                else:
                    radio_button.toggled.connect(
                        lambda checked, s=setting, k=option_label:
                        self.update_radio_setting(s, k, checked))

            self.radio_buttons[group_key] = button_group
            group_layout.addLayout(v_layout)

        def update_radio_setting(self, setting, key, checked):
            """Updates the state of radio buttons within a group."""
            if checked:
                for k in setting.attributes['_RADIO']:
                    if not k.endswith('_COMMENT') and not k.endswith('_CHILDREN'):
                        setting.attributes['_RADIO'][k] = (k == key)
                self.changes_made = True
                print(f"Setting: {setting.key} changed to {setting.attributes['_RADIO']}")

        def update_radio_setting_with_visibility(self, setting, key, checked, controlled_settings, current_group_key=""):
            # Update the radio button state first
            self.update_radio_setting(setting, key, checked)

            # Then handle visibility
            controlling_parent_identifier = f"radio_{current_group_key}_{setting.key}_{key}" if current_group_key else f"radio_{setting.key}_{key}"
            for setting_path in controlled_settings:
                self._set_widget_visibility_by_path(setting_path, controlling_parent_identifier, checked)

        def _add_comment(self, layout, comment):
            """Adds a grey, indented comment label to the layout."""
            comment_layout = QHBoxLayout()
            spacer_label = QLabel()
            spacer_label.setFixedWidth(DynamicGui.SPACER_WIDTH)  # Use class constant
            comment_label = QLabel(comment)
            comment_font = QFont()
            comment_font.setPointSize(DynamicGui.COMMENT_FONT_SIZE)  # Use class constant
            comment_label.setFont(comment_font)
            comment_label.setStyleSheet("color: grey;")
            comment_layout.addWidget(spacer_label)
            comment_layout.addWidget(comment_label)
            layout.addLayout(comment_layout)

        def update_bool_setting(self, setting, state):
            """Updates a boolean setting based on checkbox state."""
            setting.attributes['value'] = (state == Qt.Checked)
            self.changes_made = True
            print(f'Setting: {setting.key} changed to {setting.attributes["value"]}')

        def _clean_input_text(self, text):
            """Cleans input text by removing quotes, 'file:///' prefix, and normalizing path separators."""
            if text.startswith("'") and text.endswith("'"):
                text = text[1:-1]
            elif text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            if text.startswith("file:///"):
                text = text[8:]
            if '/' in text:
                text = text.replace('/', os.sep)
            return text

        def update_text_setting(self, setting, text):
            """Updates a text setting, attempting to convert to int/float if possible."""
            cleaned_text = self._clean_input_text(text)

            converted_text = cleaned_text
            try:
                converted_text = int(cleaned_text)
            except ValueError:
                try:
                    converted_text = float(cleaned_text)
                except ValueError:
                    pass  # Keep as string if neither int nor float

            if not setting.attributes['value'] == converted_text or type(setting.attributes['value']) != type(
                    converted_text):
                setting.attributes['value'] = converted_text
                self.changes_made = True
                print(f"Setting: {setting.key} changed to {setting.attributes['value']}")

        def _add_setting_to_setting_area(self, setting, top_layout, current_group_key=""):
            """Adds a single setting widget (checkbox, radio, or text input) to the provided layout."""
            suffix_list = list(setting.attributes.keys())

            # Handle boolean settings (checkboxes)
            if isinstance(setting.attributes.get('value'), bool):
                controlled_settings = setting.attributes.get('_CHILDREN', [])
                checkbox = QCheckBox(setting.key)
                checkbox.setFont(self.field_font)
                checkbox.setChecked(setting.attributes['value'])

                if controlled_settings:
                    checkbox.stateChanged.connect(
                        lambda state, s=setting, ctrl=controlled_settings, cgk=current_group_key:  # Pass cgk
                        self.update_checkbox_setting_with_visibility(s, state, ctrl, cgk))  # Pass cgk
                else:
                    checkbox.stateChanged.connect(
                        lambda state, s=setting:
                        self.update_bool_setting(s, state))
                top_layout.addWidget(checkbox)  # Changed from top_layout to top_horizontal_layout
                return

            # Handle _RADIO settings
            if '_RADIO' in suffix_list:
                if 'value' in suffix_list:
                    raise ValueError(
                        f'.json settings improperly made: cannot have "_RADIO" and "value" for setting "{setting.key}"')
                self._add_radio_buttons(setting, top_layout, current_group_key)
                return

            text_entry_layout = QVBoxLayout()


            # Dictionary to map suffixes to their respective dialog functions
            dialog_handlers = {
                '_SELECT_FILE': self.update_textfield_from_file_dialog,
                '_SELECT_FOLDER': self.update_textfield_from_folder_dialog,
                '_SELECT_LAYER': self.update_textfield_from_layer_file_dialog,
            }

            # Check for file/folder/layer selection suffixes and add appropriate widgets
            for suffix, handler_func in dialog_handlers.items():
                if suffix in suffix_list:
                    btn_layout = QHBoxLayout()
                    if suffix == '_SELECT_LAYER':
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
                        btn_layout.addWidget(combobox, 1)

                    ellipsis_button = QPushButton("...")
                    ellipsis_button.setFont(self.ellipsis_font)
                    # Use lambda _ for unused argument from clicked signal
                    ellipsis_button.clicked.connect(lambda _, k=setting: handler_func(k))
                    btn_layout.addWidget(ellipsis_button)
                    text_entry_layout.addLayout(btn_layout)
                    break  # Assuming only one SELECT type per setting

            # --- Handle text-based settings (QLineEdit, possibly with file/folder/layer dialogs) ---
            value = setting.attributes.get('value', "")
            line_edit = plugin_tools.CustomLineEdit(str(value))
            line_edit.setFont(self.field_font)
            line_edit.setAcceptDrops(True)
            line_edit.textChanged.connect(lambda text, s=setting: self.update_text_setting(s, text))
            line_edit_label = QLabel(setting.key)
            line_edit_label.setFont(self.field_font)
            setting.line_edit = line_edit  # Store reference for later access

            h_layout = QHBoxLayout()
            h_layout.addWidget(line_edit_label)
            h_layout.addWidget(line_edit)
            text_entry_layout.addLayout(h_layout)
            top_layout.addLayout(text_entry_layout)


        def _add_video_to_setting_area(self, top_layout, vid_name):
            """Adds a video icon button to the provided layout."""
            vid_button = QPushButton()
            vid_icon_path = os.path.join(plugin_dir, DynamicGui.VIDEO_ICON_PATH)  # Use class constant
            vid_button.setIcon(QIcon(vid_icon_path))
            vid_button.setIconSize(QSize(24, 24))
            vid_button.setFixedSize(QSize(24, 24))
            vid_button.clicked.connect(lambda: self.play_vid(os.path.join(self.video_folder_path, vid_name)))
            top_layout.addWidget(vid_button)

        def _create_setting_widget_area(self, setting, parent_layout, current_group_key=""):
            '''
            |---------|------|
            | SETTING | VID  |
            |---------|------|
            | COMMENT |      |
            |---------|------|
            '''

            suffix_list = list(setting.attributes.keys())

            # Create a container widget for the entire setting area
            setting_area_widget = QWidget()
            setting_area_layout = QVBoxLayout(setting_area_widget)
            setting_area_widget.setLayout(setting_area_layout)

            # Set object name for visibility control (e.g., controlled by _CHILDREN)
            widget_object_name = f"{current_group_key}/{setting.key}" if current_group_key else setting.key
            setting_area_widget.setObjectName(widget_object_name.replace(" ", "_").replace("/", "_"))

            # Horizontal layout for the setting input and optional video button
            top_horizontal_layout = QHBoxLayout()

            # Add the core setting widget
            self._add_setting_to_setting_area(setting, top_horizontal_layout, current_group_key)

            # Add video button if specified
            if '_VIDEO' in suffix_list:
                self._add_video_to_setting_area(top_horizontal_layout, setting.attributes['_VIDEO'])

            setting_area_layout.addLayout(top_horizontal_layout)

            # Add comment if specified
            if '_COMMENT' in suffix_list:
                self._add_comment(setting_area_layout, setting.attributes['_COMMENT'])

            # Add the complete setting area widget to the parent layout
            parent_layout.addWidget(setting_area_widget)

    # This line should be outside the class definition, at the end of the `change_settings` function
    # as it's the return value for that function.
    return DynamicGui(parsed_data, iface)
