from pickletools import uint8

from osgeo import gdal
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import distance, ConvexHull, cKDTree
from scipy.ndimage import minimum_filter, gaussian_filter, label, center_of_mass, binary_fill_holes, binary_dilation
import matplotlib.pyplot as plt

from matplotlib import cm

from shapely.geometry import LineString, Point, Polygon
from collections import OrderedDict
import csv
import networkx as nx
import sys
import os
import time
from datetime import timedelta
from PyQt5.QtWidgets import QApplication, QFileDialog
import gc

# IMPORT 3rd PARTY libraries
plugin_dir = os.path.dirname(os.path.realpath(__file__))
# Path to the subdirectory containing the external libraries
lib_dir = os.path.join(plugin_dir, 'plugin_3rd_party_libs')
# Add this directory to sys.path so Python knows where to find the external libraries
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
from skimage.draw import line #3rd PARTY library
from skimage.graph import route_through_array #3rd PARTY library
from skimage.morphology import skeletonize #3rd PARTY library
from skimage.transform import resize #3rd PARTY library
from skimage.measure import block_reduce #3rd PARTY library
import rasterio #3rd PARTY library
from rasterio.features import rasterize #3rd PARTY library
from rasterio.windows import Window #3rd PARTY library
from affine import Affine #3rd PARTY library



def connect_cut_path_masks(start_pixs, end_pixs, mask_shape):
    """
    Connect consecutive cut_path_masks by drawing lines from the end of one path to the start of the next.

    Parameters:
        start_pixs (list of tuple): Each element is a (row, col) coordinate for the start of a cut path.
        end_pixs (list of tuple): Each element is a (row, col) coordinate for the end of a cut path.
        mask_shape (tuple): The shape of the mask array in which to draw the connecting lines.

    Returns:
        np.ndarray: A binary mask (same shape as mask_shape) with lines connecting each end to the next start.
                    If you have N cut paths, you'll get N-1 lines connecting them in sequence.
    """
    connecting_lines_mask = np.zeros(mask_shape, dtype=np.uint8)

    # We assume start_pixs[i] and end_pixs[i] correspond to the same cut_path_mask.
    # We want to connect end_pixs[i] -> start_pixs[i+1].
    num_paths = len(start_pixs)
    for i in range(num_paths - 1):
        end_pt = end_pixs[i]
        start_pt_next = start_pixs[i + 1]

        # Draw the connecting line
        rr, cc = line(int(end_pt[0]), int(end_pt[1]), int(start_pt_next[0]), int(start_pt_next[1]))
        connecting_lines_mask[rr, cc] = 1

    return connecting_lines_mask

def narrow_overlap_vrt(wide_ext_overlap_vrt, output_path):
    with rasterio.open(wide_ext_overlap_vrt) as src:
        width = src.width
        height = src.height
        block_size = 4096  # Start with larger blocks, adjust if necessary
        min_row = None
        max_row = None
        min_col = None
        max_col = None

        # Iterate over the raster in blocks
        for row_off in range(0, height, block_size):
            row_count = min(block_size, height - row_off)
            for col_off in range(0, width, block_size):
                col_count = min(block_size, width - col_off)
                window = Window(col_off, row_off, col_count, row_count)
                data = src.read(1, window=window)

                # Find indices of non-zero pixels
                rows, cols = np.nonzero(data)
                if rows.size > 0:
                    global_rows = rows + row_off
                    global_cols = cols + col_off

                    if min_row is None:
                        min_row = global_rows.min()
                        max_row = global_rows.max()
                        min_col = global_cols.min()
                        max_col = global_cols.max()
                    else:
                        min_row = min(min_row, global_rows.min())
                        max_row = max(max_row, global_rows.max())
                        min_col = min(min_col, global_cols.min())
                        max_col = max(max_col, global_cols.max())

        # Check if any non-zero data was found
        if min_row is not None:
            # Define the window of the valid data
            height_window = max_row - min_row + 1
            width_window = max_col - min_col + 1
            window = Window(min_col, min_row, width_window, height_window)

            # Update the profile for the output dataset
            profile = src.profile
            transform = rasterio.windows.transform(window, src.transform)
            profile.update({
                'height': height_window,
                'width': width_window,
                'transform': transform,
                'dtype': 'uint8',  # Ensure binary data is stored as 8-bit unsigned integer
                'driver': 'GTiff',  # Save as GeoTIFF
                'compress': 'LZW',  # Apply LZW compression
                'nbits': 1,  # Use 1-bit depth for binary mask
                'tiled': True  # Enable tiling for performance
            })

            # Write the cropped data to the output file
            with rasterio.open(output_path, 'w', **profile) as dst:
                for i in range(1, src.count + 1):
                    data = src.read(i, window=window)
                    dst.write(data, i)

            # Return the geotransform of the cropped mask
            return transform.to_gdal()
        else:
            print("No non-zero data found in the raster.")
            return None

def get_file_size_in_gb(file_path):
    file_size_bytes = os.path.getsize(file_path)
    return file_size_bytes / (1024 ** 3)

def get_time_sofar(start_time, stage='Current stage'):
    end_time = time.time()
    execution_time = end_time - start_time
    duration = human_readable_duration(execution_time)
    if duration:
        print(f"{stage} done at {duration}...")
    else:
        print(f"{stage} done at {round(execution_time,4)} s ...")


def normalize_to_unit_range(array):
    """
    Normalize a NumPy array to the range [0, 1].

    Args:
        array (numpy.ndarray): Input array to normalize.

    Returns:
        numpy.ndarray: Normalized array with values in the range [0, 1].
    """
    min_val = np.min(array)
    max_val = np.max(array)

    if max_val - min_val == 0:
        raise ValueError("Cannot normalize an array with zero range (all values are the same).")

    normalized_array = (array - min_val) / (max_val - min_val)
    return normalized_array

def detect_if_gappy_overlap_mask(overlap_mask, min_area_fraction=0.02):
    """
    Detects if the overlap_mask is continuous or has gaps. If gaps exist, splits each
    continuous area into a separate mask with the same shape and extent as the original.
    Masks with less than `min_area_fraction` of the total area extent are not returned.

    Parameters:
        overlap_mask (numpy.ndarray): Binary mask indicating overlap areas.
        min_area_fraction (float): Minimum fraction of total extent area for a mask to be returned.

    Returns:
        list of numpy.ndarray: List of masks. If continuous, the list contains the original mask.
                               If not, the list contains one mask per continuous area, filtered by size.
    """
    # Total extent area
    total_area = overlap_mask.size
    print('getting_destinct_areas...')
    # Label connected components in the mask
    labeled_mask, num_features = label(overlap_mask)

    if num_features <= 1:
        # If there's only one continuous area, check its size
        if overlap_mask.sum() >= total_area * min_area_fraction:
            return [overlap_mask]
        else:
            return []

    # Otherwise, split each connected area into a separate mask
    masks = []
    for feature_id in range(1, num_features + 1):
        separate_mask = (labeled_mask == feature_id).astype(np.uint8)
        area_coverage = separate_mask.sum()

        # Filter out masks with less than the minimum area fraction
        if area_coverage >= total_area * min_area_fraction:
            masks.append(separate_mask)
    return masks

# Function to map GDAL data types to NumPy data types
def gdal_dtype_to_numpy(gdal_dtype):
    dtype_mapping = {
        gdal.GDT_Byte: np.uint8,
        gdal.GDT_UInt16: np.uint16,
        gdal.GDT_Int16: np.int16,
        gdal.GDT_UInt32: np.uint32,
        gdal.GDT_Int32: np.int32,
        gdal.GDT_Float32: np.float32,
        gdal.GDT_Float64: np.float64,
        gdal.GDT_CInt16: np.complex64,  # Complex types
        gdal.GDT_CInt32: np.complex64,
        gdal.GDT_CFloat32: np.complex64,
        gdal.GDT_CFloat64: np.complex128,
    }
    return dtype_mapping.get(gdal_dtype, np.float32)  # Default to float32 if not found



def select_folder(default_location=None):
    # Create a Qt application instance
    app = QApplication(sys.argv)

    # Set the default directory to show in the file dialog
    default_location = default_location if default_location else "C:/"

    # Open the folder dialog
    folder = QFileDialog.getExistingDirectory(None, "Select Folder", default_location)

    # Clean up the application instance
    app.exit()

    # Return the selected folder, or None if no selection was made
    return folder


def select_tiff_files(default_location=None):
    # Create a Qt application instance
    app = QApplication(sys.argv)

    # Set the default directory to show in the file dialog
    default_location = default_location if default_location else "C:/"

    # Open the file dialog to select multiple files
    files, _ = QFileDialog.getOpenFileNames(
        None,
        "Select Two TIFF Files",
        default_location,
        "TIFF Files (*.tiff *.tif);;All Files (*)"
    )

    # Clean up the application instance
    app.exit()

    # Check if exactly two files were selected
    if len(files) == 2:
        return files
    else:
        print("Please select exactly two TIFF files.")
        return select_tiff_files(default_location)


def simplify_graph(H):
    while True:
        changes_made = False

        # Remove nodes with degree 0 (isolated)
        isolated_nodes = [node for node in H.nodes() if H.degree(node) == 0]
        if isolated_nodes:
            H.remove_nodes_from(isolated_nodes)
            changes_made = True

        # Remove nodes with degree 1 and short edges
        degree_1_nodes = [node for node in H.nodes() if H.degree(node) == 1]
        for node in degree_1_nodes:
            neighbors_list = list(H.neighbors(node))
            if not neighbors_list:
                # No neighbors? Just remove the node to keep graph consistent.
                H.remove_node(node)
                changes_made = True
                continue

            # Proceed only if we indeed have exactly one neighbor
            neighbor = neighbors_list[0]
            if 'weight' in H[node][neighbor] and H[node][neighbor]['weight'] < 1.5:
                H.remove_node(node)
                changes_made = True

        # Simplify nodes with degree 2
        degree_2_nodes = [node for node in H.nodes() if H.degree(node) == 2]
        for node in degree_2_nodes:
            neighbors = list(H.neighbors(node))
            if len(neighbors) != 2:
                # Safety check: if somehow not exactly two neighbors, skip
                continue
            edge1_weight = H[node][neighbors[0]].get('weight', 1)
            edge2_weight = H[node][neighbors[1]].get('weight', 1)

            # If either edge is less than 1.5, simplify
            if edge1_weight < 1.5 or edge2_weight < 1.5:
                # Add a new edge between the neighbors with combined weight
                new_weight = edge1_weight + edge2_weight
                H.add_edge(neighbors[0], neighbors[1], weight=new_weight)
                # Remove the current node
                H.remove_node(node)
                changes_made = True

        # Stop if no changes were made
        if not changes_made:
            break

    return H

def calculate_overlapping_pixels(gt1, gt2, first_raster_shape, second_raster_shape):
    """
    Calculate the number of overlapping pixels between two rasters based on their geotransform and shapes.

    Parameters:
        gt1 (tuple): Geotransform of the first raster.
        gt2 (tuple): Geotransform of the second raster.
        first_raster_shape (tuple): Shape of the first raster (rows, cols).
        second_raster_shape (tuple): Shape of the second raster (rows, cols).

    Returns:
        int: The number of overlapping pixels.
    """
    # Determine the bounds of the first raster
    x_min1 = gt1[0]
    x_max1 = x_min1 + first_raster_shape[1] * gt1[1]
    y_max1 = gt1[3]
    y_min1 = y_max1 + first_raster_shape[0] * gt1[5]

    # Determine the bounds of the second raster
    x_min2 = gt2[0]
    x_max2 = x_min2 + second_raster_shape[1] * gt2[1]
    y_max2 = gt2[3]
    y_min2 = y_max2 + second_raster_shape[0] * gt2[5]

    # Calculate the overlapping bounds
    x_overlap_min = max(x_min1, x_min2)
    x_overlap_max = min(x_max1, x_max2)
    y_overlap_min = max(y_min1, y_min2)
    y_overlap_max = min(y_max1, y_max2)

    # Check if there is an overlap
    if x_overlap_min >= x_overlap_max or y_overlap_min >= y_overlap_max:
        return 0

    # Calculate the pixel overlap in each dimension
    x_overlap_pixels = int((x_overlap_max - x_overlap_min) / gt1[1])
    y_overlap_pixels = int((y_overlap_max - y_overlap_min) / abs(gt1[5]))

    # Total overlapping pixels
    return x_overlap_pixels * y_overlap_pixels


def keep_largest_component(graph):
    """
    Retains only the largest connected component in the graph.

    Parameters:
        graph (nx.Graph): Input graph.

    Returns:
        nx.Graph: Subgraph containing only the largest connected component.
    """
    # Find all connected components
    connected_components = nx.connected_components(graph)

    # Identify the largest connected component (by number of nodes)
    largest_component = max(connected_components, key=len)

    # Create a subgraph with only the largest connected component
    largest_subgraph = graph.subgraph(largest_component).copy()

    return largest_subgraph

