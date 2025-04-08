import os

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QLabel, QApplication, QAction

from .plugin_tools import get_plugin_name

class CustomNavigationToolbar(NavigationToolbar):
    def __init__(self, canvas, parent, coordinates=True):
        super().__init__(canvas, parent, coordinates)
        self._actions_disabled = False

        # Loop through actions and remove specified ones
        actions = self.findChildren(QAction)
        for action in actions:
            if 'Subplots' in action.text() or 'Save' in action.text() or 'Customize' in action.text():
                self.removeAction(action)
                # No break here as we want to check all actions, not just the first match

    def pan(self, *args):
        super().pan(*args)
        self._toggle_click_handler()

    def zoom(self, *args):
        super().zoom(*args)
        self._toggle_click_handler()

    def _toggle_click_handler(self):
        if self.mode in ['pan/zoom', 'zoom rect']:
            self._actions_disabled = True
        else:
            self._actions_disabled = False

def plot_start():
    matplotlib.use('Qt5Agg')
    fig, ax = plt.subplots(figsize=(10, 7))
    return ax

def plot_show(ax):
    fig = ax.get_figure()
    canvas = FigureCanvas(fig)
    dialog = QDialog()
    dialog.setWindowTitle(get_plugin_name())
    dialog_layout = QVBoxLayout(dialog)
    dialog_layout.addWidget(canvas)
    bottom_bar_layout = QHBoxLayout()
    toolbar = CustomNavigationToolbar(canvas, dialog)
    bottom_bar_layout.addWidget(toolbar)
    bottom_bar_layout.addStretch(1)
    btn_accept = QPushButton("Accept and Save", dialog)
    font = btn_accept.font()
    font.setPointSize(12)
    btn_accept.setFont(font)
    btn_accept.setFixedSize(400, 30)
    btn_accept.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    btn_accept.clicked.connect(dialog.accept)
    bottom_bar_layout.addWidget(btn_accept)
    dialog_layout.addLayout(bottom_bar_layout)
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "plugin_icon.png")))
    result = dialog.exec_() == QDialog.Accepted
    plt.close(fig)
    del dialog
    return result
