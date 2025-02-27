'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings

import os
import re
import numpy as np
from pathlib import Path

from qgis.core import QgsProject, QgsLayerTreeGroup, QgsVectorLayer, QgsPointCloudLayer

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def darker_color(rgb, factor=0.8):
    return tuple(max(min(int(c * factor), 255), 0) for c in rgb)

def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb

# Global available colors and a counter for cycling through them
available_colors = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#7f7f7f",  # gray
    "#bcbd22",  # olive
    "#17becf"   # cyan
]
color_counter = 0

# Global dictionary to store base name to color mapping.
las_base_colors = {}

# --- Improved QML Template Generator ---
def create_qml_for_las(las_file, color_hex):
    # Compute a darker variant for the final ramp item.
    r, g, b = hex_to_rgb(color_hex)
    dr, dg, db = darker_color((r, g, b), factor=0.8)
    r_norm = f"{r / 255:.8f}"
    g_norm = f"{g / 255:.8f}"
    b_norm = f"{b / 255:.8f}"
    dr_norm = f"{dr / 255:.8f}"
    dg_norm = f"{dg / 255:.8f}"
    db_norm = f"{db / 255:.8f}"

    color1_str = f"{r},{g},{b},255,rgb:{r_norm},{g_norm},{b_norm},1"
    color2_str = f"{dr},{dg},{db},255,rgb:{dr_norm},{dg_norm},{db_norm},1"
    hex_color = color_hex.lower()
    hex_darker = rgb_to_hex((dr, dg, db)).lower()

    # Use the base name of the LAS file as the layer id.
    layer_id = os.path.splitext(os.path.basename(las_file))[0]

    qml_template = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.40.2-Bratislava" autoRefreshMode="Disabled" styleCategories="AllStyleCategories" autoRefreshTime="0" minScale="100000000" hasScaleBasedVisibilityFlag="0" maxScale="0" sync3DRendererTo2DRenderer="1">
  <renderer-3d type="pointcloud" layer="{layer_id}" max-screen-error="3" point-budget="5000000" show-bounding-boxes="0">
    <symbol type="color-ramp" color-ramp-shader-min="0" vertical-filter-threshold="10" horizontal-filter-threshold="10" vertical-triangle-filter="0" color-ramp-shader-max="168" horizontal-triangle-filter="0" point-size="3" render-as-triangles="0" rendering-parameter="Intensity">
      <colorrampshader clip="0" maximumValue="168" labelPrecision="4" classificationMode="1" colorRampType="INTERPOLATED" minimumValue="0">
        <colorramp type="gradient" name="[source]">
          <Option type="Map">
            <Option type="QString" value="{color1_str}" name="color1"/>
            <Option type="QString" value="{color2_str}" name="color2"/>
            <Option type="QString" value="ccw" name="direction"/>
            <Option type="QString" value="1" name="discrete"/>
            <Option type="QString" value="gradient" name="rampType"/>
            <Option type="QString" value="rgb" name="spec"/>
          </Option>
        </colorramp>
        <item value="0" color="{hex_color}" alpha="255" label="0.0000"/>
        <item value="30.894192" color="{hex_color}" alpha="255" label="30.8942"/>
        <item value="65.423064" color="{hex_color}" alpha="255" label="65.4231"/>
        <item value="102.778872" color="{hex_color}" alpha="255" label="102.7789"/>
        <item value="132.057744" color="{hex_color}" alpha="255" label="132.0577"/>
        <item value="168" color="{hex_darker}" alpha="255" label="168.0000"/>
        <rampLegendSettings minimumLabel="" direction="0" orientation="2" prefix="" useContinuousLegend="1" suffix="" maximumLabel="">
          <numericFormat id="basic">
            <Option type="Map">
              <Option type="invalid" name="decimal_separator"/>
              <Option type="int" value="6" name="decimals"/>
              <Option type="int" value="0" name="rounding_type"/>
              <Option type="bool" value="false" name="show_plus"/>
              <Option type="bool" value="true" name="show_thousand_separator"/>
              <Option type="bool" value="false" name="show_trailing_zeros"/>
              <Option type="invalid" name="thousand_separator"/>
            </Option>
          </numericFormat>
        </rampLegendSettings>
      </colorrampshader>
    </symbol>
  </renderer-3d>
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>1</Searchable>
    <Private>0</Private>
  </flags>
  <elevation zoffset="0" point_size="0.6" max_screen_error_unit="MM" respect_layer_colors="1" zscale="1" point_color="{color1_str}" max_screen_error="0.3" point_size_unit="MM" point_symbol="Square" opacity_by_distance="0">
    <data-defined-properties>
      <Option type="Map">
        <Option type="QString" value="" name="name"/>
        <Option name="properties"/>
        <Option type="QString" value="collection" name="type"/>
      </Option>
    </data-defined-properties>
  </elevation>
  <renderer renderAsTriangles="0" type="ramp" pointSize="1" pointSizeMapUnitScale="3x:0,0,0,0,0,0" drawOrder2d="0" min="0" horizontalTriangleFilterUnit="MM" attribute="Intensity" pointSizeUnit="MM" horizontalTriangleFilterThreshold="5" max="168" pointSymbol="0" maximumScreenErrorUnit="MM" horizontalTriangleFilter="0" maximumScreenError="0.3">
    <colorrampshader clip="0" maximumValue="168" labelPrecision="4" classificationMode="1" colorRampType="INTERPOLATED" minimumValue="0">
      <colorramp type="gradient" name="[source]">
        <Option type="Map">
          <Option type="QString" value="{color1_str}" name="color1"/>
          <Option type="QString" value="{color2_str}" name="color2"/>
          <Option type="QString" value="ccw" name="direction"/>
          <Option type="QString" value="1" name="discrete"/>
          <Option type="QString" value="gradient" name="rampType"/>
          <Option type="QString" value="rgb" name="spec"/>
        </Option>
      </colorramp>
      <item value="0" color="{hex_color}" alpha="255" label="0.0000"/>
      <item value="30.894192" color="{hex_color}" alpha="255" label="30.8942"/>
      <item value="65.423064" color="{hex_color}" alpha="255" label="65.4231"/>
      <item value="102.778872" color="{hex_color}" alpha="255" label="102.7789"/>
      <item value="132.057744" color="{hex_color}" alpha="255" label="132.0577"/>
      <item value="168" color="{hex_darker}" alpha="255" label="168.0000"/>
      <rampLegendSettings minimumLabel="" direction="0" orientation="2" prefix="" useContinuousLegend="1" suffix="" maximumLabel="">
        <numericFormat id="basic">
          <Option type="Map">
            <Option type="invalid" name="decimal_separator"/>
            <Option type="int" value="6" name="decimals"/>
            <Option type="int" value="0" name="rounding_type"/>
            <Option type="bool" value="false" name="show_plus"/>
            <Option type="bool" value="true" name="show_thousand_separator"/>
            <Option type="bool" value="false" name="show_trailing_zeros"/>
            <Option type="invalid" name="thousand_separator"/>
          </Option>
        </numericFormat>
      </rampLegendSettings>
    </colorrampshader>
  </renderer>
  <customproperties>
    <Option/>
  </customproperties>
  <blendMode>0</blendMode>
  <layerOpacity>1</layerOpacity>
