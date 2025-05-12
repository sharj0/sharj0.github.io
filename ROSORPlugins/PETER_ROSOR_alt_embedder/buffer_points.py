import matplotlib.pyplot as plt
from shapely.geometry import Point, MultiPolygon, Polygon
from shapely.ops import unary_union
import numpy as np
from matplotlib.widgets import RectangleSelector, Button
import time
from PyQt5.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel, QApplication

# PROFILER CHUNK 1/3 START ////////////////////////////////////////////////////////////////////////////////////
#import cProfile
#import pstats
#import io
# PROFILER CHUNK 1/3 END ////////////////////////////////////////////////////////////////////////////////////

def buffer_points_old(x_coords, y_coords, buffer):
    return [Point(x, y).buffer(buffer, resolution=4) for x, y in zip(x_coords, y_coords)]

def create_buffered_polygon(x_coords, y_coords, buffer):

    # Create points and compute buffers
    #buffered_points = buffer_points_old(x_coords, y_coords, buffer)
    buffered_points = buffer_points_new(x_coords, y_coords, buffer)
    # Combine overlapping buffers
    merged_buffer = unary_union(buffered_points)


    if isinstance(merged_buffer, (list, tuple)):
        polygons = merged_buffer
    else:
        polygons = [merged_buffer]
    if len(polygons) > 1:
        err_message = f"unexpected behaviour. increase safety buffer."
        QMessageBox.critical(None, "Error", err_message)
        raise ValueError(err_message)
    return polygons[0]


from shapely.geometry import Polygon
import numpy as np


def buffer_points_new(x_list, y_list, buffer):
    x_coords, y_coords = np.array(x_list), np.array(y_list)

    # Angles for the eight directions in radians
    angles = np.radians(np.array([0, 45, 67.5, 90, 112.5, 135, 180]))

    # Create offsets for each direction
    dx_ang = buffer * np.cos(angles)
    dy_ang  = buffer * np.sin(angles)

    dx = np.concatenate(([buffer], dx_ang, [-buffer]))
    dy = np.concatenate(([-buffer], dy_ang, [-buffer]))

    # Original coordinates expanded for broadcasting
    original_x = x_coords[:, np.newaxis]  # Shape will be (num_points, 1)
    original_y = y_coords[:, np.newaxis]  # Shape will be (num_points, 1)

    # New coordinates, shape will be (num_points, 8)
    new_x_coords = original_x + dx
    new_y_coords = original_y + dy

    polys = []
    for i in range(len(new_x_coords)):
        # Create a list of tuples for each point's buffered coordinates
        buffered_coords = list(zip(new_x_coords[i], new_y_coords[i]))
        # Ensure the polygon is closed by adding the start point to the end
        buffered_coords.append(buffered_coords[0])
        # Create a Polygon from the buffered coordinates
        poly = Polygon(buffered_coords)
        # Append the Polygon to the list
        polys.append(poly)
    return polys


def show_wait_dialog(text="Calculating buffers ..."):
    """
    Create and show a modal dialog with a "Calculating buffers ..." message.

    Returns:
        QDialog: The displayed dialog.
    """
    dialog = QDialog()
    dialog.setWindowTitle("Please wait...")
    layout = QVBoxLayout()
    label = QLabel(text)
    layout.addWidget(label)
    dialog.setLayout(layout)
    dialog.show()
    QApplication.processEvents()  # Ensure that the dialog gets painted immediately
    return dialog

def toggle_aspect(event, ax, button):
    if ax.get_aspect() == 'auto':
        ax.set_aspect('equal')
        button.label.set_text("Current aspect ratio 'real' click to set to 'flexible'")
    else:
        ax.set_aspect('auto')
        button.label.set_text("Current aspect ratio 'flexible' click to set to 'real'")
    plt.draw()


