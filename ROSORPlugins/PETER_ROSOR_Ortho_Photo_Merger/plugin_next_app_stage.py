'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''
import time
import winsound
import os
from osgeo import gdal
import xml.etree.ElementTree as ET
from qgis.core import QgsApplication

from . import plugin_load_settings
from .plugin_tools import show_error

from .merge_two_tiffs import merge_two_tiffs
from .save_geotiffs import save_vrt_as_tiff

##############################################################################
# 1. Data structures
##############################################################################
class Node:
    """
    Simple tree node with a value and a list of children.
    `value` can be the folder name override or a tiff file path, depending on context.
    """
    def __init__(self, value):
        self.value = value
        self.children = []

    def __repr__(self):
        return f"Node(value={self.value!r}, children={len(self.children)})"


##############################################################################
# 2. Parsing and building the tree from a Markdown file
##############################################################################
def parse_merge_order_tree(md_file_path):
    """
    Reads a markdown file and constructs a tree of Node objects.
    Ensures:
      - Exactly one top-level node.
      - Each non-leaf node has exactly two children (or we raise an error).
    Returns the root Node.
    """

    with open(md_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # A list of top-level nodes (we expect exactly one).
    root_nodes = []

    # Stack used to track the current path of nodes while parsing indentation
    stack = []

    # Helper function to remove quotes or extra spaces from a line
    def sanitize_line(line):
        # Remove wrapping quotes (both single or double), strip whitespace
        line = line.strip()
        line = line.lstrip('-').strip()  # remove leading '-' plus whitespace
        # Remove leading/trailing quotes if present
        if (line.startswith('"') and line.endswith('"')) or \
           (line.startswith("'") and line.endswith("'")):
            line = line[1:-1]
        return line.strip()

    for raw_line in lines:
        # Ignore empty lines or lines that do not start with a dash
        if not raw_line.strip() or not raw_line.lstrip().startswith('-'):
            continue

        # Count indentation (number of leading spaces).
        # If your markdown uses 2 spaces or 3 spaces for nesting,
        # adapt the divisor. Here we assume 4 spaces = 1 indent level.
        leading_spaces = len(raw_line) - len(raw_line.lstrip(' '))
        indent_level = leading_spaces // 4

        # Clean up the item string (remove '-' bullet and quotes)
        item_str = sanitize_line(raw_line)

        # Create a new node
        new_node = Node(item_str)

        if not stack:
            # No nodes on stack => this is a top-level node
            root_nodes.append(new_node)
            stack.append((new_node, indent_level))
        else:
            # There's a current stack. We must find the correct parent based on indentation.
            # Pop from stack until top of stack has a lower indentation level
            while stack and stack[-1][1] >= indent_level:
                stack.pop()

            # If nothing on stack, it's another top-level node
            if not stack:
                root_nodes.append(new_node)
                stack.append((new_node, indent_level))
            else:
                # Parent is the top item in the stack
                parent_node, _ = stack[-1]
                parent_node.children.append(new_node)
                stack.append((new_node, indent_level))

    # Check that we have exactly one top-level node
    if len(root_nodes) != 1:
        show_error("Provided merge order tree file has an error.\n"
                   "There must be exactly one top-level bullet item.")
        assert False
    # The single root node
    root = root_nodes[0]

    # Recursively verify each node that has children has exactly two children
    def check_children(node):
        if node.children:
            if len(node.children) != 2:
                show_error(
                    f"Provided merge order tree file has an error.\n"
                    f"'{node.value}' has {len(node.children)} child(ren). It needs exactly two."
                )
                assert False
            for c in node.children:
                check_children(c)

    check_children(root)
    return root


def gather_leaf_paths(node):
    """
    Recursively collect file paths from all leaves of the given Node.
    """
    if not node.children:
        # Leaf node => node.value should be a file path
        return [node.value]
    else:
        paths = []
        for child in node.children:
            paths.extend(gather_leaf_paths(child))
        return paths


def check_leaf_tiffs(leaf_paths):
    """
    Validates the input TIFFs:
    1) Ensures all files have valid extensions.
    2) Verifies that all files have the same CRS.
    """
    # 1) Check file extensions
    for path in leaf_paths:
        ext = os.path.splitext(path)[1].lower()
        if ext not in ['.tif', '.tiff', '.vrt']:
            err_text = f'The low level input {path} has an invalid file type: {ext}'
            show_error(err_text)
            raise ValueError(err_text)

    # 2) Check CRS consistency
    # Open the first file to get the reference CRS
    first_path = leaf_paths[0]
    first_dataset = gdal.Open(first_path)
    if first_dataset is None:
        err_text = f'Failed to open file: {first_path}'
        show_error(err_text)
        raise ValueError(err_text)

    first_crs = first_dataset.GetProjection()
    if not first_crs:
        err_text = f'File {first_path} does not have a valid CRS.'
        show_error(err_text)
        raise ValueError(err_text)

    # Check all other files against the reference CRS
    for path in leaf_paths[1:]:
        dataset = gdal.Open(path)
        if dataset is None:
            err_text = f'Failed to open file: {path}'
            show_error(err_text)
            raise ValueError(err_text)

        current_crs = dataset.GetProjection()
        if not current_crs:
            err_text = f'File {path} does not have a valid CRS.'
            show_error(err_text)
            raise ValueError(err_text)

        if current_crs != first_crs:
            err_text = f'All files must have the same CRS. {path} has a different CRS.'
            show_error(err_text)
            raise ValueError(err_text)

    print("All leaf TIFFs have consistent CRS and valid extensions.")


##############################################################################
# 3. Merging logic
##############################################################################

def build_merge_operations(node, target_GSD_cm, prefer_centre_factor, root):
    """
    Recursively walk the tree bottom-up, merging each pair of children.
    - If a node has no children, it is a leaf. Return its .value (a file path).
    - If a node has children, the .value is interpreted as the 'output_folder_name_override'
      for the merge step. We'll:
          1) build the merges for the left child => left_result
          2) build the merges for the right child => right_result
          3) call merge_two_tiffs(...) with those results
    Returns the path to the merged tiff for this node.
    """
    print(f'merge op {node}')

    # If leaf => presumably it's a file path. Just return it.
    if not node.children:
        return node.value

    # Otherwise, the current node's value is the folder override for this merge
    folder_override = node.value

    # We expect exactly two children (already validated)
    left_child, right_child = node.children[0], node.children[1]

    Ortho_photo_1_file_path = build_merge_operations(left_child, target_GSD_cm, prefer_centre_factor, root)
    Ortho_photo_2_file_path = build_merge_operations(right_child, target_GSD_cm, prefer_centre_factor, root)


    merged_result = merge_two_tiffs(
        Ortho_photo_1_file_path=Ortho_photo_1_file_path,
        Ortho_photo_2_file_path=Ortho_photo_2_file_path,
        target_GSD_cm=target_GSD_cm,
        prefer_centre_factor=prefer_centre_factor,
        output_folder_name_override=folder_override)

    # --  Now we update this node to become a "leaf" with the merged file path  --
    node.children = []
    node.value = merged_result

    # --  Export the updated tree to a new .md  --
    # We'll place the new .md in the same folder as `merged_result`.
    md_dir = os.path.dirname(merged_result)
    if not os.path.isdir(md_dir):
        md_dir = os.path.dirname(os.path.abspath(merged_result))

    # Build the .md filename from the folder_override plus "_merge_tree_remaining.md"
    md_filename = f"{folder_override}_merge_tree_remaining.md"
    md_path = os.path.join(md_dir, md_filename)

    # Export the *entire* tree (the top-level root) to that .md
    export_tree_to_md(root, md_path)
    print(f" -> Wrote updated merge tree to {md_path}")
    return merged_result

def export_tree_to_md(node, md_file_path):
    """
    Recursively serialize the current Node tree to a markdown file.
    """

    def recurse_md(nd, indent=0):
        # We'll use 4 spaces per indent level
        line_prefix = '    ' * indent + '-'
        if nd.children:
            # Non-leaf => output the node value directly
            lines.append(f"{line_prefix}{nd.value}")
            for child in nd.children:
                recurse_md(child, indent + 1)
        else:
            # Leaf => treat nd.value as a file path and quote it
            # to match the typical .md format
            lines.append(f"{line_prefix}\"{nd.value}\"")

    lines = []
    recurse_md(node, indent=0)

    with open(md_file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

def parse_qlr_to_md(qlr_path, output_md_path):
    """
    Parses a QLR file to generate an MD file with the required tree structure.

    Parameters:
    qlr_path (str): Path to the QLR file.
    output_md_path (str): Path to save the generated MD file.
    """
    if not os.path.exists(qlr_path):
        raise FileNotFoundError(f"QLR file not found: {qlr_path}")

    # Parse the QLR file
    tree = ET.parse(qlr_path)
    root = tree.getroot()

    # Function to extract and validate the folder path
    def resolve_source_path(source):
        if source.startswith("./"):
            # Resolve relative path based on QLR file location
            qlr_folder = os.path.dirname(os.path.abspath(qlr_path))
            resolved_path = os.path.join(qlr_folder, source[2:])
        else:
            resolved_path = source  # Assume it's an absolute path

        # Validate the resolved path
        if not os.path.exists(os.path.dirname(resolved_path)):
            raise FileNotFoundError(f"Could not resolve valid folder for source: {source}")

        return resolved_path.replace("\\", "/")  # Normalize for consistency

    # Recursively process the tree
    def process_node(node, indent_level=0):
        md_lines = []
        if node.tag == "layer-tree-group":
            name = node.attrib.get("name", "").strip()
            if name:  # Only include groups with names
                md_lines.append(f"{'    ' * indent_level}-{name}")
        elif node.tag == "layer-tree-layer":
            source = node.attrib.get("source", "Unknown Source").strip()
            try:
                resolved_source = resolve_source_path(source)
                md_lines.append(f"{'    ' * indent_level}-\"{resolved_source}\"")
            except FileNotFoundError as e:
                md_lines.append(f"{'    ' * indent_level}-\"Error: {e}\"")  # Log the error in the MD
        # Process children
        for child in node:
            md_lines.extend(process_node(child, indent_level + 1))
        return md_lines

    # Start processing from the first meaningful group
    markdown_lines = []
    top_groups = root.findall(".//layer-tree-group")
    if top_groups:
        # Skip the very top group if it has no meaningful name
        if not top_groups[0].attrib.get("name", "").strip():
            for child in top_groups[0]:
                markdown_lines.extend(process_node(child, 0))
        else:
            markdown_lines = process_node(top_groups[0])

    # Write the output to an MD file
    with open(output_md_path, "w") as md_file:
        md_file.write("\n".join(markdown_lines))

def main(settings_path):
    #to run in powershell
    # & "C:/Program Files/QGIS 3.38.0/bin/python-qgis.bat" "C:\Users\pyoty\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\debug_PETER_ROSOR_Ortho_Photo_Merger.py"

    settings_dict = plugin_load_settings.run(settings_path)

    target_GSD_cm = settings_dict['Target GSD cm']  # meters
    prefer_centre_factor = settings_dict['Prefer centre factor']
    beep_when_finished = settings_dict['Beep when finished']
    beep_if_error = settings_dict['Beep if error']
    do_output_tiff = ['Output .tiff when finished instead']
    merge_order_tree_file_path = settings_dict['Merge order tree file']

    base, ext = os.path.splitext(merge_order_tree_file_path)

    # 1) Parse the markdown => build the tree
    if ext.lower() == '.qlr':
        new_markdown_file = base+'.md'
        parse_qlr_to_md(merge_order_tree_file_path, new_markdown_file)
        root = parse_merge_order_tree(new_markdown_file)
    elif ext.lower() == '.md':
        root = parse_merge_order_tree(merge_order_tree_file_path)
    else:
        show_error('Input merge_order_tree_file not recodnised must be either ".md" or ".qlr"')

    # 2) Collect and check all bottom-level leaf tiffs
    leaf_paths = gather_leaf_paths(root)
    check_leaf_tiffs(leaf_paths)

    try:
        final_merged_vrt = build_merge_operations(
            node=root,
            target_GSD_cm=target_GSD_cm,
            prefer_centre_factor=prefer_centre_factor,
            root=root,
        )
        # 3) final_merged_vrt path now holds the path to the final merged result
        if do_output_tiff:
            final_merged_file = os.path.splitext(final_merged_vrt)[0]+'.tiff'
            save_vrt_as_tiff(final_merged_vrt, final_merged_file, compress=False)
        else:
            final_merged_file = final_merged_vrt

        print(f"/##########################################################################################\\")
        print("Final merged file =>", final_merged_file)
        print(f"\\##########################################################################################/")
    except Exception as e:
        # Play the beep in case of an error
        if beep_if_error:
            while True:
                winsound.Beep(200, 1000)
                time.sleep(2)
            # Optionally, you can re-raise the exception or log it for debugging
        raise RuntimeError(f"Error merging tiffs: {e}")

    if beep_when_finished:
        print('Playing completion notification noises...')
        while True:
            counter += 1
            winsound.Beep(200, 1000)
            sound_path = os.path.join(os.path.dirname(__file__),"The_geotiffs_have_been_merged.wav")
            winsound.PlaySound(sound_path, winsound.SND_FILENAME)
            if QgsApplication.instance().platform() == 'desktop':
                break
            time.sleep(2)
