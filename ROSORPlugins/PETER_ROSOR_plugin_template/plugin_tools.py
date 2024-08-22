'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

import os
from PyQt5.QtGui import QScreen, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import QCoreApplication, QTimer, QEvent, Qt
from PyQt5.QtWidgets import QMessageBox, QLineEdit, QApplication
import re


class CustomLineEdit(QLineEdit):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.double_click_timer = QTimer()
        self.double_click_timer.setSingleShot(True)
        self.double_click_timer.timeout.connect(self.reset_click_count)
        self.click_count = 0

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                self.setText(file_path)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click_count += 1
            if self.click_count == 1:
                self.selectAll()
                self.double_click_timer.start(QApplication.doubleClickInterval())
            elif self.click_count == 2:
                self.double_click_timer.stop()
                self.reset_click_count()
            else:
                super(CustomLineEdit, self).mousePressEvent(event)
        elif event.button() == Qt.RightButton:
            self.setCursorPosition(self.cursorPositionAt(event.pos()))
            super(CustomLineEdit, self).mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            super(CustomLineEdit, self).mousePressEvent(event)

    def reset_click_count(self):
        self.click_count = 0

def get_plugin_name():
    # Get the directory containing the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Path to the metadata.txt file
    metadata_file_path = os.path.join(current_dir, 'metadata.txt')

    # Open the file and search for the name=
    with open(metadata_file_path, 'r') as file:
        for line in file:
            # Remove any leading or trailing whitespace from the line
            line = line.strip()
            if line.startswith('name='):
                return line[len('name='):].strip()
            elif line.startswith('name ='):
                return line[len('name ='):].strip()

    # If the name= line is not found, raise an error
    raise ValueError("name= not found in metadata.txt")

def show_error(mesage):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setText(mesage)
    msg.setWindowTitle("Error")
    msg.setStandardButtons(QMessageBox.Ok)
    retval = msg.exec_()

def show_message(message):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setText(message)
    msg.setWindowTitle("Information")
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec_()

def show_information(message):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setText(message)
    msg.setWindowTitle("Information")
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec_()

def convert_app_cm_to_px(width_cm, height_cm):
    # Assuming this is within your QWidget or QMainWindow subclass
    app = QCoreApplication.instance()
    screen: QScreen = app.primaryScreen()
    dpi = screen.physicalDotsPerInch()
    def cm_to_pixels(cm, dpi):
        inches = cm * 0.393701  # Convert cm to inches
        pixels = inches * dpi   # Convert inches to pixels based on DPI
        return int(pixels)
    # Desired dimensions in centimeters
    width_px = cm_to_pixels(width_cm, dpi)
    height_px = cm_to_pixels(height_cm, dpi)
    return width_px, height_px

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

def find_key_in_nested_dict(nested_dict, search_key):
    if search_key in nested_dict:
        return nested_dict[search_key]

    for key, value in nested_dict.items():
        if isinstance(value, dict):
            result = find_key_in_nested_dict(value, search_key)
            if result is not None:
                return result
    return None

def get_newest_file_in(plugin_dir, folder='settings', filter='.json', time_rounding=10):
    # Construct the path to the 'settings_folder'
    settings_folder_path = os.path.join(plugin_dir, folder)

    # List all files in the settings directory that match the filter
    files = [f for f in os.listdir(settings_folder_path) if f.endswith(filter)]

    # Construct full paths and filter files by modification time
    paths = [os.path.join(settings_folder_path, f) for f in files]
    mod_times = [round(os.path.getmtime(p) / time_rounding) * time_rounding for p in paths]

    # If all modification times are the same, use numeric ending from filenames
    if len(set(mod_times)) == 1:
        def extract_numeric_ending(fname):
            # Extracts the last numeric part of the file name, returns 0 if none is found
            match = re.search(r'(\d+)\.json$', fname)
            return int(match.group(1)) if match else 0

        # Get the file with the highest numeric ending
        highest_numeric_file = max(paths, key=lambda x: extract_numeric_ending(x))
        return highest_numeric_file
    else:
        # Get the file with the latest modification time
        latest_file = max(paths, key=lambda x: os.path.getmtime(x))
        return latest_file