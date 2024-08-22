from qgis.core import QgsProject, \
    QgsVectorLayer


# Function to load a KML file as a layer and add it to the group
def load_kml_as_layer(kml_file, layer_name, group):
    uri = kml_file
    layer = QgsVectorLayer(uri, layer_name, "ogr")
    if not layer.isValid():
        print(f"Failed to load {layer_name}")
        return False
    QgsProject.instance().addMapLayer(layer, False)
    group.addLayer(layer)
    return True