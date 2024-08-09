
import os
import xml.etree.ElementTree as ET
import pathlib
from pathlib import Path
import shutil

def copy_folder_to_another_folder(plugin_path,target_folder=os.path.join(Path(__file__).parent.parent,"ROSORPlugins")):
    if os.path.basename(plugin_path).startswith("PETER_ROSOR"):
        shutil.copytree(plugin_path, target_folder)
    else:
        for root, dirs, files in os.walk(plugin_path):
            for dir in dirs:
                if dir.startswith("PETER_ROSOR"):
                    plugin_path = os.path.join(root,dir)
                    shutil.copytree(plugin_path, target_folder)


if __name__ == "__main__":
    chosen_plugin_name = "PETER_ROSOR_mag_clipper"
    chosen_plugin_path = os.path.join(os.path.dirname(__file__), chosen_plugin_name)