def compute_centerline(mask, max_dim_size=5000, clip_ends_factor=1.2, angle_threshold = 45, show_plot=False):
    # Ensure mask is boolean
    mask = mask.astype(bool)

    # Downscale the mask if the longest dimension exceeds max_dim_size
    original_shape = mask.shape
    max_dim = max(original_shape)
    print(f"{max_dim=}")
    if max_dim > max_dim_size:
        scale = max_dim_size / max_dim
        new_shape = (int(mask.shape[0] * scale), int(mask.shape[1] * scale))
        mask_resized = resize(mask, new_shape, order=0, preserve_range=True, anti_aliasing=False).astype(bool)
    else:
        mask_resized = mask
        scale = 1.0

    mask_resized = binary_fill_holes(mask_resized)
    print(f"{scale=}")

    # Compute skeleton of the mask
    skeleton = skeletonize(mask_resized)

    #plot_array(skeleton)

    # Get coordinates of skeleton pixels
    skel_coords = np.column_stack(np.nonzero(skeleton))

    # Build KDTree for skeleton coordinates
    tree = cKDTree(skel_coords)
    # Find neighboring skeleton pixels within sqrt(2) distance
    neighbor_lists = tree.query_ball_point(skel_coords, np.sqrt(2) + 0.1)

    # Create the graph
    G = nx.Graph()
    G.add_nodes_from(range(len(skel_coords)))

    # Add edges between neighboring skeleton pixels
    for idx, neighbors in enumerate(neighbor_lists):
        for neighbor_idx in neighbors:
            if neighbor_idx != idx:
                G.add_edge(idx, neighbor_idx)

    # Compute degrees of nodes
    degrees = dict(G.degree())

    # Identify branch nodes (degree > 2)
    branch_nodes = [node for node, degree in degrees.items() if degree > 2]
    branch_coords = skel_coords[branch_nodes]

    # Initialize an empty graph to store the simplified structure
    H = nx.Graph()

    # Keep track of visited edges to avoid redundant processing
    visited_edges = set()

    # Build the simplified graph
    for n in branch_nodes:
        for nbr in G.neighbors(n):
            if (n, nbr) in visited_edges or (nbr, n) in visited_edges:
                continue
            path = [n, nbr]
            visited_edges.add((n, nbr))

            # Traverse through degree 2 nodes until a branch node is found
            prev_node = n
            current_node = nbr
            path_length = 1
            while degrees[current_node] == 2:
                neighbors = list(G.neighbors(current_node))
                next_node = neighbors[0] if neighbors[0] != prev_node else neighbors[1]
                if (current_node, next_node) in visited_edges or (next_node, current_node) in visited_edges:
                    break
                visited_edges.add((current_node, next_node))
                path_length += 1
                prev_node = current_node
                current_node = next_node
            # Add edge only if the other endpoint is a branch node
            if current_node in branch_nodes:
                H.add_edge(n, current_node, weight=path_length)

    # Compute distance transform
    distance = distance_transform_edt(mask_resized)

    if show_plot:
        # Plot the state of the graph before removing loops
        fig, ax = plt.subplots(figsize=(8, 8))
        pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
        nx.draw(
            H, pos, edge_color='blue', node_size=50, with_labels=False, ax=ax, node_color='green'
        )
        ax.set_aspect('equal')  # Equal aspect ratio
        ax.set_title("Graph State Before Removing Loops")
        plt.show()

    H = keep_largest_component(H)

    # Remove loops
    while True:
        cycles = list(nx.cycle_basis(H))
        if not cycles:
            break

        for cycle in cycles:
            # Create edges for the current cycle
            edges = [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]
            edges = [edge for edge in edges if H.has_edge(*edge)]

            if edges:
                # Prioritize edge removal based on proximity to the edge of the mask
                # Compute the average distance of the nodes forming each edge to the edge of the mask
                edge_proximity_scores = {
                    edge: (
                                  distance[skel_coords[edge[0]][0], skel_coords[edge[0]][1]] +
                                  distance[skel_coords[edge[1]][0], skel_coords[edge[1]][1]]
                          ) / 2
                    for edge in edges
                }

                # Find the edge with the smallest average distance (closest to the mask edge)
                edge_to_remove = min(edge_proximity_scores, key=edge_proximity_scores.get)
                H.remove_edge(*edge_to_remove)

    # After loop removal plot
    if show_plot:
        fig, ax = plt.subplots(figsize=(8, 8))
        pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
        nx.draw(
            H, pos, edge_color='blue', node_size=50, with_labels=False, ax=ax, node_color='orange'
        )
        ax.set_aspect('equal')  # Equal aspect ratio
        ax.set_title("Graph State After Removing Loops")
        plt.show()

    # Simplify the graph
    H = simplify_graph(H)

    if show_plot:
        fig, ax = plt.subplots(figsize=(8, 8))
        pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
        nx.draw(
            H, pos, edge_color='blue', node_size=50, with_labels=False, ax=ax, node_color='orange'
        )
        ax.set_aspect('equal')  # Equal aspect ratio
        ax.set_title("after simplify_graph")
        plt.show()


    # Map node indices to their distances from the edge of the mask
    node_distances = {
        node: distance[skel_coords[node][0], skel_coords[node][1]]
        for node in H.nodes()
    }

    # Initialize list to store distances of removed nodes
    removed_node_distances = []

    # Identify nodes of degree >2
    degree_gt2_nodes = [node for node in H.nodes() if H.degree(node) > 2]

    # Iteratively remove degree 1 nodes closest to nodes of degree >2
    if show_plot and degree_gt2_nodes:
        anim_fig, ax = plt.subplots(figsize=(8, 8))
        plt.ion()  # Turn on interactive mode for dynamic plotting


    iteration = 0
    while True:
        # Identify nodes of degree >2
        degree_gt2_nodes = [node for node in H.nodes() if H.degree(node) > 2]
        # If no nodes of degree >2, break the loop
        if not degree_gt2_nodes:
            break

        # Find degree 1 nodes
        degree_1_nodes = [node for node in H.nodes() if H.degree(node) == 1]
        if not degree_1_nodes:
            break

        # For each degree-1 node, compute the shortest path length to the nearest node of degree >2
        node_distance_to_gt2 = {}
        for node in degree_1_nodes:
            # Compute shortest paths from this node to all other nodes
            lengths = nx.single_source_shortest_path_length(H, node)
            # Filter lengths to nodes of degree >2
            lengths_to_gt2 = [length for target_node, length in lengths.items() if target_node in degree_gt2_nodes]
            if lengths_to_gt2:
                min_distance = min(lengths_to_gt2)
                node_distance_to_gt2[node] = min_distance
            else:
                # If no degree >2 nodes are reachable, assign a large distance
                node_distance_to_gt2[node] = float('inf')

        # Sort degree 1 nodes by distance to the nearest degree >2 node
        # In case of ties, sort by distance to the edge (node_distances[node])
        degree_1_nodes_sorted = sorted(
            degree_1_nodes,
            key=lambda node: (node_distance_to_gt2[node], node_distances[node])
        )

        ''' maybe some other culling method is better hmm....'''

        # Remove the node closest to a degree >2 node
        node_to_remove = degree_1_nodes_sorted[0]

        # Save the distance from the edge of the node being removed
        removed_node_distances.append(node_distances[node_to_remove])

        H.remove_node(node_to_remove)

        # Recalculate degrees and distances of nodes
        node_distances = {
            node: distance[skel_coords[node][0], skel_coords[node][1]]
            for node in H.nodes()
        }
        # Visualization
        if show_plot:
            ax.clear()
            ax.imshow(mask_resized, cmap='gray', origin='upper', alpha=0.5)

            # Normalize distances for colormap
            distances = np.array(list(node_distances.values()))
            norm = plt.Normalize(vmin=distances.min(), vmax=distances.max())
            cmap = plt.cm.viridis

            # Plot the graph with remaining nodes
            remaining_pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
            node_colors = [cmap(norm(node_distances[node])) for node in H.nodes()]
            nx.draw(
                H, remaining_pos, edge_color='black', with_labels=False, node_size=50, ax=ax,
                node_color=node_colors
            )

            # Highlight the removed node
            removed_coords = (skel_coords[node_to_remove][1], skel_coords[node_to_remove][0])
            ax.scatter(*removed_coords, color='red', s=100, label=f'Removed Node {iteration}')

            ax.legend()
            ax.set_title(f"Node Removal Iteration {iteration}")
            plt.pause(0.1)  # Pause to visualize each step
            iteration += 1

    try:
        plt.close(anim_fig)
    except UnboundLocalError:
        pass  # Safely ignore if anim_fig doesn't have a close method


    # Re-connect the closest two degree-1 nodes if we have more than two endpoints
    degree_1_nodes = [node for node in H.nodes() if H.degree(node) == 1]
    if len(degree_1_nodes) > 2:
        # Find the closest pair of endpoints based on Euclidean distance between their skeleton coordinates
        dists = []
        for i in range(len(degree_1_nodes)):
            for j in range(i + 1, len(degree_1_nodes)):
                node1 = degree_1_nodes[i]
                node2 = degree_1_nodes[j]
                coord1 = skel_coords[node1]
                coord2 = skel_coords[node2]
                dist = np.linalg.norm(coord1 - coord2)
                dists.append((dist, node1, node2))

        # Sort by distance and pick the shortest one
        dists.sort(key=lambda x: x[0])
        if dists:
            closest_dist, node_a, node_b = dists[0]
            # Add an edge between these two closest endpoints
            H.add_edge(node_a, node_b, weight=closest_dist)

    # Calculate the average edge length in the graph
    if len(H.edges()) > 0:
        total_edge_weight = sum(H[u][v].get("weight", 1) for u, v in H.edges())
        num_edges = len(H.edges())
        average_edge_length = total_edge_weight / num_edges
    else:
        average_edge_length = 0  # If no edges exist, average is zero
        assert False, 'Average edge length: {average_edge_length}'

    # After the while loop, remove degree-1 nodes at the ends of paths
    if removed_node_distances:
        max_removed_distance = max(removed_node_distances)
        target_cumulative_distance = clip_ends_factor * max_removed_distance
    else:
        target_cumulative_distance = average_edge_length


    # Remove nodes at the ends of the paths
    for endpoint in [node for node in H.nodes() if H.degree(node) == 1]:
        cumulative_distance = 0
        current_node = endpoint
        path_removed = []

        while cumulative_distance < target_cumulative_distance:
            # Identify neighbors of the current node
            neighbors = list(H.neighbors(current_node))
            if not neighbors:  # No neighbors left, stop
                break

            # Choose the next node to remove (the only neighbor, since it's a path end)
            next_node = neighbors[0]

            # Add the edge weight to the cumulative distance
            if H.has_edge(current_node, next_node):
                cumulative_distance += H[current_node][next_node].get("weight", 1)

            # Remove the current node and record the removal
            path_removed.append(current_node)
            H.remove_node(current_node)

            # Move to the next node
            current_node = next_node

        # Visualization for this endpoint's removal
        if show_plot:
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.imshow(mask_resized, cmap='gray', origin='upper', alpha=0.5)

            # Plot the remaining graph
            remaining_pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
            nx.draw(
                H, remaining_pos, edge_color='black', with_labels=False, node_size=50, ax=ax,
                node_color='blue'
            )

            # Highlight removed nodes
            removed_coords = np.array([(skel_coords[node][1], skel_coords[node][0]) for node in path_removed])
            if removed_coords.size > 0:
                ax.scatter(removed_coords[:, 0], removed_coords[:, 1], color='orange', s=100, label='Removed Nodes')

            ax.legend()
            ax.set_title(f"Removing Nodes from Endpoint")
            plt.pause(0.5)
            plt.close(fig)

    # Final visualization (optional)
    if show_plot:
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.imshow(mask_resized, cmap='gray', origin='upper', alpha=0.5)

        # Plot the final graph
        remaining_pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
        nx.draw(
            H, remaining_pos, edge_color='black', with_labels=False, node_size=50, ax=ax,
            node_color='blue'
        )

        ax.set_title("Final Simplified Graph")
        plt.ioff()
        plt.show()

    # Map node indices back to coordinates for plotting or further analysis
    pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}

    # **Extract degree 1 nodes and their coordinates**
    degree_1_nodes = [node for node in H.nodes() if H.degree(node) == 1]

    degree_1_coords = np.array([pos[node] for node in degree_1_nodes])
    # Use G to compute the shortest path between the two degree_1_nodes
    shortest_path_nodes = nx.shortest_path(G, source=degree_1_nodes[0], target=degree_1_nodes[1])
    shortest_path_coords = np.array([skel_coords[node] for node in shortest_path_nodes])

    # Extract the endpoints of the shortest path
    start_point = shortest_path_coords[0]
    end_point = shortest_path_coords[-1]

    # Plot the shortest path on the skeleton
    if show_plot:
        plt.figure(figsize=(8, 8))
        plt.imshow(skeleton, cmap='gray', origin='upper')

        # Plot the shortest path
        plt.plot(shortest_path_coords[:, 1], shortest_path_coords[:, 0], color='yellow', linewidth=2,
                 label='Shortest Path')

        # Draw the simplified graph H
        nx.draw(H, pos, node_color='red', with_labels=False, node_size=50, edge_color='blue')

        # Highlight the endpoints
        plt.scatter(degree_1_coords[:, 0], degree_1_coords[:, 1], color='green', s=100, marker='x',
                    label='Endpoints')

        plt.title('Final Simplified Graph with Shortest Path (Graph-Based)')
        plt.axis('off')
        plt.legend()
        plt.show()

    # Scale shortest path coordinates back to original size
    if scale != 1.0:
        shortest_path_coords_rescaled = shortest_path_coords / scale
        start_point_rescaled = start_point / scale
        end_point_rescaled = end_point / scale
    else:
        shortest_path_coords_rescaled = shortest_path_coords
        start_point_rescaled = start_point
        end_point_rescaled = end_point

    # Mark the shortest path on the original mask
    shortest_path_mask = np.zeros_like(mask, dtype=mask.dtype)
    rows_rescaled = shortest_path_coords_rescaled[:, 0].astype(int)
    cols_rescaled = shortest_path_coords_rescaled[:, 1].astype(int)
    rows_rescaled = np.clip(rows_rescaled, 0, mask.shape[0] - 1)
    cols_rescaled = np.clip(cols_rescaled, 0, mask.shape[1] - 1)
    shortest_path_mask[rows_rescaled, cols_rescaled] = 1

    # Return the upscaled shortest_path_mask
    return shortest_path_mask, (start_point_rescaled, end_point_rescaled)


def connect_closest_ends(endss, mask_shape, show_plot=False):
    """
    Connects the closest ends of each pair of lines with straight lines of pixels.

    Parameters:
        endss (list of tuple): List of endpoints (each an iterable of (row, col) pairs)
                               for each line being considered.
        mask_shape (tuple): Shape of the mask to create for connecting lines.
        show_plot (bool): Whether to show a plot of the connecting lines (default False).

    Returns:
        np.ndarray: Binary mask containing only the connecting lines.
    """
    # Initialize an empty mask to store the connecting lines
    connecting_lines_mask = np.zeros(mask_shape, dtype=np.uint8)

    # Loop through all pairs of lines
    for i in range(len(endss)):
        for j in range(i + 1, len(endss)):
            ends1 = endss[i]
            ends2 = endss[j]

            # Find the closest pair of endpoints between these two sets
            min_distance = float('inf')
            closest_pair = None
            for end1 in ends1:
                for end2 in ends2:
                    distance = np.linalg.norm(np.array(end1) - np.array(end2))
                    if distance < min_distance:
                        min_distance = distance
                        closest_pair = (end1, end2)

            # Draw a line between the closest pair of endpoints, if any
            if closest_pair:
                start, end = closest_pair
                rr, cc = line(int(start[0]), int(start[1]), int(end[0]), int(end[1]))
                connecting_lines_mask[rr, cc] = 1

    # Optionally show the plot of the connecting lines
    if show_plot:
        plt.figure(figsize=(8, 8))
        plt.imshow(connecting_lines_mask, cmap='gray', origin='lower')
        plt.title('Connecting Lines Mask')
        plt.xlabel('Column')
        plt.ylabel('Row')
        plt.show()

    return connecting_lines_mask

def human_readable_duration(seconds):
    duration = timedelta(seconds=seconds)
    # Convert to days, hours, minutes, and seconds
    days = duration.days
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Build a human-readable string
    result = []
    if days > 0:
        result.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        result.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        result.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if seconds > 0:
        result.append(f"{seconds} second{'s' if seconds > 1 else ''}")
    return ", ".join(result)


def get_eroded_mask(overlap_mask_norm):
    height, width = overlap_mask_norm.shape # Get the dimensions of the overlap_mask_norm
    min_dim = min(height, width) # Calculate 10% of the minimum dimension
    size = max(1, int(0.1 * min_dim))  # Ensures size is at least 1
    overlap_mask_norm_no_edges = minimum_filter(overlap_mask_norm, size=size)
    return overlap_mask_norm_no_edges, size

def get_centre_path(overlap_mask):
    highlighted_middle_arr = highlight_middle(overlap_mask)
    overlap_mask_norm = overlap_mask / 255
    ridge_int_arr = calculate_inv_gradient_magnitude(highlighted_middle_arr, overlap_mask_norm, show_plot=False)
    overlap_mask_norm_no_edges, size = get_eroded_mask(overlap_mask_norm)
    ridge_int_arr_corrected = overlap_mask_norm_no_edges * ridge_int_arr + overlap_mask_norm_no_edges
    ridge_int_arr_smoothed = gaussian_filter(ridge_int_arr_corrected, sigma=1)
    threshold = np.percentile(ridge_int_arr_smoothed, 99)
    ridge_int_arr_top_percent = ridge_int_arr_smoothed >= threshold
    return ridge_int_arr_top_percent, size

def plot_2_arrays(array1, array2, title1="Array 1", title2="Array 2", cmap="gray"):
    """
    Display two 2D arrays side-by-side using matplotlib.

    Parameters:
    array1 (np.ndarray): First 2D array to display.
    array2 (np.ndarray): Second 2D array to display.
    title1 (str): Title of the first plot.
    title2 (str): Title of the second plot.
    cmap (str): Colormap to use for visualization (e.g., 'gray', 'hot').
    """
    plt.figure(figsize=(15, 7))

    # Plot the first array
    plt.subplot(1, 2, 1)
    plt.imshow(array1, cmap=cmap)
    plt.colorbar()
    plt.title(title1)
    plt.axis("off")  # Hide axis for cleaner visualization

    # Plot the second array
    plt.subplot(1, 2, 2)
    plt.imshow(array2, cmap=cmap)
    plt.colorbar()
    plt.title(title2)
    plt.axis("off")  # Hide axis for cleaner visualization

    plt.tight_layout()  # Adjust spacing to prevent overlap
    plt.show()

