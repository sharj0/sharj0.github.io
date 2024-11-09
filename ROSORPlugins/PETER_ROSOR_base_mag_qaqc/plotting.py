import os

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QLabel, QApplication, QAction

# standard libs
import os
import sys
from datetime import datetime

# other libs
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import colormaps
import matplotlib.dates as mdates
import numpy as np

# "C:\Program Files\QGIS 3.34.3\bin\python-qgis.bat" -m pip install mplcursors --target "C:\Users\pyoty\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\PETER_ROSOR_base_mag_qaqc\plugin_3rd_party_libs"
# deleted all extra dependencies for mplcursors cuz they are already available in qgis
plugin_dir = os.path.dirname(os.path.realpath(__file__))
lib_dir = os.path.join(plugin_dir, 'plugin_3rd_party_libs')
lib_dir not in sys.path and sys.path.insert(0, lib_dir)
import mplcursors


from .functions import (process_folder, get_time_mask_seconds, calculate_differences)


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

def plot_stuff(mag_data_folder,
               color_by_folder,
               sub_sample_base_for_calculations_and_display,
               base_mag_ignore_start_end_mins):
    matplotlib.use('Qt5Agg')
    dialog = QDialog()
    dialog.setWindowTitle("Base Mag QaQc")
    dialog_layout = QVBoxLayout(dialog)
    #fig, ax = plt.subplots(figsize=(10, 7))
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 10), gridspec_kw={'height_ratios': [7, 3]})

    # Format the x-axis with date format
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()

    # Place the x-axis at the top
    ax.xaxis.set_label_position('top')
    ax.xaxis.tick_top()
    # Adjust the spacing between subplots
    plt.subplots_adjust(hspace=0.4)  # hspace controls the vertical space between subplots

    mag_datas = process_folder(mag_data_folder, base_mag_ignore_start_end_mins)

    # Sort the flight times by start time
    mag_datas.sort(key=lambda x: x[0] or datetime.min)

    lines = []

    # LiDAR flight plotting
    current_row = 1
    row_cycle = 5

    colors = colormaps['tab20'].colors
    color_map = {}

    # GNSS plotting
    gnss_row_T = 17  # (row in the graph not the file)
    gnss_row_V = 30  # (row in the graph not the file)

    pdf_base_data = []
    pdf_air_data = []
    for start_time, end_time, flight_name, true_flt_false_base, mag_data in mag_datas:
        parent_folder = os.path.basename(os.path.dirname(flight_name))
        if parent_folder not in color_map:
            color_map[parent_folder] = colors[len(color_map) % len(colors)]
        color = color_map[parent_folder]
        gnss_row = gnss_row_T if 'TM' in os.path.basename(flight_name) else gnss_row_V
        if color_by_folder:
            if true_flt_false_base:
                line, = ax.plot([start_time, end_time], [current_row, current_row], marker='o', label=flight_name,
                                color=color)
            else:

                line, = ax.plot([start_time, end_time], [gnss_row, gnss_row], marker='o', label=flight_name,
                                color=color)
        else:
            if true_flt_false_base:
                line, = ax.plot([start_time, end_time], [current_row, current_row], marker='o', label=flight_name)
            else:
                line, = ax.plot([start_time, end_time], [gnss_row, gnss_row], marker='o', label=flight_name)
        lines.append(line)
        line.mag_data = mag_data
        line.true_flt_false_base = true_flt_false_base
        if not true_flt_false_base:
            sub_sampled_times = mag_data[0][::sub_sample_base_for_calculations_and_display]
            sub_sampled_mag = mag_data[1][::sub_sample_base_for_calculations_and_display]
            line.sub_sampled_times, line.sub_sampled_mag = sub_sampled_times, sub_sampled_mag

            mask_60s = get_time_mask_seconds(sub_sampled_times, 60)
            long_differences = calculate_differences(sub_sampled_mag, mask_60s)
            long_mag_thresh = 3
            line.bad_long_times = sub_sampled_times[long_differences > long_mag_thresh]
            line.bad_long_mags = sub_sampled_mag[long_differences > long_mag_thresh]
            ax.plot(line.bad_long_times, np.full(line.bad_long_times.shape, gnss_row), 'x', markersize=4, color='red')

            mask_15s = get_time_mask_seconds(sub_sampled_times, 15)
            short_differences = calculate_differences(sub_sampled_mag, mask_15s)
            short_mag_thresh = 0.5
            line.bad_short_times = sub_sampled_times[short_differences > short_mag_thresh]
            line.bad_short_mags = sub_sampled_mag[short_differences > short_mag_thresh]
            ax.plot(line.bad_short_times, np.full(line.bad_short_times.shape, gnss_row), 'x', markersize=4, color='red')

            times_mpl, values = line.mag_data[0], line.mag_data[1]
            page = []
            page.append({
                'x': times_mpl, 'y': values,
                'fmt': '.', 'markersize': 1, 'color': 'black', 'label': flight_name
            })
            page.append({
                'x': line.bad_short_times, 'y': line.bad_short_mags,
                'fmt': 'x', 'markersize': 4, 'color': 'red', 'label': flight_name
            })
            page.append({
                'x': line.bad_long_times, 'y': line.bad_long_mags,
                'fmt': 'x', 'markersize': 4, 'color': 'red', 'label': flight_name
            })
            pdf_base_data.append(page)
        else:
            pdf_air_data.append({
                'x': [start_time, end_time], 'y': [current_row, current_row],
                'fmt': 'o', 'color': color, 'label': flight_name
            })
        current_row = (current_row % row_cycle) + 1

    if line.true_flt_false_base:
        ax2.plot(line.mag_data[0], line.mag_data[1], 'g.', markersize=1)
    else:
        ax2.plot(line.mag_data[0], line.mag_data[1], '.', markersize=1, color='black')
        ax2.plot(line.bad_short_times, line.bad_short_mags, 'x', markersize=4, color='red')
        ax2.plot(line.bad_long_times, line.bad_long_mags, 'x', markersize=4, color='red')


    def on_hover(sel):
        sel.annotation.set_text(sel.artist.get_label())
        sel.annotation.get_bbox_patch().set_facecolor(sel.artist.get_color())
        sel.annotation.get_bbox_patch().set_alpha(0.7)
        # Update ax2 with generic data
        ax2.clear()

        times_mpl, values = sel.artist.mag_data[0], sel.artist.mag_data[1]

        if sel.artist.true_flt_false_base:
            ax2.plot(times_mpl, values, 'g.', markersize=1)
        else:
            ax2.plot(times_mpl, values, '.', markersize=1, color='black')
            ax2.plot(sel.artist.bad_short_times, sel.artist.bad_short_mags, 'x', markersize=4, color='red')
            ax2.plot(sel.artist.bad_long_times, sel.artist.bad_long_mags, 'x', markersize=4, color='red')
        fig.canvas.draw_idle()

    cursor = mplcursors.cursor(lines, hover=True)
    cursor.connect("add", on_hover)


    # Set y-ticks and labels
    ax.set_yticks([1, 2, 3, 4, 5, gnss_row_T, gnss_row_V])
    ax.set_yticklabels(['', '', '', '', 'MagArrow Flights', 'SmartMag "T"', 'SmartMag "V"'])
    ax_rot = 10
    # Rotate x-ticks
    ax.tick_params(axis='x', rotation=ax_rot)
    ax2.tick_params(axis='x', rotation=ax_rot)
    plt.tight_layout()


    #ax.set_title(f'plot')
    # Initialize ax2 with some generic data
    ax2.plot([], [])
    canvas = FigureCanvas(fig)
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

    return result, (pdf_base_data, pdf_air_data)
