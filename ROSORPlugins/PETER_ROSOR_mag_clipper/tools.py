import os.path

import pandas as pd
import numpy as np
from osgeo import osr

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt5 import QtWidgets

from qgis.core import QgsVectorLayer, QgsProject, QgsWkbTypes
from qgis.core import QgsExpression, QgsProperty, QgsSymbolLayer
from qgis.core import QgsRuleBasedRenderer, QgsSymbol, QgsSimpleMarkerSymbolLayer, QgsLayerTreeLayer
from qgis.utils import iface
from PyQt5.QtGui import QColor
from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem, QgsProject, QgsCoordinateTransform, QgsApplication

def mag_arrow_parse_to_df(file_path, epsg_target):
    col_names = ['Counter',
                 'Date',
                 'Time',
                 'Latitude',
                 'Longitude',
                 'Mag',
                 'MagValid',
                 'CompassX',
                 'CompassY',
                 'CompassZ',
                 'GyroscopeX',
                 'GyroscopeY',
                 'GyroscopeZ',
                 'AccelerometerX',
                 'AccelerometerY',
                 'AccelerometerZ',
                 'ImuTemperature',
                 'Track',
                 'LocationSource',
                 'Hdop',
                 'FixQuality',
                 'SatellitesUsed',
                 'Altitude',
                 'HeightOverEllipsoid',
                 'SpeedOverGround',
                 'MagneticVariation',
                 'VariationDirection',
                 'ModeIndicator',
                 'GgaSentence',
                 'RmcSentence',
                 'EventCode',
                 'EventInfo',
                 'EventDataLength',
                 'EventData',
                 'uk1',
                 'uk2',
                 'uk3',
                 'uk4',
                 'uk5',
                 'uk6',
                 'uk7',
                 'uk8',
                 'uk9',
                 'uk10',
                 'uk11',
                 'uk12',
                 'uk13',
                 'uk14',
                 'uk15',
                 'uk16',
                 'uk17',
                 'uk18',
                 'uk19',
                 'uk20',
                 'uk21',
                 'uk22',
                 'uk23',
                 'uk24',
                 'uk25',
                 'uk26',
                 'uk27',
                 'uk28',
                 'uk29',
                 'uk30',]

    df = pd.read_csv(file_path,
                     names=col_names,
                     header=None,
                     skiprows=[0,1],
                     low_memory=False)
    df = df.rename(columns={"Mag": "Mag_TMI_nT", "MagValid": "Mag_Lock"})
    # Concatenating date and time fields to form a datetime string, then converting to datetime object
    datetime_str = df['Date'] + ' ' + df['Time']

    # Your custom parsing function
    def parse_datetime(datetime_str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S.%f"):
            try:
                return pd.to_datetime(datetime_str, format=fmt)
            except ValueError:
                continue
        # Raise an error if none of the formats work
        raise ValueError(f"Unknown format for datetime: {datetime_str}")

    UTC_time_stamps = parse_datetime(datetime_str)
    df.insert(1, 'UTC_time_stamps', [time_date.time() for time_date in UTC_time_stamps])
    elapsed_time = (UTC_time_stamps - UTC_time_stamps.iloc[0]).dt.total_seconds() / 60
    df.insert(2, 'elapsed_time_minutes', elapsed_time)

    # Define the source and target spatial references
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)  # WGS84

    target = osr.SpatialReference()
    target.ImportFromEPSG(int(epsg_target))

    # Create a coordinate transformation
    transform = osr.CoordinateTransformation(source, target)

    # Extract latitude and longitude and convert them to NumPy arrays
    lats, lons = df.Latitude.values, df.Longitude.values

    coords = np.vstack([lats, lons, np.zeros_like(lats)]).T  # Correct order: lat, lon, z

    # Apply the transformation and split the result
    utm_coords = np.array([transform.TransformPoint(*coord)[:2] for coord in coords])

    # Split the transformed coordinates
    utmes, utmns = utm_coords[:, 0], utm_coords[:, 1]

    if str(epsg_target)[:3][-1] == '6':
        hemis = 'N'
    if str(epsg_target)[:3][-1] == '7':
        hemis = 'S'

    utm_target = str(epsg_target)[3:]

    df.insert(4, 'UTME', utmes)
    df.insert(5, 'UTMN', utmns)
    df.insert(6, 'UTM_zone', utm_target)
    df.insert(7, 'UTM_letter', hemis)
    pd.set_option('display.max_columns', None)
    return df

