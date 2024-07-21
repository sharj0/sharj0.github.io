import os
import warnings
from functools import partial

# Non-Standard Libraries
import numpy as np
from scipy.interpolate import griddata
from scipy.spatial import cKDTree
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.collections as mcoll
from matplotlib.widgets import Button, RadioButtons, RectangleSelector
from matplotlib.ticker import MultipleLocator, MaxNLocator
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QWidget, QLineEdit, QLabel
from PyQt5.QtGui import QIcon

# PETER_ROSOR_alt_embedder related
from PETER_ROSOR_alt_embedder.tools import extract_2D_subarray_with_buffer

def run(waypoints, dsm, dem, surf_samples, grnd_samples):
    def make_segments(x, y):
        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        return segments

    def colorline(ax, x, y, c, cmap=plt.get_cmap('inferno'), norm=plt.Normalize(0.0, 1.0)):
        c = 1 - (c - np.min(c)) / (np.max(c) - np.min(c))
        segments = make_segments(x, y)
        lc = mcoll.LineCollection(segments, array=c, cmap=cmap, norm=norm, linewidth=2)
        ax.add_collection(lc)
        ax.autoscale()
        ax.margins(0.1)

    def update_waypoints_altitude(waypoints, selected_indices, new_altitude):
        waypoints[selected_indices, 3] = new_altitude

    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Waypoints")

    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)

    matplotlib.use('Qt5Agg')
    # globally accessible variables
    global radio
    # initialize the canopy
    canopy = Canopy()

    # unpacking dsm and dem
    surf_arr, surf_x_coords, surf_y_coords = dsm
    grnd_arr, grnd_x_coords, grnd_y_coords = dem

    # Create the figure
    fig = plt.figure(figsize=(10, 8))

    # ax1 remains the same
    ax1 = plt.subplot2grid((12, 12), (0, 0), rowspan=8, colspan=9)

    # ax2 is now flatter and spans two columns
    ax2 = plt.subplot2grid((12, 12), (9, 0), rowspan=3, colspan=12)

    # ax3 is also flatter and on the top-right
    ax3 = plt.subplot2grid((12, 12), (0, 9), rowspan=3, colspan=3)

    ax4 = plt.subplot2grid((12, 12), (3, 9), rowspan=3, colspan=3)
    ax4.axis('off')  # Turn off the axis since we just want it for positioning text

    edge = 0.07
    other_edge = 1 - edge
    fig.subplots_adjust(left=edge, right=other_edge, top=other_edge, bottom=edge-0.03, wspace=0.2, hspace=0.2)
    ax1.set_adjustable('datalim')
    ax2.set_adjustable('datalim')

    # Plotting on the upper axis (ax1)
    surf_pixel_width = surf_x_coords[1] - surf_x_coords[0]
    surf_pixel_height = surf_y_coords[1] - surf_y_coords[0]
    extent = (surf_x_coords[0],
              surf_x_coords[-1] + surf_pixel_width,
              surf_y_coords[0],
              surf_y_coords[-1] + surf_pixel_height)
    im = ax1.imshow(surf_arr, cmap='terrain', extent=extent, origin='lower')
    cbar = fig.colorbar(im, ax=ax1, orientation='vertical')  # Add a colorbar
    ax1.plot(waypoints[:, 4], waypoints[:, 5], color='purple', marker='.', linewidth=2)
    ax1.tick_params(axis='x', rotation=45)

    # Plotting on the lower axis (ax2)
    ax2.plot(waypoints[:, 0], waypoints[:, 8], color='black', marker='.', ms=3, linewidth=1.3)

    y_waypoints_interpolated = np.interp(grnd_samples[:, 0], waypoints[:, 0], waypoints[:, 3])
    uav_agl = grnd_samples[:, 3] - y_waypoints_interpolated
    colorline(ax2, grnd_samples[:, 0], y_waypoints_interpolated, uav_agl)
    ax2.scatter(surf_samples[:, 0], surf_samples[:, 3], color='green', s=2)
    ax2.scatter(grnd_samples[:, 0], grnd_samples[:, 3], color='brown', s=2)
    ax2.set_aspect('equal')

    # New histogram for surf_samples and grnd_samples on ax3
    data_min = int(np.floor(min(np.min(surf_samples[:, 8]), np.min(grnd_samples[:, 8]))))
    data_max = int(np.ceil(max(np.max(surf_samples[:, 8]), np.max(grnd_samples[:, 8]))))
    target_number_of_bins = 20
    bin_width = int(np.ceil((data_max - data_min) / target_number_of_bins))
    bins = np.arange(data_min, data_max + bin_width + 1, bin_width)

    weights_surf = np.ones_like(surf_samples[:, 8]) / len(surf_samples[:, 8])
    weights_grnd = np.ones_like(grnd_samples[:, 8]) / len(grnd_samples[:, 8])

    ax3.hist(surf_samples[:, 8], bins=bins, color='green', alpha=0.5, label='Surface', weights=weights_surf)
    ax3.hist(grnd_samples[:, 8], bins=bins, color='brown', alpha=0.5, label='Ground', weights=weights_grnd)

    ax3.xaxis.set_major_locator(MaxNLocator(integer=True))
    minor_locator = MultipleLocator(1)
    ax3.xaxis.set_minor_locator(minor_locator)

    yticks = ax3.get_yticks()
    ax3.set_yticks(yticks)
    ax3.set_yticklabels(['{:.0f}%'.format(y * 100) for y in yticks])

    ax3.set_title('Histogram of Altitudes')
    ax3.set_xlabel('Altitude (m)')
    ax3.legend(loc='lower center', bbox_to_anchor=(0.5, -0.62), ncol=2)
    ax3.tick_params(axis='x', rotation=45)
    ax3.grid(True, which='major', axis='both', linestyle='--', linewidth=0.5)
    ax3.tick_params(axis='x', which='major', length=5)

    hover_handler = UAVHover(fig, ax1, ax2, surf_samples, grnd_samples, waypoints)
    fig.canvas.mpl_connect('motion_notify_event', hover_handler.hover)

    hover_handler.text_above_surface = ax4.text(-0.02, -0.13, '',
                                                size=10, color='green', ha='left',
                                                transform=ax4.transAxes)

    hover_handler.text_above_ground = ax4.text(-0.02, -0.77, '',
                                               size=10, color='brown', ha='left',
                                               transform=ax4.transAxes)

    hover_handler.text_canopy_height = ax4.text(-0.02, -1.04, '',
                                                size=10, color='blue', ha='left',
                                                transform=ax4.transAxes)

    hover_handler.text_above_surface.set_text(
        f"Sensor altitude above surface:\n"
        f"Max: {hover_handler.max_alt_surface:.2f}\n"
        f"Median: {hover_handler.median_alt_surface:.2f}\n"
        f"Min: {hover_handler.min_alt_surface:.2f}\n"
        f"At cursor: "
    )

    hover_handler.text_above_ground.set_text(
        f"Sensor altitude above ground:\n"
        f"Max: {hover_handler.max_alt_ground:.2f}\n"
        f"Median: {hover_handler.median_alt_ground:.2f}\n"
        f"Min: {hover_handler.min_alt_ground:.2f}\n"
        f"At cursor: "
    )

    hover_handler.text_canopy_height.set_text(f"Canopy height:\n"
                                              f"At cursor: ")

    def update_image_and_colorbar(ax, arr, waypoints, extent, cbar, hover_handler):
        cbar.remove()
        im = ax.imshow(arr, cmap='terrain', extent=extent, origin='lower')
        cbar = fig.colorbar(im, ax=ax, orientation='vertical')
        ax.plot(waypoints[:, 4], waypoints[:, 5], color='purple', marker='.', linewidth=2)
        hover_handler.set_data(arr, waypoints)
        fig.canvas.draw()

    def radio_button_handler(label, ax, surf_arr, grnd_arr, surf_x_coords, surf_y_coords, cbar, waypoints, hover_handler):
        if label == 'Surface':
            update_image_and_colorbar(ax, surf_arr, waypoints, extent, cbar, hover_handler)
        elif label == 'Ground':
            update_image_and_colorbar(ax, grnd_arr, waypoints, extent, cbar, hover_handler)
        elif label == 'Difference':
            difference = surf_arr - grnd_arr
            update_image_and_colorbar(ax, difference, waypoints, extent, cbar, hover_handler)

    radio_button_handler_partial = partial(radio_button_handler, ax=ax1, surf_arr=surf_arr, grnd_arr=grnd_arr,
                                           surf_x_coords=surf_x_coords, surf_y_coords=surf_y_coords, cbar=cbar,
                                           waypoints=waypoints, hover_handler=hover_handler)

    ax_radio = plt.subplot2grid((12, 12), (6, 9), rowspan=1, colspan=3)
    radio = RadioButtons(ax_radio, ('Surface', 'Ground', 'Difference'))
    radio.on_clicked(radio_button_handler_partial)

    # Setting up buttons in dialog
    # Accept Button
    accept_button = QPushButton("Accept Waypoints", dialog)
    accept_button.setToolTip('Accept and proceed with the current waypoints.')
    accept_button.setIcon(QIcon('accept_icon.png'))  # Assuming you have an accept icon
    accept_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # Redo Button
    redo_button = QPushButton("Redo Waypoints", dialog)
    redo_button.setToolTip('Redo the waypoint selection process.')
    redo_button.setIcon(QIcon('redo_icon.png'))  # Assuming you have a redo icon
    redo_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # Add canvas to the layout
    canvas = FigureCanvas(fig)
    toolbar = NavigationToolbar(canvas, dialog)

    dialog_layout.addWidget(toolbar)
    dialog_layout.addWidget(canvas)

    # Button layout
    button_layout = QHBoxLayout()
    button_layout.addWidget(accept_button)
    button_layout.addWidget(redo_button)

    # Altitude input layout
    altitude_layout = QHBoxLayout()
    altitude_label = QLabel("Set Altitude:", dialog)
    altitude_input = QLineEdit(dialog)
    altitude_input.setPlaceholderText("Enter new altitude")
    altitude_layout.addWidget(altitude_label)
    altitude_layout.addWidget(altitude_input)

    # Add button layout to the dialog layout
    dialog_layout.addLayout(altitude_layout)
    dialog_layout.addLayout(button_layout)

    # Initialize selected indices
    selected_indices = []

    # RectangleSelector callback functions
    def on_select(eclick, erelease):
        nonlocal selected_indices
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        selected_indices = np.where((waypoints[:, 4] >= min(x1, x2)) & (waypoints[:, 4] <= max(x1, x2)) &
                                    (waypoints[:, 5] >= min(y1, y2)) & (waypoints[:, 5] <= max(y1, y2)))[0]

    # Create RectangleSelector
    rect_selector = RectangleSelector(ax1, on_select, useblit=True,
                                      button=[1],  # Left mouse button
                                      minspanx=5, minspany=5, spancoords='pixels',
                                      interactive=True)

    # Connect the set altitude functionality to the text input box
    def set_altitude():
        try:
            new_altitude = float(altitude_input.text())
            update_waypoints_altitude(waypoints, selected_indices, new_altitude)
            ax1.clear()
            ax2.clear()
            ax3.clear()
            ax4.clear()
            # Redraw plots with updated waypoints
            im = ax1.imshow(surf_arr, cmap='terrain', extent=extent, origin='lower')
            cbar = fig.colorbar(im, ax=ax1, orientation='vertical')  # Add a colorbar
            ax1.plot(waypoints[:, 4], waypoints[:, 5], color='purple', marker='.', linewidth=2)
            ax1.tick_params(axis='x', rotation=45)

            ax2.plot(waypoints[:, 0], waypoints[:, 8], color='black', marker='.', ms=3, linewidth=1.3)

            y_waypoints_interpolated = np.interp(grnd_samples[:, 0], waypoints[:, 0], waypoints[:, 3])
            uav_agl = grnd_samples[:, 3] - y_waypoints_interpolated
            colorline(ax2, grnd_samples[:, 0], y_waypoints_interpolated, uav_agl)
            ax2.scatter(surf_samples[:, 0], surf_samples[:, 3], color='green', s=2)
            ax2.scatter(grnd_samples[:, 0], grnd_samples[:, 3], color='brown', s=2)
            ax2.set_aspect('equal')

            data_min = int(np.floor(min(np.min(surf_samples[:, 8]), np.min(grnd_samples[:, 8]))))
            data_max = int(np.ceil(max(np.max(surf_samples[:, 8]), np.max(grnd_samples[:, 8]))))
            target_number_of_bins = 20
            bin_width = int(np.ceil((data_max - data_min) / target_number_of_bins))
            bins = np.arange(data_min, data_max + bin_width + 1, bin_width)

            weights_surf = np.ones_like(surf_samples[:, 8]) / len(surf_samples[:, 8])
            weights_grnd = np.ones_like(grnd_samples[:, 8]) / len(grnd_samples[:, 8])

            ax3.hist(surf_samples[:, 8], bins=bins, color='green', alpha=0.5, label='Surface', weights=weights_surf)
            ax3.hist(grnd_samples[:, 8], bins=bins, color='brown', alpha=0.5, label='Ground', weights=weights_grnd)

            ax3.xaxis.set_major_locator(MaxNLocator(integer=True))
            minor_locator = MultipleLocator(1)
            ax3.xaxis.set_minor_locator(minor_locator)

            yticks = ax3.get_yticks()
            ax3.set_yticks(yticks)
            ax3.set_yticklabels(['{:.0f}%'.format(y * 100) for y in yticks])

            ax3.set_title('Histogram of Altitudes')
            ax3.set_xlabel('Altitude (m)')
            ax3.legend(loc='lower center', bbox_to_anchor=(0.5, -0.62), ncol=2)
            ax3.tick_params(axis='x', rotation=45)
            ax3.grid(True, which='major', axis='both', linestyle='--', linewidth=0.5)
            ax3.tick_params(axis='x', which='major', length=5)

            hover_handler.set_data(surf_arr, waypoints)
            hover_handler.text_above_surface.set_text(
                f"Sensor altitude above surface:\n"
                f"Max: {hover_handler.max_alt_surface:.2f}\n"
                f"Median: {hover_handler.median_alt_surface:.2f}\n"
                f"Min: {hover_handler.min_alt_surface:.2f}\n"
                f"At cursor: "
            )

            hover_handler.text_above_ground.set_text(
                f"Sensor altitude above ground:\n"
                f"Max: {hover_handler.max_alt_ground:.2f}\n"
                f"Median: {hover_handler.median_alt_ground:.2f}\n"
                f"Min: {hover_handler.min_alt_ground:.2f}\n"
                f"At cursor: "
            )

            hover_handler.text_canopy_height.set_text(f"Canopy height:\n"
                                                      f"At cursor: ")

            fig.canvas.draw()
        except ValueError:
            print("Invalid altitude value. Please enter a valid number.")

    # Connect the button to the function
    altitude_input.returnPressed.connect(set_altitude)

    # Show the dialog
    dialog.exec_()
    dialog.show()

    if hasattr(dialog, "result"):
        dialog_result = dialog.result()
    else:
        dialog_result = dialog.result

    return waypoints, dialog_result