def split_linear_ring_to_linestrings(outer_buff):
    """
    Split a linear ring (represented as a 2D numpy array) into two line strings
    based on the max and min x coordinates.

    Parameters:
        outer_buff (numpy.ndarray): The linear ring represented as a 2xN numpy array.

    Returns:
        numpy.ndarray, numpy.ndarray: Two line strings of the split linear ring.
    """
    # Separate the x and y coordinates
    x_coords, y_coords = outer_buff

    # Find the indices of the min and max x coordinates
    min_x_index = np.argmin(x_coords)
    max_x_index = np.argmax(x_coords)

    # Create two line strings from the min to max and max to min (wrapping around)
    if min_x_index <= max_x_index:
        first_half_x = np.concatenate([x_coords[min_x_index:max_x_index+1], [x_coords[max_x_index]]])
        first_half_y = np.concatenate([y_coords[min_x_index:max_x_index+1], [y_coords[max_x_index]]])
        second_half_x = np.concatenate([x_coords[max_x_index:], x_coords[:min_x_index+1]])
        second_half_y = np.concatenate([y_coords[max_x_index:], y_coords[:min_x_index+1]])
    else:
        first_half_x = np.concatenate([x_coords[min_x_index:], x_coords[:max_x_index+1]])
        first_half_y = np.concatenate([y_coords[min_x_index:], y_coords[:max_x_index+1]])
        second_half_x = np.concatenate([x_coords[max_x_index:min_x_index+1], [x_coords[min_x_index]]])
        second_half_y = np.concatenate([y_coords[max_x_index:min_x_index+1], [y_coords[min_x_index]]])

    # Combine the x and y coordinates back into 2D arrays
    first_half = np.vstack([first_half_x, first_half_y])
    second_half = np.vstack([second_half_x, second_half_y])

    return first_half, second_half


def resolve_from_small_polygons(
    small_polys,
    noise_point_indices=None,
    total_gnd_polys=0
):
    """
    small_polys: list of Polygon = grnd_polygons + surf_polygons
    noise_point_indices: indices into surf_polygons (0..Ns-1)
    total_gnd_polys:     number of ground_polygons at start of small_polys
    """
    polys = list(small_polys)
    noise_set = {i + total_gnd_polys for i in (noise_point_indices or [])}
    point_size = 100 / 3  # one-third original

    while True:
        # compute centroids
        centroids = [(p.centroid.x, p.centroid.y) for p in polys]
        xs, ys = zip(*centroids)

        # split into surface vs ground indices
        ground_idx  = list(range(total_gnd_polys))
        surface_idx = list(range(total_gnd_polys, len(polys)))

        # set up figure
        fig, ax = plt.subplots(figsize=(19,10))
        ax.set_title("Drag to select centroids (blue) → Remove Points")

        # 0) polygon outlines, colored to match each point
        poly_artists = []
        for idx, poly in enumerate(polys):
            x_poly, y_poly = poly.exterior.xy

            if idx in noise_set:
                col = 'red'
            elif idx < total_gnd_polys:
                col = 'brown'
            else:
                col = 'green'

            artist, = ax.plot(
                x_poly, y_poly,
                linestyle='--', linewidth=1,
                color=col,
                visible=False,
                zorder=0
            )
            poly_artists.append(artist)

        # 1) surface (green) at z=1
        if surface_idx:
            xs_s = [centroids[i][0] for i in surface_idx]
            ys_s = [centroids[i][1] for i in surface_idx]
            surf_scat = ax.scatter(xs_s, ys_s,
                                   c='green', s=point_size/2,
                                   zorder=1)

        # 2) ground (brown) at z=2
        if ground_idx:
            xs_g = [centroids[i][0] for i in ground_idx]
            ys_g = [centroids[i][1] for i in ground_idx]
            grd_scat = ax.scatter(xs_g, ys_g,
                                  c='brown', s=point_size/2,
                                  zorder=2)

        # 3) noise (red) at z=3
        if noise_set:
            xs_n = [centroids[i][0] for i in noise_set if i < len(centroids)]
            ys_n = [centroids[i][1] for i in noise_set if i < len(centroids)]
            noise_scat = ax.scatter(xs_n, ys_n,
                                    c='red', s=point_size,
                                    zorder=3)

        # 4) placeholder for blue selection at z=4
        sel_scat = None
        selected = set()

        # auto‐scale
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        dx, dy = max_x - min_x, max_y - min_y
        m = 0.2
        ax.set_xlim(min_x - dx*m, max_x + dx*m)
        ax.set_ylim(min_y - dy*m, max_y + dy*m)

        # ─── selection callback ───
        def onselect(eclick, erelease):
            nonlocal sel_scat
            x0, x1 = sorted([eclick.xdata, erelease.xdata])
            y0, y1 = sorted([eclick.ydata, erelease.ydata])
            for idx, (cx, cy) in enumerate(centroids):
                if x0 <= cx <= x1 and y0 <= cy <= y1:
                    selected.add(idx)

            btn_remove.label.set_text(
                "Remove the blue points" if selected
                else "Continue without removing points"
            )

            if sel_scat:
                sel_scat.remove()

            if selected:
                xs_b = [centroids[i][0] for i in selected]
                ys_b = [centroids[i][1] for i in selected]
                sel_scat = ax.scatter(xs_b, ys_b,
                                      c='blue', s=point_size,
                                      zorder=4)

            fig.canvas.draw_idle()

        # keep a reference so it doesn’t get GC’d:
        rectsel = RectangleSelector(
            ax, onselect,
            button=[1], minspanx=5, minspany=5,
            spancoords='pixels'
        )

        # ─── aspect toggle ───
        ax_aspect = plt.axes([0.55, 0.02, 0.15, 0.05])
        btn_aspect = Button(ax_aspect, "Aspect: Equal")
        btn_aspect.on_clicked(lambda ev: toggle_aspect(ev, ax, btn_aspect))

        # ─── polygon toggle ───
        def toggle_polys(ev):
            vis = not poly_artists[0].get_visible()
            for art in poly_artists:
                art.set_visible(vis)
            btn_poly.label.set_text(
                "Hide Polygons" if vis else "Show Polygons"
            )
            fig.canvas.draw_idle()

        ax_poly = plt.axes([0.35, 0.02, 0.15, 0.05])
        btn_poly = Button(ax_poly, "Show Polygons")
        btn_poly.on_clicked(toggle_polys)

        # ─── remove/continue ───
        ax_remove = plt.axes([0.8, 0.02, 0.15, 0.05])
        btn_remove = Button(ax_remove, "Continue without removing points")
        result = {'merged': None, 'keep': None}

        def on_remove(ev):
            keep = [p for i,p in enumerate(polys) if i not in selected]
            result['keep']   = keep
            result['merged'] = unary_union(keep)
            plt.close(fig)

        btn_remove.on_clicked(on_remove)

        plt.show()

        if result['merged'] is None:
            raise RuntimeError("Interactive cleanup aborted by user")

        if isinstance(result['merged'], MultiPolygon):
            polys = result['keep']
            continue

        return result['merged']