def plot_array(array, title="Array Visualization", cmap="gray"):
    """
    Display a 2D array using matplotlib.

    Parameters:
    array (np.ndarray): 2D array to display.
    title (str): Title of the plot.
    cmap (str): Colormap to use for visualization (e.g., 'gray', 'hot').
    """
    plt.figure(figsize=(10, 5))
    plt.imshow(array, cmap=cmap)
    plt.colorbar()
    plt.title(title)
    plt.axis("off")  # Hide axis for cleaner visualization
    plt.show()


def apply_viridis_with_transparency(input_arr, mask):
    """
    Apply the Viridis colormap to a 2D numpy array and make pixels transparent based on a mask.

    Parameters:
        input_arr (np.ndarray): 2D array to which the colormap will be applied.
        mask (np.ndarray): Boolean mask of the same shape as input_arr, where True indicates transparency.

    Returns:
        rgba_arr (np.ndarray): 3D RGBA array with the Viridis colormap applied and transparent pixels where mask is True.
    """
    # Normalize the input array to [0, 1] for colormap application
    normalized_arr = (input_arr - np.min(input_arr)) / (np.max(input_arr) - np.min(input_arr))

    # Apply the Viridis colormap
    viridis = cm.get_cmap('viridis')
    rgba_arr = viridis(normalized_arr)

    # Set alpha channel to 0 where the mask is True, 1 otherwise
    rgba_arr[..., 3] = np.where(mask, 0, 1)

    return rgba_arr


def new_calculate_inv_gradient_magnitude(input_arr, overlap_mask, erod_by, show_plot=False):
    gradient_y, gradient_x = np.gradient(input_arr)
    gradient_magnitude = np.sqrt(gradient_x ** 2 + gradient_y ** 2)
    inv_gradient_magnitude = gradient_magnitude.max() - gradient_magnitude
    overlap_mask_erod = minimum_filter(overlap_mask, erod_by)
    inv_gradient_magnitude_masked = inv_gradient_magnitude * overlap_mask_erod
    min_value = np.min(inv_gradient_magnitude_masked[overlap_mask_erod == 1])

    # Subtract min_value and normalize
    inv_gradient_magnitude_masked = np.maximum(inv_gradient_magnitude_masked - min_value, 0)  # Ensure no negative values
    max_inv_gradient_magnitude_masked = np.max(inv_gradient_magnitude_masked[overlap_mask_erod == 1])  # New max within the masked area
    if max_inv_gradient_magnitude_masked > 0:
        inv_gradient_magnitude_masked = inv_gradient_magnitude_masked / max_inv_gradient_magnitude_masked  # Normalize to range [0, 1] after adjustment

    inv_gradient_magnitude_masked = inv_gradient_magnitude_masked * overlap_mask_erod

    # Show plot if requested
    if show_plot:
        # Create a plot with two subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6))


        # Original imshow with Viridis colormap (no transparency)
        ax1.imshow(inv_gradient_magnitude_masked, cmap='viridis')
        ax1.set_title("Original Imshow with Viridis")
        ax1.axis('off')

        # Imshow with Viridis colormap and transparency from mask
        rgba_result = apply_viridis_with_transparency(input_arr, np.logical_not(overlap_mask_erod))
        ax2.imshow(rgba_result)
        ax2.set_title("Imshow with Viridis and Transparency")
        ax2.axis('off')

        # Show the plot
        plt.tight_layout()
        plt.show()

    return inv_gradient_magnitude_masked


def adjust_coordinates_by_cost(coords, centreline_mask, cost_array, search_radius):
    """Adjust coordinates to the lowest cost pixel on the centreline within a search radius.

    Parameters
    ----------
    coords : list of tuples
        List of (x, y) coordinates to adjust.
    centreline_mask : 2D array
        Binary mask where 1 indicates centreline presence.
    cost_array : 2D array
        Array of cost values corresponding to each pixel.
    search_radius : int
        Radius (in pixels) around each coordinate to search.

    Returns
    -------
    adjusted_coords : list of tuples
        Adjusted coordinates, each corresponding to the lowest cost
        centreline pixel within the search radius. If none found,
        returns the original coordinate.
    """
    adjusted_coords = []
    for i, (x, y) in enumerate(coords):
        x, y = int(x), int(y)


        # Define initial search bounds
        min_x = x - search_radius
        max_x = x + search_radius + 1
        min_y = y - search_radius
        max_y = y + search_radius + 1


        # Clamp search bounds
        min_x = max(0, min_x)
        min_y = max(0, min_y)
        max_x = min(centreline_mask.shape[1], max_x)
        max_y = min(centreline_mask.shape[0], max_y)



        # Check if search region is valid
        if min_x >= max_x or min_y >= max_y:

            adjusted_coords.append((x, y))

            continue

        # Extract local regions
        local_centreline = centreline_mask[min_y:max_y, min_x:max_x]
        local_cost = cost_array[min_y:max_y, min_x:max_x]


        if local_centreline.size == 0:

            adjusted_coords.append((x, y))

            continue

        # Gather stats
        flat_centreline = local_centreline.flatten()
        flat_cost = local_cost.flatten()


        if np.sum(flat_centreline == 1) == 0:

            adjusted_coords.append((x, y))

            continue

        # Identify indices of pixels that are on the centreline
        centreline_indices = np.where(flat_centreline == 1)[0]
        centreline_costs = flat_cost[centreline_indices]

        # Find the lowest cost among centreline pixels
        min_cost_index_in_centreline = np.argmin(centreline_costs)
        chosen_flat_index = centreline_indices[min_cost_index_in_centreline]

        # Convert flat index back to local coordinates
        local_y, local_x = np.unravel_index(chosen_flat_index, local_centreline.shape)
        chosen_x = local_x + min_x
        chosen_y = local_y + min_y

        chosen_cost = cost_array[chosen_y, chosen_x]
        chosen_val_in_mask = centreline_mask[chosen_y, chosen_x]


        adjusted_coords.append((chosen_x, chosen_y))

    return adjusted_coords

def find_shortest_distance(coords):
    """Compute the shortest distance between coordinates."""
    if len(coords) < 2:
        return 0  # No distance to compute for fewer than 2 points
    dist_matrix = distance.cdist(coords, coords, metric='euclidean')
    np.fill_diagonal(dist_matrix, np.inf)  # Ignore self-distances
    return np.min(dist_matrix)

def compute_full_path(adjusted_cropped_coords, cost_array, show_plot=False):
    # This will store the final combined path indices (row, col)
    final_path = []

    # Iterate over consecutive pairs of coords
    for i in range(len(adjusted_cropped_coords)-1):
        start_pt = adjusted_cropped_coords[i]   # (x, y)
        end_pt = adjusted_cropped_coords[i+1]   # (x, y)

        # Determine bounding box around the two points
        min_x = min(start_pt[0], end_pt[0])
        max_x = max(start_pt[0], end_pt[0])
        min_y = min(start_pt[1], end_pt[1])
        max_y = max(start_pt[1], end_pt[1])

        # Add a 20% margin to bounding box
        # Use the largest dimension (either width or height) for margin calculation
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        largest_dim = max(width, height)
        margin = max(1, int(0.2 * largest_dim))  # Ensure margin is at least 1 pixel

        # Apply the margin uniformly to both dimensions
        sub_min_x = max(0, min_x - margin)
        sub_min_y = max(0, min_y - margin)
        sub_max_x = min(cost_array.shape[1] - 1, max_x + margin)
        sub_max_y = min(cost_array.shape[0] - 1, max_y + margin)

        # Extract the sub-array
        sub_cost_array = cost_array[sub_min_y:sub_max_y+1, sub_min_x:sub_max_x+1]

        # Adjust start and end coordinates to sub-array's coordinate system
        # route_through_array expects (row, col) = (y, x)
        sub_start = (start_pt[1] - sub_min_y, start_pt[0] - sub_min_x)
        sub_end = (end_pt[1] - sub_min_y, end_pt[0] - sub_min_x)

        # Run route_through_array on the smaller array
        indices, weight = route_through_array(sub_cost_array, sub_start, sub_end, fully_connected=True)
        # Convert sub-array indices back to full coordinates
        full_indices = [(r + sub_min_y, c + sub_min_x) for (r, c) in indices]

        # If plotting inside the loop
        if show_plot:
            plt.figure(figsize=(8, 8))
            plt.title(f"Sub-path {i+1} of {len(adjusted_cropped_coords)-1}")
            plt.imshow(sub_cost_array, cmap='gray', origin='lower')
            # Plot start and end on sub array (note swap x,y to c,r for plotting)
            plt.scatter(sub_start[1], sub_start[0], label='Sub Start', s=50, color='green')
            plt.scatter(sub_end[1], sub_end[0], label='Sub End', s=50, color='red')
            # Plot the path
            path_cols = [p[1] for p in indices]
            path_rows = [p[0] for p in indices]
            plt.plot(path_cols, path_rows, linewidth=2, label='Sub-path', color='blue')
            plt.legend()
            plt.xlabel("Column")
            plt.ylabel("Row")
            plt.show()

        # Append to final_path, avoiding duplication of the joining point
        if i > 0:
            # Omit the first point of this segment as it was the last of the previous one
            full_indices = full_indices[1:]
        final_path.extend(full_indices)

    # Optional: plot the final combined path over the full cost_array
    if show_plot:
        plt.figure(figsize=(10, 10))
        plt.imshow(cost_array, cmap='gray', origin='lower')
        path_cols = [p[1] for p in final_path]
        path_rows = [p[0] for p in final_path]
        plt.plot(path_cols, path_rows, linewidth=2, color='magenta', label='Final Path')
        plt.scatter(final_path[0][1], final_path[0][0], color='green', s=100, label='Start')
        plt.scatter(final_path[-1][1], final_path[-1][0], color='red', s=100, label='End')
        plt.title("Final Combined Path at Full Scale")
        plt.xlabel("Column")
        plt.ylabel("Row")
        plt.legend()
        plt.show()

    return final_path


# Cull the adjusted_cropped_coords
def cull_coordinates(coords):
    """
    Cull the coordinates to keep the first and last points and remove 50% of the points in between.

    Parameters
    ----------
    coords : list of tuples
        List of coordinates to cull.

    Returns
    -------
    culled_coords : list of tuples
        Culled list of coordinates.
    """
    if len(coords) <= 2:
        # If there are 2 or fewer points, just return the original list
        return coords

    # Keep the first point, then take every other point from the middle, and the last point
    culled_coords = [coords[0]] + coords[1:-1][::2] + [coords[-1]]
    return culled_coords


def find_path(path_pref, overlap_mask, start, end, centreline_mask, full_centreline_coords_xy, show_plot=False):
    # Determine the bounding box of the overlap_mask
    rows, cols = np.where(overlap_mask == 1)
    min_row, max_row = rows.min(), rows.max()
    min_col, max_col = cols.min(), cols.max()

    del overlap_mask
    gc.collect()

    # Determine if cropping is needed based on the cropped area
    row_size, col_size = path_pref.shape
    original_area = row_size * col_size
    cropped_rows = max_row - min_row + 1
    cropped_cols = max_col - min_col + 1
    cropped_area = cropped_rows * cropped_cols

    # Skip cropping if cropped area >= 80% of original area
    skip_cropping = (cropped_area >= 0.80 * original_area)
    print(f'{skip_cropping = }')

    if skip_cropping:
        # No cropping
        cropped_path_pref = path_pref
        cropped_centreline_mask = centreline_mask
        cropped_full_centreline_coords_xy = full_centreline_coords_xy
        cropped_start = start
        cropped_end = end
    else:
        # Perform cropping
        cropped_path_pref = path_pref[min_row:max_row + 1, min_col:max_col + 1]
        cropped_centreline_mask = centreline_mask[min_row:max_row + 1, min_col:max_col + 1]

        cropped_full_centreline_coords_xy = [
            (x - min_col, y - min_row)
            for x, y in full_centreline_coords_xy
            if min_row <= y <= max_row and min_col <= x <= max_col
        ]

        cropped_start = (start[0] - min_row, start[1] - min_col)
        cropped_end = (end[0] - min_row, end[1] - min_col)


    # Plot before and after cropping
    if show_plot:
        fig, axes = plt.subplots(2, 2, figsize=(15, 15))

        # Plot original path_pref and centreline_mask
        axes[0, 0].imshow(path_pref, cmap='gray', origin='lower')
        axes[0, 0].scatter(start[1], start[0], color='green', label='Start', s=50)
        axes[0, 0].scatter(end[1], end[0], color='red', label='End', s=50)
        if len(cropped_full_centreline_coords_xy) > 0:
            cx, cy = zip(*full_centreline_coords_xy)
            axes[0, 0].scatter(cx, cy, color='blue', label='Original Centreline', s=10)
        axes[0, 0].set_title("Original Path Preference")
        axes[0, 0].legend()

        axes[0, 1].imshow(centreline_mask, cmap='gray', origin='lower')
        axes[0, 1].set_title("Original Centreline Mask")

        # Plot cropped path_pref and centreline_mask
        axes[1, 0].imshow(cropped_path_pref, cmap='gray', origin='lower')
        axes[1, 0].scatter(cropped_start[1], cropped_start[0], color='green', label='Start (Adjusted)', s=50)
        axes[1, 0].scatter(cropped_end[1], cropped_end[0], color='red', label='End (Adjusted)', s=50)
        if len(cropped_full_centreline_coords_xy)>0:
            cx, cy = zip(*cropped_full_centreline_coords_xy)
            axes[1, 0].scatter(cx, cy, color='blue', label='Cropped Centreline', s=10)
        axes[1, 0].set_title("Cropped Path Preference")
        axes[1, 0].legend()

        axes[1, 1].imshow(cropped_centreline_mask, cmap='gray', origin='lower')
        axes[1, 1].set_title("Cropped Centreline Mask")

        plt.tight_layout()
        plt.show()



    cropped_path_pref *= 255

    cost_array = cropped_path_pref.max() - cropped_path_pref
    cost_array = cost_array.astype(np.uint8)


    print(f'{len(np.unique(cost_array))=}')

    if show_plot:
        plt.figure(figsize=(10, 10))
        plt.imshow(cost_array, cmap='gray', origin='lower', alpha=0.7, label='Cost Array')
        plt.show()

    # Compute shortest distance and define search radius
    shortest_distance_coords = find_shortest_distance(cropped_full_centreline_coords_xy)
    search_radius = int(0.4 * shortest_distance_coords)

    # Separate start & end before culling
    #start_coord = cropped_full_centreline_coords_xy[0]
    #end_coord = cropped_full_centreline_coords_xy[-1]
    middle_coords = cropped_full_centreline_coords_xy[1:-1]

    # Cull coordinates before adjust_coordinates_by_cost (every other point)
    middle_coords = middle_coords[::2]

    # Adjust only the middle coords
    adjusted_middle_coords = []
    if len(middle_coords) > 0:
        adjusted_middle_coords = adjust_coordinates_by_cost(
            middle_coords, cropped_centreline_mask, cost_array, search_radius
        )

    # Reassemble final adjusted coords
    adjusted_cropped_coords = [(cropped_start[1], cropped_start[0])] + adjusted_middle_coords + [(cropped_end[1], cropped_end[0])]

    # Plot before route_through_array if show_plot
    if show_plot:
        plt.figure(figsize=(10, 10))
        plt.imshow(cost_array, cmap='gray', origin='lower', alpha=0.7, label='Cost Array')
        plt.imshow(cropped_centreline_mask, cmap='viridis', origin='lower', alpha=0.5, label='Centreline Mask')
        plt.scatter(cropped_start[1], cropped_start[0], color='green', label='Start (Adjusted)', s=50)
        plt.scatter(cropped_end[1], cropped_end[0], color='red', label='End (Adjusted)', s=50)

        if len(cropped_full_centreline_coords_xy) > 0:
            cx, cy = zip(*cropped_full_centreline_coords_xy)
            plt.scatter(cx, cy, color='blue', label='Original Centreline', s=10)

        if len(adjusted_cropped_coords) > 0:
            ax, ay = zip(*adjusted_cropped_coords)
            plt.scatter(ax, ay, color='orange', label='Adjusted Centreline', s=10)

        plt.title("Adjusted Coordinate Frame with Centreline Adjustments (Cropped)")
        plt.xlabel("Column")
        plt.ylabel("Row")
        plt.legend()
        plt.show()

    # Compute full path from pairs of adjusted_cropped_coords
    cropped_path = compute_full_path(adjusted_cropped_coords, cost_array, show_plot=show_plot)

    if not skip_cropping:
        # Un-crop the path back to original coordinates
        un_cropped_path = [(r + min_row, c + min_col) for (r, c) in cropped_path]

        # Plot un-cropped result if show_plot
        if show_plot:
            plt.figure(figsize=(10, 10))
            plt.imshow(path_pref, cmap='gray', origin='lower', alpha=0.7, label='Original Cost Array')
            if len(un_cropped_path) > 0:
                path_cols = [p[1] for p in un_cropped_path]
                path_rows = [p[0] for p in un_cropped_path]
                plt.plot(path_cols, path_rows, linewidth=2, color='magenta', label='Un-cropped Final Path')
                plt.scatter(start[1], start[0], color='green', s=100, label='Start')
                plt.scatter(end[1], end[0], color='red', s=100, label='End')

            plt.title("Final Path (Un-cropped)")
            plt.xlabel("Column")
            plt.ylabel("Row")
            plt.legend()
            plt.show()

        final_path = un_cropped_path
    else:
        # No cropping, cropped_path is already in original coordinates
        final_path = cropped_path

    # Create a uint8 mask of the same shape as path_pref
    path_mask = np.zeros(path_pref.shape, dtype=np.uint8)
    for (r, c) in final_path:
        path_mask[r, c] = 1

    return path_mask


