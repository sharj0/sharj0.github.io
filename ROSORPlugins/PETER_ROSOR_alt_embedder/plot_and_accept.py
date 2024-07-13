# Standard Libraries
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
from matplotlib.widgets import Button
from matplotlib.ticker import MultipleLocator, MaxNLocator
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QSizePolicy, QHBoxLayout, QWidget
from PyQt5.QtGui import QIcon



# PETER_ROSOR_alt_embedder related
from PETER_ROSOR_alt_embedder.tools import extract_2D_subarray_with_buffer

def run(waypoints, dsm, dem, surf_samples, grnd_samples):
    # surf / grnd samples_merged and new_waypoints format what each col represents
    # 0-dist_allong_whole_flight,
    # 1-dist_allong_seg,
    # 2-dist_to each side_of flight path,
    # 3-alt,
    # 4-UTME
    # 5-UTMN
    # 6-seg_number
    # 7-heading
    # 8-(if samples: vert_dist) OR (if new_waypoints: UAV_alt)

    def make_segments(x, y):
        """
        Create a list of line segments from x and y coordinates, in the correct format for LineCollection.
        """
        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        return segments

    def colorline(ax, x, y, c, cmap=plt.get_cmap('inferno'), norm=plt.Normalize(0.0, 1.0)):
        """
        Plot a colored line with coordinates x and y and colors c.
        """
        c = 1 - (c - np.min(c)) / (np.max(c) - np.min(c))
        segments = make_segments(x, y)
        lc = mcoll.LineCollection(segments, array=c, cmap=cmap, norm=norm, linewidth=2)

        ax.add_collection(lc)
        ax.autoscale()
        ax.margins(0.1)

    dialog = QDialog()
    dialog.setWindowTitle("Check and Accept Waypoints")

    # QVBoxLayout for dialog
    dialog_layout = QVBoxLayout(dialog)


    matplotlib.use('Qt5Agg')
    # globally accecable variables
    global radio
    # initialize the canopy
    canopy = Canopy()

    # unpacking dsm and dem
    surf_arr, surf_x_coords, surf_y_coords  = dsm
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
    #ax2.plot(waypoints[:, 0], waypoints[:, 3], color='purple', marker='.', ms=3, linewidth=1.3)

    ax2.scatter(surf_samples[:, 0], surf_samples[:, 3], color='green', s=2)
    ax2.scatter(grnd_samples[:, 0], grnd_samples[:, 3], color='brown', s=2)
    ax2.set_aspect('equal')

    # New histogram for surf_samples and grnd_samples on ax3
    # Determine the range of your combined data
    data_min = int(np.floor(min(np.min(surf_samples[:, 8]), np.min(grnd_samples[:, 8]))))
    data_max = int(np.ceil(max(np.max(surf_samples[:, 8]), np.max(grnd_samples[:, 8]))))

    # Determine the bin width based on your target # of  bins, but make sure it's an integer value
    target_number_of_bins = 20
    bin_width = int(np.ceil((data_max - data_min) / target_number_of_bins))

    # Create bin edges based on this bin width
    bins = np.arange(data_min, data_max + bin_width + 1, bin_width)

    # Normalize the histograms as before
    weights_surf = np.ones_like(surf_samples[:, 8]) / len(surf_samples[:, 8])
    weights_grnd = np.ones_like(grnd_samples[:, 8]) / len(grnd_samples[:, 8])

    ax3.hist(surf_samples[:, 8], bins=bins, color='green', alpha=0.5, label='Surface', weights=weights_surf)
    ax3.hist(grnd_samples[:, 8], bins=bins, color='brown', alpha=0.5, label='Ground', weights=weights_grnd)

    # Set major ticks at integer locations
    ax3.xaxis.set_major_locator(MaxNLocator(integer=True))

    # Set minor ticks for the x-axis at 0.5 intervals for granularity between integers
    minor_locator = MultipleLocator(1)
    ax3.xaxis.set_minor_locator(minor_locator)

    # Adjust y-ticks to show percentages
    yticks = ax3.get_yticks()
    ax3.set_yticks(yticks)
    ax3.set_yticklabels(['{:.0f}%'.format(y * 100) for y in yticks])

    ax3.set_title('Histogram of Altitudes')
    ax3.set_xlabel('Altitude (m)')
    ax3.legend(loc='lower center', bbox_to_anchor=(0.5, -0.62), ncol=2)

    # Ensure the x-axis tick labels don't overlap
    ax3.tick_params(axis='x', rotation=45)

    # Add a grid that aligns with the major ticks
    ax3.grid(True, which='major', axis='both', linestyle='--', linewidth=0.5)

    # Make the major ticks a bit longer
    ax3.tick_params(axis='x', which='major', length=5)

    # Instantiate UAVHover class and attach the hover function to motion_notify_event
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
        ax.clear()
        im = ax.imshow(arr, cmap='terrain', extent=extent, origin='lower')
        ax.plot(waypoints[:, 4], waypoints[:, 5], color='purple', marker='.', linewidth=2)
        hover_handler.redraw_uav_marker()
        cbar.update_normal(im)
        plt.draw()

    def show_surface(ax, surf_arr, surf_x_coords, surf_y_coords, waypoints, event):
        extent_surf = get_extent_from_coords(surf_x_coords, surf_y_coords)
        update_image_and_colorbar(ax, surf_arr, waypoints, extent_surf, cbar, hover_handler)

    def show_ground(ax, grnd_arr, grnd_x_coords, grnd_y_coords, waypoints, event):
        extent_grnd = get_extent_from_coords(grnd_x_coords, grnd_y_coords)
        update_image_and_colorbar(ax, grnd_arr, waypoints, extent_grnd, cbar, hover_handler)

    def show_canopy(ax,
                    surf_arr, surf_x_coords, surf_y_coords,
                    grnd_arr, grnd_x_coords, grnd_y_coords,
                    waypoints, event):
        if not canopy.diff_arr:
            canopy.diff_arr, canopy.diff_x_coords, canopy.diff_y_coords = compute_difference(surf_arr, surf_x_coords, surf_y_coords,
                                                                        grnd_arr, grnd_x_coords, grnd_y_coords)
        extent_canopy = get_extent_from_coords(canopy.diff_x_coords, canopy.diff_y_coords)
        update_image_and_colorbar(ax, canopy.diff_arr, waypoints, extent_canopy, cbar, hover_handler)

    # Get the position of ax1
    pos = ax1.get_position()

    # Set button width and height
    btn_width = 0.1
    btn_height = 0.04

    # Calculate the left positions of the buttons to align them against the right edge of ax1
    left_grnd = pos.x1 - btn_width  # Align the right edge of the second button with ax1's right edge
    left_surf = left_grnd - btn_width - 0.02  # Some gap between the buttons

    # Position the buttons just above the top edge of ax1
    top_btn = pos.y1 + 0.01  # Just above the top edge of ax1

    # Now define the axes for the buttons
    ax_surf = plt.axes([left_surf, top_btn, btn_width, btn_height])
    ax_grnd = plt.axes([left_grnd, top_btn, btn_width, btn_height])
    # ax_canopy = plt.axes([0.44, 0.45, 0.1, 0.04])

    # Rest of your button creation and event binding remains the same...
    btn_surf = Button(ax_surf, 'Show Surface')
    btn_grnd = Button(ax_grnd, 'Show Ground')
    # btn_canopy = Button(ax_canopy, 'Canopy')


    # Attach the callbacks to the buttons with additional parameters
    btn_surf.on_clicked(partial(show_surface, ax1, surf_arr, surf_x_coords, surf_y_coords, waypoints))
    btn_grnd.on_clicked(partial(show_ground, ax1, grnd_arr, grnd_x_coords, grnd_y_coords, waypoints))
    #btn_canopy.on_clicked(partial(show_canopy, ax1,
    #                              surf_arr, surf_x_coords, surf_y_coords,
    #                              grnd_arr, grnd_x_coords, grnd_y_coords,
    #                              waypoints))



    # Create a canvas with the figure and add it to the dialog layout
    canvas = FigureCanvas(fig)
    dialog_layout.addWidget(canvas)

    # Bottom bar layout (for the toolbar and accept button)
    bottom_bar_layout = QHBoxLayout()
    toolbar = NavigationToolbar(canvas, dialog)
    btn_accept = QPushButton("Accept", dialog)
    # Modify the button's appearance
    font = btn_accept.font()
    font.setPointSize(12)  # Set font size
    btn_accept.setFont(font)
    btn_accept.setFixedSize(300, 30)  # Set fixed width and height
    btn_accept.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Ensure button retains its size

    bottom_bar_layout.addWidget(toolbar)
    bottom_bar_layout.addStretch(1)  # Adds a stretchable space between the toolbar and the accept button
    bottom_bar_layout.addWidget(btn_accept)

    dialog_layout.addLayout(bottom_bar_layout)

    btn_accept.clicked.connect(dialog.accept)

    # Set the icon to the button
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    dialog.setWindowIcon(QIcon(os.path.join(plugin_dir, "Waypoint_Terrain_Follow.png")))

    # Return True if the "Accept" button was clicked, False otherwise
    # Execute the dialog
    result = dialog.exec_() == QDialog.Accepted

    # Close the Matplotlib figure
    plt.close(fig)

    # Explicitly delete the dialog
    del dialog

    return result

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