def run(grnd_x, grnd_y, grnd_buffer, grnd_nodata_value,
        surf_x, surf_y, surf_buffer, surf_nodata_value, detect_noise_distance,
        skip_flights_where_geotiff_data_missing=False, manually_remove_noise=False,
        plot=False):
    # PROFILER CHUNK 2/3 START ////////////////////////////////////////////////////////////////////////////////////
    #pr = cProfile.Profile()
    #pr.enable()
    # PROFILER CHUNK 2/3 END ////////////////////////////////////////////////////////////////////////////////////
    bad_samples = False

    #see if we are trying to sample anywhere where there is no data:
    if np.any(grnd_y == grnd_nodata_value):
        if skip_flights_where_geotiff_data_missing:
            return None
        else:
            err_message = f"Flying over areas without ground data!"
            QMessageBox.critical(None, "Error", err_message)
            plot, bad_samples = True, True
    if np.any(surf_y == surf_nodata_value):
        if skip_flights_where_geotiff_data_missing:
            return None
        else:
            err_message = f"Flying over areas without surface data!"
            QMessageBox.critical(None, "Error", err_message)
            plot, bad_samples = True, True

    #dialog = show_wait_dialog("Calculating buffers ...")
    start_time = time.perf_counter()

    try:
        grnd_polygons = buffer_points_new(grnd_x, grnd_y, grnd_buffer)
    except Exception as e:
        if skip_flights_where_geotiff_data_missing:
            return None
        else:
            raise

    try:
        surf_polygons = buffer_points_new(surf_x, surf_y, surf_buffer)
    except Exception as e:
        if skip_flights_where_geotiff_data_missing:
            return None
        else:
            raise


    print(f"Elapsed time: {time.perf_counter() - start_time} seconds")
    #dialog.close()
    # split the buffer polygon into top and bottom
    if not bad_samples:
        merged_buffer = unary_union(grnd_polygons+surf_polygons)
        if not manually_remove_noise:
            try:
                outer_buff = np.array(merged_buffer.exterior.xy)
            except AttributeError:

                merged_buffer = resolve_from_small_polygons(
                    grnd_polygons + surf_polygons,
                    noise_point_indices=[],
                    total_gnd_polys=len(grnd_polygons)
                )
                outer_buff = np.array(merged_buffer.exterior.xy)
        elif manually_remove_noise:
            from sklearn.cluster import DBSCAN
            db = DBSCAN(eps=detect_noise_distance, min_samples=5).fit(np.column_stack((surf_x, surf_y)))
            labels = db.labels_  # length Ns
            noise_mask = (labels == -1)  # True for noisy points
            noise_idxs = np.nonzero(noise_mask)[0].tolist()  # list of int indices
            if not noise_idxs:
                outer_buff = np.array(merged_buffer.exterior.xy)
            else:
                merged_buffer = resolve_from_small_polygons(
                    grnd_polygons + surf_polygons,
                    noise_point_indices=noise_idxs,
                    total_gnd_polys=len(grnd_polygons)
                )
                outer_buff = np.array(merged_buffer.exterior.xy)

        outer_buff1, outer_buff2 = split_linear_ring_to_linestrings(outer_buff)

        # determine which is the top vs bottom by taking ave y value
        mean_ys = np.array([outer_buff1[1].mean(), outer_buff2[1].mean()])
        if np.argmax(mean_ys) == 0:
            outer_buff = outer_buff1
        else:
            outer_buff = outer_buff2

    else:
        outer_buff = None
    if plot:
        grnd_polygon = unary_union(grnd_polygons)
        surf_polygon = unary_union(surf_polygons)
        plot_polygons(grnd_polygon, surf_polygon, grnd_x, grnd_y, surf_x, surf_y, outer_buff)
    if bad_samples:
        err_message = f"Need more lidar coverage or interpolation"
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(err_message)
        msg.setWindowTitle(err_message)
        msg.exec_()

    # PROFILER CHUNK 3/3 START ////////////////////////////////////////////////////////////////////////////////////
    #pr.disable()
    #s = io.StringIO()
    #sortby = 'cumulative'  # Can be 'calls', 'time', 'cumulative', etc.
    #ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    #ps.print_stats()
    #print(s.getvalue())
    # PROFILER CHUNK 3/3  TEMP END ////////////////////////////////////////////////////////////////////////////////////

    return outer_buff