</qgis>
"""
    return qml_template

def main(settings_path):
    settings_dict = plugin_load_settings.run(settings_path)

    input_folder = settings_dict['📂 Input folder']
    dont_load_files_smaller_than_MB = float(settings_dict.get('Do not Load files less than X MB', "0"))
    apply_colors = settings_dict.get("Apply colors", False)
    apply_same_color_to_same_name_las = settings_dict["Apply same colors to las's with same names"]
    collapse_groups = settings_dict['Completely']
    settings_dict = None  # don't use settings_dict from here on

    if not apply_colors:
        apply_same_color_to_same_name_las = False

    insert_at_bottom_instead_of_top = False
    get_group_name_from_parent_dir = False

    process_folder(input_folder,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                   insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                   collapse_groups=collapse_groups,
                   dont_load_files_smaller_than_MB=dont_load_files_smaller_than_MB,
                   apply_colors=apply_colors,
                   apply_same_color_to_same_name_las=apply_same_color_to_same_name_las)

# --- New function to load a LAS (or LAZ) file with file size check and optional QML styling ---
def load_las_as_layer(las_file, layer_name, group, min_size_mb, apply_colors, apply_same_color_to_same_name_las):
    # Check the file size in MB before proceeding.
    file_size_bytes = os.path.getsize(las_file)
    file_size_mb = file_size_bytes / (1024 * 1024)
    if file_size_mb < min_size_mb:
        print(f"Skipping {las_file}: file size {file_size_mb:.2f} MB is less than threshold {min_size_mb} MB.")
        return False

    # If apply_colors is enabled, generate a QML sidecar file next to the LAS.
    if apply_colors:
        global color_counter, las_base_colors
        directory, filename = os.path.split(las_file)
        base_name = os.path.splitext(filename)[0]
        if apply_same_color_to_same_name_las:
            if base_name in las_base_colors:
                current_color = las_base_colors[base_name]
            else:
                current_color = available_colors[color_counter % len(available_colors)]
                las_base_colors[base_name] = current_color
                color_counter += 1
        else:
            current_color = available_colors[color_counter % len(available_colors)]
            color_counter += 1

        qml_content = create_qml_for_las(las_file, current_color)
        qml_path = os.path.join(directory, base_name + ".qml")
        try:
            with open(qml_path, "w", encoding="utf-8") as f:
                f.write(qml_content)
            print(f"Created QML sidecar for {las_file}:\n  {qml_path}")
        except Exception as e:
            print(f"Error writing QML file for {las_file}: {e}")

    # Load the LAS file as a point cloud layer using PDAL.
    pointcloud_layer = QgsPointCloudLayer(uri=las_file, baseName=layer_name, providerLib="pdal")
    if pointcloud_layer.isValid():
        QgsProject.instance().addMapLayer(pointcloud_layer, False)
        group.addLayer(pointcloud_layer)
        print("Point cloud layer loaded successfully!")
        return True
    else:
        try:
            error_msg = pointcloud_layer.error()
            print("Error loading point cloud layer:", error_msg)
        except Exception:
            print("Failed to load point cloud layer, but no detailed error was returned.")
        return False

def alphanum_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

# --- Recursive function to process folders and subfolders ---
def process_folder(path,
                   parent_group=None,
                   depth=0,
                   get_group_name_from_parent_dir=False,
                   insert_at_bottom_instead_of_top=False,
                   collapse_groups=False,
                   dont_load_files_smaller_than_MB=0,
                   apply_colors=False,
                   apply_same_color_to_same_name_las=False):
    counter = 0   # Count of LAS/LAZ files loaded
    folder_counter = 0  # Count of subfolders processed
    root = QgsProject.instance().layerTreeRoot() if parent_group is None else parent_group
    folder_name = os.path.basename(path)

    if get_group_name_from_parent_dir:
        group = QgsLayerTreeGroup(os.path.basename(os.path.dirname(path)))
    else:
        group = QgsLayerTreeGroup(folder_name)

    if insert_at_bottom_instead_of_top:
        root.insertChildNode(-1, group)
    else:
        root.insertChildNode(0, group)

    indent = '↴ ' * depth
    items = os.listdir(path)
    items.sort(key=alphanum_key)

    for item in items:
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            folder_counter += 1
            process_folder(full_path,
                           group,
                           depth + 1,
                           get_group_name_from_parent_dir=get_group_name_from_parent_dir,
                           insert_at_bottom_instead_of_top=insert_at_bottom_instead_of_top,
                           collapse_groups=collapse_groups,
                           dont_load_files_smaller_than_MB=dont_load_files_smaller_than_MB,
                           apply_colors=apply_colors,
                           apply_same_color_to_same_name_las=apply_same_color_to_same_name_las)
        else:
            layer_name = os.path.splitext(item)[0]
            if item.lower().endswith(('.las', '.laz')) and not item.lower().endswith(".copc.laz"):
                counter += 1
                load_las_as_layer(full_path, layer_name, group, dont_load_files_smaller_than_MB, apply_colors, apply_same_color_to_same_name_las)

    if counter == 0 and folder_counter == 0:
        parent_group.removeChildNode(group)
    else:
        print(f"{indent}{folder_name} -> {counter} files, {folder_counter} folders")

    if depth == 0:
        check_and_remove_empty_groups(root)
        if collapse_groups:
            collapse_group_and_children(root)
        else:
            collapse_group_and_children_if_contains_layers_only(root)

def check_and_remove_empty_groups(group):
    child_nodes = group.children()
    empty_groups = []
    for node in child_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            check_and_remove_empty_groups(node)
            if not node.children():
                empty_groups.append(node)
    for empty_group in empty_groups:
        group.removeChildNode(empty_group)

def collapse_group_and_children(group):
    group.setExpanded(False)
    child_nodes = group.children()
    for node in child_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            collapse_group_and_children(node)
            node.setExpanded(False)

def collapse_group_and_children_if_contains_layers_only(group):
    child_nodes = group.children()
    only_contains_layers = True
    for node in child_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            only_contains_layers = False
            collapse_group_and_children_if_contains_layers_only(node)
    if only_contains_layers:
        group.setExpanded(False)
