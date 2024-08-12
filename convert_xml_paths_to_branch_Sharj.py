import os
from pathlib import Path
from lxml import etree

"""CHANGE THIS STRING FOR BRANCH NAME"""
branch_name_string = "sharj_import_csv_import_kml_split"



URI_HEAD_STRING = "https://raw.githubusercontent.com"
REPO_USER_STRING = "sharj0"
REPO_NAME_STRING = "sharj0.github.io"

branch_URI_directory = "/".join([URI_HEAD_STRING, REPO_USER_STRING, REPO_NAME_STRING, branch_name_string])

def convert_xml_paths_to_branch(xml_file_path=(Path(__file__).parent / "plugins_leak.xml").as_posix(), target_branch_dir=branch_URI_directory):

    if not os.path.exists(xml_file_path):
        print("given plugin xml doesn't exist in the parent directory")
        return None

    tree = etree.parse(xml_file_path)
    root = tree.getroot()

    for plugin in root.finall("pyqgis_plugin"):

        plugin_zip_path =


if __name__ == "__main__":
    print((Path(__file__).parent / "plugins_leak.xml").as_posix())