def is_qgis_desktop_running():
    if QgsApplication.instance().platform() == 'desktop':
        return True
    else:
        return False

def expand_true_ranges(arr, expansion_count):
    expanded = np.copy(arr)
    for _ in range(expansion_count):
        expanded_left = np.roll(expanded, 1)  # Shift True values one position to the left
        expanded_right = np.roll(expanded, -1)  # Shift True values one position to the right
        expanded = np.logical_or(expanded, np.logical_or(expanded_left, expanded_right))
    return expanded

def calculate_4th_difference(arr):
    # Efficiently calculate the 4th difference using NumPy
    diff = np.pad(arr, (2, 2), 'constant', constant_values=(0, 0))
    return diff[4:] - 4 * diff[3:-1] + 6 * diff[2:-2] - 4 * diff[1:-3] + diff[:-4]

def calculate_smoothed_z_scores(arr, window_size=20):
    # Ensure window_size is odd for symmetric padding
    if window_size % 2 == 0:
        window_size += 1

    # Calculate rolling mean and standard deviation with valid boundary handling
    pad_width = window_size // 2
    rolling_mean = np.convolve(arr, np.ones(window_size) / window_size, mode='valid')
    rolling_std = np.sqrt(np.convolve(np.square(arr), np.ones(window_size) / window_size, mode='valid') - np.square(rolling_mean))

    # Pad the start and end of the statistics arrays to match the original array length
    extended_mean = np.pad(rolling_mean, (pad_width, pad_width), mode='edge')
    extended_std = np.pad(rolling_std, (pad_width, pad_width), mode='edge')

    # Calculate Z-scores for the entire array (using extended arrays for consistency)
    z_scores = np.abs((arr - extended_mean) / extended_std)
    # Smooth the Z-scores using a rolling average
    smoothed_z_scores = np.convolve(z_scores, np.ones(window_size) / window_size, mode='same')
    return smoothed_z_scores

# Function to calculate the range noise
def calculate_range_noise(arr, num_points, z_score_smoothing_factor):
    pad_width = num_points // 2
    padded_arr = np.pad(arr, pad_width, mode='reflect')
    noise_range = np.zeros(len(arr))
    for i in range(len(arr)):
        window = padded_arr[i:i+num_points]
        noise_range[i] = window.max() - window.min()

    smoothed_z_scores = calculate_smoothed_z_scores(arr, num_points * z_score_smoothing_factor)
    noise_range = smoothed_z_scores * noise_range
    return noise_range

class CustomNavigationToolbar(NavigationToolbar):
    def __init__(self, canvas, parent, coordinates=True):
        super().__init__(canvas, parent, coordinates)
        self._actions_disabled = False

        # Remove 'configure subplots', 'save the figure', and 'edit axes' actions
        actions_to_remove = ['Subplots', 'Save', 'Customize']
        actions = self.findChildren(QtWidgets.QAction)
        for action in actions:
            for action_text in actions_to_remove:
                if action_text in action.text():
                    self.removeAction(action)
                    break  # Break the inner loop, continue with the next action

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

