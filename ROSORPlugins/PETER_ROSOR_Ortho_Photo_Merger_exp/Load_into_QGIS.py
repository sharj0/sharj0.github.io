import os

def load_mask_into_qgis(mask_path):
    """
    Attempts to load the specified mask (raster file) into QGIS if running in a QGIS environment.

    Parameters:
    mask_path (str): The file path of the mask raster to be loaded.

    Returns:
    None
    """
    try:
        from qgis.core import QgsProject, QgsRasterLayer
        from qgis.utils import iface
        if iface:  # Check if in QGIS Desktop environment
            layer_name = os.path.basename(mask_path)
            raster_layer = QgsRasterLayer(mask_path, layer_name)
            if raster_layer.isValid():
                QgsProject.instance().addMapLayer(raster_layer)
                print(f"Loaded {layer_name} into QGIS.")
            else:
                print(f"Failed to load {layer_name} into QGIS.")
    except ImportError:
        print("Not running within QGIS Desktop; skipping layer loading.")
