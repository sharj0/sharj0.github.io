from pickletools import uint8
import inspect
from osgeo import gdal, ogr, osr
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import distance, ConvexHull, cKDTree
from scipy.ndimage import minimum_filter, gaussian_filter, label, center_of_mass, binary_fill_holes, binary_dilation
import matplotlib.pyplot as plt
import tempfile
from matplotlib import cm
import random

from scipy.spatial import ConvexHull
from scipy.spatial.distance import cdist

from shapely.geometry import LineString, Point, Polygon, MultiPoint
from collections import OrderedDict
import csv
import networkx as nx
import sys
import os
import time
from datetime import timedelta
from PyQt5.QtWidgets import QApplication, QFileDialog
import gc
import math

import re

from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from shapely.errors import ShapelyError
from shapely import wkt

from itertools import combinations

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
from skimage.measure import block_reduce, find_contours #3rd PARTY library
import rasterio #3rd PARTY library
from rasterio.features import rasterize #3rd PARTY library
from rasterio.windows import Window #3rd PARTY library
from affine import Affine #3rd PARTY library

from qgis.core import (
    QgsApplication,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsCoordinateTransformContext
)
import xml.etree.ElementTree as ET

import os
from osgeo import gdal, ogr
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
import matplotlib.pyplot as plt
import numpy as np
from skimage.measure import block_reduce
from skimage.graph import route_through_array


class Calls:
    def __init__(self, total):
        self.total = total
        self.current = 0

    @property
    def p(self):
        self.current += 1
        return f"{self.current}/{self.total}"

calls = Calls(total=26)


