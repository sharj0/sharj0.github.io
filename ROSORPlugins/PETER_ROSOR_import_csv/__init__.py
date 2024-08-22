import os
import shutil

def classFactory(iface):
    from .plugin_qgis_module import plugin_class
    return plugin_class(iface)