def get_overlap_mask_old(first_ds, second_ds):
    """
    Returns a mask representing the overlap (AND operation) between two rasters,
    with any holes in the mask filled.
    """
    # Helper function to compute pixel bounds for overlap
    def compute_window(ds, overlap_minx, overlap_maxx, overlap_miny, overlap_maxy):
        gt = ds.GetGeoTransform()
        inv_gt = gdal.InvGeoTransform(gt)
        px_ul, py_ul = gdal.ApplyGeoTransform(inv_gt, overlap_minx, overlap_maxy)
        px_lr, py_lr = gdal.ApplyGeoTransform(inv_gt, overlap_maxx, overlap_miny)
        xoff = max(0, int(np.floor(min(px_ul, px_lr))))
        yoff = max(0, int(np.floor(min(py_ul, py_lr))))
        xend = min(ds.RasterXSize, max(0, int(np.ceil(max(px_ul, px_lr)))))
        yend = min(ds.RasterYSize, max(0, int(np.ceil(max(py_ul, py_lr)))))
        xsize = xend - xoff
        ysize = yend - yoff
        return xoff, yoff, xsize, ysize

    # Get extents of datasets
    gt1 = first_ds.GetGeoTransform()
    gt2 = second_ds.GetGeoTransform()
    extent1 = (gt1[0], gt1[3] + first_ds.RasterYSize * gt1[5],
               gt1[0] + first_ds.RasterXSize * gt1[1], gt1[3])
    extent2 = (gt2[0], gt2[3] + second_ds.RasterYSize * gt2[5],
               gt2[0] + second_ds.RasterXSize * gt2[1], gt2[3])

    # Calculate overlap extent
    overlap_minx = max(extent1[0], extent2[0])
    overlap_maxx = min(extent1[2], extent2[2])
    overlap_miny = max(extent1[1], extent2[1])
    overlap_maxy = min(extent1[3], extent2[3])

    if overlap_minx >= overlap_maxx or overlap_miny >= overlap_maxy:
        return None, None  # No overlap

    # Compute windows for overlapping regions
    xoff1, yoff1, xsize1, ysize1 = compute_window(first_ds, overlap_minx, overlap_maxx, overlap_miny, overlap_maxy)
    xoff2, yoff2, xsize2, ysize2 = compute_window(second_ds, overlap_minx, overlap_maxx, overlap_miny, overlap_maxy)

    xsize = min(xsize1, xsize2)
    ysize = min(ysize1, ysize2)
    if xsize <= 0 or ysize <= 0:
        return None, None  # No valid overlap

    print(f"Overlap extent: minx={overlap_minx}, maxx={overlap_maxx}, miny={overlap_miny}, maxy={overlap_maxy}")
    print(f"Window for first raster: xoff={xoff1}, yoff={yoff1}, xsize={xsize1}, ysize={ysize1}")
    print(f"Window for second raster: xoff={xoff2}, yoff={yoff2}, xsize={xsize2}, ysize={ysize2}")

    # Read only overlapping regions
    band1 = first_ds.GetRasterBand(1).ReadAsArray(xoff1, yoff1, xsize, ysize)
    band2 = second_ds.GetRasterBand(1).ReadAsArray(xoff2, yoff2, xsize, ysize)

    # Create initial overlap mask
    mask = np.logical_and(band1 != 0, band2 != 0).astype(np.uint8)

    # Fill holes in the mask
    filled_mask = binary_fill_holes(mask).astype(np.uint8) * 255

    # Compute overlap geotransform
    overlap_geotransform = (
        gt1[0] + xoff1 * gt1[1],
        gt1[1],
        0,
        gt1[3] + yoff1 * gt1[5],
        0,
        gt1[5]
    )

    return filled_mask, overlap_geotransform

def get_overlap_mask_old(first_ds, second_ds):
    """
    Returns a mask representing the overlap (AND operation) between two rasters.
    """
    # Helper function to get the extent of a dataset
    def get_extent(ds):
        gt = ds.GetGeoTransform()
        cols = ds.RasterXSize
        rows = ds.RasterYSize
        minx = gt[0]
        maxx = gt[0] + cols * gt[1]
        miny = gt[3] + rows * gt[5]
        maxy = gt[3]
        return (minx, miny, maxx, maxy)

    # Compute extents
    extent1 = get_extent(first_ds)
    extent2 = get_extent(second_ds)

    # Find overlapping region
    overlap_minx = max(extent1[0], extent2[0])
    overlap_maxx = min(extent1[2], extent2[2])
    overlap_miny = max(extent1[1], extent2[1])
    overlap_maxy = min(extent1[3], extent2[3])

    if (overlap_minx >= overlap_maxx) or (overlap_miny >= overlap_maxy):
        print("No overlap between the two rasters.")
        return None, None, None, None

    # Helper function to compute offsets and sizes
    def compute_window(ds, overlap_minx, overlap_maxx, overlap_miny, overlap_maxy):
        gt = ds.GetGeoTransform()
        inv_gt = gdal.InvGeoTransform(gt)
        # Map overlap region to pixel coordinates in the dataset
        px_ul, py_ul = gdal.ApplyGeoTransform(inv_gt, overlap_minx, overlap_maxy)
        px_lr, py_lr = gdal.ApplyGeoTransform(inv_gt, overlap_maxx, overlap_miny)
        # Compute integer pixel indices
        xoff = int(np.floor(min(px_ul, px_lr)))
        yoff = int(np.floor(min(py_ul, py_lr)))
        xend = int(np.ceil(max(px_ul, px_lr)))
        yend = int(np.ceil(max(py_ul, py_lr)))
        xsize = xend - xoff
        ysize = yend - yoff
        # Clip to dataset dimensions
        xoff = max(0, xoff)
        yoff = max(0, yoff)
        xsize = max(0, min(ds.RasterXSize - xoff, xsize))
        ysize = max(0, min(ds.RasterYSize - yoff, ysize))
        return xoff, yoff, xsize, ysize

    # Compute windows for both datasets
    xoff1, yoff1, xsize1, ysize1 = compute_window(first_ds, overlap_minx, overlap_maxx, overlap_miny, overlap_maxy)
    xoff2, yoff2, xsize2, ysize2 = compute_window(second_ds, overlap_minx, overlap_maxx, overlap_miny, overlap_maxy)

    # Use the smallest window size to ensure both datasets have the same dimensions
    xsize = min(xsize1, xsize2)
    ysize = min(ysize1, ysize2)

    if xsize <= 0 or ysize <= 0:
        print("No valid overlap in pixel coordinates.")
        return None, None, None, None

    # Read bands for the overlapping region
    num_bands1 = first_ds.RasterCount
    bands1 = [first_ds.GetRasterBand(i + 1).ReadAsArray(xoff1, yoff1, xsize, ysize) for i in range(num_bands1)]
    num_bands2 = second_ds.RasterCount
    bands2 = [second_ds.GetRasterBand(i + 1).ReadAsArray(xoff2, yoff2, xsize, ysize) for i in range(num_bands2)]

    # Stack bands
    stacked_data1 = np.stack(bands1, axis=-1)
    stacked_data2 = np.stack(bands2, axis=-1)

    # Create overlap mask
    valid1 = np.any(stacked_data1 != 0, axis=-1)
    valid2 = np.any(stacked_data2 != 0, axis=-1)
    mask = np.zeros_like(valid1, dtype=np.uint8)
    mask[valid1 & valid2] = 255

    # Compute overlap geotransform based on the first dataset
    gt1 = first_ds.GetGeoTransform()
    overlap_geotransform = (
        gt1[0] + xoff1 * gt1[1],
        gt1[1],
        0,
        gt1[3] + yoff1 * gt1[5],
        0,
        gt1[5]
    )

    first_ds = None
    second_ds = None

    return mask, overlap_geotransform

def get_footprint_mask(first_raster_path, second_raster_path):
    """
    Returns a mask representing the footprint (OR operation) of two rasters,
    showing areas covered by either raster minus transparent edges.
    """

    # Open the datasets
    first_ds = gdal.Open(first_raster_path)
    second_ds = gdal.Open(second_raster_path)

    # Get geotransforms and projections
    gt1 = first_ds.GetGeoTransform()
    proj1 = first_ds.GetProjection()

    # Calculate the full footprint extent that contains both rasters
    extent1 = get_extent(first_ds)
    extent2 = get_extent(second_ds)

    footprint_minx = min(extent1[0], extent2[0])
    footprint_maxx = max(extent1[2], extent2[2])
    footprint_miny = min(extent1[1], extent2[1])
    footprint_maxy = max(extent1[3], extent2[3])

    # Calculate the size of the footprint in pixels based on the geotransform
    pixel_width = gt1[1]
    pixel_height = abs(gt1[5])
    xsize = int(np.ceil((footprint_maxx - footprint_minx) / pixel_width))
    ysize = int(np.ceil((footprint_maxy - footprint_miny) / pixel_height))

    # Define the geotransform for the footprint grid
    footprint_geotransform = (
        footprint_minx,
        pixel_width,
        0,
        footprint_maxy,
        0,
        -pixel_height
    )

    # Reproject each raster onto the footprint grid
    def reproject_to_footprint(ds, xsize, ysize, geotransform, projection):
        mem_driver = gdal.GetDriverByName('MEM')
        reprojected_ds = mem_driver.Create('', xsize, ysize, 1, gdal.GDT_Byte)
        reprojected_ds.SetGeoTransform(geotransform)
        reprojected_ds.SetProjection(projection)

        gdal.ReprojectImage(
            ds, reprojected_ds,
            ds.GetProjection(), projection,
            gdal.GRA_NearestNeighbour
        )

        # Read reprojected band as array
        band = reprojected_ds.GetRasterBand(1)
        data = band.ReadAsArray()
        band = None
        reprojected_ds = None

        # Mask for non-zero (valid) data
        return data != 0

    valid1 = reproject_to_footprint(first_ds, xsize, ysize, footprint_geotransform, proj1)
    valid2 = reproject_to_footprint(second_ds, xsize, ysize, footprint_geotransform, proj1)

    # Create the footprint mask using an "OR" operation
    mask = np.zeros((ysize, xsize), dtype=np.uint8)
    mask[valid1 | valid2] = 255

    first_ds = None
    second_ds = None

    return mask, footprint_geotransform, proj1


import numpy as np

def get_extended_extent(mask, buffer_ratio=0.1):
    """
    Get the extended extent of a mask with a buffer added to all sides.
    Ensures the buffer does not exceed the bounds of the mask array and that
    the extent values make sense.

    Parameters:
        mask: numpy.ndarray
            A 2D binary mask array with 1s indicating the area of interest.
        buffer_ratio: float
            The percentage (as a fraction) to extend the bounds in each direction.

    Returns:
        tuple: The extended extent (min_row, min_col, max_row, max_col).
    """
    # Find the bounding box of the 1s in the mask
    rows, cols = np.where(mask == 1)
    if rows.size == 0 or cols.size == 0:
        raise ValueError("The mask does not contain any 1s.")

    min_row, max_row = rows.min(), rows.max()
    min_col, max_col = cols.min(), cols.max()

    # Calculate the buffer size
    height = max_row - min_row + 1
    width = max_col - min_col + 1

    buffer_rows = int(np.ceil(buffer_ratio * height))
    buffer_cols = int(np.ceil(buffer_ratio * width))

    # Ensure the buffer does not go beyond the array bounds
    extended_min_row = max(0, min_row - buffer_rows)
    extended_max_row = min(mask.shape[0] - 1, max_row + buffer_rows)
    extended_min_col = max(0, min_col - buffer_cols)
    extended_max_col = min(mask.shape[1] - 1, max_col + buffer_cols)

    # Validate the output extent
    if extended_min_row >= extended_max_row or extended_min_col >= extended_max_col:
        raise ValueError(
            f"Invalid extent: (min_row={extended_min_row}, max_row={extended_max_row}, "
            f"min_col={extended_min_col}, max_col={extended_max_col})."
        )

    return (extended_min_row, extended_min_col, extended_max_row, extended_max_col)




def highlight_middle(overlap_mask):
    """
    Calculate the centerline of the overlap mask where pixel values represent
    distance from the nearest edge, scaled from 0 at the edges to 254 at the center.

    Parameters:
    overlap_mask (np.ndarray): 2D binary array where 255 represents overlap area,
                               and 0 represents the edge.

    Returns:
    np.ndarray: 2D array with values scaled between 0 (edge) and 254 (center).
    """
    # Ensure overlap mask is binary: 1 for overlap, 0 for background
    binary_mask = (overlap_mask > 0).astype(int)

    # Compute the Euclidean distance transform within the overlap region
    distance = distance_transform_edt(binary_mask)

    # Normalize distance to a range of 0 to 254
    max_distance = np.max(distance)
    highlighted_middle = (distance / max_distance) * 254
    highlighted_middle = highlighted_middle.astype(np.uint8)

    return highlighted_middle