def get_rid_of_extra_cutpath_arms(cut_path_mask, start_pix, end_pix, show_plot=False):
    """
    Simplifies the given binary mask (cut_path_mask) by removing branches and keeping
    only the shortest path between start_pix and end_pix.

    Parameters
    ----------
    cut_path_mask : 2D numpy array (dtype int or bool)
        A binary mask with 1s for the path pixels and 0s elsewhere.
    start_pix : (row, col)
        Starting pixel in the original full-resolution array.
    end_pix : (row, col)
        Ending pixel in the original full-resolution array.
    show_plot : bool, optional
        If True, plots the intermediate path_mask_upsampled and cut_path_mask
        at 50% transparency to visualize overlap.

    Returns
    -------
    final_path : 2D numpy array (same shape as cut_path_mask, dtype uint8)
        A binary mask containing only the shortest path pixels (1) and 0 elsewhere.
    """

    # -------------------------------------------------
    # 1) DOWN-SCALE BY FACTOR OF 4 IN ONE STEP
    # -------------------------------------------------
    reduced_mask = block_reduce(
        cut_path_mask, block_size=(4, 4), func=np.max
    ).astype(bool)

    # -------------------------------------------------
    # 2) MAP START/END PIXELS INTO REDUCED MASK SPACE
    # -------------------------------------------------
    start_coarse = (start_pix[0] // 4, start_pix[1] // 4)
    end_coarse   = (end_pix[0] // 4, end_pix[1] // 4)

    # -------------------------------------------------
    # 3) SHORTEST PATH ON REDUCED MASK
    # -------------------------------------------------
    cost_array = np.where(reduced_mask, 1, 1e9)
    indices, cost = route_through_array(
        cost_array,
        start_coarse,
        end_coarse,
        fully_connected=True
    )

    path_mask_reduced = np.zeros_like(reduced_mask, dtype=bool)
    indices_array = np.array(indices)
    path_mask_reduced[indices_array[:, 0], indices_array[:, 1]] = True

    # -------------------------------------------------
    # 4) THICKEN PATH_MASK_REDUCED BY 2 PIXELS
    # -------------------------------------------------
    structure = np.ones((7, 7), dtype=bool)  # 7x7 structure expands by 3 pixels
    path_mask_reduced = binary_dilation(path_mask_reduced, structure=structure)

    # -------------------------------------------------
    # 5) UPSAMPLE BACK TO ORIGINAL RESOLUTION
    # -------------------------------------------------
    path_mask_upsampled = np.kron(
        path_mask_reduced,
        np.ones((4, 4), dtype=bool)
    )

    H, W = cut_path_mask.shape
    path_mask_upsampled = path_mask_upsampled[:H, :W]

    # -------------------------------------------------
    # 6) PLOT IF REQUIRED
    # -------------------------------------------------
    if show_plot:
        plt.figure(figsize=(10, 10))
        plt.imshow(cut_path_mask, cmap="gray", alpha=0.5, label="Original Mask")
        plt.imshow(path_mask_upsampled, cmap="hot", alpha=0.5, label="Upsampled Path")
        plt.title("Overlap Between Path Mask and Original Mask")
        plt.legend(loc="upper right")
        plt.show()

    # -------------------------------------------------
    # 7) INTERSECT UPSAMPLED PATH WITH ORIGINAL MASK
    # -------------------------------------------------
    final_path = path_mask_upsampled & cut_path_mask.astype(bool)

    # Convert to uint8 for binary mask output
    return final_path.astype(np.uint8)



def flatten_and_find_furthest_points(intersections_per_ovelap_area):
    """
    Flattens a list of lists containing Shapely POINT geometries and finds the two furthest points.

    Args:
        intersections_per_ovelap_area (list): Nested list of Shapely POINT geometries.

    Returns:
        tuple: The two furthest points.
    """
    # Flatten the list of lists
    flat_points = [point for sublist in intersections_per_ovelap_area for point in sublist]

    # Find the two furthest points
    max_distance = -1
    furthest_points = None
    for p1, p2 in combinations(flat_points, 2):  # All unique pairs
        distance = p1.distance(p2)
        if distance > max_distance:
            max_distance = distance
            furthest_points = (p1, p2)

    return furthest_points

def polygonize_and_find_intersections(
    lr_mask_tif1,
    lr_mask_tif2,
    output_kml_path,
    target_epsg_code,
    save_intersections_to_shp=False,
    show_plot=False,
):
    """
    Polygonizes two low-res mask TIFFs (each assumed to contain DN=1 for the region
    of interest), extracts the largest polygon from each, and finds the intersection
    'crossing' points between their outer boundaries.

    - If the two polygons only touch at a boundary (no interior overlap), any line
      intersection is simplified to its centroid (replicated into a pair of identical
      points). Any single intersection point is replicated into a pair of identical
      points.

    - If the polygons overlap in the interior, we look at each polygon's exterior:
        * The segments of that exterior which lie inside the other polygon are
          extracted. Each segment's endpoints are recorded as an (entrance, exit).
        * If a segment is actually a boundary-overlapping line, we reduce it to
          one centroid and replicate that point for the pair.
        * If a 'segment' is just a single point, replicate it for the pair.

    The final intersection list must have an even number of points (2, 4, 6, ...),
    and must not be empty. Otherwise, an exception is raised.

    Args:
        lr_mask_tif1 (str): Path to first mask raster.
        lr_mask_tif2 (str): Path to second mask raster.
        output_kml_path (str): Path to .shp where intersection points will be saved (if flag is True).
        target_epsg_code (int): EPSG code for the output shapefile projection.
        save_intersections_to_shp (bool): If True, saves intersection points to .shp.
        show_plot (bool): If True, shows a matplotlib plot of the two polygons and intersection points.

    Returns:
        list of (float, float): A list of intersection points in the same coordinate
                                space as the input masks. The number of points is always even.
    Raises:
        ValueError: if no intersection is found (0 points) or if something goes wrong
                    polygonizing or unioning.
    """

    # --------------------------------------------
    # 1. Helper: Convert a polygon or multipolygon to largest polygon
    # --------------------------------------------
    def _largest_polygon(geom):
        """
        Given a shapely geometry which could be a Polygon or MultiPolygon,
        return the largest single Polygon.
        """
        if geom.is_empty:
            raise ValueError("Provided geometry is empty.")

        if geom.geom_type == "Polygon":
            return geom
        elif geom.geom_type == "MultiPolygon":
            # pick largest by area
            max_area = 0
            largest_poly = None
            for g in geom.geoms:
                if g.area > max_area:
                    largest_poly = g
                    max_area = g.area
            if largest_poly is None:
                raise ValueError("No valid polygons found in MultiPolygon.")
            return largest_poly
        else:
            raise ValueError(f"Unexpected geometry type: {geom.geom_type}")

    # --------------------------------------------
    # 2. Helper: polygonize a single mask => largest polygon
    # --------------------------------------------
    def _polygonize_single_mask(tiff_path):
        """
        Polygonize one mask TIF where DN=1 is the region of interest.
        Returns the largest polygon (shapely Polygon).
        """
        ds = gdal.Open(tiff_path)
        if ds is None:
            raise ValueError(f"Could not open dataset {tiff_path}")

        band = ds.GetRasterBand(1)
        if band is None:
            raise ValueError(f"Could not get band from {tiff_path}")

        # Create an in-memory OGR layer for polygon results
        drv_mem = ogr.GetDriverByName("Memory")
        dst_ds = drv_mem.CreateDataSource("")
        dst_layer = dst_ds.CreateLayer("poly", srs=None)

        # We'll store the pixel value in a field named 'DN'
        fld = ogr.FieldDefn("DN", ogr.OFTInteger)
        dst_layer.CreateField(fld)

        # Polygonize
        gdal.Polygonize(
            band,
            None,
            dst_layer,
            0,  # the field index for DN
            [],
            callback=None
        )
        dst_layer.ResetReading()

        # Collect polygons with DN == 1
        collected_polys = []
        for i, feat in enumerate(dst_layer):
            val = feat.GetField("DN")
            geom_ref = feat.GetGeometryRef()
            if val == 1 and geom_ref is not None:
                wkt_str = geom_ref.ExportToWkt()
                shape_obj = wkt.loads(wkt_str)
                if not shape_obj.is_empty:
                    collected_polys.append(shape_obj)

        if not collected_polys:
            raise ValueError(f"No polygons with DN==1 found in {tiff_path}.")

        # Union all polygons
        unioned = unary_union(collected_polys)
        if unioned.is_empty:
            raise ValueError(f"Union of polygons in {tiff_path} is empty.")

        # Extract largest polygon
        largest_poly = _largest_polygon(unioned)
        if largest_poly.is_empty:
            raise ValueError("Largest polygon is empty.")

        return largest_poly

    def extract_polygons(geometry_collection):
        """
        Extracts Polygon geometries from a Shapely geometry, handling Polygons,
        MultiPolygons, and GeometryCollections. Converts MultiPolygons into
        individual Polygons and returns them as a flat list.

        Args:
            geometry_collection (Geometry): A Shapely Geometry (Polygon, MultiPolygon, GeometryCollection).

        Returns:
            list: A list of Polygon geometries.
        """
        flat_polygons = []

        # Check the type of the input geometry
        if geometry_collection.geom_type == "Polygon":
            flat_polygons.append(geometry_collection)
        elif geometry_collection.geom_type == "MultiPolygon":
            # Break MultiPolygon into individual Polygons
            flat_polygons.extend(list(geometry_collection.geoms))
        elif geometry_collection.geom_type == "GeometryCollection":
            # Recursively handle nested GeometryCollections
            for geom in geometry_collection.geoms:
                flat_polygons.extend(extract_polygons(geom))
        else:
            # Skip unsupported geometries
            pass

        return flat_polygons

    # Flatten the GeometryCollection
    def extract_linestrings_and_points(geometry_collection):
        """
        Extracts LINESTRING and POINT geometries from a Shapely GeometryCollection,
        and returns them as a flat list.
        """
        flat_geometries = []
        for geom in geometry_collection.geoms:
            if geom.geom_type == "LineString":
                flat_geometries.append(geom)
            elif geom.geom_type == "Point":
                flat_geometries.append(geom)
            elif geom.geom_type == "MultiLineString":
                # Break MultiLineString into individual LineStrings
                flat_geometries.extend(list(geom.geoms))
            elif geom.geom_type == "MultiPoint":
                # Break MultiPoint into individual Points
                flat_geometries.extend(list(geom.geoms))
            elif geom.geom_type == "GeometryCollection":
                # Recursively handle nested GeometryCollections
                flat_geometries.extend(extract_linestrings_and_points(geom))
        return flat_geometries

    def plot_intersections_and_polys(polyA, polyB, flat_list, intersect_polys_flat):
        """
        Plots:
        - Two input polygons (polyA and polyB).
        - LineStrings and Points from flat_list with pre-defined colors,
          marking their start and end points.
        - Intersection polygons from intersect_polys_flat.
        """
        # Predefined color set, excluding green, red, blue, and black
        predefined_colors = ['orange', 'purple', 'cyan', 'magenta', 'brown', 'yellow']

        fig, ax = plt.subplots(figsize=(10, 10))

        # Plot original polygons
        xA, yA = polyA.exterior.xy
        xB, yB = polyB.exterior.xy
        ax.plot(xA, yA, color='red', label='Polygon A Outline')
        ax.plot(xB, yB, color='blue', label='Polygon B Outline')

        # Plot intersection polygons
        for poly in intersect_polys_flat:
            if poly.geom_type == "Polygon":
                x, y = poly.exterior.xy
                ax.fill(x, y, color='green', alpha=0.5, label='Intersection Polygon')

        # Plot LineStrings and Points from flat_list
        color_index = 0
        for geom in flat_list:
            if geom.geom_type == "LineString":
                # Use a color from the predefined set
                color = predefined_colors[color_index % len(predefined_colors)]
                color_index += 1

                x, y = geom.xy
                # Plot the LineString
                ax.plot(x, y, color=color, alpha=0.5, linewidth=3, label='LineString')
                # Mark the start and end points
                start_point = Point(geom.coords[0])
                end_point = Point(geom.coords[-1])
                ax.scatter(start_point.x, start_point.y, color='black', marker='o', label='Start Point')
                ax.scatter(end_point.x, end_point.y, color='black', marker='x', label='End Point')
            elif geom.geom_type == "Point":
                # Plot single Points
                ax.scatter(geom.x, geom.y, color='purple', marker='s', label='Point')

        ax.set_title("Polygons, LineStrings, and Points")
        ax.legend(loc='upper right', fontsize='small')
        ax.set_aspect('equal', adjustable='datalim')
        plt.show()

    def merge_colocated_linestrings(flat_list, tolerance=1e-8):
        """
        Merges LineStrings in the input list if their start or end points
        are co-located within a given tolerance.

        Args:
            flat_list (list): A list of Shapely geometries (LineStrings and Points).
            tolerance (float): Tolerance for considering points as co-located.

        Returns:
            list: A new list with merged LineStrings and original Points.
        """
        # Separate LineStrings and Points
        linestrings = [geom for geom in flat_list if isinstance(geom, LineString)]
        points = [geom for geom in flat_list if isinstance(geom, Point)]

        # A dictionary to track whether a LineString has been merged
        merged = [False] * len(linestrings)

        # Resultant merged LineStrings
        merged_linestrings = []

        for i, ls1 in enumerate(linestrings):
            if merged[i]:
                continue

            # Start a new merged LineString
            current_coords = list(ls1.coords)
            merged[i] = True

            # Look for connections
            merged_something = True
            while merged_something:
                merged_something = False
                for j, ls2 in enumerate(linestrings):
                    if merged[j] or i == j:
                        continue

                    # Check if the end of current connects to the start of ls2
                    if Point(current_coords[-1]).distance(Point(ls2.coords[0])) < tolerance:
                        current_coords.extend(ls2.coords[1:])  # Merge ls2
                        merged[j] = True
                        merged_something = True
                    # Check if the start of current connects to the end of ls2
                    elif Point(current_coords[0]).distance(Point(ls2.coords[-1])) < tolerance:
                        current_coords = list(ls2.coords[:-1]) + current_coords  # Merge ls2
                        merged[j] = True
                        merged_something = True

            # Add the final merged LineString to the result
            merged_linestrings.append(LineString(current_coords))

        # Combine merged LineStrings and original Points
        return merged_linestrings + points

    def find_points_on_intersect_polys(intersect_polys_flat, flat_list_better, tolerance=1e-8):
        """
        Finds points that lie on the exterior of each polygon in intersect_polys_flat by comparing
        with geometries in flat_list_better.

        Args:
            intersect_polys_flat (list): List of individual polygons.
            flat_list_better (list): List of LineStrings and Points.
            tolerance (float): Tolerance for considering geometries as lying on the exterior.

        Returns:
            list: A list of lists of points, one list of points for each polygon.
        """
        results = []

        for intersect_poly in intersect_polys_flat:
            # List to store points for the current polygon
            points_on_exterior = []

            for geom in flat_list_better:
                if isinstance(geom, Point):
                    # Check if the point lies on the exterior
                    if intersect_poly.exterior.distance(geom) < tolerance:
                        points_on_exterior.append(geom)

                elif isinstance(geom, LineString):
                    # Check if both ends of the LineString lie on the exterior
                    start_point = Point(geom.coords[0])
                    end_point = Point(geom.coords[-1])
                    start_on_exterior = intersect_poly.exterior.distance(start_point) < tolerance
                    end_on_exterior = intersect_poly.exterior.distance(end_point) < tolerance

                    if start_on_exterior and end_on_exterior:
                        # Both ends on exterior: Use the midpoint
                        total_length = geom.length
                        midpoint = geom.interpolate(total_length * 0.5)
                        points_on_exterior.append(midpoint)
                    elif start_on_exterior:
                        # Only the start lies on the exterior
                        points_on_exterior.append(start_point)
                    elif end_on_exterior:
                        # Only the end lies on the exterior
                        points_on_exterior.append(end_point)

            # Append points for the current polygon
            results.append(points_on_exterior)

        return results

    def plot_points_on_polygons(polyA, polyB, intersect_polys_flat, points_on_polys):
        """
        Plots:
        - Two input polygons (polyA and polyB).
        - Intersection polygons (intersect_polys_flat).
        - Points (points_on_polys) clearly assigned to the correct polygon.
        """
        # Predefined colors for polygons and their points
        polygon_colors = ['orange', 'purple', 'cyan', 'magenta', 'yellow', 'brown']

        fig, ax = plt.subplots(figsize=(12, 12))

        # Plot original polygons
        xA, yA = polyA.exterior.xy
        xB, yB = polyB.exterior.xy
        ax.plot(xA, yA, color='red', label='Polygon A Outline')
        ax.plot(xB, yB, color='blue', label='Polygon B Outline')

        # Plot intersection polygons and their corresponding points
        for i, intersect_poly in enumerate(intersect_polys_flat):
            # Assign a unique color to each intersect_poly
            poly_color = polygon_colors[i % len(polygon_colors)]

            # Plot the intersection polygon
            if intersect_poly.geom_type == "Polygon":
                x, y = intersect_poly.exterior.xy
                ax.fill(x, y, color=poly_color, alpha=0.5, label=f'Intersection Polygon {i + 1}')

            # Plot the points corresponding to this polygon
            for point in points_on_polys[i]:
                if isinstance(point, Point):
                    ax.scatter(point.x, point.y, color=poly_color, marker='o')

        # Add legend and formatting
        ax.set_title("Polygons and Points on Their Exteriors")
        ax.legend(loc='upper right', fontsize='small', ncol=2)
        ax.set_aspect('equal', adjustable='datalim')
        plt.show()

    def ensure_two_points_per_polygon(intersect_polys_flat, points_on_polys, tolerance=1e-9):
        """
        Ensures each polygon in intersect_polys_flat has exactly two points.
        Raises an error if fewer than two points are found.
        If more than two points are found, selects the two furthest points.

        Args:
            intersect_polys_flat (list): List of individual polygons.
            points_on_polys (list): List of lists of points corresponding to each polygon.
            tolerance (float): Tolerance for point comparison.

        Returns:
            list: A list of lists, each containing exactly two points for each polygon.
        """
        result_points = []

        for i, (intersect_poly, poly_points) in enumerate(zip(intersect_polys_flat, points_on_polys)):
            if len(poly_points) < 2:
                raise ValueError(f"Polygon {i + 1} has fewer than 2 points on its exterior.")
            elif len(poly_points) > 2:
                # Find the two furthest points
                max_distance = -1
                furthest_points = None

                for p1 in poly_points:
                    for p2 in poly_points:
                        if p1 != p2:
                            distance = p1.distance(p2)
                            if distance > max_distance:
                                max_distance = distance
                                furthest_points = (p1, p2)

                if furthest_points:
                    result_points.append(list(furthest_points))
                else:
                    raise ValueError(f"Could not determine furthest points for Polygon {i + 1}.")
            else:
                # Exactly two points
                result_points.append(poly_points)

        return result_points

    # --------------------------------------------
    # 8. Main function steps
    # --------------------------------------------
    # a) Polygonize each mask => largest polygons
    polyA = _polygonize_single_mask(lr_mask_tif1)
    polyB = _polygonize_single_mask(lr_mask_tif2)

    # Intersection and normalization
    boundary_int = polyA.exterior.intersection(polyB.exterior)

    flat_list = extract_linestrings_and_points(boundary_int)

    flat_list_better = merge_colocated_linestrings(flat_list)

    intersect_polys = polyA.intersection(polyB)

    intersect_polys_flat = extract_polygons(intersect_polys)

    points_on_polys  = find_points_on_intersect_polys(intersect_polys_flat, flat_list_better)

    result_points_per_poly = ensure_two_points_per_polygon(intersect_polys_flat, points_on_polys)

    if show_plot:
        plot_intersections_and_polys(polyA, polyB, flat_list_better, intersect_polys_flat)
        plot_points_on_polygons(polyA, polyB, intersect_polys_flat, result_points_per_poly)

    if save_intersections_to_shp:
        shapely_points = [item for sublist in result_points_per_poly for item in sublist]
        save_shp_or_kml(
            geoms=shapely_points,
            out_path=output_kml_path,
            out_layer_name="Intersection points",
            target_epsg_code=f'EPSG:{target_epsg_code}',
            save_shp_not_kml=False
        )

    print(result_points_per_poly)
    return result_points_per_poly

# -----------------------------------------------------------------------------
# Supporting helpers for saving shapefile & plotting
# -----------------------------------------------------------------------------

def _plot_results(tif1, tif2, polyA, polyB, intersection_points):
    """
    Quick matplotlib plot of the two mask polygons and the intersection points.
    """
    import matplotlib.pyplot as plt
    from osgeo import gdal

    def _compute_extent(ds):
        gt = ds.GetGeoTransform()
        w = ds.RasterXSize
        h = ds.RasterYSize
        # corners
        x_min = gt[0]
        x_max = x_min + gt[1]*w + gt[2]*h
        y_min = gt[3] + gt[4]*w + gt[5]*h
        y_max = gt[3]
        # sort
        left, right = sorted([x_min, x_max])
        bottom, top = sorted([y_min, y_max])
        return (left, right, bottom, top)

    ds1 = gdal.Open(tif1)
    arr1 = ds1.GetRasterBand(1).ReadAsArray()
    ext1 = _compute_extent(ds1)

    ds2 = gdal.Open(tif2)
    arr2 = ds2.GetRasterBand(1).ReadAsArray()
    ext2 = _compute_extent(ds2)

    fig, ax = plt.subplots(figsize=(10, 10))

    # Show the two masks with transparency
    ax.imshow(arr1, extent=ext1, origin='upper', cmap='Reds', alpha=0.3)
    ax.imshow(arr2, extent=ext2, origin='upper', cmap='Blues', alpha=0.3)

    # Plot polygon A
    xA, yA = polyA.exterior.xy
    ax.plot(xA, yA, color='red', label='Poly A Outline')

    # Plot polygon B
    xB, yB = polyB.exterior.xy
    ax.plot(xB, yB, color='blue', label='Poly B Outline')

    # Plot intersection points
    if intersection_points:
        ix, iy = zip(*intersection_points)
        ax.scatter(ix, iy, c='k', marker='x', label='Intersections')

    ax.set_aspect('equal', 'datalim')
    ax.legend()
    ax.set_title("Polygons & Intersection Points (Entrance/Exit Pairs)")
    plt.show()





def get_epsg_code(dataset):
    """
    Extracts the EPSG code from a GDAL dataset's projection.

    Parameters:
        dataset (gdal.Dataset): The GDAL dataset object.

    Returns:
        str: The EPSG code in the format 'EPSG:xxxx', or None if unavailable.
    """
    proj_wkt = dataset.GetProjection()  # Get the WKT projection
    if not proj_wkt:
        return None  # No projection found

    # Create a SpatialReference object
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj_wkt)

    # Get the EPSG code
    epsg_code = srs.GetAuthorityCode(None)

    return epsg_code



def downsample_two_masks(
    mask_path_1,
    mask_path_2,
    lr_tif1,
    lr_tif2,
    target_res=2000
):
    """
    Reads two bit-mask GeoTIFFs, computes a shared downsampling factor
    (so the largest dimension is X), and writes two low-resolution
    GeoTIFF masks to `output_folder_path`.
    """

    # Open both datasets
    ds1 = gdal.Open(mask_path_1)
    ds2 = gdal.Open(mask_path_2)

    # Original dimensions
    w1, h1 = ds1.RasterXSize, ds1.RasterYSize
    w2, h2 = ds2.RasterXSize, ds2.RasterYSize

    largest_dim = max(w1, h1, w2, h2)
    block_size = math.ceil(largest_dim / target_res)

    # Read the full arrays into memory
    band1 = ds1.GetRasterBand(1)
    mask_arr1 = band1.ReadAsArray().astype(np.uint8)
    band2 = ds2.GetRasterBand(1)
    mask_arr2 = band2.ReadAsArray().astype(np.uint8)

    # Downsample using np.max in each block => if any pixel is 1, block is 1
    lr_mask1 = block_reduce(mask_arr1, block_size=(block_size, block_size), func=np.max)
    lr_mask2 = block_reduce(mask_arr2, block_size=(block_size, block_size), func=np.max)

    # Original geotransforms
    gt1 = ds1.GetGeoTransform()
    gt2 = ds2.GetGeoTransform()

    # Extract CRS from the input datasets
    proj1 = ds1.GetProjection()  # CRS of mask 1
    proj2 = ds2.GetProjection()  # CRS of mask 2

    ds1 = None
    ds2 = None
    band1 = None
    band2 = None
    # Freed the big arrays from memory if you like
    del mask_arr1
    del mask_arr2

    # Build new geotransforms
    new_gt1 = (
        gt1[0],
        gt1[1] * block_size,
        gt1[2] * block_size,
        gt1[3],
        gt1[4] * block_size,
        gt1[5] * block_size
    )
    new_gt2 = (
        gt2[0],
        gt2[1] * block_size,
        gt2[2] * block_size,
        gt2[3],
        gt2[4] * block_size,
        gt2[5] * block_size
    )

    # Write out the low-res masks as 8-bit single-band GeoTIFF
    def write_mask_tiff(outfile, arr, gt, proj=None):
        driver = gdal.GetDriverByName("GTiff")
        ny, nx = arr.shape
        out_ds = driver.Create(outfile, nx, ny, 1, gdal.GDT_Byte)
        out_ds.SetGeoTransform(gt)
        if proj:
            out_ds.SetProjection(proj)
        out_ds.GetRasterBand(1).WriteArray(arr)
        out_ds.GetRasterBand(1).SetNoDataValue(0)  # optional
        out_ds.FlushCache()
        out_ds = None

    # Pass the CRS while writing the low-res masks
    write_mask_tiff(lr_tif1, lr_mask1, new_gt1, proj1)
    write_mask_tiff(lr_tif2, lr_mask2, new_gt2, proj2)


def save_shp_or_kml(geoms, out_path, out_layer_name, target_epsg_code, save_shp_not_kml=True):
    """
    Saves a list of Shapely geometries to a shapefile or KML file using QGIS.

    Parameters:
        geoms (list): List of Shapely geometry objects.
        out_path (str): Output file path.
        out_layer_name (str): Name of the output layer.
        target_epsg_code (str): EPSG code of the target CRS.
        save_shp_not_kml (bool): Whether to save as shapefile (True) or KML (False).
    """
    # Make necessary folders
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Set up vector file writing options
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile" if save_shp_not_kml else "KML"
    options.fileEncoding = "UTF-8"

    # Create a memory layer
    _layer = QgsVectorLayer(f"Point?crs={target_epsg_code}", out_layer_name, "memory")
    _layer_data_provider = _layer.dataProvider()
    _layer.startEditing()

    # Add geometries to the layer
    for geom in geoms:
        qgs_geom = QgsGeometry.fromWkt(geom.wkt)  # Convert Shapely geometry to QgsGeometry
        _feature = QgsFeature()
        _feature.setGeometry(qgs_geom)
        _layer_data_provider.addFeatures([_feature])

    _layer.commitChanges()

    # Write the memory layer to file
    QgsVectorFileWriter.writeAsVectorFormatV3(
        _layer, out_path, QgsCoordinateTransformContext(), options
    )

    print(f"File saved to {out_path}")


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

def flatten_raster_construction_tree(raster_construction_tree):
    """
    Flattens a nested raster_construction_tree dictionary into a list of sources.
    Each source is a dict with:
        msk,
        tif,
        raster_name,
        inputrelated_save_base,
        gt,
        shape
    """
    flattened_list = []

    for _, source_data in raster_construction_tree.items():
        # Case 1: If sub_sources exist (typical if source_type="vrt")
        if "sub_sources" in source_data:
            for _, sub_val in source_data["sub_sources"].items():
                flattened_list.append({
                    "msk": sub_val.get("msk"),
                    "tif": sub_val.get("tif"),
                    "raster_name": sub_val.get("raster_name"),
                    "inputrelated_save_base": sub_val.get("inputrelated_save_base"),
                    "gt": sub_val.get("gt"),
                    "shape": sub_val.get("shape")  # Add shape
                })
        # Case 2: If no sub_sources (typical if source_type="tif")
        else:
            flattened_list.append({
                "msk": source_data.get("msk"),
                "tif": source_data.get("tif"),
                "raster_name": source_data.get("raster_name"),
                "inputrelated_save_base": source_data.get("inputrelated_save_base"),
                "gt": source_data.get("gt"),
                "shape": source_data.get("shape")  # Add shape
            })

    return flattened_list



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


def angle(p1, p2):
    """
    Returns the angle (in degrees) of the vector p1->p2 relative
    to the positive x-axis, in [0, 360).
    p1 and p2 are (x, y) tuples.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    theta = math.degrees(math.atan2(dy, dx))
    return theta % 360


def angle_diff(a, b):
    """
    Returns the minimal difference (in degrees) between angles a and b,
    taking into account that angles wrap around at 360.
    For example, angle_diff(356, 2) -> 6 (because 356 is "near" 0).
    """
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def euclidean_dist(p1, p2):
    """
    Euclidean distance between p1=(x1, y1) and p2=(x2, y2).
    """
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def angle_diff(a, b):
    """
    Minimal absolute difference between two angles a and b in [0,360).
    E.g. angle_diff(350, 10) = 20
    """
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def angle_cost(line_angle, edge_angle):
    """
    Returns the cost of how far edge_angle is from line_angle.
    We treat 0-10 deg as cost=1, 10-20 deg=2, 20-30 deg=3, 30-40 deg=4

    Also handle the possibility that 0° ~ 180°, i.e., we check both the
    direct angle_diff(line_angle, edge_angle) and angle_diff(line_angle, edge_angle+180).
    We'll return the minimum cost of these two comparisons to be direction-agnostic.
    """
    # Direct difference
    d1 = angle_diff(line_angle, edge_angle)
    # Opposite direction difference
    d2 = angle_diff(line_angle, (edge_angle + 180) % 360)

    # We'll compute cost for each difference and take the minimum
    def diff_to_cost(d):
        # Each 10° step adds 1 cost, so 0-10 => cost=1, 30-40 => cost=4
        return int(d // 10) + 1  # integer division

    return min(diff_to_cost(d1), diff_to_cost(d2))


def compute_edge_angle(pos_u, pos_v):
    """
    Return angle (in degrees) of vector (u->v) relative to +x-axis in [0, 360).
    """
    dx = pos_v[0] - pos_u[0]
    dy = pos_v[1] - pos_u[1]
    theta = math.degrees(math.atan2(dy, dx))
    return theta % 360


def node_degree_cost(deg):
    """
    Node cost depending on degree:
        deg >= 3 => 1
        deg = 1 or 2 => 2
    """
    return 1 if deg >= 3 else 2


def distance_cost(node_pos, intersection_pos, max_dist):
    """
    Distance-based cost:
      - 0 if node is at the intersection
      - up to 9 if node is at the furthest distance
      - We subdivide the distance range into 10 steps (0..9).
    """
    dx = node_pos[0] - intersection_pos[0]
    dy = node_pos[1] - intersection_pos[1]
    d = math.hypot(dx, dy)
    if max_dist == 0:
        # Avoid division by zero if everything is at the intersection
        return 0
    ratio = d / max_dist
    # scale ratio * 10, then floor; cap at 9
    cost = int(math.floor(ratio * 10))
    return min(cost, 9)


def select_lowest_cost_nodes(H, pos, intersections, show_plot=False):
    """
    1) Compute reference angle from intersections[0] to intersections[1].
    2) For each edge, compute angle cost => edge_cost[e].
    3) For each node, pick the lowest angle cost among edges connected to it => angle_cost_node[n].
    4) Node degree cost => 1 if deg>=3, else 2.
    5) For each intersection:
         - Compute the maximum distance among all nodes in H (for that intersection).
         - For each node, compute distance cost from that intersection.
         - Total node cost = angle_cost_node[n] + node_degree_cost + distance_cost.
         - Pick the node with the minimum total cost (if angle_cost_node[n] == ∞, total cost is ∞).
         - Plot a figure (2 subplots total, one per intersection).

    Returns:
        [node_for_intersection0, node_for_intersection1]
    """
    if len(intersections) != 2:
        raise ValueError("Expected exactly two intersections, got {}".format(len(intersections)))

    intersection1, intersection2 = intersections
    # 1) Reference angle
    dx = intersection2[0] - intersection1[0]
    dy = intersection2[1] - intersection1[1]
    line_angle = math.degrees(math.atan2(dy, dx)) % 360

    # 2) Edge angle cost
    edge_cost_dict = {}  # (u,v) -> cost
    for (u, v) in H.edges():
        if u not in pos or v not in pos:
            continue
        e_angle = compute_edge_angle(pos[u], pos[v])
        cost_a = angle_cost(line_angle, e_angle)
        edge_cost_dict[(u, v)] = cost_a
        edge_cost_dict[(v, u)] = cost_a  # for undirected; store both ways

    # 3) Node angle cost = min cost among edges connected to it
    node_angle_cost = {}
    for n in H.nodes():
        # If node has no edges, you might define cost as ∞ or skip
        connected_edges = H.edges(n)
        costs = []
        for e in connected_edges:
            # e is (n, neighbor) or (neighbor, n)
            if e in edge_cost_dict:
                costs.append(edge_cost_dict[e])
            else:
                # The edge might be stored as (neighbor, n)
                costs.append(edge_cost_dict.get((e[1], e[0]), math.inf))
        node_angle_cost[n] = min(costs) if costs else math.inf

    # 4) Node degree cost
    node_deg_cost = {}
    for n in H.nodes():
        node_deg_cost[n] = node_degree_cost(H.degree[n])

    # We'll prepare for plotting two subplots if show_plot
    # Because we do a separate cost scenario for each intersection (distance cost differs)
    fig, axes = (None, None)
    if show_plot:
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    chosen_nodes = []
    for i, intersection_pt in enumerate([intersection1, intersection2]):
        # 5a) Find maximum distance for this intersection
        #    so we can define distance cost for each node
        max_dist = 0.0
        for n in H.nodes():
            dx = pos[n][0] - intersection_pt[0]
            dy = pos[n][1] - intersection_pt[1]
            dist = math.hypot(dx, dy)
            if dist > max_dist:
                max_dist = dist

        # 5b) For each node, compute distance cost and total cost
        node_total_cost = {}
        for n in H.nodes():
            dist_c = distance_cost(pos[n], intersection_pt, max_dist)
            ac = node_angle_cost[n]
            if ac == math.inf:
                # If angle cost is infinite, total is infinite
                node_total_cost[n] = math.inf
            else:
                node_total_cost[n] = ac + node_deg_cost[n] + dist_c

        # 5c) Find the node with the minimum total cost
        valid_nodes = [n for n in H.nodes() if node_total_cost[n] != math.inf]
        if valid_nodes:
            best_node = min(valid_nodes, key=lambda n: node_total_cost[n])
        else:
            best_node = None
        chosen_nodes.append(best_node)

        # 5d) Plot if show_plot
        if show_plot:
            ax = axes[i]
            ax.set_title(f"Intersection {i + 1} (Cost View)")
            ax.set_aspect('equal')

            # --- Plot edges ---
            # We'll color edges by their angle cost: 1..4 => gradient, ∞ => black
            # Construct a colormap from cost=1..4
            # We'll do a simple discrete color mapping for demonstration
            # e.g. cost=1 => green, 2 => yellow, 3 => orange, 4 => red, inf=> black
            edge_colors = []
            for (u, v) in H.edges():
                c = edge_cost_dict.get((u, v), math.inf)
                if c == 1:
                    ec = "green"
                elif c == 2:
                    ec = "yellow"
                elif c == 3:
                    ec = "orange"
                elif c == 4:
                    ec = "red"
                else:
                    ec = "black"
                edge_colors.append(ec)

            # We can use nx.draw_networkx_edges with 'edge_color=edge_colors' if we
            # provide edges in the same order as we provide edge_colors
            # So let's gather edges in a list:
            edges_list = list(H.edges())
            nx.draw_networkx_edges(H, pos, edgelist=edges_list, edge_color=edge_colors, ax=ax)

            # --- Plot nodes ---
            # We'll color nodes by total cost in a gradient from 0..(4+2+9=15).
            # If cost=∞ => color them black or grey.
            # We'll build a list of all node costs, then map to a color scale.
            all_costs = [c for c in node_total_cost.values() if c != math.inf]
            min_c = 0
            max_c = 15  # theoretical max: angle(4) + deg(2) + dist(9)=15
            # In practice, might be smaller, but let's fix 0..15 for the colormap.

            # To build a continuous colormap, let's use a simple linear mapping
            cmap = plt.cm.viridis  # can choose another
            norm = plt.Normalize(vmin=min_c, vmax=max_c)

            node_color_map = {}
            for n in H.nodes():
                c = node_total_cost[n]
                if c == math.inf:
                    node_color_map[n] = "black"
                else:
                    # Map c to [0..1], then get a color from the colormap
                    t = norm(c)
                    node_color_map[n] = cmap(t)

            # Draw nodes individually to control color & label
            for n in H.nodes():
                x, y = pos[n]
                ax.scatter(x, y, color=node_color_map[n], s=50, zorder=3)
                # Annotate the cost next to each node
                cost_text = (f"{node_total_cost[n]:.0f}"
                             if node_total_cost[n] != math.inf
                             else "inf")
                ax.text(x + 2, y + 2, cost_text, fontsize=8, color="black")

            # Plot the intersection point
            ax.scatter(intersection_pt[0], intersection_pt[1], color="red", s=120, marker="X", zorder=5,
                       label="Intersection")

            # Highlight the chosen node (lowest cost)
            if best_node is not None:
                bx, by = pos[best_node]
                # use a thick outline or bigger marker
                ax.scatter(bx, by, facecolor="none", edgecolor="cyan", s=200, linewidth=2, zorder=6, label="Best Node")

            ax.legend()

    if show_plot:
        plt.tight_layout()
        plt.show()

    return chosen_nodes


def compute_centerline(mask, intersections_per_ovelap_area_pixel_coords, max_dim_size=4000, show_plot=False):
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

    intersection_average_centers = []
    resized_intersections_per_ovelap_area = []
    print(f'{intersections_per_ovelap_area_pixel_coords = }')
    for intersections in intersections_per_ovelap_area_pixel_coords:
        resized_intersections = [
            (int(coord[0] * scale), int(coord[1] * scale)) for coord in intersections
        ]
        centroid = MultiPoint(resized_intersections).centroid
        intersection_average_center = centroid.x, centroid.y
        intersection_average_centers.append(intersection_average_center)
        resized_intersections_per_ovelap_area.append(resized_intersections)

    mask_resized = binary_fill_holes(mask_resized)
    print(f"{scale=}")

    # Compute the centroid of the resized mask
    mask_coords = np.argwhere(mask_resized)
    mask_centroid = mask_coords.mean(axis=0)
    mask_centroid_point = Point(mask_centroid[1], mask_centroid[0])  # (x, y)

    # Find the closest intersection_average_center to the mask's centroid
    closest_index = None
    min_distance = float('inf')
    for i, center in enumerate(intersection_average_centers):
        center_point = Point(center)
        distance = mask_centroid_point.distance(center_point)
        if distance < min_distance:
            min_distance = distance
            closest_index = i

    if closest_index is None:
        raise ValueError("No intersection center was found close to the mask centroid.")

    # Extract the closest list of resized intersections
    resized_intersections = resized_intersections_per_ovelap_area[closest_index]

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

    # Simplify the graph
    H = simplify_graph(H)

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

        # After loop removal plot
        if show_plot:
            fig, ax = plt.subplots(figsize=(8, 8))

            # Extract node positions
            pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}

            # Draw the graph
            nx.draw(
                H, pos, edge_color='blue', node_size=50, with_labels=False, ax=ax, node_color='orange'
            )

            # Extract intersection points
            x_coords_intrs, y_coords_intrs = zip(*resized_intersections)

            # Draw a line connecting the intersections
            ax.plot(x_coords_intrs, y_coords_intrs, color='red', linewidth=2, label="Intersection Line", zorder=5)

            # Set aspect ratio, title, and legend
            ax.set_aspect('equal')
            ax.set_title("Graph State After Removing Loops with Intersections")
            ax.legend()
            plt.show()

    pos = {node: (skel_coords[node][1], skel_coords[node][0]) for node in H.nodes()}
    result_nodes = select_lowest_cost_nodes(H, pos, resized_intersections, show_plot=show_plot)

    degree_1_nodes = [node for node in H.nodes() if H.degree(node) == 1]
    degree_1_coords = np.array([pos[node] for node in degree_1_nodes])

    # Shortest path in the original skeleton graph G
    shortest_path_nodes = nx.shortest_path(G, source=result_nodes[0], target=result_nodes[1])
    shortest_path_coords = np.array([skel_coords[node] for node in shortest_path_nodes])

    start_point = shortest_path_coords[0]
    end_point   = shortest_path_coords[-1]

    # -------------------------------------------------------------------------
    # 1) Scale the shortest path coordinates (and the start/end points) back
    #    to the original mask's coordinate system.
    # -------------------------------------------------------------------------
    if scale != 1.0:
        shortest_path_coords_rescaled = shortest_path_coords / scale
        start_point_rescaled = start_point / scale
        end_point_rescaled = end_point / scale
    else:
        shortest_path_coords_rescaled = shortest_path_coords
        start_point_rescaled = start_point
        end_point_rescaled = end_point

    # -------------------------------------------------------------------------
    # 2) Rescale the chosen intersections back as well.
    # -------------------------------------------------------------------------
    if scale != 1.0:
        resized_intersections_rescaled = [
            (pt[1] / scale, pt[0] / scale) for pt in resized_intersections
        ]
    else:
        resized_intersections_rescaled = [(pt[1], pt[0]) for pt in resized_intersections]

    # Plot the elements for debugging
    if show_plot:
        fig, axes = plt.subplots(1, 2, figsize=(18, 6))

        # Plot the mask with rescaled shortest path
        axes[0].imshow(mask, cmap="gray")
        axes[0].scatter(shortest_path_coords_rescaled[:, 1], shortest_path_coords_rescaled[:, 0],
                        color="yellow", label="Shortest Path Rescaled", s=10)
        axes[0].scatter([start_point_rescaled[1]], [start_point_rescaled[0]],
                        color="green", label="Start Point", s=50)
        axes[0].scatter([end_point_rescaled[1]], [end_point_rescaled[0]],
                        color="red", label="End Point", s=50)
        axes[0].legend()
        axes[0].set_title("Mask with Rescaled Shortest Path")

        # Plot resized intersections
        axes[1].imshow(mask, cmap="gray")
        x_coords, y_coords = zip(*resized_intersections_rescaled)
        axes[1].scatter(y_coords, x_coords, color="blue", label="Resized Intersections", s=30)
        axes[1].legend()
        axes[1].set_title("Mask with Resized Intersections")

        plt.tight_layout()
        plt.show()

    # -------------------------------------------------------------------------
    # 3) Find the single closest intersection to start and end points
    # -------------------------------------------------------------------------
    def euclidean_distance(a, b):
        return np.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    closest_intersection_to_start = min(
        resized_intersections_rescaled,
        key=lambda pt: euclidean_distance(pt, start_point_rescaled)
    )
    closest_intersection_to_end = min(
        resized_intersections_rescaled,
        key=lambda pt: euclidean_distance(pt, end_point_rescaled)
    )

    # -------------------------------------------------------------------------
    # 4) Draw lines using skimage.draw.line()
    # -------------------------------------------------------------------------
    sr0, sc0 = map(int, start_point_rescaled)
    si0, si1 = map(int, closest_intersection_to_start)
    er0, ec0 = map(int, end_point_rescaled)
    ei0, ei1 = map(int, closest_intersection_to_end)

    # Clip the endpoints to prevent out-of-bounds errors
    sr0 = np.clip(sr0, 0, mask.shape[0] - 1)
    sc0 = np.clip(sc0, 0, mask.shape[1] - 1)
    si0 = np.clip(si0, 0, mask.shape[0] - 1)
    si1 = np.clip(si1, 0, mask.shape[1] - 1)
    er0 = np.clip(er0, 0, mask.shape[0] - 1)
    ec0 = np.clip(ec0, 0, mask.shape[1] - 1)
    ei0 = np.clip(ei0, 0, mask.shape[0] - 1)
    ei1 = np.clip(ei1, 0, mask.shape[1] - 1)

    # Draw lines
    rr1, cc1 = line(sr0, sc0, si0, si1)
    rr2, cc2 = line(er0, ec0, ei0, ei1)

    # Clip the resulting line coordinates
    rr1 = np.clip(rr1, 0, mask.shape[0] - 1)
    cc1 = np.clip(cc1, 0, mask.shape[1] - 1)
    rr2 = np.clip(rr2, 0, mask.shape[0] - 1)
    cc2 = np.clip(cc2, 0, mask.shape[1] - 1)

    # Plot lines for debugging
    if show_plot:
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.imshow(mask, cmap="gray")
        ax.plot(cc1, rr1, color="green", label="Line: Start -> Intersection", linewidth=1)
        ax.plot(cc2, rr2, color="red", label="Line: End -> Intersection", linewidth=1)
        ax.legend()
        ax.set_title("Lines Drawn on Mask")
        plt.show()

    # -------------------------------------------------------------------------
    # 5) Combine lines with shortest_path_mask
    # -------------------------------------------------------------------------
    shortest_path_mask = np.zeros_like(mask, dtype=bool)
    rows_rescaled = shortest_path_coords_rescaled[:, 0].astype(int)
    cols_rescaled = shortest_path_coords_rescaled[:, 1].astype(int)
    rows_rescaled = np.clip(rows_rescaled, 0, mask.shape[0] - 1)
    cols_rescaled = np.clip(cols_rescaled, 0, mask.shape[1] - 1)
    shortest_path_mask[rows_rescaled, cols_rescaled] = True

    line_mask = np.zeros_like(mask, dtype=bool)
    line_mask[rr1, cc1] = True
    line_mask[rr2, cc2] = True

    final_mask = np.logical_or(shortest_path_mask, line_mask)

    # -------------------------------------------------------------------------
    # 6) Return both final_mask and resized_intersections_rescaled
    # -------------------------------------------------------------------------
    return final_mask.astype(mask.dtype), resized_intersections_rescaled


def connect_sorted_ends(endss, mask_shape, show_plot=False):
    """
    Connect lines in a sorted order from 'end' of one line to 'start' of the next
    based on their centroid positions along the axis defined by the two furthest endpoints.

    Parameters:
        endss (list of tuple):
            A list of line endpoints, where each element is a tuple
            ((row1, col1), (row2, col2)).
        mask_shape (tuple): Shape of the mask (rows, cols) to create for connecting lines.
        show_plot (bool): Whether to show a plot of the connecting lines.

    Returns:
        np.ndarray: A binary mask with the connecting lines drawn.
    """

    # --- 1) Flatten all endpoints and find the two furthest points F1, F2 ---
    all_points = []
    for (p1, p2) in endss:
        all_points.append(np.array(p1))
        all_points.append(np.array(p2))

    # Find the two points with the maximum Euclidean distance
    max_dist = 0.0
    F1, F2 = None, None
    for i in range(len(all_points)):
        for j in range(i + 1, len(all_points)):
            dist = np.linalg.norm(all_points[i] - all_points[j])
            if dist > max_dist:
                max_dist = dist
                F1, F2 = all_points[i], all_points[j]

    F1 = np.array(F1, dtype=float)
    F2 = np.array(F2, dtype=float)

    # If there's only one line or something degenerate, just return an empty mask
    if F1 is None or F2 is None or np.allclose(F1, F2):
        raise TypeError("There's only one line or something degenerate")

    # --- 2) For each line, compute its centroid ---
    centroids = []
    for i, (e1, e2) in enumerate(endss):
        e1_arr = np.array(e1, dtype=float)
        e2_arr = np.array(e2, dtype=float)
        centroid = 0.5 * (e1_arr + e2_arr)
        centroids.append(centroid)

    # --- 3) Project each line's centroid onto the vector (F2 - F1) for sorting ---
    direction = F2 - F1
    direction_sqnorm = np.dot(direction, direction)  # ||F2 - F1||^2

    # To get the scalar projection of a point P onto the vector F1->F2:
    #   param = ( (P - F1) . direction ) / ( direction . direction )
    # We'll store (param, line_index) so we can sort by param.
    line_params = []
    for i, c in enumerate(centroids):
        param = np.dot((c - F1), direction) / direction_sqnorm
        line_params.append((param, i))
    line_params.sort(key=lambda x: x[0])  # sort by param

    # --- 4) For each line, define "start" as the endpoint with smaller projection param ---
    #         and "end" as the endpoint with larger projection param, *relative to F1->F2*.
    # We'll create a new structure that keeps track of sorted lines and their start/end.
    sorted_lines = []
    for param, i in line_params:
        (e1, e2) = endss[i]
        e1_arr = np.array(e1, dtype=float)
        e2_arr = np.array(e2, dtype=float)
        param_e1 = np.dot((e1_arr - F1), direction) / direction_sqnorm
        param_e2 = np.dot((e2_arr - F1), direction) / direction_sqnorm
        if param_e1 < param_e2:
            start_pt, end_pt = e1, e2
        else:
            start_pt, end_pt = e2, e1
        sorted_lines.append((start_pt, end_pt))

    # --- 5) Initialize an empty mask and connect consecutive lines in sorted order ---
    connecting_lines_mask = np.zeros(mask_shape, dtype=np.uint8)

    # We'll connect line[i].end -> line[i+1].start
    for i in range(len(sorted_lines) - 1):
        _, this_end = sorted_lines[i]
        next_start, _ = sorted_lines[i + 1]

        r0, c0 = int(this_end[0]), int(this_end[1])
        r1, c1 = int(next_start[0]), int(next_start[1])

        rr, cc = line(r0, c0, r1, c1)
        connecting_lines_mask[rr, cc] = 1

    # --- 6) Optionally, show the plot of the connecting lines ---
    if show_plot:
        plt.figure(figsize=(8, 6))
        plt.imshow(connecting_lines_mask, cmap='gray', origin='lower')
        coords = np.array(endss).reshape(-1, 2)  # Reshape into a 2D array with [y, x] pairs
        y_coords, x_coords = coords[:, 0], coords[:, 1]
        plt.scatter(x_coords,y_coords)
        plt.title('Connecting Lines (Sorted)')
        plt.show()

    return connecting_lines_mask

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

    if show_plot:
        plt.figure(figsize=(10, 5))
        coords = np.array(endss).reshape(-1, 2)  # Reshape into a 2D array with [y, x] pairs
        y_coords, x_coords = coords[:, 0], coords[:, 1]
        plt.scatter(x_coords,y_coords)
        plt.show()

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


def plot_array(array, title=None, cmap="gray"):
    """
    Display a 2D array using matplotlib with interpolation disabled.

    Parameters:
    array (np.ndarray): 2D array to display.
    title (str): Title of the plot. If None, the name of the input variable is used.
    cmap (str): Colormap to use for visualization (e.g., 'gray', 'hot').
    """
    if title is None:
        # Extract the variable name from the calling environment
        frame = inspect.currentframe().f_back
        variable_name = [name for name, val in frame.f_locals.items() if val is array]
        title = variable_name[0] if variable_name else "Array Visualization"

    plt.figure(figsize=(10, 5))
    plt.imshow(array, cmap=cmap, interpolation='none')  # Disable interpolation
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

        # Plot to visualize the sub-array and endpoints before calling route_through_array
        if show_plot:
            plt.figure(figsize=(8, 8))
            plt.title(f"Debug Plot Before route_through_array (Segment {i+1})")
            plt.imshow(sub_cost_array, cmap='gray', origin='lower')
            plt.scatter(sub_start[1], sub_start[0], color='green', label='Start Point', s=100)
            plt.scatter(sub_end[1], sub_end[0], color='red', label='End Point', s=100)
            plt.legend()
            plt.xlabel("Column")
            plt.ylabel("Row")
            plt.show()

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


def find_path(path_pref, overlap_mask, start, end, centreline_mask, full_centreline_coords_xy, num_segments=5, show_plot=False):
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
        if len(full_centreline_coords_xy) > 0:
            cx, cy = zip(*full_centreline_coords_xy)
            axes[0, 0].scatter(cx, cy, color='blue', label='Original Centreline', s=10)
            # Add numbers next to the centreline points
            for idx, (x, y) in enumerate(zip(cx, cy), start=1):
                axes[0, 0].annotate(
                    str(idx), (x, y), textcoords="offset points", xytext=(3, 3), fontsize=8, color='black'
                )
        axes[0, 0].set_title("Original Path Preference")
        axes[0, 0].legend()

        axes[0, 1].imshow(centreline_mask, cmap='gray', origin='lower')
        axes[0, 1].set_title("Original Centreline Mask")

        # Plot cropped path_pref and centreline_mask
        axes[1, 0].imshow(cropped_path_pref, cmap='gray', origin='lower')
        axes[1, 0].scatter(cropped_start[1], cropped_start[0], color='green', label='Start (Adjusted)', s=50)
        axes[1, 0].scatter(cropped_end[1], cropped_end[0], color='red', label='End (Adjusted)', s=50)
        if len(cropped_full_centreline_coords_xy) > 0:
            cx, cy = zip(*cropped_full_centreline_coords_xy)
            axes[1, 0].scatter(cx, cy, color='blue', label='Cropped Centreline', s=10)
            # Add numbers next to the cropped centreline points
            for idx, (x, y) in enumerate(zip(cx, cy), start=1):
                axes[1, 0].annotate(
                    str(idx), (x, y), textcoords="offset points", xytext=(3, 3), fontsize=8, color='black'
                )
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

    # Remove points that are outside the cost_array
    cropped_full_centreline_coords_xy = [
        (r, c) for (r, c) in cropped_full_centreline_coords_xy
        if 0 <= c < cost_array.shape[0] and 0 <= r < cost_array.shape[1]
    ]

    # Compute shortest distance and define search radius
    shortest_distance_coords = find_shortest_distance(cropped_full_centreline_coords_xy)
    search_radius = int(0.4 * shortest_distance_coords)

    # Separate start & end before culling
    #start_coord = cropped_full_centreline_coords_xy[0]
    #end_coord = cropped_full_centreline_coords_xy[-1]
    middle_coords = cropped_full_centreline_coords_xy[1:-1]


    # Dynamic culling based on num_segments
    if num_segments is not None and len(middle_coords) > 0:
        if num_segments < 2 or num_segments > len(middle_coords):
            print("Invalid num_segments value. Falling back to default culling behavior (every other point).")
            middle_coords = middle_coords[::2]
        else:
            step = max(1, len(middle_coords) // num_segments)
            middle_coords = middle_coords[::step]

    # Adjust only the middle coords
    adjusted_middle_coords = []
    if len(middle_coords) > 0:
        adjusted_middle_coords = adjust_coordinates_by_cost(
            middle_coords, cropped_centreline_mask, cost_array, search_radius
        )

    # Reassemble final adjusted coords
    adjusted_cropped_coords = [(cropped_start[1], cropped_start[0])] + adjusted_middle_coords + [(cropped_end[1], cropped_end[0])]

    # Remove points that are outside the cost_array
    adjusted_cropped_coords = [
        (r, c) for (r, c) in adjusted_cropped_coords
        if 0 <= c < cost_array.shape[0] and 0 <= r < cost_array.shape[1]
    ]

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

def generate_linestring(mask, num_points = 10, show_plot = False):
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


import numpy as np
from osgeo import gdal
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon, Point

def extend_linestring_past_footprint(linestring_coords_xy,
                                     raster_path,
                                     footprint_vrt_path,
                                     intersection_points,  # <-- Real-world coords of two intersection points
                                     show_plot=False):
    """
    Extend each end of a linestring so that it passes through a specified intersection point
    outside the current extent, and continues until it exits the footprint polygon.

    MODIFICATIONS in this version:
      - The very first and last points of the original linestring are removed.
      - The new 'start_pt' is the second point from the original linestring.
      - The new 'end_pt' is the second-last point from the original linestring.
      - Intersection points are plotted in *all* plots.
      - Any code we removed is explained in comments.

    :param linestring_coords_xy: List of (x, y) pixel coordinates (in the main raster's coordinate system).
    :param raster_path: Path to the main raster (used for geotransform and optional plotting).
    :param footprint_vrt_path: Path to the footprint VRT (for geotransform and bounding polygon).
    :param intersection_points: A list/tuple of two shapely Points (in x_world, y_world),
                               one off each end of the line.
    :param show_plot: Whether to show debug/diagnostic plots.
    :return: N x 2 numpy array of extended linestring coordinates in pixel (row/col) space.
    """

    ############################################################################
    # 1) OPEN AND INSPECT THE RASTER(S)
    ############################################################################
    raster_ds = gdal.Open(raster_path)
    if raster_ds is None:
        raise ValueError(f"Unable to open raster file at {raster_path}")
    raster_geotransform = raster_ds.GetGeoTransform()
    raster_width = raster_ds.RasterXSize
    raster_height = raster_ds.RasterYSize

    footprint_ds = gdal.Open(footprint_vrt_path)
    if footprint_ds is None:
        raise ValueError(f"Unable to open VRT file at {footprint_vrt_path}")
    footprint_geotransform = footprint_ds.GetGeoTransform()
    footprint_width = footprint_ds.RasterXSize
    footprint_height = footprint_ds.RasterYSize

    # (Kept for debugging - often useful to confirm geotransform & dimensions)
    print("Raster geotransform:", raster_geotransform)
    print(f"Raster dimensions: {raster_width} x {raster_height}")
    print("Footprint geotransform:", footprint_geotransform)
    print(f"Footprint dimensions: {footprint_width} x {footprint_height}")

    ############################################################################
    # 2) HELPER FUNCTIONS
    ############################################################################
    def pixel_to_world(geo_transform, px, py):
        """Convert pixel (px, py) to world (x, y) using the given geotransform."""
        x = geo_transform[0] + px * geo_transform[1] + py * geo_transform[2]
        y = geo_transform[3] + px * geo_transform[4] + py * geo_transform[5]
        return (x, y)

    def world_to_pixel(geo_transform, x, y):
        """
        Inverse of pixel_to_world for a simple north-up case (no rotation).
        If your data has rotation (geo_transform[2] or geo_transform[4] != 0),
        you'd need a full inverse transform. This code does not handle that fully.
        """
        inv_x = (x - geo_transform[0]) / geo_transform[1]
        inv_y = (y - geo_transform[3]) / geo_transform[5]
        return (inv_x, inv_y)

    def get_raster_extent(geo_transform, width, height):
        """Return (x_min, x_max, y_min, y_max) for a raster given transform and size."""
        x_min = geo_transform[0]
        y_max = geo_transform[3]
        x_max = x_min + width * geo_transform[1] + height * geo_transform[2]
        y_min = y_max + width * geo_transform[4] + height * geo_transform[5]
        return x_min, x_max, y_min, y_max

    ############################################################################
    # 3) CONVERT LINESTRING PIXEL COORDS -> WORLD COORDS
    ############################################################################
    # Convert each (row, col) pixel coordinate to world coords
    world_coords = [
        pixel_to_world(raster_geotransform, x, y)
        for (x, y) in linestring_coords_xy
    ]

    # Build a shapely LineString from all the original points
    original_line = LineString(world_coords)

    # == MODIFICATION ==
    # We remove the FIRST and LAST points from the original linestring.
    #    This means we only keep the second -> second-last points.
    #    Then we re-build the 'line' from that subset.
    # WHY? Because the user asked to "delete the first and last points on the line and
    #      use the second and second-last points as the new start/end."
    #
    # (Below we show the old line creation is replaced.)
    new_world_coords = world_coords[1:-1]  # remove first and last
    line = LineString(new_world_coords)

    # Basic sanity check after removing ends
    if len(line.coords) < 2:
        raise ValueError("Linestring must have at least 2 points after removing first and last points.")

    ############################################################################
    # 4) OPTIONAL: PLOT THE (TRUNCATED) LINESTRING IN WORLD COORDINATES
    ############################################################################
    if show_plot:
        raster_band = raster_ds.GetRasterBand(1)
        raster_data = raster_band.ReadAsArray()

        # Compute extent in world coords (naive bounding box)
        min_x = raster_geotransform[0]
        max_y = raster_geotransform[3]
        max_x = min_x + raster_width * raster_geotransform[1] + raster_height * raster_geotransform[2]
        min_y = max_y + raster_width * raster_geotransform[4] + raster_height * raster_geotransform[5]
        extent = [min_x, max_x, min_y, max_y]

        plt.figure(figsize=(10, 10))
        plt.imshow(raster_data, cmap='gray', extent=extent, origin='upper')

        # Plot the new truncated line
        xs_world, ys_world = line.xy
        plt.plot(xs_world, ys_world, 'r-', linewidth=2, label='Truncated Line')
        plt.scatter(xs_world, ys_world, c='red')

        # == MODIFICATION ==
        # Always plot the intersection points in world coords here, too.
        intersection_xs = [pt.x for pt in intersection_points]
        intersection_ys = [pt.y for pt in intersection_points]
        plt.scatter(intersection_xs, intersection_ys, c='orange', marker='x', s=100, label='Intersection Points')

        plt.title('Truncated Linestring on Main Raster (World Coords)')
        plt.xlabel('World X')
        plt.ylabel('World Y')
        plt.legend()
        plt.show()

    ############################################################################
    # 5) BUILD THE FOOTPRINT POLYGON IN WORLD COORDINATES
    ############################################################################
    fxmin, fxmax, fymin, fymax = get_raster_extent(footprint_geotransform,
                                                   footprint_width,
                                                   footprint_height)
    footprint_polygon = Polygon([
        (fxmin, fymax),  # upper-left
        (fxmax, fymax),  # upper-right
        (fxmax, fymin),  # lower-right
        (fxmin, fymin),  # lower-left
        (fxmin, fymax)   # close polygon
    ])
    print("Footprint extent:", (fxmin, fxmax, fymin, fymax))

    ############################################################################
    # 6) DETERMINE START/END POINTS AND WHICH INTERSECTION GOES WHERE
    ############################################################################
    # == MODIFICATION ==
    # Now that we've removed the first/last coords, the "start_pt" is line.coords[0]
    # and the "end_pt" is line.coords[-1].
    start_pt = Point(line.coords[0])
    end_pt   = Point(line.coords[-1])

    if len(intersection_points) != 2:
        raise ValueError("Expected exactly two intersection points.")
    # Distances from new start
    d0_start = start_pt.distance(intersection_points[0])
    d1_start = start_pt.distance(intersection_points[1])
    # Distances from new end
    d0_end   = end_pt.distance(intersection_points[0])
    d1_end   = end_pt.distance(intersection_points[1])

    # The intersection that is closer to 'start_pt' is intersection_start
    # The other is intersection_end
    if d0_start < d1_start:
        intersection_start = intersection_points[0]
        intersection_end   = intersection_points[1]
    else:
        intersection_start = intersection_points[1]
        intersection_end   = intersection_points[0]

    print("New Start:", start_pt)
    print("New End:", end_pt)
    print("Intersection (start side):", intersection_start)
    print("Intersection (end side):", intersection_end)

    ############################################################################
    # 7) FUNCTION TO EXTEND A SEGMENT PAST THE INTERSECTION UNTIL FOOTPRINT EXIT
    ############################################################################
    def extend_past_intersection(p_inside, p_outside, polygon):
        """
        Extend a line that starts at p_inside and heads toward p_outside,
        continuing beyond p_outside in the same direction until it
        intersects the polygon boundary. Returns the final intersection point
        with the polygon.
        """
        dx = p_outside.x - p_inside.x
        dy = p_outside.y - p_inside.y

        if (abs(dx) < 1e-12 and abs(dy) < 1e-12):
            return p_outside  # No direction

        # Create a very long segment outward
        T = 1e6
        far_x = p_inside.x + T * dx
        far_y = p_inside.y + T * dy
        candidate_line = LineString([(p_inside.x, p_inside.y), (far_x, far_y)])

        boundary_intersection = candidate_line.intersection(polygon.exterior)

        if boundary_intersection.is_empty:
            # No intersection found
            return Point(far_x, far_y)
        else:
            # Could be multipoint or single point
            best_pt = None
            dist_needed = p_inside.distance(p_outside)

            if 'Multi' in boundary_intersection.geom_type:
                candidates = [g for g in boundary_intersection.geoms if g.geom_type == 'Point']
                # Sort by distance from p_inside
                candidates_sorted = sorted(candidates, key=lambda c: p_inside.distance(c))
                for c in candidates_sorted:
                    if p_inside.distance(c) >= dist_needed:
                        best_pt = c
                        break
                if best_pt is None and len(candidates_sorted) > 0:
                    best_pt = candidates_sorted[-1]
            elif boundary_intersection.geom_type == 'Point':
                best_pt = boundary_intersection
            else:
                # If it's a line or something else, pick centroid for simplicity
                best_pt = boundary_intersection.centroid

            return best_pt

    ############################################################################
    # 8) EXTEND EACH END FROM THE NEW START/END THROUGH THE CORRECT INTERSECTION
    ############################################################################
    extended_start_polygon_pt = extend_past_intersection(start_pt, intersection_start, footprint_polygon)
    extended_end_polygon_pt   = extend_past_intersection(end_pt,   intersection_end,   footprint_polygon)

    # Build final extended linestring in world coords
    extended_line_coords = [
        (extended_start_polygon_pt.x, extended_start_polygon_pt.y),
        (intersection_start.x, intersection_start.y),
    ] + list(line.coords) + [
        (intersection_end.x, intersection_end.y),
        (extended_end_polygon_pt.x, extended_end_polygon_pt.y)
    ]

    extended_line = LineString(extended_line_coords)

    ############################################################################
    # 9) OPTIONAL: PLOT THE EXTENDED LINE WITH THE FOOTPRINT POLYGON
    ############################################################################
    if show_plot:
        plt.figure(figsize=(10, 10))

        # Plot the footprint polygon
        fx, fy = footprint_polygon.exterior.xy
        plt.plot(fx, fy, color='black', linestyle='--', label='Footprint Polygon')

        # Plot the truncated line (before extension)
        ox, oy = line.xy
        plt.plot(ox, oy, 'g--', label='Truncated Line')

        # Plot the extended linestring
        ex, ey = extended_line.xy
        plt.plot(ex, ey, 'b-', linewidth=2, label='Extended Line')
        plt.scatter(ex, ey, c='blue')

        # Plot the intersection points (always visible)
        plt.scatter(
            [intersection_start.x, intersection_end.x],
            [intersection_start.y, intersection_end.y],
            c='red', marker='x', s=100, label='Intersection Points'
        )

        # == MODIFICATION ==
        # Scatter the removed first and last points from the original line
        first_point_removed = original_line.coords[0]
        last_point_removed = original_line.coords[-1]
        plt.scatter(
            [first_point_removed[0], last_point_removed[0]],
            [first_point_removed[1], last_point_removed[1]],
            c='purple', marker='o', s=100, label='Removed First/Last Points'
        )

        plt.legend()
        plt.title('Extended Linestring over Footprint Polygon')
        plt.xlabel('World X')
        plt.ylabel('World Y')
        plt.axis('equal')
        plt.show()

    ############################################################################
    # 10) CONVERT EXTENDED LINE BACK TO PIXEL COORDS (MAIN RASTER SPACE)
    ############################################################################
    extended_pixel_coords = []
    for (wx, wy) in extended_line.coords:
        px, py = world_to_pixel(raster_geotransform, wx, wy)
        extended_pixel_coords.append([px, py])

    extended_pixel_coords = np.array(extended_pixel_coords)

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

import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point
from shapely.affinity import translate
from rasterio.features import rasterize
from affine import Affine

def extend_line(line, extension_length=1):
    """
    Helper function to extend a line by extension_length (in pixel coordinates)
    at both ends.
    """
    # Start and end points
    start = Point(line.coords[0])
    end = Point(line.coords[-1])

    # Direction vectors (normalized) for each end
    start_dir = np.array(line.coords[0]) - np.array(line.coords[1])
    end_dir = np.array(line.coords[-1]) - np.array(line.coords[-2])

    # Handle zero-length segments gracefully
    if np.linalg.norm(start_dir) == 0:
        start_dir = np.array([0, 0])
    if np.linalg.norm(end_dir) == 0:
        end_dir = np.array([0, 0])

    start_dir = start_dir / (np.linalg.norm(start_dir) + 1e-12)
    end_dir = end_dir / (np.linalg.norm(end_dir) + 1e-12)

    # Extend start and end
    extended_start = start.coords[0] + start_dir * extension_length
    extended_end = end.coords[0] + end_dir * extension_length

    # Construct new line
    extended_line = LineString([extended_start, extended_end])
    return extended_line

def rasterize_line_ends(
        linestring_coords_xy,
        footprint_shape,
        footprint_geotransform,
        overlap_geotransform,
        start_pix,
        end_pix,
        show_plot=False
):
    """
    Rasterize line ends into a minimal bounding sub-raster. Returns:
      mask_small, new_geotransform

    Parameters
    ----------
    linestring_coords_xy : list of (x, y)
        Coordinates of the linestring in the overlap (pixel) frame.
    footprint_shape : (height, width)
        Shape of the full footprint frame. (Used for clamping the bounding box.)
    footprint_geotransform : tuple of length 6
        GDAL-style geotransform for the full footprint.
    overlap_geotransform : tuple of length 6
        GDAL-style geotransform for the overlap frame (used to convert from
        overlap pixels to world coords, then to footprint).
    start_pix : (row, col)
        Pixel coordinate of the start (in overlap frame).
    end_pix : (row, col)
        Pixel coordinate of the end (in overlap frame).
    show_plot : bool
        If True, shows debug plots.

    Returns
    -------
    mask_small : 2D numpy array (uint8)
        Rasterized line ends in a minimal bounding box.
    new_gt : tuple
        Updated geotransform corresponding to mask_small.
    """
    # Create affine transforms
    affine_overlap = Affine.from_gdal(*overlap_geotransform)
    affine_footprint = Affine.from_gdal(*footprint_geotransform)

    # Helper: convert (x, y) from overlap's pixel coords -> world coords -> footprint pixel coords
    def overlap_pix_to_footprint_pix(x, y):
        # from overlap-pixel coords to world
        wx, wy = affine_overlap * (x, y)
        # from world -> footprint-pixel coords
        fx, fy = ~affine_footprint * (wx, wy)
        return (fx, fy)

    # Convert entire linestring from overlap -> footprint
    linestring_coords_footprint = [overlap_pix_to_footprint_pix(x, y)
                                   for (x, y) in linestring_coords_xy]
    line = LineString(linestring_coords_footprint)

    # First and last segments in footprint
    first_segment = LineString([line.coords[0], line.coords[1]])
    last_segment = LineString([line.coords[-2], line.coords[-1]])

    # Convert start_pix and end_pix to footprint frame
    x_start_f, y_start_f = overlap_pix_to_footprint_pix(start_pix[1], start_pix[0])
    x_end_f, y_end_f     = overlap_pix_to_footprint_pix(end_pix[1],   end_pix[0])

    start_point = Point(x_start_f, y_start_f)
    end_point   = Point(x_end_f,   y_end_f)

    # Interpolate the projected start and end on their segments
    #projected_start = first_segment.interpolate(first_segment.project(start_point))
    #projected_end   = last_segment.interpolate(last_segment.project(end_point))

    # Define lines from projected points to the line edges
    line_start_to_edge = LineString([start_point, line.coords[0]])
    line_end_to_edge   = LineString([end_point,   line.coords[-1]])

    # Extend the lines by 1 pixel
    line_start_to_edge_ext = extend_line(line_start_to_edge, 1)
    line_end_to_edge_ext   = extend_line(line_end_to_edge,   1)

    # Convert extended lines to integer pixel coords (in footprint space)
    def line_to_pixel_coords(line_shp):
        """
        Round and convert float coords -> (x_int, y_int) for pixel indexing.
        Note: (x, y) here means (col, row).
        """
        return [
            (int(round(pt[0])), int(round(pt[1])))
            for pt in line_shp.coords
        ]

    line_start_pix_ext = line_to_pixel_coords(line_start_to_edge_ext)
    line_end_pix_ext   = line_to_pixel_coords(line_end_to_edge_ext)

    # Collect all pixel coords so we can find bounding box
    all_coords = line_start_pix_ext + line_end_pix_ext
    x_vals = [c[0] for c in all_coords]
    y_vals = [c[1] for c in all_coords]

    # If there's nothing to rasterize
    if not x_vals or not y_vals:
        raise TypeError("If there's nothing to rasterize")

    min_x, max_x = min(x_vals), max(x_vals)
    min_y, max_y = min(y_vals), max(y_vals)

    # Clamp to the original footprint boundaries so we don't go out of range
    # footprint_shape = (height, width)
    H, W = footprint_shape
    min_x = max(min_x, 0)
    max_x = min(max_x, W - 1)
    min_y = max(min_y, 0)
    max_y = min(max_y, H - 1)

    # Add a small margin (optional), e.g. 1 pixel on each side
    margin = 1
    min_x = max(min_x - margin, 0)
    min_y = max(min_y - margin, 0)
    max_x = min(max_x + margin, W - 1)
    max_y = min(max_y + margin, H - 1)

    # If the bounding box is invalid (no size), return empty
    if (max_x < min_x) or (max_y < min_y):
        empty_mask = np.zeros((1,1), dtype='uint8')
        return empty_mask, footprint_geotransform

    # Compute new width/height
    new_width  = max_x - min_x + 1
    new_height = max_y - min_y + 1

    # Shift geometries so that (min_x, min_y) goes to (0,0)
    # i.e. subtract min_x from all x, and min_y from all y
    def shift_coords(coords, shift_x, shift_y):
        return [(x - shift_x, y - shift_y) for (x, y) in coords]

    line_start_pix_ext_shifted = shift_coords(line_start_pix_ext, min_x, min_y)
    line_end_pix_ext_shifted   = shift_coords(line_end_pix_ext,   min_x, min_y)

    # Prepare geometries for rasterization
    geometries = [
        (LineString(line_start_pix_ext_shifted), 1),
        (LineString(line_end_pix_ext_shifted),   1)
    ]

    # Now define the new geotransform:
    # new_gt(0,0) should correspond to old_gt(min_x, min_y) in world space.
    # Using the Affine multiplication approach:
    old_aff = affine_footprint  # old footprint transform
    shift_aff = Affine.translation(min_x, min_y)
    # We want the new transform to map pixel (0,0) in the sub-raster
    # to the same world coordinate that (min_x, min_y) had in the old system:
    new_aff = old_aff * shift_aff

    # Rasterize into this smaller array
    out_shape_small = (new_height, new_width)
    mask_small = rasterize(
        geometries,
        out_shape=out_shape_small,
        transform=Affine.identity(),  # because we manually shifted coords to local (0,0)
        fill=0,
        all_touched=True,
        dtype='uint8'
    )

    # Optionally show a debug plot
    if show_plot:
        plt.figure(figsize=(10, 8))

        # Show the rasterized mask
        plt.imshow(mask_small, cmap='hot', origin='upper', alpha=0.8)

        # Plot the vector line for the start (shifted to sub-raster coordinates)
        line_start_vector = LineString(line_start_pix_ext_shifted)
        x_start, y_start = line_start_vector.xy
        plt.plot(x_start, y_start, color='blue', linewidth=3, alpha=0.3, label='Start Line')

        # Plot the vector line for the end (shifted to sub-raster coordinates)
        line_end_vector = LineString(line_end_pix_ext_shifted)
        x_end, y_end = line_end_vector.xy
        plt.plot(x_end, y_end, color='green', linewidth=3, alpha=0.3, label='End Line')

        # Add a title, legend, and colorbar for clarity
        plt.title("Rasterized Line Ends with Vector Overlay", fontsize=14)
        plt.legend(loc='upper right', fontsize=12)
        plt.colorbar(label='Raster Value', shrink=0.75)

        plt.show()

    # Convert the new Affine back to GDAL geotransform tuple if desired
    # new_aff = | a  b  x0 |
    #           | d  e  y0 |
    #           | 0  0   1 |
    #
    # GDAL-style geotransform: (x0, a, b, y0, d, e)
    new_gt = (
        new_aff.c,  # x0
        new_aff.a,  # a (pixel width in x)
        new_aff.b,  # b (rotation, usually 0)
        new_aff.f,  # y0
        new_aff.d,  # d (rotation, usually 0)
        new_aff.e   # e (pixel height in y, negative if north-up)
    )

    return mask_small, new_gt


def combine_masks_in_common_frame(
    mask1, gt1, mask2, gt2,
    fill_value=0
):
    """
    Merge two binary masks (uint8) in a new common bounding frame,
    *without* iterating over every pixel.

    Parameters
    ----------
    mask1 : 2D np.ndarray (uint8)
        The first mask to be merged.
    gt1 : tuple (GDAL-style geotransform)
        (x0, x_res, 0, y0, 0, y_res) for mask1.
    mask2 : 2D np.ndarray (uint8)
        The second mask to be merged.
    gt2 : tuple
        Same as above, for mask2.
    fill_value : int
        Value to fill in the new, larger array (0 or 255, typically).

    Returns
    -------
    merged_mask : 2D np.ndarray (uint8)
        The combined mask in the new bounding frame.
    merged_gt : tuple
        The new geotransform for merged_mask.
    """

    #--------------------------------------------------------------------------
    # 1. Parse geotransforms and shapes
    #--------------------------------------------------------------------------
    x0_1, xres_1, _, y0_1, _, yres_1 = gt1
    x0_2, xres_2, _, y0_2, _, yres_2 = gt2
    H1, W1 = mask1.shape
    H2, W2 = mask2.shape

    # Quick check: must have same resolution for a simple slice-based merge
    if not np.isclose(xres_1, xres_2, atol=1e-9) or not np.isclose(yres_1, yres_2, atol=1e-9):
        raise ValueError("Resolutions differ. Use reprojection if needed.")

    #--------------------------------------------------------------------------
    # 2. Compute bounding boxes in world coords
    #   For each raster:
    #     left   = x0
    #     right  = x0 + W * xres
    #     top    = y0
    #     bottom = y0 + H * yres
    #   Then form the union bounding box
    #--------------------------------------------------------------------------
    def raster_world_bounds(x0, y0, xres, yres, width, height):
        # Corners in world coords:
        left   = x0
        right  = x0 + width * xres
        top    = y0
        bottom = y0 + height * yres
        return min(left, right), max(left, right), min(top, bottom), max(top, bottom)

    left1, right1, top1, bot1 = raster_world_bounds(x0_1, y0_1, xres_1, yres_1, W1, H1)
    left2, right2, top2, bot2 = raster_world_bounds(x0_2, y0_2, xres_2, yres_2, W2, H2)

    overall_left  = min(left1,  left2)
    overall_right = max(right1, right2)
    overall_top   = min(top1,   top2)
    overall_bot   = max(bot1,   bot2)

    #--------------------------------------------------------------------------
    # 3. Define the new geotransform for the merged frame
    #    We'll keep xres_1,yres_1 for the output.
    #    For typical north-up data with negative yres_1:
    #      - The "top-left corner" in geotransform often has the maximum Y (overall_bot).
    #    For positive yres, it's the minimum Y (overall_top).
    #--------------------------------------------------------------------------
    dx = xres_1
    dy = yres_1

    if yres_1 < 0:
        # In a north-up dataset with negative yres, the top-left corner is the *max* Y
        y0_merged = overall_bot
    else:
        # If yres is positive, the top-left corner is the min Y
        y0_merged = overall_top

    x0_merged = overall_left

    #--------------------------------------------------------------------------
    # 4. Compute new width & height (round up).
    #--------------------------------------------------------------------------
    full_width_m  = overall_right - overall_left
    full_height_m = overall_bot   - overall_top
    new_width  = int(np.ceil(abs(full_width_m  / dx)))
    new_height = int(np.ceil(abs(full_height_m / dy)))

    # Construct the merged geotransform
    merged_gt = (x0_merged, dx, 0.0, y0_merged, 0.0, dy)

    #--------------------------------------------------------------------------
    # 5. Allocate output array
    #--------------------------------------------------------------------------
    merged_mask = np.full((new_height, new_width), fill_value, dtype=np.uint8)

    #--------------------------------------------------------------------------
    # 6. Helper to compute "top-left corner" of each old mask in the new array
    #    We'll use an affine transform for convenience.
    #--------------------------------------------------------------------------
    aff_1 = Affine.from_gdal(*gt1)
    aff_2 = Affine.from_gdal(*gt2)
    aff_m = Affine.from_gdal(*merged_gt)

    # The world coord of (col=0, row=0) in old mask is simply (x0, y0).
    # But we can be robust by actually applying the old affine to (0,0) and
    # then applying the *inverse* of the merged affine to find the new pixel coords.
    def compute_offset(old_affine, new_affine):
        # top-left corner in world coords
        x_world_0, y_world_0 = old_affine * (0, 0)
        # convert that to pixel coords in the new frame
        new_col_f, new_row_f = ~new_affine * (x_world_0, y_world_0)
        return int(np.floor(new_col_f)), int(np.floor(new_row_f))

    offset_col_1, offset_row_1 = compute_offset(aff_1, aff_m)
    offset_col_2, offset_row_2 = compute_offset(aff_2, aff_m)

    #--------------------------------------------------------------------------
    # 7. Define a function to "burn" old_mask into merged_mask via slicing
    #--------------------------------------------------------------------------
    def burn_mask(old_mask, offset_col, offset_row):
        H_old, W_old = old_mask.shape

        # Slices in the new array
        row_start = max(0, offset_row)
        row_end   = min(new_height, offset_row + H_old)
        col_start = max(0, offset_col)
        col_end   = min(new_width,  offset_col + W_old)

        # If there's no overlap, skip
        if (row_end <= row_start) or (col_end <= col_start):
            return

        # Slices in the old mask
        old_row_start = max(0, -offset_row)
        old_col_start = max(0, -offset_col)
        old_row_end   = old_row_start + (row_end - row_start)
        old_col_end   = old_col_start + (col_end - col_start)


        merged_mask[row_start:row_end, col_start:col_end] |= \
            old_mask[old_row_start:old_row_end, old_col_start:old_col_end]

    #--------------------------------------------------------------------------
    # 8. Burn both masks
    #--------------------------------------------------------------------------
    burn_mask(mask1, offset_col_1, offset_row_1)
    burn_mask(mask2, offset_col_2, offset_row_2)

    return merged_mask, merged_gt

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


def _check_and_flip(mask, corner, adjacent):
    """
    If the corner and its adjacent pixels are all 1, flip them to 0 in-place.
    """
    pixels_to_check = [corner] + adjacent
    if all(mask[r, c] == 1 for r, c in pixels_to_check):
        # Flip to zero
        for r, c in pixels_to_check:
            mask[r, c] = 0

def save_binary_mask_no_crs(mask, out_path):
    """
    Save a binary mask as a 1-bit-per-pixel TIFF with LZW compression.

    Parameters:
        mask (np.ndarray): Binary mask to save.
        out_path (str): Output file path (including .tiff extension).
    """
    # Convert the mask to uint8 if it's not already
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)

    # Ensure the mask only contains 0 and 1 values
    mask[mask != 0] = 1

    # Get the mask dimensions
    height, width = mask.shape

    # Create a GDAL driver for GeoTIFF
    driver = gdal.GetDriverByName("GTiff")

    # Create the dataset
    out_ds = driver.Create(out_path, width, height, 1, gdal.GDT_Byte, ["NBITS=1", "COMPRESS=LZW"])
    if out_ds is None:
        raise RuntimeError(f"Failed to create the output TIFF at {out_path}")

    # Write the mask to the dataset
    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(mask)

    # Set NoData value
    out_band.SetNoDataValue(0)

    # Flush and close the dataset
    out_band.FlushCache()
    out_ds.FlushCache()
    out_ds = None


def transform_edge_points(edge_points, original_geotransform, target_geotransform, target_shape):
    """
    Transform edge points from the original geotransform to the target geotransform.

    Parameters:
        edge_points (list of tuples): List of (row, col) points in the original geotransform.
        original_geotransform (tuple): Geotransform of the original mask.
        target_geotransform (tuple): Geotransform of the target mask.
        target_shape (tuple): Shape (rows, cols) of the target mask.

    Returns:
        transformed_points (list of tuples): List of transformed (row, col) points in the target geotransform.
    """
    affine_original = Affine.from_gdal(*original_geotransform)
    affine_target_inv = ~Affine.from_gdal(*target_geotransform)

    transformed_points = []
    for row, col in edge_points:
        geo_x, geo_y = affine_original * (col, row)  # Convert to geographic coordinates
        target_col, target_row = affine_target_inv * (geo_x, geo_y)  # Convert to target pixel coordinates
        target_row = np.clip(int(round(target_row)), 0, target_shape[0] - 1)  # Ensure in bounds
        target_col = np.clip(int(round(target_col)), 0, target_shape[1] - 1)  # Ensure in bounds
        transformed_points.append((target_row, target_col))

    return transformed_points

def cutline_to_mask(cut_shifted, unit_vector, input_related_save_base, show_plot=False):

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

        gc.collect()

        keep_mask_hi_res_cropped_exp =  expand_array_with_zeros(keep_mask_hi_res_cropped)
        edge_points = furthest_apart_points_distance_transform(cutline_hi_res_cropped)
        culine_hi_res_cropped_exp = expand_mask_in_vector_direction(cutline_hi_res_cropped,
                                                                    edge_points,
                                                                    unit_vector, show_plot=show_plot)

        #out_path = input_related_save_base + "pre_binary_fill_holes_mask_0.tiff"
        #save_binary_mask_no_crs(culine_hi_res_cropped_exp, out_path)

        keep_mask_comb = np.logical_or(keep_mask_hi_res_cropped_exp,
                                       culine_hi_res_cropped_exp)

        print('fill_holes...')
        if show_plot:

            print('Going to show: before and after flood fill stage expanded')
            filled_holes = binary_fill_holes(keep_mask_comb)
            fig, axes = plt.subplots(1, 2, figsize=(15, 5))

            # Plot the original mask
            axes[0].imshow(keep_mask_comb, interpolation='none', origin='upper')
            axes[0].set_title(f"Original Mask. Keep unit vector: {unit_vector}")
            # Add an arrow to the first plot
            axes[0].annotate(
                '',
                xy=(0.5 + unit_vector[0], 0.5 + unit_vector[1]),  # End of arrow, relative to axes
                xytext=(0.5, 0.5),  # Start of arrow, relative to axes
                arrowprops=dict(facecolor='red', arrowstyle='->'),
                fontsize=12,
                xycoords='axes fraction',  # Coordinates are relative to the axes
                textcoords='axes fraction'  # Start point coordinates are also relative to the axes
            )

            # Plot the filled mask
            axes[1].imshow(filled_holes, interpolation='none', origin='upper')
            axes[1].set_title("Filled Mask")

            plt.tight_layout()
            plt.show()
            keep_mask_filled_cropped = shrink_array(filled_holes)
        else:
            keep_mask_filled_cropped = shrink_array(binary_fill_holes(keep_mask_comb))

        #out_path = input_related_save_base + "pre_binary_fill_holes_mask.tiff"
        #save_binary_mask_no_crs(keep_mask_comb, out_path)

        del culine_hi_res_cropped_exp, keep_mask_hi_res_cropped_exp
        gc.collect()

        keep_mask_hi_res[min_row:max_row + 1, min_col:max_col + 1] = keep_mask_filled_cropped
        keep_mask = keep_mask_hi_res
    else:
        keep_mask = np.logical_or((labeled_array == keep_label), cut_bool).astype(np.uint8)

    assert keep_mask.shape == original_shape
    if np.all(keep_mask == 1):
        #out_path = input_related_save_base + "pre_binary_fill_holes_mask"
        #save_binary_mask_no_crs(keep_mask_comb, out_path)
        raise AssertionError(f'Problem with fill holes, the whole mask is "1"s. Bit-mask saved to \n{out_path}\n for debugging. ')
    assert not np.all(keep_mask == 0)
    return keep_mask



def binary_fill_holes_on_tiff(input_tiff_path, output_path, save_bit_mask_with_gdal):
    """
    Perform binary fill holes on a TIFF bit mask and save the result.

    Parameters:
        input_tiff_path (str): Path to the input TIFF file.
    """
    # Open the input TIFF
    dataset = gdal.Open(input_tiff_path, gdal.GA_ReadOnly)
    if dataset is None:
        raise FileNotFoundError(f"Unable to open input TIFF: {input_tiff_path}")

    # Read the raster data as a NumPy array
    band = dataset.GetRasterBand(1)
    mask = band.ReadAsArray()

    # Ensure the data is binary (0 and 1)
    mask = (mask > 0).astype(np.uint8)

    # Perform binary fill holes
    filled_mask = binary_fill_holes(mask).astype(np.uint8)

    save_bit_mask_with_gdal(filled_mask, output_path, dataset.GetGeoTransform(), dataset.GetProjection())

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


def shift_mask_frame_and_extend(current_mask, current_geotransform,
                                target_geotransform, target_mask_shape,
                                show_plot=False):
    """
    Shift a binary mask to a target geospatial frame and extend it to edges.

    Parameters:
        current_mask (np.ndarray): Input binary mask.
        current_geotransform (tuple): Geotransform of the input mask.
        target_geotransform (tuple): Geotransform of the target frame.
        target_mask_shape (tuple): Shape (rows, cols) of the target mask.
        show_plot (bool): Whether to plot the mask before and after.

    Returns:
        shifted_mask (np.ndarray): Shifted and extended binary mask.
        edge_points (list of tuples): Coordinates of two points touching the edges.
    """
    # Transform coordinates
    affine_current = Affine.from_gdal(*current_geotransform)
    affine_target_inv = ~Affine.from_gdal(*target_geotransform)

    rows, cols = np.where(current_mask > 0)
    geo_x, geo_y = affine_current * (cols, rows)
    target_cols, target_rows = affine_target_inv * (geo_x, geo_y)

    # Round and filter valid indices
    target_rows = np.round(target_rows).astype(int)
    target_cols = np.round(target_cols).astype(int)
    valid_mask = (
        (target_rows >= 0) & (target_rows < target_mask_shape[0]) &
        (target_cols >= 0) & (target_cols < target_mask_shape[1])
    )
    target_rows = target_rows[valid_mask]
    target_cols = target_cols[valid_mask]

    if len(target_rows) == 0:
        print("No overlap between current_mask and target extent. Skipping...")
        return None

    # Create the shifted mask
    shifted_mask = np.zeros(target_mask_shape, dtype=current_mask.dtype)
    shifted_mask[target_rows, target_cols] = 1

    # Extend the mask to edges
    shifted_mask, edge_points = extend_to_edges(shifted_mask, show_plot=show_plot)

    if show_plot:
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))
        axes[0].imshow(current_mask, cmap='gray', interpolation='none')
        axes[0].set_title("Input Mask")
        axes[1].imshow(shifted_mask, cmap='gray', interpolation='none')
        edge_y, edge_x = zip(*edge_points)
        axes[1].scatter(edge_x, edge_y, color='red', label='Edge Points')
        axes[1].legend()
        axes[1].set_title("Shifted and Extended Mask")
        plt.show()

    return shifted_mask

def furthest_apart_points_distance_transform(mask: np.ndarray):
    """
    Find two furthest-apart points in a sparse binary mask using a Convex Hull.
    This is efficient when fewer than ~1% of pixels are '1'.

    Parameters:
        mask (np.ndarray): 2D binary array (1s and 0s).

    Returns:
        (y1, x1), (y2, x2): The coordinates of the two furthest-apart points.
    """

    # Get (row, col) coordinates of all '1' pixels
    ys, xs = np.where(mask == 1)
    coords = np.column_stack((ys, xs))

    if coords.shape[0] < 2:
        raise ValueError("Mask must contain at least two '1' pixels to find a pair.")

    # Compute the convex hull of these points
    hull = ConvexHull(coords)

    # Extract hull vertices
    hull_points = coords[hull.vertices]

    # Compute pairwise distances between hull points
    # This is O(H^2), where H is the number of hull vertices (often much smaller than total points).
    dist_matrix = cdist(hull_points, hull_points, metric='euclidean')

    # Find the two points with the largest distance
    i, j = np.unravel_index(np.argmax(dist_matrix), dist_matrix.shape)
    point1 = tuple(hull_points[i])
    point2 = tuple(hull_points[j])

    return point1, point2

def expand_mask_in_vector_direction(mask: np.ndarray,
                                    edge_points: tuple[tuple[int, int], tuple[int, int]],
                                    unit_vector: tuple[float, float],
                                    show_plot: bool = False) -> np.ndarray:
    """
    Expand the mask by 1 pixel in all directions (output shape = (H+2, W+2)),
    then fill the boundary (the "new ring") in a single continuous arc from
    edge_points[0] to edge_points[1] with '1's in the direction indicated by
    unit_vector (CW or CCW around the boundary), and '0's in the opposite arc.

    Parameters:
        mask (np.ndarray): 2D binary array (shape H×W) of 0/1.
        edge_points: A tuple of two (row, col) points on the ORIGINAL mask's boundary,
                     both must be '1'.
        unit_vector: (vy, vx); a unit vector indicating which arc (CW vs. CCW)
                     around the boundary should be filled with '1's.
        show_plot: If True, plot the input and output masks for debugging.

    Returns:
        np.ndarray: The expanded mask (shape (H+2, W+2)) with exactly one boundary
                    arc set to 1, and the other arc set to 0.
    """
    arr = np.asarray(mask, dtype=np.uint8)
    H, W = arr.shape

    def find_nearest_1_along_boundary(r, c, max_search=100):
        # Allow for "nearly" on-boundary coordinates:
        # Top edge: allow r to be 0 or 1 (treat as top edge)
        if r in [0, 1]:
            effective_r = 0
            search_range = np.where(arr[effective_r, max(0, c - max_search):min(W, c + max_search)] == 1)[0]
            if search_range.size > 0:
                return (effective_r, search_range[0] + max(0, c - max_search))

        # Bottom edge: allow r to be H-2 or H-1 (treat as bottom edge)
        elif r in [H - 2, H - 1]:
            effective_r = H - 1
            search_range = np.where(arr[effective_r, max(0, c - max_search):min(W, c + max_search)] == 1)[0]
            if search_range.size > 0:
                return (effective_r, search_range[0] + max(0, c - max_search))

        # Left edge: allow c to be 0 or 1 (treat as left edge)
        elif c in [0, 1]:
            effective_c = 0
            search_range = np.where(arr[max(0, r - max_search):min(H, r + max_search), effective_c] == 1)[0]
            if search_range.size > 0:
                return (search_range[0] + max(0, r - max_search), effective_c)

        # Right edge: allow c to be W-2 or W-1 (treat as right edge)
        elif c in [W - 2, W - 1]:
            effective_c = W - 1
            search_range = np.where(arr[max(0, r - max_search):min(H, r + max_search), effective_c] == 1)[0]
            if search_range.size > 0:
                return (search_range[0] + max(0, r - max_search), effective_c)

        # If no '1' is found within the specified range, plot the target point before raising an error.
        if show_plot:
            plt.figure(figsize=(8, 8))
            plt.imshow(arr, cmap="gray", interpolation="none")
            plt.scatter([c], [r], color="red", s=100, label=f"Target: ({r}, {c})")
            plt.title(f"No '1' found within {max_search} pixels of ({r}, {c}).")
            plt.legend()
            plt.show()

        raise ValueError(f"No '1' found within {max_search} pixels of ({r}, {c}).")


    # Validate and correct edge_points
    corrected_points = []
    for (r, c) in edge_points:
        corrected_points.append(find_nearest_1_along_boundary(r, c))


    # Determine the shifted coordinates based on boundary edge
    def shift_edge_point(r, c):
        print(f'shift_edge_point {r=}, {c=}')
        if r == 0:  # Top edge
            return (0, c + 1)
        elif r == H - 1:  # Bottom edge
            return (H + 1, c + 1)
        elif c == 0:  # Left edge
            return (r + 1, 0)
        elif c == W - 1:  # Right edge
            return (r + 1, W + 1)
        else:
            print(f'{r=}, {c=}')
            # Plot the current mask with the problematic point highlighted
            if show_plot:
                plt.figure(figsize=(8, 8))
                plt.imshow(arr, cmap="gray", origin="upper", interpolation="none")
                plt.scatter([c], [r], color="red", s=100, label="Off-boundary Point")
                plt.title("Error: Point not on the Original Mask Boundary")
                plt.legend()
                plt.show()
            # Add more detailed feedback if the point is not on the boundary
            raise ValueError(
                f"Point ({r}, {c}) is not on the boundary of the original mask. "
                f"Valid boundaries are: r=0 (top), r=H-1 (bottom), c=0 (left), c=W-1 (right).")

    # Shift the corrected edge points
    p0 = shift_edge_point(*corrected_points[0])
    p1 = shift_edge_point(*corrected_points[1])

    # Plot the input mask if show_plot is True
    if show_plot:
        plt.figure(figsize=(8, 8))
        plt.imshow(arr, cmap="gray", origin="upper", interpolation="none")
        plt.scatter([p[1] for p in corrected_points], [p[0] for p in corrected_points],
                    color="red", label="Corrected Edge Points")
        plt.annotate(
            '',
            xy=(0.5 + unit_vector[0], 0.5 + unit_vector[1]),  # End of arrow, relative to axes
            xytext=(0.5, 0.5),  # Start of arrow, relative to axes
            arrowprops=dict(color='red', arrowstyle='->'),  # Set the arrow color to red
            fontsize=12,
            xycoords='axes fraction',  # Coordinates are relative to the axes
            textcoords='axes fraction'  # Start point coordinates are also relative to the axes
        )
        plt.title(f"Input Mask with Corrected Edge Points and Unit Vector {unit_vector}")
        plt.legend()
        plt.show()

    # Expand the mask
    out = np.zeros((H + 2, W + 2), dtype=np.uint8)
    out[1:-1, 1:-1] = arr

    # Check that p0, p1 are indeed on the boundary of 'out'
    # boundary of 'out' => r=0 or r=H+1 or c=0 or c=W+1
    def is_on_expanded_boundary(r, c):
        return (r == 0 or r == H + 1 or c == 0 or c == W + 1)

    if not is_on_expanded_boundary(*p0):
        raise ValueError(f"Shifted point p0={p0} not on expanded boundary.")
    if not is_on_expanded_boundary(*p1):
        raise ValueError(f"Shifted point p1={p1} not on expanded boundary.")

    # Convert to perimeter parameters
    t0 = boundary_param(*p0, H, W)
    t1 = boundary_param(*p1, H, W)

    # Compute the centroid of the two arcs
    cw_centroid = arc_centroid(t0, t1, H, W)
    ccw_centroid = arc_centroid(t1, t0, H, W)

    # We'll compare the dot product from the midpoint of p0 and p1
    # to these centroids, with the provided unit_vector.
    mid = np.array([(p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0])
    uv = np.array([-unit_vector[1], unit_vector[0]], dtype=float)

    vec_cw = cw_centroid - mid
    vec_ccw = ccw_centroid - mid

    dot_cw = vec_cw.dot(uv)
    dot_ccw = vec_ccw.dot(uv)

    # Decide which arc is "the 1 arc"
    if dot_cw > dot_ccw:
        arc_ones_t0, arc_ones_t1 = t0, t1
    else:
        arc_ones_t0, arc_ones_t1 = t1, t0

    # Set the entire boundary to 0, then fill only the chosen arc with 1
    fill_entire_boundary(out, 0)
    fill_arc(arc_ones_t0, arc_ones_t1, out, 1)

    if show_plot:
        # Plot the output mask
        plt.figure(figsize=(8, 8))
        plt.imshow(out, cmap="gray", origin="upper", interpolation="none")
        plt.scatter([p0[1], p1[1]], [p0[0], p1[0]], color="green", label="Shifted Points")
        plt.title("Output Mask with Filled Arc")
        plt.legend()
        plt.show()

    return out


def boundary_param(r: int, c: int, H: int, W: int) -> float:
    """
    Return the "distance along the rectangle boundary" from (0,0) in
    a clockwise direction to the boundary point (r, c), for a rectangle
    of shape (H+2, W+2).

    (0,0) => top-left corner
    (0, W+1) => top-right corner
    (H+1, W+1) => bottom-right
    (H+1, 0) => bottom-left

    The perimeter = 2*(H+2 + W+2) = 2*(H + W + 4).

    Edges in clockwise order:
      1) top edge:    y=0, x from 0 to W+1
      2) right edge:  x=W+1, y from 0 to H+1
      3) bottom edge: y=H+1, x from W+1 down to 0
      4) left edge:   x=0, y from H+1 down to 0
    """
    # Because r,c is guaranteed on boundary, exactly one of these conditions is true
    # We'll measure distance from (0,0) in a clockwise sense
    if r == 0:
        # top edge: param = c
        return float(c)
    elif c == W+1:
        # right edge: param starts at (W+1) at top-right corner, plus how far down we are
        return float((W+1) + r)
    elif r == H+1:
        # bottom edge: param starts at (W+1) + (H+1) at bottom-right corner
        # but we measure x from right to left
        return float((W+1) + (H+1) + (W+1 - c))
    elif c == 0:
        # left edge: param starts at (W+1)+(H+1)+(W+1) = 2*(W+1)+(H+1) at bottom-left corner
        # then we measure y from bottom to top
        return float((W+1)*2 + (H+1) + (H+1 - r))
    else:
        raise ValueError(f"Point (r={r}, c={c}) not on boundary for H={H}, W={W}.")


def arc_centroid(t0: float, t1: float, H: int, W: int) -> np.ndarray:
    """
    Compute the centroid (row, col) of the boundary arc from param t0 to param t1
    in a clockwise direction, *without enumerating every boundary pixel*.

    This is done by splitting the arc into at most 4 segments (one per edge).
    We find the line-segment portion on each edge, compute its length and centroid
    in closed form, and accumulate a weighted average.
    """
    perimeter = 2*((H+2) + (W+2))  # = 2*(H+W+4)
    # Normalize so 0 <= t0, t1 < perimeter
    # (already in range, but just in case we want mod)
    t0_mod = t0 % perimeter
    t1_mod = t1 % perimeter

    # If t1_mod >= t0_mod, the arc is [t0_mod, t1_mod].
    # If t1_mod < t0_mod, the arc wraps around the perimeter end -> 0.
    # We'll just unify the logic by a small helper that merges intervals.
    if t0_mod <= t1_mod:
        arc_length = t1_mod - t0_mod
        segments = _build_segments_for_arc(t0_mod, t1_mod, H, W)
    else:
        arc_length = (perimeter - t0_mod) + t1_mod
        segments = _build_segments_for_arc(t0_mod, perimeter, H, W)
        segments += _build_segments_for_arc(0, t1_mod, H, W)

    if arc_length == 0:
        # degenerate
        return param_to_point(t0, H, W)

    # Weighted sum for centroid
    total_len = 0.0
    accum = np.zeros(2, dtype=float)

    for seg in segments:
        length = seg['length']
        cent   = seg['centroid']
        accum += length * cent
        total_len += length

    if total_len < 1e-12:
        # degenerate arc
        return param_to_point(t0, H, W)
    else:
        return accum / total_len


def _build_segments_for_arc(tstart: float, tend: float, H: int, W: int):
    """
    Build a list of line-segment descriptors for the arc in [tstart, tend]
    in a rectangle boundary of shape (H+2, W+2). Each segment is a dict:
      {
        'length': float,
        'centroid': np.array([row_center, col_center]),
      }
    where 'centroid' is the midpoint of that line segment in continuous coordinates.
    We do at most 4 segments (since we can cross at most 3 corners in that range).
    """
    segments = []
    EPS = 1e-12
    perimeter = 2*(W+2 + H+2)

    # We'll do a small loop that will handle crossing up to corners.
    # The rectangle has corner parameters:
    corner_params = [
        0.0,               # top-left corner
        (W+1),             # top-right corner
        (W+1)+(H+1),       # bottom-right corner
        2*(W+1)+(H+1),     # bottom-left corner
        perimeter          # wraps back to top-left corner
    ]

    # start from t = tstart
    cur_t = tstart
    while cur_t < tend - EPS:
        # find which corner is next
        next_corner = None
        for cp in corner_params:
            if cp > cur_t + EPS:  # must be strictly greater
                next_corner = cp
                break
        if next_corner is None:
            # should not happen unless cur_t is near perimeter
            next_corner = perimeter

        seg_end = min(next_corner, tend)
        if seg_end < cur_t + EPS:
            break  # done

        # build a line segment from cur_t to seg_end
        seg_dict = _segment_info(cur_t, seg_end, H, W)
        segments.append(seg_dict)

        cur_t = seg_end
        if abs(cur_t - tend) < EPS:
            break

    return segments


def _segment_info(tA: float, tB: float, H: int, W: int):
    """
    Return {'length': L, 'centroid': (row, col)}
    for the boundary segment in [tA, tB] (clockwise param).
    """
    pA = param_to_point(tA, H, W)
    pB = param_to_point(tB, H, W)
    # The segment is a straight line between pA and pB
    # length = Euclidean distance
    v = pB - pA  # 2D
    L = np.hypot(v[0], v[1])
    cent = 0.5*(pA + pB)
    return {'length': L, 'centroid': cent}


def param_to_point(t: float, H: int, W: int) -> np.ndarray:
    """
    Inverse of boundary_param: given t in [0, perimeter), return (row, col)
    on the boundary of shape (H+2, W+2), in float coordinates.

    We do piecewise:
      Edge0 (top)    : param in [0,      W+1]
      Edge1 (right)  : param in [W+1,    W+1 + (H+1)]
      Edge2 (bottom) : param in [W+1+H+1, W+1+H+1 + (W+1)]
      Edge3 (left)   : ...
    """
    perimeter = 2*(W+2 + H+2)
    tmod = t % perimeter  # just in case

    # corners in param-space
    top_right     = (W+1)
    bottom_right  = (W+1) + (H+1)
    bottom_left   = (W+1)*2 + (H+1)

    if tmod <= top_right:
        # top edge: row=0, col goes from 0..W+1
        return np.array([0.0, tmod])
    elif tmod <= bottom_right:
        # right edge
        dist_down = tmod - (W+1)
        return np.array([dist_down, W+1])
    elif tmod <= bottom_left:
        # bottom edge
        dist_along = tmod - bottom_right  # goes from 0..(W+1)
        col = (W+1) - dist_along
        return np.array([H+1, col])
    else:
        # left edge
        dist_along = tmod - bottom_left  # goes from 0..(H+1)
        row = (H+1) - dist_along
        return np.array([row, 0.0])


def fill_entire_boundary(out: np.ndarray, val: int):
    """
    Fill the entire outer boundary of 'out' with the given value, in slice-chunks.
    'out' is shape (H+2, W+2).
    """
    h, w = out.shape
    # top row
    out[0, :] = val
    # bottom row
    out[h-1, :] = val
    # left col
    out[:, 0] = val
    # right col
    out[:, w-1] = val


def fill_arc(t0: float, t1: float, out: np.ndarray, val: int):
    """
    Fill the boundary from param t0 to param t1 in a clockwise direction
    with 'val', using chunk-based slicing (not pixel-by-pixel).
    """
    # We'll do exactly what _build_segments_for_arc does to break
    # it into line segments, but for each segment, do a direct slice assignment.
    H = out.shape[0] - 2
    W = out.shape[1] - 2
    segments = _build_segments_for_arc(t0, t1, H, W)

    for seg in segments:
        # Each seg is from param tA to tB
        # We'll get the integer bounding of that portion on one edge
        # We can fill it in one or two slices (depending on orientation).
        # But because each segment is guaranteed to lie on a single edge
        # or corner crossing is handled by splitting into segments,
        # we can just fill the portion on that edge.
        # We'll get tA, tB from the 'centroid' method again.
        pass

    # We actually need the param sub-intervals to do the slice fill. Let's replicate the logic:
    perimeter = 2*(W+2 + H+2)
    # Normalize
    t0_mod = t0 % perimeter
    t1_mod = t1 % perimeter
    def next_corner_after(tc):
        corner_params = [
            0.0,
            (W+1),
            (W+1)+(H+1),
            2*(W+1)+(H+1),
            perimeter
        ]
        for cp in corner_params:
            if cp > tc:
                return cp
        return perimeter

    # We'll do a loop from tA to min(tB, next_corner), fill. Then move tA to that corner, etc.
    # We define a small helper to fill a sub-segment on a single edge:
    def fill_subsegment(tA, tB):
        # param -> integer points
        # The edge is determined by param_to_point(floor).
        # Actually, let's do it systematically by seeing which edge tA is on.
        pA = param_to_point(tA, H, W)
        pB = param_to_point(tB, H, W)
        # Because tA..tB is guaranteed not to cross a corner (by construction),
        # pA and pB lie on the same edge. We'll fill from pA to pB in integer slices.

        # We'll figure out which edge by checking the integer parts of pA:
        # e.g. if pA[0] ~ 0 => top edge; if pA[1] ~ W+1 => right edge, etc.
        # Then we do a slicing approach.
        (rA, cA) = pA
        (rB, cB) = pB

        # We can round to int in a consistent manner for the boundary:
        # Because the boundary is exactly at integer coordinates (except corners),
        # rA,cA might already be integer, but let's do:
        rA_i = int(round(rA))
        cA_i = int(round(cA))
        rB_i = int(round(rB))
        cB_i = int(round(cB))

        # The edge can be top, right, bottom, or left
        if rA_i == 0 and rB_i == 0:
            # top edge
            col_start = min(cA_i, cB_i)
            col_end   = max(cA_i, cB_i)
            out[0, col_start:col_end+1] = val
        elif rA_i == H+1 and rB_i == H+1:
            # bottom edge
            col_start = min(cA_i, cB_i)
            col_end   = max(cA_i, cB_i)
            out[H+1, col_start:col_end+1] = val
        elif cA_i == W+1 and cB_i == W+1:
            # right edge
            row_start = min(rA_i, rB_i)
            row_end   = max(rA_i, rB_i)
            out[row_start:row_end+1, W+1] = val
        elif cA_i == 0 and cB_i == 0:
            # left edge
            row_start = min(rA_i, rB_i)
            row_end   = max(rA_i, rB_i)
            out[row_start:row_end+1, 0] = val
        else:
            # If it's a corner to corner sub-segment, we can handle that
            # with a single pixel assignment or a diagonal?
            # Actually, on a purely rectangular boundary, corner->corner
            # won't happen except if tB - tA = 0 or a corner is shared.
            # But let's be safe:
            # We'll handle the corner as a single coordinate
            out[rA_i, cA_i] = val
            out[rB_i, cB_i] = val

    # A small routine to build sub-arcs in [tA, tB] if tB >= tA, otherwise wrap
    def fill_arc_interval(tA, tB):
        EPS = 1e-9
        # step from tA..tB corner by corner
        current = tA
        while current + EPS < tB:
            nc = next_corner_after(current + EPS)
            seg_end = min(nc, tB)
            if seg_end <= current + EPS:
                break
            fill_subsegment(current, seg_end)
            current = seg_end

    # Now fill t0->t1 or possibly wrap
    if t0_mod <= t1_mod:
        fill_arc_interval(t0_mod, t1_mod)
    else:
        fill_arc_interval(t0_mod, perimeter)
        fill_arc_interval(0, t1_mod)


def extend_to_edges(mask: np.ndarray, show_plot=False):
    """
    Extend a binary mask to the edges based on its furthest-apart points.

    Parameters:
        mask (np.ndarray): Input binary mask.
        show_plot (bool): Whether to plot the mask.

    Returns:
        output (np.ndarray): Mask extended to edges.
        edge_points (list of tuples): Coordinates of the two points touching the edges.
    """
    # Ensure mask is uint8
    mask = mask.astype(np.uint8)
    h, w = mask.shape

    # Find two furthest-apart pixels
    point1, point2 = furthest_apart_points_distance_transform(mask)

    # Helper function to find the closest edge for a given pixel
    def find_closest_edge(y, x, height, width):
        distances = {
            'top': y,
            'bottom': height - 1 - y,
            'left': x,
            'right': width - 1 - x
        }
        edge_name = min(distances, key=distances.get)
        return edge_name, distances[edge_name]

    # Prepare an output copy and list to store edge points
    output = mask.copy()
    edge_points = []

    # Helper to extend to the edge
    def connect_to_edge(out, y, x, edge):
        if edge == 'top':
            out[:y + 1, x] = 1
            return 0, x
        elif edge == 'bottom':
            out[y:, x] = 1
            return h - 1, x
        elif edge == 'left':
            out[y, :x + 1] = 1
            return y, 0
        elif edge == 'right':
            out[y, x:] = 1
            return y, w - 1

    # Extend each furthest point to its closest edge
    for pt in (point1, point2):
        y, x = pt
        edge, _ = find_closest_edge(y, x, h, w)
        edge_point = connect_to_edge(output, y, x, edge)
        edge_points.append(edge_point)

    if show_plot:
        plt.figure(figsize=(10, 10))
        plt.title("Extended Mask with Highlighted Edge Points")
        plt.imshow(output, cmap='gray', interpolation='none')
        edge_y, edge_x = zip(*edge_points)
        plt.scatter(edge_x, edge_y, color='red', s=50, label='Edge Points')
        plt.legend()
        plt.show()

    return output, edge_points



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
    #print(cutline_to_mask(cut_shifted, unit_vector))

    input = [
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 1, 0],
        [0, 0, 1, 1, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0]
    ]
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