class UAVHover:
    def __init__(self, fig, ax_target, ax_source, surf_samples, grnd_samples, waypoints):
        self.figure = fig
        self.ax_target = ax_target
        self.ax_source = ax_source
        self.surf_samples = surf_samples
        self.grnd_samples = grnd_samples
        self.waypoints = waypoints
        self.uav_map_pos_show = None
        self.ground_point = None
        self.surf_point = None
        self.interpolated_point = None

        # Compute statistics for altitude above surface
        self.max_alt_surface = np.max(surf_samples[:, 8])
        self.median_alt_surface = np.median(surf_samples[:, 8])
        self.min_alt_surface = np.min(surf_samples[:, 8])

        # Compute statistics for altitude above ground
        self.max_alt_ground = np.max(grnd_samples[:, 8])
        self.median_alt_ground = np.median(grnd_samples[:, 8])
        self.min_alt_ground = np.min(grnd_samples[:, 8])

    def redraw_uav_marker(self):
        if self.uav_map_pos_show:
            x, y = self.uav_map_pos_show.get_position()
            angle = self.uav_map_pos_show.get_rotation()
            self.uav_map_pos_show = self.ax_target.text(x, y, ' ', ha='center', va='center',
                                                        rotation=angle, fontsize=12, color='red',
                                                        bbox=dict(boxstyle="rarrow,pad=0.01", lw=1, facecolor='white'))

    def hover(self, event):
        ax2_surf_coord = (0, 0)  # Default value
        ax2_grnd_coord = (0, 0)  # Default value

        if not event.inaxes == self.ax_source:
            # Check and remove the ground point
            if self.ground_point and self.ground_point in self.ax_source.lines:
                self.ground_point.remove()
                self.ground_point = None

            # Check and remove the surf point
            if self.surf_point and self.surf_point in self.ax_source.lines:
                self.surf_point.remove()
                self.surf_point = None

            # Check and remove the int_point
            if self.interpolated_point and self.interpolated_point in self.ax_source.lines:
                self.interpolated_point.remove()
                self.interpolated_point = None

            plt.draw()
            return

        # Get the closest index from surf_samples and grnd_samples based on event.xdata
        idx_surf = (np.abs(self.surf_samples[:, 0] - event.xdata)).argmin()
        idx_grnd = (np.abs(self.grnd_samples[:, 0] - event.xdata)).argmin()

        dist_surf = np.abs(self.surf_samples[idx_surf, 0] - event.xdata)
        dist_grnd = np.abs(self.grnd_samples[idx_grnd, 0] - event.xdata)

        # Determine which sample (ground or surface) is closer to the hover event
        if dist_surf < dist_grnd:
            x, y, angle = self.surf_samples[idx_surf, 4], self.surf_samples[idx_surf, 5], self.surf_samples[idx_surf, 7]
        else:
            x, y, angle = self.grnd_samples[idx_grnd, 4], self.grnd_samples[idx_grnd, 5], self.grnd_samples[idx_grnd, 7]

        # Update the UAV marker on ax1
        if not self.uav_map_pos_show:
            self.uav_map_pos_show = self.ax_target.text(x, y, ' ', ha='center', va='center',
                                                        rotation=angle, fontsize=12, color='red',
                                                        bbox=dict(boxstyle="rarrow,pad=0.01", lw=1, facecolor='white'))
        else:
            self.uav_map_pos_show.set_x(x)
            self.uav_map_pos_show.set_y(y)
            self.uav_map_pos_show.set_rotation(angle)

            # Update the ground point using ax2_grnd_coord
            ax2_y_ground = self.grnd_samples[idx_grnd, 3]
            ax2_grnd_coord = (self.grnd_samples[idx_grnd, 0], ax2_y_ground)
            if ax2_y_ground:
                if not self.ground_point:
                    self.ground_point, = self.ax_source.plot(ax2_grnd_coord[0], ax2_grnd_coord[1], 'o', color='brown',
                                                             markeredgecolor='black', markersize=5)
                else:
                    self.ground_point.set_data(ax2_grnd_coord[0], ax2_grnd_coord[1])

            # Get the closest index from surf_samples based on event.xdata
            differences_surf = np.abs(self.surf_samples[:, 0] - event.xdata)
            sorted_indices_surf = np.argsort(differences_surf)
            top_4_indices_surf = sorted_indices_surf[:4]

            # for display purposes
            # Get the y-values of the 4 closest points and select the highest one as long as it is within 2m
            y_values_surf = self.surf_samples[top_4_indices_surf, 3]
            x_values_surf = self.surf_samples[top_4_indices_surf, 0]
            x_dist_away = np.abs(x_values_surf - x_values_surf[0])
            mask_too_far = x_dist_away < 2
            y_values_surf = y_values_surf[mask_too_far]
            # x_values_surf = x_values_surf[mask_too_far] not needed further
            ax2_y_surf = np.max(y_values_surf)
            ax2_surf_coord = (self.surf_samples[idx_surf, 0], ax2_y_surf)

            # Update the surf point using ax2_surf_coord
            if ax2_y_surf:
                if not self.surf_point:
                    self.surf_point, = self.ax_source.plot(ax2_surf_coord[0], ax2_surf_coord[1], 'o', color='green',
                                                           markeredgecolor='black', markersize=5)
                else:
                    self.surf_point.set_data(ax2_surf_coord[0], ax2_surf_coord[1])

        # Interpolated point on the waypoints line
        x_interpolated = np.clip(event.xdata, self.waypoints[:, 0].min(), self.waypoints[:, 0].max())
        y_interpolated = np.interp(x_interpolated, self.waypoints[:, 0], self.waypoints[:, 3])

        # Update or plot the interpolated point
        if not self.interpolated_point:
            self.interpolated_point, = self.ax_source.plot(x_interpolated, y_interpolated, 'o', color='purple',
                                                           markeredgecolor='black', markersize=5)
        else:
            self.interpolated_point.set_data(x_interpolated, y_interpolated)

        alt_above_surface = y_interpolated - ax2_surf_coord[1]
        alt_above_ground = y_interpolated - ax2_grnd_coord[1]
        canopy_height = ax2_surf_coord[1] - ax2_grnd_coord[1]


        # Update only the 'At cursor:' part for altitude above surface and above ground
        self.text_above_surface.set_text(
            f"Sensor altitude above surface:\n"
            f"Max: {self.max_alt_surface:.2f}\n"
            f"Median: {self.median_alt_surface:.2f}\n"
            f"Min: {self.min_alt_surface:.2f}\n"
            f"At cursor: {alt_above_surface:.2f}"
        )

        self.text_above_ground.set_text(
            f"Sensor altitude above ground:\n"
            f"Max: {self.max_alt_ground:.2f}\n"
            f"Median: {self.median_alt_ground:.2f}\n"
            f"Min: {self.min_alt_ground:.2f}\n"
            f"At cursor: {alt_above_ground:.2f}"
        )

        self.text_canopy_height.set_text(f"Canopy height:\n"
                                         f"At cursor: {canopy_height:.2f}")

        plt.draw()

class Canopy():
    def __init__(self):
        self.diff_arr = None
        self.diff_x_coords = None
        self.diff_y_coords = None

def get_extent_from_coords(x_coords, y_coords):
    pixel_width = x_coords[1] - x_coords[0]
    pixel_height = y_coords[1] - y_coords[0]
    return (x_coords[0],
            x_coords[-1] + pixel_width,
            y_coords[0],
            y_coords[-1] + pixel_height)

def update(val):
    global radio
    choice = radio.value_selected
    if choice == 'Surface':
        ax1.imshow(surf_arr, cmap='terrain', extent=extent, origin='lower')
    elif choice == 'Ground':
        ax1.imshow(grnd_arr, cmap='terrain', extent=extent, origin='lower')
    fig.canvas.draw_idle()