def generate_linestring(mask, num_points = 15, show_plot = False):
    # Step 1: Extract coordinates of the pixels where mask == 1
    coords = np.column_stack(np.nonzero(mask))  # Shape: (N, 2), where N is the number of ones

    # Step 2: Find the start and end points by finding the two furthest points
    # Use Convex Hull to reduce computation for large datasets
    hull = ConvexHull(coords)
    hull_coords = coords[hull.vertices]

    # Compute pairwise distances among hull points
    hull_dists = distance.pdist(hull_coords, 'euclidean')
    hull_dists_square = distance.squareform(hull_dists)

    # Find the indices of the two furthest points
    i, j = np.unravel_index(np.argmax(hull_dists_square), hull_dists_square.shape)
    start_point = hull_coords[i]
    end_point = hull_coords[j]


    t_values = np.linspace(0, 1, num_points)
    line_points = start_point + t_values[:, None] * (end_point - start_point)

    # Step 4: Project all the pixels onto the line
    line_dir = end_point - start_point
    line_dir_norm = line_dir / np.linalg.norm(line_dir)
    vecs = coords - start_point
    proj_lengths = np.dot(vecs, line_dir_norm)
    projected_points = start_point + np.outer(proj_lengths, line_dir_norm)

    # Step 5: Adjust the intermediate points to the nearest original pixel
    intermediate_line_points = line_points[1:-1]  # Exclude start and end points
    # Compute distances between intermediate points and projected pixels
    dists = distance.cdist(intermediate_line_points, projected_points)
    # Find indices of the closest projected pixels
    closest_indices = np.argmin(dists, axis=1)
    # Map back to original pixel coordinates
    closest_pixel_coords = coords[closest_indices]

    # Combine start point, adjusted intermediate points, and end point
    final_coords = np.vstack([start_point, closest_pixel_coords, end_point])

    if show_plot:
        plot_linestring_over_mask(mask, final_coords)

    return final_coords


def plot_linestring_over_mask(mask, linestring):
    # Plot the mask points
    mask_coords = np.column_stack(np.nonzero(mask))
    plt.scatter(mask_coords[:, 1], mask_coords[:, 0], color='lightgrey', label='Mask Points', s=10)
    plt.axis("equal")
    # Plot the final line coordinates on top of the mask
    plt.plot(linestring[:, 1], linestring[:, 0], color='blue', marker='o', markersize=5, linestyle='-', label='Path Coordinates')

    # Mark start and end points for clarity
    plt.scatter(linestring[0, 1], linestring[0, 0], color='green', s=100, label='Start Point')
    plt.scatter(linestring[-1, 1], linestring[-1, 0], color='red', s=100, label='End Point')

    # Labeling the plot
    plt.gca().invert_yaxis()  # Invert y-axis for proper orientation
    plt.legend()
    plt.title("Mask with Path Coordinates Overlay")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.show()

def reverse_order_sample_arr(input_arr, show_plot=False):
    """
    Reverses the order of non-zero elements in `input_arr` while maintaining their positions.

    Parameters:
    - input_arr: numpy array, input array with sampled values.
    - show_plot: bool, if True, plots the input and output arrays.

    Returns:
    - reversed_input_arr: numpy array with the reversed order of non-zero elements.
    """

    line = input_arr[np.where(input_arr>0)]

    line_rev = line.max()-line

    # Create a new array to store the reversed order
    reversed_input_arr = np.zeros_like(input_arr)
    reversed_input_arr[np.where(input_arr>0)] = line_rev

    # Plot the input and output arrays if show_plot is True
    if show_plot:
        plt.figure(figsize=(10, 5))

        # Plot the input array
        plt.subplot(1, 2, 1)
        plt.title("Input Array")
        plt.imshow(input_arr, cmap='viridis')
        plt.colorbar(label="Value")
        plt.xlabel("Columns")
        plt.ylabel("Rows")

        # Plot the reversed array
        plt.subplot(1, 2, 2)
        plt.title("Reversed Array")
        plt.imshow(reversed_input_arr, cmap='viridis')
        plt.colorbar(label="Value")
        plt.xlabel("Columns")
        plt.ylabel("Rows")

        plt.tight_layout()
        plt.show()

    return reversed_input_arr


def first_match_position(integer_path, gappy_mask, show_plot=False):
    """
    Finds the row and column of the first pixel in `integer_path` that lands on a '1' in `gappy_mask`.

    Parameters:
    - integer_path: numpy array, integer array with ordered pixel path.
    - gappy_mask: numpy array, binary mask with 1s and 0s.
    - show_plot: bool, if True, plots the input arrays and the match result.

    Returns:
    - (row, col): Tuple of the row and column of the first matching pixel.
                  Returns None if no matching pixel is found.
    """

    # Ensure both arrays are of the same shape
    assert integer_path.shape == gappy_mask.shape, "Shapes of integer_path and gappy_mask must match."

    # Find the positions in integer_path that correspond to '1' in gappy_mask
    match_positions = (integer_path > 0) & (gappy_mask == 1)

    # Get the integer_path values at these matching positions
    output_values = np.where(match_positions, integer_path, 0)

    # Check if there are any non-zero values in output_values
    non_zero_values = output_values[output_values > 0]
    if non_zero_values.size == 0:
        if show_plot:
            plt.figure(figsize=(8, 6))
            plt.title("Integer Path and Gappy Mask")
            plt.imshow(integer_path, cmap='viridis', alpha=0.5)
            plt.imshow(gappy_mask, cmap='gray', alpha=0.7)
            plt.colorbar(label="Integer Path Values")
            plt.show()
        return None  # No match found

    # Find the smallest non-zero value
    min_value = non_zero_values.min()

    # Get the position of the first match (row, col) based on the smallest value
    row, col = np.argwhere(integer_path == min_value)[0]

    # Plot the inputs and match result if show_plot is True
    if show_plot:
        plt.figure(figsize=(8, 6))
        plt.title("Integer Path and Gappy Mask with Match Highlight")

        # Overlay integer_path as a contour
        plt.contour(
            integer_path,
            levels=[0.5],  # Contour at boundaries of the integer path
            colors='black',
            linewidths=1
        )

        # Overlay gappy_mask
        plt.imshow(gappy_mask, cmap='gray', alpha=0.5)

        # Highlight the match result
        plt.scatter(col, row, color='red', marker='o', label='First Match (row, col)')

        # Add legend and colorbar
        plt.legend()
        plt.colorbar(label="Gappy Mask and Integer Path Overlay")
        plt.xlabel("Column Index")
        plt.ylabel("Row Index")
        plt.show()

    return row, col


def calculate_inv_gradient_magnitude(input_arr, overlap_mask_norm, show_plot=False):
    # Calculate gradients in the y and x directions
    gradient_y, gradient_x = np.gradient(input_arr)

    # Compute gradient magnitude
    gradient_magnitude = np.sqrt(gradient_x ** 2 + gradient_y ** 2)

    ridge_int_arr_iverted = gradient_magnitude.max() - gradient_magnitude

    ridge_int_arr_iverted = ridge_int_arr_iverted * overlap_mask_norm


    # Show plot if requested
    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(ridge_int_arr_iverted, cmap='viridis')
        plt.colorbar(label='Inv Gradient Magnitude')
        plt.title('Inv Gradient Magnitude')
        plt.show()

    return ridge_int_arr_iverted


def extend_linestring_past_footprint(linestring_coords_xy, raster_path, footprint_vrt_path, show_plot=False):
    # Load the raster to get geotransform and to plot
    raster_ds = gdal.Open(raster_path)
    if raster_ds is None:
        raise ValueError(f"Unable to open raster file at {raster_path}")

    raster_geotransform = raster_ds.GetGeoTransform()
    raster_width = raster_ds.RasterXSize
    raster_height = raster_ds.RasterYSize

    # Load the footprint VRT to get geotransform and size
    footprint_ds = gdal.Open(footprint_vrt_path)
    if footprint_ds is None:
        raise ValueError(f"Unable to open VRT file at {footprint_vrt_path}")

    footprint_geotransform = footprint_ds.GetGeoTransform()
    footprint_width = footprint_ds.RasterXSize
    footprint_height = footprint_ds.RasterYSize

    # Debugging information
    print(f"Raster geotransform: {raster_geotransform}")
    print(f"Raster dimensions: {raster_width} x {raster_height}")
    print(f"Footprint geotransform: {footprint_geotransform}")
    print(f"Footprint dimensions: {footprint_width} x {footprint_height}")

    # Plot the raster with linestring_coords_xy on top in the raster's coordinate system (pixel coordinates)
    if show_plot:
        # Read the raster data (assuming it's a single-band raster for simplicity)
        raster_band = raster_ds.GetRasterBand(1)
        raster_data = raster_band.ReadAsArray()

        plt.figure(figsize=(10, 10))
        plt.imshow(raster_data, cmap='gray', origin='upper')
        x_coords = [coord[0] for coord in linestring_coords_xy]
        y_coords = [coord[1] for coord in linestring_coords_xy]
        plt.plot(x_coords, y_coords, 'r-', linewidth=2, label='Linestring (Pixel Coordinates)')
        plt.scatter(x_coords, y_coords, c='red')
        plt.legend()
        plt.title('Raster with Linestring in Pixel Coordinates')
        plt.xlabel('Pixel X')
        plt.ylabel('Pixel Y')
        plt.gca().invert_yaxis()  # Invert Y-axis if needed (depends on raster orientation)
        plt.show()

    # Now, transform the linestring_coords_xy to world coordinates using the raster's geotransform
    def pixel_to_world(geo_transform, x, y):
        world_x = geo_transform[0] + x * geo_transform[1] + y * geo_transform[2]
        world_y = geo_transform[3] + x * geo_transform[4] + y * geo_transform[5]
        return (world_x, world_y)

    world_coords = [pixel_to_world(raster_geotransform, x, y) for x, y in linestring_coords_xy]

    # Plot the raster in world coordinates with the transformed linestring overlaid
    if show_plot:
        # Read the raster data again if necessary (assuming single-band raster)
        raster_band = raster_ds.GetRasterBand(1)
        raster_data = raster_band.ReadAsArray()

        # Create extent for the raster in world coordinates
        min_x = raster_geotransform[0]
        max_y = raster_geotransform[3]
        max_x = min_x + raster_width * raster_geotransform[1] + raster_height * raster_geotransform[2]
        min_y = max_y + raster_width * raster_geotransform[4] + raster_height * raster_geotransform[5]
        extent = [min_x, max_x, min_y, max_y]

        plt.figure(figsize=(10, 10))
        plt.imshow(raster_data, cmap='gray', extent=extent, origin='upper')
        x_coords_world = [coord[0] for coord in world_coords]
        y_coords_world = [coord[1] for coord in world_coords]
        plt.plot(x_coords_world, y_coords_world, 'r-', linewidth=2, label='Linestring (World Coordinates)')
        plt.scatter(x_coords_world, y_coords_world, c='red')
        plt.legend()
        plt.title('Raster with Linestring in World Coordinates')
        plt.xlabel('World X')
        plt.ylabel('World Y')
        plt.show()

    # Proceed with the extension logic
    # Helper function to convert pixel space to world space (already defined)
    # pixel_to_world = ...

    # Now proceed to calculate the alignment and extension as before
    # Since we now have the geotransform and world coordinates, we can adjust the offsets

    # Calculate offsets between the geotransforms
    x_offset = footprint_geotransform[0] - raster_geotransform[0]
    y_offset = footprint_geotransform[3] - raster_geotransform[3]

    print(f"Calculated offsets: x_offset={x_offset}, y_offset={y_offset}")

    # Adjust linestring coordinates for alignment
    aligned_coords = [
        (
            (x - x_offset) / raster_geotransform[1],
            (y - y_offset) / raster_geotransform[5]
        )
        for x, y in world_coords  # world_coords are in world space
    ]

    # Create a LineString from the world coordinates
    line = LineString(world_coords)

    # Calculate the bounding box of the footprint in world coordinates
    def get_raster_extent(geo_transform, width, height):
        x_min = geo_transform[0]
        y_max = geo_transform[3]
        x_max = x_min + width * geo_transform[1] + height * geo_transform[2]
        y_min = y_max + width * geo_transform[4] + height * geo_transform[5]
        return x_min, x_max, y_min, y_max

    footprint_extent = get_raster_extent(footprint_geotransform, footprint_width, footprint_height)
    print(f"Footprint extent: {footprint_extent}")

    # Create footprint polygon
    footprint_polygon = Polygon([
        (footprint_extent[0], footprint_extent[3]),  # Upper-left
        (footprint_extent[1], footprint_extent[3]),  # Upper-right
        (footprint_extent[1], footprint_extent[2]),  # Lower-right
        (footprint_extent[0], footprint_extent[2]),  # Lower-left
        (footprint_extent[0], footprint_extent[3])  # Close the polygon
    ])

    # Points and directions for extension
    if len(line.coords) < 2:
        print("Linestring has fewer than 2 points.")
        raise ValueError("Linestring must have at least 2 points.")

    start = Point(line.coords[0])
    end = Point(line.coords[-1])
    second_point = Point(line.coords[1])
    second_last_point = Point(line.coords[-2])

    # Extend start and end points
    try:
        extended_start = extend_to_bbox(second_point, start, footprint_polygon, show_plot=show_plot)
    except Exception as e:
        print(f"Error extending start point: {e}")
        raise

    try:
        extended_end = extend_to_bbox(second_last_point, end, footprint_polygon, show_plot=show_plot)
    except Exception as e:
        print(f"Error extending end point: {e}")
        raise

    print(f"Extended start: {extended_start}, Extended end: {extended_end}")

    # Create extended coordinates list
    if len(line.coords) > 2:
        middle_coords = [Point(coord) for coord in line.coords[1:-1]]
    else:
        middle_coords = []

    extended_coords = [extended_start] + middle_coords + [extended_end]

    # Plot the extended linestring over the footprint polygon
    if show_plot:
        plt.figure(figsize=(10, 10))

        # Plot the footprint polygon
        x, y = footprint_polygon.exterior.xy
        plt.plot(x, y, color='black', linestyle='--', label='Footprint Polygon')

        # Plot the original linestring
        x_original = [pt[0] for pt in line.coords]
        y_original = [pt[1] for pt in line.coords]
        plt.plot(x_original, y_original, 'g--', label='Original Linestring')

        # Plot the extended linestring
        x_extended = [pt.x for pt in extended_coords]
        y_extended = [pt.y for pt in extended_coords]
        plt.plot(x_extended, y_extended, 'b-', linewidth=2, label='Extended Linestring')
        plt.scatter(x_extended, y_extended, c='blue')

        plt.legend()
        plt.title('Extended Linestring over Footprint Polygon')
        plt.xlabel('World X')
        plt.ylabel('World Y')
        plt.axis('equal')
        plt.show()

    # Convert extended coordinates back to pixel space if needed
    extended_pixel_coords = np.array([
        [
            (pt.x - raster_geotransform[0]) / raster_geotransform[1],
            (pt.y - raster_geotransform[3]) / raster_geotransform[5]
        ]
        for pt in extended_coords
    ])

    print(f"Extended pixel coordinates: {extended_pixel_coords}")

    return extended_pixel_coords


