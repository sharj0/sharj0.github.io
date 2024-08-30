from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsWkbTypes
from .Global_Singleton import Global_Singleton

# Function to load a KML file as a layer and add it to the group
def load_kml_as_layer(kml_file, layer_name, group):
    uri = kml_file
    layer = QgsVectorLayer(uri, layer_name, "ogr")
    if not layer.isValid():
        print(f"Failed to load {layer_name}")
        return False

    global_singleton = Global_Singleton()
    global_singleton.import_dict[kml_file] = layer

    QgsProject.instance().addMapLayer(layer, False)
    group.addLayer(layer)
    return True