def load_and_transform_vector_lines(vector_path, epsg_target):
    # Load the vector layer
    layer = QgsVectorLayer(vector_path, "line_layer", "ogr")

    # Check if layer is valid
    if not layer.isValid():
        print("Layer failed to load!")
        return []

    # Define the source and target spatial references
    source = osr.SpatialReference()
    if vector_path.endswith(".kml"):
        epsg_code = 4326
    else:
        epsg_code = int(layer.crs().authid().split(":")[-1])
    source.ImportFromEPSG(epsg_code)
    target = osr.SpatialReference()
    target.ImportFromEPSG(int(epsg_target))  # Target UTM zone
    transform = osr.CoordinateTransformation(source, target)

    # Extract and transform line geometries from the layer
    transformed_line_geometries = []
    grid_line_names = []
    for feature in layer.getFeatures():
        geom = feature.geometry()
        # Skip empty geometries or non-line geometries
        if geom.isEmpty() or geom.type() != QgsWkbTypes.LineGeometry:
            continue  # Skip this feature and move to the next one
        grid_fltln = feature['Grid_Fltln'] if 'Grid_Fltln' in feature.fields().names() else ''
        grid_line_names.append(grid_fltln)
        # Assuming the geometry is a line or multiline, transform each point
        if geom.wkbType() in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            # Extract points from the line geometry for transformation
            points = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for line in points:
                transformed_line = []
                for x, y in line:
                    if epsg_code == 4326:
                        x, y = y, x
                    # Convert each point
                    point = transform.TransformPoint(x, y)[:2]  # Note: TransformPoint takes lon, lat order
                    transformed_line.append(point)
                # Add the transformed line as a single list of tuples
                transformed_line_geometries.append(transformed_line)

    return transformed_line_geometries, grid_line_names

def zoom_in_on_layer(layer):
    layer_crs = layer.crs()  # Get the layer's CRS (e.g., WGS 84)
    canvas_crs = QgsProject.instance().crs()  # Get the map canvas CRS (e.g., UTM)

    # Create a coordinate transformation based on the layer's CRS and the canvas CRS
    transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())

    # Get the layer's extent in its own coordinate system
    layer_extent = layer.extent()

    # Transform the layer's extent to the canvas coordinate system
    transformed_extent = transform.transformBoundingBox(layer_extent)



    if is_qgis_desktop_running():
        # Now, zoom the canvas to the transformed extent
        canvas = iface.mapCanvas()  # Get the map canvas
        canvas.setExtent(transformed_extent)  # Set the canvas extent to the transformed extent
        canvas.refresh()  # Refresh the map canvas


def load_csv_data_to_qgis(output_csv_path, add_to_group_name:str, set_symbols_and_colors = True):
    uri = f"file:///{output_csv_path}?delimiter=,&xField=Longitude&yField=Latitude&crs=epsg:4326"
    layer_name = os.path.basename(output_csv_path)
    layer = QgsVectorLayer(uri, layer_name, "delimitedtext")

    if not layer.isValid():
        print(f"Failed to load {layer_name}")
        return False

    if not add_to_group_name == '':
        # Check if the group exists, if not create it
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(add_to_group_name)
        if not group:  # If the group does not exist
            group = root.addGroup(add_to_group_name)  # Create the group
            # Move the group to the top of the layer stack
            root.insertChildNode(0, group.clone())
            root.removeChildNode(group)
            group = root.findGroup(add_to_group_name)
        QgsProject.instance().addMapLayer(layer, False)  # Add the layer to the project but not to the layer tree
        # Create a new layer node
        layer_node = QgsLayerTreeLayer(layer)
        # Insert the new layer node at the top of the group
        group.insertChildNode(0, layer_node)  # Insert at the top
    else:
        QgsProject.instance().addMapLayer(layer)
    zoom_in_on_layer(layer)

    if set_symbols_and_colors:
        # Set the data-defined properties for symbol layer
        # This example assumes a single-symbol point layer; adjust as necessary for your layer type and structure
        symbol = layer.renderer().symbol()
        symbol_layer = symbol.symbolLayer(0)  # Get the first (or only) symbol layer

        # Correctly set color based on attributes, scaling RGB values up to 0-255 range
        symbol_layer.setDataDefinedProperty(QgsSymbolLayer.PropertyFillColor,
                                            QgsProperty.fromExpression('color_rgb("r"*255, "g"*255, "b"*255)'))

        # Set the size of the symbols based on an attribute, adjust "size_attribute" with your actual field name
        # and adjust scaling as needed
        symbol_layer.setDataDefinedProperty(QgsSymbolLayer.PropertySize,
                                            QgsProperty.fromExpression('if("size" > 10, "size" / 15, "size / 10")'))

        # Remove the outline by setting its color to transparent
        symbol_layer.setStrokeColor(QColor(0, 0, 0, 0))  # RGBA where A (alpha) is 0 for transparency

        # Apply the changes to the layer
        layer.triggerRepaint()


        if is_qgis_desktop_running():
            iface.layerTreeView().refreshLayerSymbology(layer.id())