def extend_to_bbox(p_start, p_direction, bbox_polygon, show_plot=False):
    print(f"Extending from {p_start} in direction {p_direction} to bbox {bbox_polygon.bounds}")

    # Calculate the direction vector
    direction = np.array([p_direction.x - p_start.x, p_direction.y - p_start.y])
    print(f"Calculated direction vector: {direction}")

    norm = np.linalg.norm(direction)
    if norm == 0:
        print("Direction vector has zero length. Cannot normalize.")
        raise ValueError("Direction vector has zero length.")

    direction = direction / norm
    print(f"Normalized direction vector: {direction}")

    # Extend far beyond the bounding box to ensure intersection
    bbox_width = bbox_polygon.bounds[2] - bbox_polygon.bounds[0]
    bbox_height = bbox_polygon.bounds[3] - bbox_polygon.bounds[1]
    large_distance = 10 * max(bbox_width, bbox_height)
    print(f"Large distance for extension: {large_distance}")

    extended_point = Point(p_start.x + direction[0] * large_distance, p_start.y + direction[1] * large_distance)
    print(f"Extended point: {extended_point}")

    # Create a line from p_start to extended_point
    extended_line = LineString([p_start, extended_point])
    print(f"Created extended line: {extended_line}")

    # Calculate the intersection between the extended line and the bounding box
    intersection = extended_line.intersection(bbox_polygon)
    print(f"Intersection result: {intersection}")

    # Plot debugging information if show_plot is enabled
    if show_plot:
        plt.figure(figsize=(10, 10))
        x, y = bbox_polygon.exterior.xy
        plt.plot(x, y, color='black', linestyle='--', label='Bounding Box')
        plt.plot(p_start.x, p_start.y, 'go', label='Start Point')
        plt.plot(p_direction.x, p_direction.y, 'mo', label='Direction Point')
        x_ext, y_ext = extended_line.xy
        plt.plot(x_ext, y_ext, 'b-', label='Extended Line')

        if isinstance(intersection, LineString):
            x_int, y_int = intersection.xy
            plt.plot(x_int, y_int, 'rx', label='Intersection Line')
        elif isinstance(intersection, Point):
            plt.plot(intersection.x, intersection.y, 'rx', label='Intersection Point')
        else:
            print(f"Unexpected intersection type: {type(intersection)}")
            raise ValueError('Unexpected intersection type')

        plt.legend()
        plt.title('Extend to Bounding Box')
        plt.xlabel('World X')
        plt.ylabel('World Y')
        plt.axis('equal')
        plt.show()

    if isinstance(intersection, LineString):
        intersection_coords = list(intersection.coords)
        if not intersection_coords:
            print("Intersection LineString has no coordinates.")
            raise IndexError("Intersection LineString has no coordinates.")
        print(f"Returning endpoint of intersection: {intersection_coords[-1]}")
        return Point(intersection_coords[-1][0], intersection_coords[-1][1])
    elif isinstance(intersection, Point):
        print(f"Returning intersection point: {intersection}")
        return intersection
    else:
        print("No valid intersection found.")
        raise IndexError("Intersection did not yield valid coordinates")

def get_vrt_shape(vrt_path):
    """
    Returns the shape (rows, columns) of a VRT file.

    Args:
        vrt_path (str): Path to the .vrt file.

    Returns:
        tuple: A tuple containing the number of rows and columns (rows, cols).
    """
    from osgeo import gdal

    # Open the VRT dataset
    dataset = gdal.Open(vrt_path)
    if dataset is None:
        raise RuntimeError(f"Failed to open the VRT file at {vrt_path}")

    # Get the shape (rows, columns)
    rows = dataset.RasterYSize
    cols = dataset.RasterXSize

    return rows, cols


def extend_linestring_past_footprint_old(linestring_coords,
                                     footprint_shape,
                                     footprint_geotransform,
                                     linestring_geotransform,
                                     show_plot=False):

    # Convert coordinates from pixel space to world space using a specific geotransform
    def pixel_to_world(geo_transform, x, y):
        return (
            geo_transform[0] + x * geo_transform[1] + y * geo_transform[2],
            geo_transform[3] + x * geo_transform[4] + y * geo_transform[5]
        )

    # Convert linestring coordinates from linestring_geotransform to world coordinates
    world_coords = [pixel_to_world(linestring_geotransform, x, y) for x, y in linestring_coords]
    line = LineString(world_coords)

    # Calculate the bounding box of the footprint in world coordinates
    footprint_height, footprint_width  = footprint_shape
    footprint_bbox_world = [
        pixel_to_world(footprint_geotransform, 0, 0),
        pixel_to_world(footprint_geotransform, footprint_width - 1, 0),
        pixel_to_world(footprint_geotransform, footprint_width - 1, footprint_height - 1),
        pixel_to_world(footprint_geotransform, 0, footprint_height - 1)
    ]

    # Create footprint polygon
    footprint_polygon = Polygon(footprint_bbox_world)

    # Points and directions for extension
    start, end = Point(line.coords[0]), Point(line.coords[-1])
    second_point = Point(line.coords[1])
    second_last_point = Point(line.coords[-2])


    # Extend start and end points
    extended_start = extend_to_bbox(second_point, start, footprint_polygon, show_plot=False)
    extended_end = extend_to_bbox(second_last_point, end, footprint_polygon, show_plot=False)

    # Create extended coordinates list
    extended_coords = [extended_start] + [Point(coord) for coord in line.coords[1:-1]] + [extended_end]

    if show_plot:
        # Plot the footprint polygon
        x, y = footprint_polygon.exterior.xy
        plt.plot(x, y, color='black', linestyle='--', label='Footprint Bounding Box')

        # Plot the original linestring in world coordinates
        original_linestring_world = np.array(
            [pixel_to_world(linestring_geotransform, x, y) for x, y in linestring_coords])
        plt.plot(original_linestring_world[:, 0], original_linestring_world[:, 1],
                 color='green', marker='o', markersize=5, linestyle='--', label='Original Path')

        # Plot the extended linestring in world coordinates
        extended_linestring_world = np.array([pt.coords[0] for pt in extended_coords])
        plt.plot(extended_linestring_world[:, 0], extended_linestring_world[:, 1],
                 color='blue', marker='o', markersize=8, linestyle='-', label='Extended Path')

        plt.axis("equal")
        plt.legend()
        plt.show()

    # Convert extended coordinates back to pixel space if needed
    extended_pixel_coords = np.array([[(pt.x - linestring_geotransform[0]) / linestring_geotransform[1],
                                       (pt.y - linestring_geotransform[3]) / linestring_geotransform[5]] for pt in
                                      extended_coords])

    return extended_pixel_coords

def closeness_to_centreline_old(overlap_mask, full_centreline_coords_xy, show_plot=False):
    # Get the indices where the mask is 1
    rows, cols = np.where(overlap_mask == 1)
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError("The mask contains no '1' values; no distances to compute.")

    # Plot the mask and centerline points to ensure alignment
    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(overlap_mask, cmap='gray')
        plt.plot(full_centreline_coords_xy[:, 0], full_centreline_coords_xy[:, 1], color='red', marker='o', linewidth=1,
                 markersize=4)
        plt.colorbar(label='Mask Values')
        plt.title('Overlap Mask with Centerline Overlay')
        plt.show()

    # Prepare the points where mask == 1
    points = np.stack((cols, rows), axis=1)  # Shape: (num_points, 2)

    # Prepare segments from the centerline coordinates
    A = full_centreline_coords_xy[:-1, :]  # Start points of segments
    B = full_centreline_coords_xy[1:, :]  # End points of segments
    AB = B - A  # Vectors representing the segments
    AB_norm2 = np.sum(AB ** 2, axis=1)  # Squared lengths of segments
    AB_norm2 = np.where(AB_norm2 == 0, 1e-10, AB_norm2)  # Avoid division by zero

    # Compute vectors from segment start points to the points
    AP = points[:, np.newaxis, :] - A[np.newaxis, :, :]  # Shape: (num_points, num_segments, 2)

    # Compute the projection scalar of each point onto each segment
    numerator = np.sum(AP * AB[np.newaxis, :, :], axis=2)
    u = numerator / AB_norm2[np.newaxis, :]
    u_clipped = np.clip(u, 0, 1)  # Clip to segment boundaries

    # Compute the closest points on the segments
    C = A[np.newaxis, :, :] + u_clipped[:, :, np.newaxis] * AB[np.newaxis, :, :]

    # Compute squared distances from the points to the closest points on the segments
    dist2 = np.sum((points[:, np.newaxis, :] - C) ** 2, axis=2)

    # Find the minimum distance for each point
    min_dist = np.sqrt(np.min(dist2, axis=1))

    # Normalize distances to the range [0, 1]
    max_dist = np.max(min_dist)
    min_dist_normalized = 1 - (min_dist / max_dist)

    # Initialize the normalized closeness array and assign computed values
    closeness = np.zeros_like(overlap_mask, dtype=float)
    closeness[rows, cols] = min_dist_normalized

    # Show final normalized closeness plot if requested
    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(closeness, cmap='viridis')
        plt.colorbar(label='Closeness to Centerline (Normalized)')
        plt.title('Closeness to Centerline (0 = Furthest, 1 = Closest)')
        plt.show()

    return closeness

def closeness_to_centreline(overlap_mask, full_centreline_coords_xy, show_plot=False, batch_size=1000000):
    # Get the indices where the mask is 1
    rows, cols = np.where(overlap_mask == 1)
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError("The mask contains no '1' values; no distances to compute.")

    # Prepare the points where mask == 1
    points = np.stack((cols, rows), axis=1)  # Shape: (num_points, 2)
    num_points = points.shape[0]

    # Prepare segments from the centerline coordinates
    A = full_centreline_coords_xy[:-1, :]  # Start points of segments
    B = full_centreline_coords_xy[1:, :]   # End points of segments
    num_segments = A.shape[0]

    # Initialize min_distances
    min_distances = np.full(num_points, np.inf)

    # Process points in batches
    for batch_start in range(0, num_points, batch_size):
        batch_end = min(batch_start + batch_size, num_points)
        batch_points = points[batch_start:batch_end]
        batch_min_distances = np.full(batch_end - batch_start, np.inf)

        # For each segment, compute distances to the batch of points
        for i in range(num_segments):
            a = A[i]
            b = B[i]
            ab = b - a
            ab_squared = np.dot(ab, ab)
            if ab_squared == 0:
                # The segment is a point
                distances = np.linalg.norm(batch_points - a, axis=1)
            else:
                ap = batch_points - a
                t = np.dot(ap, ab) / ab_squared
                t = np.clip(t, 0, 1)
                projection = a + t[:, np.newaxis] * ab
                distances = np.linalg.norm(batch_points - projection, axis=1)

            # Update the minimum distances
            batch_min_distances = np.minimum(batch_min_distances, distances)

        # Store the batch results
        min_distances[batch_start:batch_end] = batch_min_distances

    # Normalize distances to the range [0, 1]
    max_dist = np.max(min_distances)
    min_dist_normalized = 1 - (min_distances / max_dist)

    # Initialize the normalized closeness array and assign computed values
    closeness = np.zeros_like(overlap_mask, dtype=float)
    closeness[rows, cols] = min_dist_normalized

    # Plotting code if needed
    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(closeness, cmap='viridis')
        plt.colorbar(label='Closeness to Centerline (Normalized)')
        plt.title('Closeness to Centerline (0 = Furthest, 1 = Closest)')
        plt.show()

    return closeness

def sample_line_over_raster(raster_mask, full_centreline_coords_xy, show_plot=False):
    """
    Sample the raster under the line such that there are no gaps in the path of the pixels.
    Diagonal pixels are allowed. The function returns an integer array with the same shape as the input raster.
    The sampled pixel closest to the beginning of the line is labeled '1', then '2', and so on.
    """
    raster_rows, raster_cols = raster_mask.shape

    pixel_indices = []

    num_points = full_centreline_coords_xy.shape[0]
    for i in range(num_points - 1):
        x0, y0 = full_centreline_coords_xy[i]
        x1, y1 = full_centreline_coords_xy[i + 1]

        # Convert coordinates to integer indices
        col0, row0 = int(round(x0)), int(round(y0))
        col1, row1 = int(round(x1)), int(round(y1))

        # Get line indices
        rr, cc = line(row0, col0, row1, col1)

        # Collect the indices
        pixel_indices.extend(zip(rr, cc))

    # Filter indices within raster bounds
    valid_indices = [(r, c) for r, c in pixel_indices if 0 <= r < raster_rows and 0 <= c < raster_cols]

    # Remove duplicates while preserving order
    unique_indices = list(OrderedDict.fromkeys(valid_indices))

    # Initialize output array
    output_array = np.zeros_like(raster_mask, dtype=int)

    # Assign values
    for idx, (r, c) in enumerate(unique_indices):
        output_array[r, c] = idx + 1  # Values from 1 to N

    # Plot the progress if requested
    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(output_array, cmap='jet', origin='upper')
        plt.colorbar(label='Pixel Order Along Line')
        plt.title('Sampled Pixels Along Line')
        plt.show()

    return output_array


def compute_similarity_old(first_overlap_path, second_overlap_path, overlap_mask, show_plot=False):
    """
    Computes per-pixel color similarity between two pre-clipped RGB rasters of the same overlapping region,
    and applies a mask to remove nodata values around the edges.

    Parameters:
    first_overlap_path (str): Path to the first clipped RGB raster (tif).
    second_overlap_path (str): Path to the second clipped RGB raster (tif).
    overlap_mask (numpy.ndarray): A 2D numpy array with the same dimensions as the inputs.
                                  Non-zero indicates valid overlap pixels; zero indicates nodata.
    show_plot (bool): If True, displays a plot of the similarity.

    Returns:
    numpy.ndarray: A 2D array of similarity scores normalized between 0 and 1, with nodata areas as 0.
    """

    # Open both datasets
    first_ds = gdal.Open(first_overlap_path, gdal.GA_ReadOnly)
    second_ds = gdal.Open(second_overlap_path, gdal.GA_ReadOnly)

    # Get dimensions
    cols = first_ds.RasterXSize
    rows = first_ds.RasterYSize
    memmap_path = os.path.join(os.path.dirname(__file__),'temp_band_diff_memmap.dat')

    diffs = np.memmap(memmap_path, dtype=np.int32, mode='w+', shape=(3, rows, cols))
    for band in [1,2,3]:
        diffs[band-1] = (first_ds.GetRasterBand(band).ReadAsArray(0, 0, cols, rows).astype(np.int16) -
                         second_ds.GetRasterBand(band).ReadAsArray(0, 0, cols, rows).astype(np.int16))

    distance = np.sqrt(diffs[0] ** 2 + diffs[1] ** 2 + diffs[2] ** 2)

    del diffs
    gc.collect()
    os.remove(memmap_path)

    # Maximum possible distance in RGB space
    max_distance = np.sqrt(3 * (255 ** 2))

    # Convert distance to similarity (1 - normalized_distance)
    normalized_distance = distance / max_distance

    del distance
    gc.collect()

    similarity = 1 - normalized_distance
    similarity = np.clip(similarity, 0, 1)

    # Apply the overlap mask: zero out invalid pixels immediately
    # This ensures that nodata pixels do not affect normalization
    similarity[overlap_mask == 0] = np.nan

    # Compute normalization only on valid pixels
    valid_pixels = similarity[~np.isnan(similarity)]
    if valid_pixels.size > 0:
        min_value = np.min(valid_pixels)
        similarity = similarity - min_value
        # After shifting, any negative values become 0 (though there shouldn't be any)
        similarity = np.maximum(similarity, 0)

        # Recompute max on valid pixels after shift
        valid_pixels = similarity[~np.isnan(similarity)]
        max_similarity = np.max(valid_pixels) if valid_pixels.size > 0 else 0

        if max_similarity > 0:
            similarity = similarity / max_similarity

    # Convert NaNs (nodata areas) back to 0
    similarity[np.isnan(similarity)] = 0

    # Optional plot
    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(similarity, cmap='viridis')
        plt.colorbar(label='Color similarity (Normalized)')
        plt.title('Adjusted color similarity with nodata masked out')
        plt.show()

    return similarity

