import os

import numpy as np

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import colors
from matplotlib import cm
from matplotlib import ticker
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QLabel, QApplication, QAction

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

def plot_with_colored_segments(surf_samples, regular_spaced, surf_x_coords, surf_y_coords, surf_arr,
                               percent_dist_above_thresh, total_average_slope):
    matplotlib.use('Qt5Agg')
    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Waypoints")
    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)

    fig, ax = plt.subplots(figsize=(10, 7))
    # Use pcolormesh for plotting the surface data
    X, Y = np.meshgrid(surf_x_coords, surf_y_coords)
    c = ax.pcolormesh(X, Y, surf_arr, shading='nearest', cmap='terrain')
    fig.colorbar(c, ax=ax, label='Surface Data')
    # Loop through the datasets
    for indx, (_surf_sample, _regular_spaced) in enumerate(zip(surf_samples, regular_spaced)):
        # Interpolate the y values for regular_spaced data
        _regular_spaced_y = np.interp(_regular_spaced.T[0], _surf_sample.T[0], _surf_sample.T[2])

        # Normalize the color range based on regular_spaced[0].T[1] values
        norm = plt.Normalize(min(regular_spaced[0].T[1]), max(regular_spaced[0].T[1]))

        # Plot each segment with varying thickness if the 5th row value is 1
        for i in range(len(_regular_spaced.T[0]) - 1):
            #first plot non-steep
            if _regular_spaced.T[5][i] == 0:
                segment_x = _regular_spaced.T[3][i:i + 2]
                segment_y = _regular_spaced.T[4][i:i + 2]
                lw = 1.5
                ax.plot(segment_x, segment_y, color='white', linewidth=lw+.3)
                ax.plot(segment_x, segment_y, color='purple', linewidth=lw)

        for i in range(len(_regular_spaced.T[0]) - 1):
            #then plot steep
            if _regular_spaced.T[5][i] == 1:
                segment_x = _regular_spaced.T[3][i:i + 2]
                segment_y = _regular_spaced.T[4][i:i + 2]
                lw = 3
                ax.plot(segment_x, segment_y, color='white', linewidth=lw+.4)
                ax.plot(segment_x, segment_y, color='red', linewidth=lw)

    # Formatting the axis labels
    ax.set_title(f'Steep Dist {round(percent_dist_above_thresh, 2)}%, Ave Slope {round(total_average_slope, 2)}%',
             fontsize=16)
    ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.axis('equal')
    #plt.show()

    canvas = FigureCanvas(fig)
    dialog_layout.addWidget(canvas)

    # Bottom bar layout
    bottom_bar_layout = QHBoxLayout()

    toolbar = CustomNavigationToolbar(canvas, dialog)
    bottom_bar_layout.addWidget(toolbar)

    # Add a stretch first to push everything after it to the right
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
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "Waypoint_Terrain_Follow.png")))

    result = dialog.exec_() == QDialog.Accepted
    plt.close(fig)
    del dialog
    return result

