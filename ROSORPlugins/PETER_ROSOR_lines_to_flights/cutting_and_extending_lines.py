from qgis.core import QgsVectorLayer
from qgis import processing
import os
from .plugin_tools import show_error
from .loading_functions import reproject_vector_layer

# optional plotting
import matplotlib.pyplot as plt

def _unique_vector_path(path: str) -> str:
    """
    If `path` already exists, append _v2, _v3, … before the extension
    until a non‐existent filename is found.
    """
    base, ext = os.path.splitext(path)
    version = 1
    unique = path
    while os.path.exists(unique):
        version += 1
        unique = f"{base}_v{version}{ext}"
    return unique

def cut_and_extend_lines(cutter_lines_file_path: str,
                         flight_lines_path: str,
                         extend_distance_meters: float,
                         global_crs_target: dict,
                         show_plot: bool = False) -> tuple:
    """
    Splits `flight_lines_path` wherever it intersects `cutter_lines_file_path`, then
    extends every resulting segment by `extend_distance_meters` at both ends.
    Ensures split/extended shapefile names are unique by appending _v2, _v3, …
    """
    orig_path = flight_lines_path

    # 1) Load cutter lines
    cutter_layer = QgsVectorLayer(cutter_lines_file_path, "cutter_lines", "ogr")
    if not cutter_layer.isValid():
        show_error(f"Cutter file not valid: {cutter_lines_file_path}")

    # 2) Reproject cutter if needed
    current_epsg = int(cutter_layer.crs().authid().split(':')[1])
    target_epsg = global_crs_target['target_crs_epsg_int']
    if current_epsg != target_epsg:
        repro_path = os.path.splitext(cutter_lines_file_path)[0] + \
                     f"_UTM{global_crs_target['target_utm_num_int']}.shp"
        repro_path = _unique_vector_path(repro_path)
        reproject_vector_layer(cutter_layer, repro_path, target_epsg)
        cutter_lines_file_path = repro_path
        cutter_layer = QgsVectorLayer(cutter_lines_file_path, "cutter_lines_utm", "ogr")
        if not cutter_layer.isValid():
            show_error(f"Failed reprojection of cutter lines: {repro_path}")

    # 3) Split flight lines by cutter lines
    desired_split = os.path.splitext(flight_lines_path)[0] + "_split.shp"
    split_path = _unique_vector_path(desired_split)
    processing.run("native:splitwithlines", {
        'INPUT':  QgsVectorLayer(flight_lines_path, "flight_lines", "ogr"),
        'LINES':  cutter_layer,
        'OUTPUT': split_path
    })
    copy_output_style_qml(split_path)

    # 4) Extend every segment at both ends
    desired_ext = os.path.splitext(split_path)[0] + "_extended.shp"
    extended_path = _unique_vector_path(desired_ext)
    res = processing.run("native:extendlines", {
        'INPUT':          QgsVectorLayer(split_path, "flight_lines_split", "ogr"),
        'START_DISTANCE': extend_distance_meters,
        'END_DISTANCE':   extend_distance_meters,
        'OUTPUT':         extended_path
    })
    copy_output_style_qml(extended_path)

    new_layer = QgsVectorLayer(res['OUTPUT'], "flight_lines_extended", "ogr")
    if not new_layer.isValid():
        show_error(f"Extend failed: {res['OUTPUT']}")

    # 5) Optional overlay plot of original vs extended
    if show_plot:
        def extract_coords(layer):
            coords = []
            for feat in layer.getFeatures():
                geom = feat.geometry()
                parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
                for part in parts:
                    xs, ys = zip(*[(pt.x(), pt.y()) for pt in part])
                    coords.append((xs, ys))
            return coords

        orig_coords = extract_coords(QgsVectorLayer(orig_path, "orig_lines", "ogr"))
        ext_coords  = extract_coords(new_layer)

        plt.figure()
        for xs, ys in orig_coords:
            plt.plot(xs, ys, '--', label='original' if 'original' not in plt.gca().get_legend_handles_labels()[1] else "")
        for xs, ys in ext_coords:
            plt.plot(xs, ys, '-',  label='extended' if 'extended' not in plt.gca().get_legend_handles_labels()[1] else "")
        plt.legend()
        plt.title('Original vs Extended Lines')
        plt.xlabel('X'); plt.ylabel('Y')
        plt.show()

    return res['OUTPUT'], new_layer

def copy_output_style_qml(target_shapefile_path: str):
    """
    Copies output_style.qml from the plugin directory to the same location as the target shapefile,
    renaming it to match the shapefile (with .qml extension).
    """
    try:
        import shutil
        plugin_dir = os.path.dirname(__file__)
        template_qml_path = os.path.join(plugin_dir, "output_style.qml")
        target_qml_path = os.path.splitext(target_shapefile_path)[0] + ".qml"
        shutil.copyfile(template_qml_path, target_qml_path)
    except Exception as e:
        print(f"Failed to copy output_style.qml for {target_shapefile_path}: {e}")
        