def compute_path_preference_arr(color_similarity, closeness_to_centreline_arr, prefer_centre_factor, show_plot=False):
    path_pref = color_similarity + closeness_to_centreline_arr * prefer_centre_factor
    min_val = path_pref.min()
    max_val = path_pref.max()
    normalized_path_pref = (path_pref - min_val) / (max_val - min_val)

    if show_plot:
        plt.figure(figsize=(10, 6))
        plt.imshow(normalized_path_pref, cmap='viridis')
        plt.colorbar(label='pref path (Normalized)')
        plt.title('pref (0 = Furthest, 1 = Closest)')
        plt.show()
    return normalized_path_pref


def transform_coords(coords, src_geotransform, dst_geotransform):
    """Converts coordinates from source to destination geotransform."""
    src_scale_x, src_skew_x, src_trans_x, src_skew_y, src_scale_y, src_trans_y = src_geotransform
    dst_scale_x, dst_skew_x, dst_trans_x, dst_skew_y, dst_scale_y, dst_trans_y = dst_geotransform

    transformed_coords = []
    for x, y in coords:
        # Convert to geospatial coordinates in source system
        geo_x = src_trans_x + x * src_scale_x + y * src_skew_x
        geo_y = src_trans_y + x * src_skew_y + y * src_scale_y
        # Convert to pixel coordinates in destination system
        px_x = (geo_x - dst_trans_x) / dst_scale_x
        px_y = (geo_y - dst_trans_y) / dst_scale_y
        transformed_coords.append((px_x, px_y))
    return transformed_coords

def transform_coords(coords, src_geotransform, dst_geotransform):
    """Converts coordinates from source to destination geotransform."""
    if not isinstance(src_geotransform, Affine):
        src_geotransform = Affine.from_gdal(*src_geotransform)
    if not isinstance(dst_geotransform, Affine):
        dst_geotransform = Affine.from_gdal(*dst_geotransform)

    transformed_coords = []
    for x, y in coords:
        # Convert to geospatial coordinates in source system
        geo_x, geo_y = src_geotransform * (x, y)
        # Convert to pixel coordinates in destination system
        px_x, px_y = ~dst_geotransform * (geo_x, geo_y)
        transformed_coords.append((px_x, px_y))
    return transformed_coords


def extend_line(line, extension_length=1):
    """Extend a LineString by extension_length at both ends."""
    from math import sqrt

    coords = list(line.coords)
    p1 = coords[0]
    p2 = coords[1]

    # Compute the vector from p1 to p2
    vx = p2[0] - p1[0]
    vy = p2[1] - p1[1]
    len_v = sqrt(vx**2 + vy**2)

    if len_v == 0:
        # Cannot extend a zero-length line
        return line

    # Normalize the vector
    unit_vx = vx / len_v
    unit_vy = vy / len_v

    # Extend p1 backward
    new_p1 = (p1[0] - unit_vx * extension_length, p1[1] - unit_vy * extension_length)

    # Extend p2 forward
    new_p2 = (p2[0] + unit_vx * extension_length, p2[1] + unit_vy * extension_length)

    # Create new extended LineString
    extended_line = LineString([new_p1, new_p2])

    return extended_line

def rasterize_line_ends(
        linestring_coords_xy,
        footprint_shape,
        footprint_geotransform,
        overlap_geotransform,
        start_pix,
        end_pix,
        cut_path_mask_footprint_frame,
        show_plot=False
):
    # Define affine transformations
    affine_overlap = Affine.from_gdal(*overlap_geotransform)
    affine_footprint = Affine.from_gdal(*footprint_geotransform)

    # Convert a point from the overlap frame to world coordinates, then to footprint pixel coordinates
    def convert_to_footprint_frame(x, y):
        # Convert to world coordinates using overlap geotransform
        world_x, world_y = affine_overlap * (x, y)
        # Convert from world coordinates to footprint pixel coordinates
        return ~affine_footprint * (world_x, world_y)

    # Convert linestring coordinates to the footprint frame
    linestring_coords_footprint = [convert_to_footprint_frame(x, y) for x, y in linestring_coords_xy]
    line = LineString(linestring_coords_footprint)

    # Extract the first and last segments of the line
    first_segment = LineString([line.coords[0], line.coords[1]])
    last_segment = LineString([line.coords[-2], line.coords[-1]])

    # Convert start_pix and end_pix to the footprint frame
    x_start_footprint, y_start_footprint = convert_to_footprint_frame(start_pix[1], start_pix[0])
    x_end_footprint, y_end_footprint = convert_to_footprint_frame(end_pix[1], end_pix[0])

    start_point = Point(x_start_footprint, y_start_footprint)
    end_point = Point(x_end_footprint, y_end_footprint)

    # Project start and end points onto the first and last segments
    projected_start = first_segment.interpolate(first_segment.project(start_point))
    projected_end = last_segment.interpolate(last_segment.project(end_point))

    # Calculate percentage distances
    start_percentage = first_segment.project(start_point) / first_segment.length * 100
    end_percentage = last_segment.project(end_point) / last_segment.length * 100

    # Print results
    #print(f"Projected start point is at {start_percentage:.2f}% of the first segment.")
    #print(f"Projected end point is at {end_percentage:.2f}% of the last segment.")

    # Define the final lines from the edge to the projected points
    line_start_to_edge = LineString([projected_start, line.coords[0]])
    line_end_to_edge = LineString([projected_end, line.coords[-1]])

    # Extend the lines by one pixel length
    line_start_to_edge_ext = extend_line(line_start_to_edge, extension_length=1)
    line_end_to_edge_ext = extend_line(line_end_to_edge, extension_length=1)

    # Convert extended lines to pixel coordinates
    def line_to_pixel_coords(line):
        return [(int(round(coord[0])), int(round(coord[1]))) for coord in line.coords]

    line_start_to_edge_pixels_ext = line_to_pixel_coords(line_start_to_edge_ext)
    line_end_to_edge_pixels_ext = line_to_pixel_coords(line_end_to_edge_ext)

    # Prepare geometries with extended lines for rasterization
    geometries = [
        (LineString(line_start_to_edge_pixels_ext), 1),
        (LineString(line_end_to_edge_pixels_ext), 1)
    ]

    # Rasterize the line ends
    mask = rasterize(
        geometries,
        out_shape=footprint_shape,
        transform=Affine.identity(),  # No transform needed since we're in pixel space
        fill=0,
        all_touched=True,
        dtype='uint8'
    )

    # Plot the results if requested
    if show_plot:
        plt.figure(figsize=(12, 8))

        # Plot the full linestring in blue
        plt.plot(
            [pt[0] for pt in linestring_coords_footprint],
            [pt[1] for pt in linestring_coords_footprint],
            color='blue',
            linewidth=1
        )

        # Plot the first segment in dotted teal
        plt.plot(
            [first_segment.coords[0][0], first_segment.coords[1][0]],
            [first_segment.coords[0][1], first_segment.coords[1][1]],
            color='teal',
            linestyle=':',
            linewidth=2,
            label='First Segment (Dotted)'
        )
        # Plot the projected start point in teal
        plt.scatter(projected_start.x, projected_start.y, color='teal', marker='o', label='Projected Start Point')

        plt.scatter(start_point.x, start_point.y, color='teal', marker='x', label='Start Point')

        # Plot the last segment in dotted purple
        plt.plot(
            [last_segment.coords[0][0], last_segment.coords[1][0]],
            [last_segment.coords[0][1], last_segment.coords[1][1]],
            color='purple',
            linestyle=':',
            linewidth=2,
            label='Last Segment (Dotted)'
        )
        # Plot the projected end point in purple
        plt.scatter(projected_end.x, projected_end.y, color='purple', marker='o', label='Projected End Point')

        plt.scatter(end_point.x, end_point.y, color='purple', marker='x', label='End Point')

        #plt.imshow(mask, cmap='Reds', alpha=0.7)

        # Plot line from projected start to edge in solid teal
        plt.plot(
            [line_start_to_edge.coords[0][0], line_start_to_edge.coords[1][0]],
            [line_start_to_edge.coords[0][1], line_start_to_edge.coords[1][1]],
            color='teal',
            linestyle='-',
            linewidth=2,
            label='Line Start to Edge (Solid)'
        )

        # Plot line from projected end to edge in solid purple
        plt.plot(
            [line_end_to_edge.coords[0][0], line_end_to_edge.coords[1][0]],
            [line_end_to_edge.coords[0][1], line_end_to_edge.coords[1][1]],
            color='purple',
            linestyle='-',
            linewidth=2,
            label='Line End to Edge (Solid)'
        )

        plt.imshow(cut_path_mask_footprint_frame, alpha=0.5)

        plt.legend()
        plt.title('Rasterized Line Ends with Cut Path Mask Overlay')
        plt.show()

    return mask


def shift_mask_frame_and_extend(external_mask, overlap_geotransform, footprint_geotransform, footprint_shape, show_plot=False):
    # Process external_mask first
    external_mask = extend_to_edges(external_mask.copy())

    # Create shifted mask
    affine_overlap = Affine.from_gdal(*overlap_geotransform)
    affine_footprint_inv = ~Affine.from_gdal(*footprint_geotransform)

    rows, cols = np.where(external_mask > 0)

    geo_x, geo_y = affine_overlap * (cols, rows)
    footprint_cols, footprint_rows = affine_footprint_inv * (geo_x, geo_y)

    # Round and convert to integers
    footprint_rows = np.round(footprint_rows).astype(int)
    footprint_cols = np.round(footprint_cols).astype(int)

    # Filter out-of-bound indices
    valid_mask = (footprint_rows >= 0) & (footprint_rows < footprint_shape[0]) & \
                 (footprint_cols >= 0) & (footprint_cols < footprint_shape[1])

    footprint_rows = footprint_rows[valid_mask]
    footprint_cols = footprint_cols[valid_mask]

    shifted_mask = np.zeros(footprint_shape, dtype=external_mask.dtype)
    shifted_mask[footprint_rows, footprint_cols] = 1

    # Process shifted_mask
    shifted_mask = extend_to_edges(shifted_mask)

    if show_plot:
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))
        #visualization_mask_in = visualize_extent(external_mask)
        visualization_mask_out = visualize_extent(shifted_mask)
        #axes[0].imshow(visualization_mask_in)
        #axes[0].set_title("Processed Input Mask")
        axes[1].imshow(visualization_mask_out)
        axes[1].set_title("Processed Output Mask")
        plt.show()

    return shifted_mask


def shift_mask_frame(external_mask, overlap_geotransform, footprint_geotransform, footprint_shape):
    shifted_mask = np.zeros(footprint_shape, dtype=external_mask.dtype)

    affine_overlap = Affine.from_gdal(*overlap_geotransform)
    affine_footprint_inv = ~Affine.from_gdal(*footprint_geotransform)

    rows, cols = np.where(external_mask > 0)

    geo_x, geo_y = affine_overlap * (cols, rows)
    footprint_cols, footprint_rows = affine_footprint_inv * (geo_x, geo_y)

    # Round and convert to integers
    footprint_rows = np.round(footprint_rows).astype(int)
    footprint_cols = np.round(footprint_cols).astype(int)

    # Option A: Filter out-of-bound indices
    valid_mask = (footprint_rows >= 0) & (footprint_rows < footprint_shape[0]) & \
                 (footprint_cols >= 0) & (footprint_cols < footprint_shape[1])

    footprint_rows = footprint_rows[valid_mask]
    footprint_cols = footprint_cols[valid_mask]

    # Create the shifted mask
    shifted_mask[footprint_rows, footprint_cols] = 1

    return shifted_mask


def visualize_extent(external_mask):
    """
    Visualize a mask with a filled extent (bounding box) in a distinct color.

    Parameters:
        external_mask (ndarray): Binary mask with ones and zeros.

    Returns:
        Tuple[ndarray, ListedColormap]: Visualization mask and colormap.
    """
    print('Calculating bounding box for visualization...')
    # Find the extent (bounding box) of the 1s in the mask
    rows = np.any(external_mask, axis=1)
    cols = np.any(external_mask, axis=0)
    row_start, row_end = np.where(rows)[0][[0, -1]]
    col_start, col_end = np.where(cols)[0][[0, -1]]


    print('creating visualization mask...')
    # Create a visualization mask
    visualization_mask = np.zeros_like(external_mask, dtype=np.uint8)

    # Fill the bounding box in the visualization mask
    visualization_mask[row_start:row_end + 1, col_start:col_end + 1] = 1

    visualization_mask[external_mask > 0] = 3  # Original mask

    print('visualization processing completed.')
    return visualization_mask


def get_relative_direction(footprint_geotransform, footprint_shape, gt, stacked_data_shape, show_plot=False):
    """
    Determines the relative direction of a raster compared to the footprint and optionally plots it.

    Parameters:
        footprint_geotransform (tuple): Geotransform of the footprint.
        gt (tuple): Geotransform of the smaller raster.
        stacked_data_shape (tuple): Shape of the smaller raster (rows, cols).
        footprint_shape (tuple): Shape of the footprint (rows, cols).
        show_plot (bool): If True, plots the centers and direction vectors.

    Returns:
        dict: A dictionary containing the direction vector and angle (degrees).
    """
    # Convert geotransforms to Affine objects
    affine_footprint = Affine.from_gdal(*footprint_geotransform)
    affine_gt = Affine.from_gdal(*gt)

    # Calculate the center of the footprint in world coordinates
    footprint_center_x, footprint_center_y = affine_footprint * (
        footprint_shape[1] / 2,  # cols
        footprint_shape[0] / 2  # rows
    )

    # Calculate the center of the smaller raster in world coordinates
    raster_center_x, raster_center_y = affine_gt * (
        stacked_data_shape[1] / 2,  # cols
        stacked_data_shape[0] / 2  # rows
    )

    # Compute the direction vector
    direction_vector = np.array([raster_center_x - footprint_center_x, raster_center_y - footprint_center_y])

    # Normalize the vector to get the unit direction vector
    unit_vector = direction_vector / np.linalg.norm(direction_vector)

    # Plot if required
    if show_plot:
        plt.figure(figsize=(8, 8))
        plt.scatter(footprint_center_x, footprint_center_y, color='red', label='Footprint Center')
        plt.scatter(raster_center_x, raster_center_y, color='blue', label='Raster Center')

        # Plot direction vector as an arrow
        plt.quiver(
            footprint_center_x, footprint_center_y,
            direction_vector[0], direction_vector[1],
            angles='xy', scale_units='xy', scale=1, color='green', label='Direction Vector'
        )
        plt.axis("equal")
        plt.title("Relative Direction in World Coordinates")
        plt.xlabel("World X")
        plt.ylabel("World Y")
        plt.legend()
        plt.grid()
        plt.show()

    return unit_vector

def compute_centroid(binary_mask):
    # binary_mask is a 2D boolean or uint8 array
    # Centroid is the average of coordinates where binary_mask is True/1
    if binary_mask.dtype != bool:
        # Convert to boolean for indexing if necessary
        binary_mask = binary_mask.astype(bool)
    coords = np.argwhere(binary_mask)
    if coords.size == 0:
        return (0.0, 0.0)
    centroid_y = np.mean(coords[:, 0])
    centroid_x = np.mean(coords[:, 1])
    return (centroid_y, centroid_x)

def largest_power_of_ten(n):
    return 10 ** np.floor(np.log10(n))

def print_ram(all_vars):
    # Convert sizes to GB and filter variables larger than 100 MB
    all_vars_filtered = [(name, size / (1024 ** 3)) for name, size in all_vars if size >= 100 * (1024 ** 2)]

    # Sort by size (descending)
    all_vars_sorted = sorted(all_vars_filtered, key=lambda x: x[1], reverse=True)

    # Print the results
    for var_name, size_gb in all_vars_sorted:
        print(f"{var_name}: {size_gb:.2f} GB")