def plot_polygons(grnd_polygon, surf_polygon, grnd_x, grnd_y, surf_x, surf_y, outer_buff):
    fig, ax = plt.subplots(figsize=(10, 10))
    plt.subplots_adjust(bottom=0.2)  # make space for the button
    # Plotting ground polygon
    if isinstance(grnd_polygon, MultiPolygon):
        for poly in grnd_polygon.geoms:
            x, y = poly.exterior.xy
            ax.fill(x, y, alpha=0.3, edgecolor='brown', facecolor='brown')
    else:
        x, y = grnd_polygon.exterior.xy
        ax.fill(x, y, alpha=0.3, edgecolor='brown', facecolor='brown')
    # Plotting surface polygon
    if isinstance(surf_polygon, MultiPolygon):
        for poly in surf_polygon.geoms:
            x, y = poly.exterior.xy
            ax.fill(x, y, alpha=0.3, edgecolor='green', facecolor='green')
    else:
        x, y = surf_polygon.exterior.xy
        ax.fill(x, y, alpha=0.3, edgecolor='green', facecolor='green')
    # Plot the merged_buffer as a thin black line
    if not outer_buff is None:
        x, y = outer_buff
        ax.plot(x, y, color='black', linewidth=1)
    ax.scatter(surf_x, surf_y, color='green', s=10)  # s sets the size of the scatter points for surface
    ax.scatter(grnd_x, grnd_y, color='brown', s=10)  # s sets the size of the scatter points for ground
    ax.set_title(f'Points and their Buffers')
    ax.set_aspect('equal')
    # Create toggle button
    ax_toggle = plt.axes([0.25, 0.05, 0.5, 0.075])
    toggle_button = Button(ax_toggle, "Current aspect ratio 'real' click to set to 'flexible'")
    toggle_button.on_clicked(lambda event: toggle_aspect(event, ax, toggle_button))
    plt.show()