'''
def compute_difference(surf_arr, surf_x_coords, surf_y_coords, grnd_arr, grnd_x_coords, grnd_y_coords):
    # Define a grid for the overlapping region
    x_min = max(np.min(surf_x_coords), np.min(grnd_x_coords))
    x_max = min(np.max(surf_x_coords), np.max(grnd_x_coords))
    y_min = max(np.min(surf_y_coords), np.min(grnd_y_coords))
    y_max = min(np.max(surf_y_coords), np.max(grnd_y_coords))

    # Adjust the boundaries by a 5% buffer
    x_buffer = 0.05 * (x_max - x_min)
    y_buffer = 0.05 * (y_max - y_min)

    x_min += x_buffer
    x_max -= x_buffer
    y_min += y_buffer
    y_max -= y_buffer

    # Determine the number of grid points based on the original data's resolution
    num_x_points = min(len(surf_x_coords), len(grnd_x_coords))
    num_y_points = min(len(surf_y_coords), len(grnd_y_coords))

    x = np.linspace(x_min, x_max, num_x_points)
    y = np.linspace(y_min, y_max, num_y_points)

    X, Y = np.meshgrid(x, y)

    surf_X, surf_Y = np.meshgrid(surf_x_coords, surf_y_coords)
    surf_points = np.vstack((surf_X.ravel(), surf_Y.ravel())).T

    grnd_X, grnd_Y = np.meshgrid(grnd_x_coords, grnd_y_coords)
    grnd_points = np.vstack((grnd_X.ravel(), grnd_Y.ravel())).T

    # Interpolate values from surf and grnd onto the overlapping grid
    surf_values_on_grid = griddata(surf_points, surf_arr.ravel(), (X, Y), method='linear', fill_value=0)
    grnd_values_on_grid = griddata(grnd_points, grnd_arr.ravel(), (X, Y), method='linear', fill_value=0)

    # Compute the difference
    diff_arr = surf_values_on_grid - grnd_values_on_grid
    diff_x_coords = x
    diff_y_coords = y

    return diff_arr, diff_x_coords, diff_y_coords'''