def scale_coordinates(coords, input_shape, target_shape):
    """
    Scales coordinates from the input shape to the target shape.

    Parameters:
        coords: tuple
            A tuple (min_row, min_col, max_row, max_col) in the input shape.
        input_shape: tuple
            Shape of the input mask (height, width).
        target_shape: tuple
            Desired target shape (height, width).

    Returns:
        tuple: Scaled coordinates in the target shape.
    """
    scale_row = target_shape[0] / input_shape[0]
    scale_col = target_shape[1] / input_shape[1]

    min_row, min_col, max_row, max_col = coords
    scaled_min_row = int(min_row * scale_row)
    scaled_min_col = int(min_col * scale_col)
    scaled_max_row = int(max_row * scale_row)
    scaled_max_col = int(max_col * scale_col)

    return (scaled_min_row, scaled_min_col, scaled_max_row, scaled_max_col)


def largest_contiguous_group(mask: np.ndarray) -> np.ndarray:
    """
    Returns a mask containing only the largest contiguous group of pixels from the input mask.
    Contiguity is defined as 8-connectivity: pixels touching along edges or corners are considered connected.
    """
    # Ensure mask is uint8
    mask = mask.astype(np.uint8)

    # Define a 3x3 structure of all ones to ensure 8-connectivity
    structure = np.ones((3, 3), dtype=np.uint8)

    # Label the connected components
    labeled_mask, num_features = label(mask, structure=structure)

    if num_features == 0:
        # No connected components, return an empty mask
        return np.zeros_like(mask, dtype=np.uint8)

    # Count the size of each connected component
    # labels go from 1 to num_features
    component_sizes = np.bincount(labeled_mask.flat)[1:]  # skip 0 because background is labeled as 0
    largest_label = np.argmax(component_sizes) + 1  # +1 because labels start from 1

    # Create a mask for the largest component
    largest_component_mask = (labeled_mask == largest_label).astype(np.uint8)
    return largest_component_mask


def cutline_to_mask(cut_shifted, unit_vector, show_plot=False):


    # Ensure cut_shifted is uint8
    if cut_shifted.dtype != np.uint8:
        cut_shifted = cut_shifted.astype(np.uint8)

    original_shape = cut_shifted.shape  # Save original shape

    scale_factor = 1
    if np.max(cut_shifted.shape) > 10_000:
        cut_shifted_hi_res = cut_shifted
        # Compute the scale factor
        scale_factor = largest_power_of_ten(np.max(cut_shifted.shape)) / 100
        reduction_factor = int(np.ceil(scale_factor))
        print('too big reducing resolution...')
        # Apply max pooling (block_reduce with max operation)
        cut_shifted = block_reduce(cut_shifted, block_size=(reduction_factor, reduction_factor), func=np.max)

        # Ensure the downscaled mask is still uint8
        cut_shifted = cut_shifted.astype(np.uint8)

    # Convert to a boolean mask for logical operations if needed
    cut_bool = (cut_shifted > 0)

    # Invert the cut_shifted mask to prepare for labeling
    # Path pixels are zeros in cut_shifted, so now we want inverse
    inv_mask = np.logical_not(cut_bool)

    print(f'labeled_array...')
    # Label connected regions in the inverted mask
    labeled_array, num_features = label(inv_mask)

    # Determine which regions to consider
    if num_features > 2:
        # Use bincount to get the size of each region
        region_sizes = np.bincount(labeled_array.ravel())[1:]  # Ignore background label 0
        largest_two_labels = region_sizes.argsort()[-2:] + 1  # Labels start from 1
        labels_to_consider = largest_two_labels.tolist()
    elif num_features == 2:
        labels_to_consider = [1, 2]
    else:
        # Handle cases where there is only one region
        labels_to_consider = [1]

    # Manually compute centroids of the regions
    centroids = []
    for label_value in labels_to_consider:
        mask = (labeled_array == label_value)
        centroid = compute_centroid(mask)
        centroids.append(centroid)

    # If only one region, we cannot compute vector between centroids
    if len(centroids) == 2:
        # Compute vector between the centroids
        vec = np.array([centroids[1][1] - centroids[0][1],
                        centroids[1][0] - centroids[0][0]])  # (x, y) format

        # Normalize the vector
        norm = np.linalg.norm(vec)
        if norm == 0:
            # Degenerate case where centroids are the same, just keep the first
            keep_label = labels_to_consider[0]
        else:
            vec_norm = vec / norm

            # Flip the unit_vector
            flipped_unit_vector = (unit_vector[0], -unit_vector[1])

            # Determine which region to keep
            dot_product = np.dot(vec_norm, flipped_unit_vector)
            if dot_product > 0:
                keep_label = labels_to_consider[1]  # Corresponds to centroid1
            else:
                keep_label = labels_to_consider[0]  # Corresponds to centroid0
    else:
        # If only one region, keep it
        keep_label = labels_to_consider[0]

    # Create the final mask including the path

    keep_mask = (labeled_array == keep_label).astype(np.uint8)

    # Scale back to original resolution
    if scale_factor > 1:
        # Example usage
        # Original keep_mask shape
        keep_mask_shape = keep_mask.shape

        # Get the extent in the low-resolution mask
        min_row_, min_col_, max_row_, max_col_ = get_extended_extent(np.logical_not(keep_mask), buffer_ratio=0.2)

        # Scale the extent to the high-resolution shape
        min_row_1, min_col_1, max_row_1, max_col_1 = scale_coordinates(
            (min_row_, min_col_, max_row_, max_col_),
            keep_mask_shape,
            original_shape
        )

        print(f"keep_mask_hi_res crop extent: {min_row_1}, {min_col_1}, {max_row_1}, {max_col_1}")

        # Get the extent of the 1s in the mask
        min_row_2, min_col_2, max_row_2, max_col_2 = get_extended_extent(cut_shifted_hi_res, buffer_ratio=0.2)


        print(f"cut_shifted_hi_res crop extent: {min_row_2}, {min_col_2}, {max_row_2}, {max_col_2}")

        min_row, min_col = np.min([min_row_1, min_row_2]), np.min([min_col_1, min_col_2])
        max_row, max_col = np.max([max_row_1, max_row_2]), np.max([max_col_1, max_col_2])

        print('scale back to hi res...')
        keep_mask_hi_res = resize(keep_mask, original_shape, order=0, preserve_range=True, anti_aliasing=False).astype(np.uint8)

        keep_mask_hi_res_cropped = keep_mask_hi_res[min_row:max_row + 1, min_col:max_col + 1]
        cutline_hi_res_cropped = cut_shifted_hi_res[min_row:max_row + 1, min_col:max_col + 1]

        #del cut_shifted_hi_res
        gc.collect()
        keep_mask_hi_res_cropped_exp =  expand_array_with_zeros(keep_mask_hi_res_cropped)
        culine_hi_res_cropped_exp = expand_mask_with_intersection(cutline_hi_res_cropped)



        keep_mask_comb = np.logical_or(keep_mask_hi_res_cropped_exp,
                                       culine_hi_res_cropped_exp)

        print_ram([(name, sys.getsizeof(obj)) for name, obj in locals().items()])
        print_ram([(name, sys.getsizeof(obj)) for name, obj in globals().items()])
        print('fill_holes...')
        if show_plot:
            print('before and after flood fill stage expanded')
            filled_holes = binary_fill_holes(keep_mask_comb)
            fig, axes = plt.subplots(1, 2, figsize=(15, 5))
            axes[0].imshow(culine_hi_res_cropped_exp, interpolation='none')
            axes[1].imshow(filled_holes, interpolation='none')
            plt.show()
            keep_mask_filled_cropped = shrink_array(filled_holes)
        else:
            keep_mask_filled_cropped = shrink_array(binary_fill_holes(keep_mask_comb))

        del culine_hi_res_cropped_exp, keep_mask_hi_res_cropped_exp
        gc.collect()

        if show_plot:
            print('before and after flood fill stage cropped size')
            fig, axes = plt.subplots(1, 2, figsize=(15, 5))
            axes[0].imshow(keep_mask_comb, interpolation='none')
            axes[1].imshow(keep_mask_filled_cropped, interpolation='none')
            plt.show()

        keep_mask_hi_res[min_row:max_row + 1, min_col:max_col + 1] = keep_mask_filled_cropped
        keep_mask = keep_mask_hi_res
    else:
        keep_mask = np.logical_or((labeled_array == keep_label), cut_bool).astype(np.uint8)

    assert keep_mask.shape == original_shape

    return keep_mask

def shrink_array(array):
    # Shrink the array by removing one row/column from each edge
    if array.shape[0] <= 2 or array.shape[1] <= 2:
        raise ValueError("Array is too small to shrink.")
    return array[1:-1, 1:-1]

def expand_array_with_zeros(array):
    # Expand the array with padding of zeros
    return np.pad(array, pad_width=1, mode='constant', constant_values=0)

def expand_mask_with_intersection(mask):
    # Convert input to numpy array if not already
    arr = np.array(mask, dtype=np.uint8)

    H, W = arr.shape

    # Check which edges are touched
    top_touched = np.any(arr[0, :] == 1)
    bottom_touched = np.any(arr[-1, :] == 1)
    left_touched = np.any(arr[:, 0] == 1)
    right_touched = np.any(arr[:, -1] == 1)

    # Create output array
    out = np.zeros((H + 2, W + 2), dtype=np.uint8)

    # Place the original array inside
    out[1:-1, 1:-1] = arr

    # Set edges according to touched edges
    if top_touched:
        out[0, :] = 1
    if bottom_touched:
        out[-1, :] = 1
    if left_touched:
        out[:, 0] = 1
    if right_touched:
        out[:, -1] = 1

    return out

def get_extent(mask):
    """Get the extent (bounding box) of the 1s in a binary mask."""
    coords = np.argwhere(mask)
    if coords.size == 0:
        return None  # No 1s in the mask
    min_row, min_col = coords.min(axis=0)
    max_row, max_col = coords.max(axis=0)
    return min_row, max_row, min_col, max_col


# Function to save metrics to a CSV
def save_metrics_to_csv(csv_path, **metrics):
    """
    Save metrics to a CSV file dynamically based on the input variables.

    Parameters:
        csv_path (str): Path to the CSV file.
        **metrics: Arbitrary keyword arguments representing metric names and values.

    Example usage:
        save_metrics_to_csv('metrics.csv', execution_time=12.34, file_size_gb=1.23, gsd=15.6)
    """
    # Get the names of the metrics from the arguments
    metric_names = list(metrics.keys())
    metric_values = list(metrics.values())

    # Check if CSV exists to determine if headers are needed
    file_exists = os.path.isfile(csv_path)

    # Open the CSV file and write data
    with open(csv_path, mode='a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(metric_names)
        writer.writerow([round(value, 2) if isinstance(value, (float, int)) else value for value in metric_values])

    print(f"Metrics saved to {csv_path}")

def simplified_name(file_path):
    """
    Simplifies the file name by removing leading underscores, the string '_MERGED',
    and converting everything to lowercase.

    Args:
        file_path (str): The full file path.

    Returns:
        str: The simplified file path.
    """
    # Get the directory and filename
    directory, filename = os.path.split(file_path)

    # Remove leading underscores and '_MERGED', and convert to lowercase
    simplified_filename = filename.lstrip('_').replace('_MERGED', '').lower()

    # Combine back into the full path
    return os.path.join(directory, simplified_filename)


def extend_to_edges(mask: np.ndarray) -> np.ndarray:
    # Ensure mask is uint8
    mask = mask.astype(np.uint8)

    # Get dimensions
    h, w = mask.shape

    # Get coordinates of all true pixels
    ys, xs = np.where(mask == 1)
    if len(ys) == 0:
        # No '1's in the mask, just return the mask as is
        return mask.copy()

    # Identify candidate pixels:
    # topmost
    min_y = np.min(ys)
    top_candidates = np.where(ys == min_y)[0]
    top_pix = (min_y, xs[top_candidates[0]])  # just pick first if multiple

    # bottommost
    max_y = np.max(ys)
    bottom_candidates = np.where(ys == max_y)[0]
    bottom_pix = (max_y, xs[bottom_candidates[0]])

    # leftmost
    min_x = np.min(xs)
    left_candidates = np.where(xs == min_x)[0]
    left_pix = (ys[left_candidates[0]], min_x)

    # rightmost
    max_x = np.max(xs)
    right_candidates = np.where(xs == max_x)[0]
    right_pix = (ys[right_candidates[0]], max_x)

    # Compute distances to respective edges
    distances = []
    # topmost distance to top edge = row index
    distances.append(('top', top_pix, top_pix[0]))
    # bottommost distance to bottom edge = h - 1 - row
    distances.append(('bottom', bottom_pix, (h - 1 - bottom_pix[0])))
    # leftmost distance to left edge = col index
    distances.append(('left', left_pix, left_pix[1]))
    # rightmost distance to right edge = w - 1 - col
    distances.append(('right', right_pix, (w - 1 - right_pix[1])))

    # Sort by distance
    distances.sort(key=lambda x: x[2])

    # Pick the two closest pixels (ensure they are not the same pixel)
    chosen = []
    for d in distances:
        if d[1] not in [c[1] for c in chosen]:
            chosen.append(d)
        if len(chosen) == 2:
            break

    # Print the distances of chosen pixels
    for c in chosen:
        direction, (y, x), dist = c
        if direction == 'top':
            edge_desc = "top"
        elif direction == 'bottom':
            edge_desc = "bottom"
        elif direction == 'left':
            edge_desc = "left"
        elif direction == 'right':
            edge_desc = "right"
        print(f"Chosen pixel {y, x} is {dist} pixels away from the {edge_desc} edge.")

    # Create a copy for output
    output = mask.copy()

    # Extend lines for each chosen pixel
    for c in chosen:
        direction, (y, x), dist = c
        if direction == 'top':
            # fill all pixels from (y,x) up to row=0
            output[0:y + 1, x] = 1
        elif direction == 'bottom':
            # fill all pixels from (y,x) down to row=h-1
            output[y:h, x] = 1
        elif direction == 'left':
            # fill all pixels from (y,x) left to col=0
            output[y, 0:x + 1] = 1
        elif direction == 'right':
            # fill all pixels from (y,x) right to col=w-1
            output[y, x:w] = 1

    return output

if __name__ == '__main__':
    #cut_path_mask_dataset = gdal.Open(r"E:\pichette\pichette out\5,1mr_5_GSD\4,1mr_5_gsd_cut_path_mask_input_frame.tiff")
    #cut_path_mask_dataset = gdal.Open(
    #    r"E:\pichette\pichette out\4,1mr_10_gsd_cut_path_mask_input_frame.tiff")
    #cut_shifted = cut_path_mask_dataset.GetRasterBand(1).ReadAsArray().astype(np.uint8)
    #unit_vector = np.array([-1.,  0.])
    #print('running...')

    #extent =get_extended_extent(cut_shifted)
    #min_row, min_col, max_row, max_col = extent
    #cut_shifted_cropped = cut_shifted[min_row:max_row + 1, min_col:max_col + 1]
    #print(cut_shifted_cropped)
    #fig, ax = plt.subplots(figsize=(8, 8))
    #ax.imshow(cut_shifted_cropped)
    #plt.show()
    #print(cutline_to_mask(cut_shifted, unit_vector, show_plot=True))

    input = [
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 1, 0],
        [0, 0, 1, 1, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0]
    ]

    print(extend_to_edges(np.array(input)))
    '''
    closest_pixels = [
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 1, 0]
        [0, 0, 1, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
    ]

    extentions = [
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 1]
        [1, 1, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
    ]

    output = [
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 1, 1, 1]
        [1, 1, 1, 1, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
        [0, 0, 0, 0, 0, 0, 0]
    ]
    '''