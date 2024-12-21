import os
import sys
import json
from PyQt5.QtWidgets import QWidget, QScrollArea, \
    QSizePolicy, QVBoxLayout, QHBoxLayout, \
    QLabel, QLineEdit, QCheckBox, QFileDialog,\
    QFormLayout, QGroupBox, QPushButton
from PyQt5.QtGui import QFont, QIcon
from functools import partial
from . import gui_tools


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
            # Dictionary to store references to QLineEdit objects
            self.line_edits = {}
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

        def on_accept(self):
            # Define what should happen when the Accept button is clicked
            print("Accept button clicked!")
            # For example, you can close the window:
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
                    if "_SELECT_FILE" in key:
                        self._remove_unwanted_line_edit(parent_layout)

        def _remove_unwanted_line_edit(self, layout):
            # Find and remove unwanted QLineEdit
            for i in reversed(range(layout.count())):
                widget = layout.itemAt(i).widget()
                if isinstance(widget, QLineEdit) and widget != self.select_file_line_edit:
                    widget.deleteLater()

        def _add_widget_for_value(self, key, value, layout):
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

            elif "_SELECT_FILE" in key:
                actual_key = key.replace("_SELECT_FILE", "")  # Get the key without the SELECT_FILE suffix

                if actual_key not in self.line_edits:
                    # If the actual key's QLineEdit hasn't been created yet, create it
                    self.line_edits[actual_key] = QLineEdit(self.data.get(actual_key, ""))

                    font = QFont()
                    font.setPointSize(self.field_font_size)
                    self.line_edits[actual_key].setFont(font)

                    select_file_btn = QPushButton("...")
                    select_file_btn.clicked.connect(partial(self._open_file_dialog, actual_key))

                    h_layout = QHBoxLayout()
                    h_layout.addWidget(self.line_edits[actual_key])
                    h_layout.addWidget(select_file_btn)
                    layout.addLayout(h_layout)
            elif key not in self.line_edits:
                # This ensures that keys that are neither comments nor SELECT_FILE will still get line edits
                # Use QLineEdit for other types
                line_edit = QLineEdit(str(value))
                font = QFont()
                font.setPointSize(self.field_font_size)
                line_edit.setFont(font)
                line_edit_label = QLabel(key)
                line_edit_label.setFont(font)

                h_layout = QHBoxLayout()
                h_layout.addWidget(line_edit_label)
                h_layout.addWidget(line_edit)
                layout.addLayout(h_layout)

            else:
                field_font = QFont()
                field_font.setPointSize(self.field_font_size)

                if isinstance(value, bool):
                    # Use QCheckBox for boolean values
                    checkbox = QCheckBox(key)
                    checkbox.setFont(field_font)
                    checkbox.setChecked(value)
                    layout.addWidget(checkbox)
                else:
                    # Use QLineEdit for other types
                    line_edit = QLineEdit(str(value))
                    line_edit.setFont(field_font)
                    line_edit_label = QLabel(key)
                    line_edit_label.setFont(field_font)
                    h_layout = QHBoxLayout()
                    h_layout.addWidget(line_edit_label)
                    h_layout.addWidget(line_edit)
                    layout.addLayout(h_layout)

        def _open_file_dialog(self, key):
            options = QFileDialog.Options()
            file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*)", options=options)
            if file_name:
                self.line_edits[key].setText(file_name)
    return DynamicGui(parsed_data)


