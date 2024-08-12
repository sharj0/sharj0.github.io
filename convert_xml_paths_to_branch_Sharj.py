import os
from pathlib import Path
from lxml import etree

"""CHANGE THIS STRING FOR BRANCH NAME (DO NOT PUT ANY SLASHES)"""
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

    for plugin in root.findall("pyqgis_plugin"):

        old_name = plugin.get("name")

        if old_name.startswith(".ROSOR"):
            new_name = old_name.replace(".ROSOR", ".DEV " + branch_name_string, 1)
            plugin.set("name", new_name)

        old_plugin_zip_path = plugin.find("download_url").text
        old_plugin_icon_path = plugin.find("icon").text

        latter_plugin_path = Path(*Path(old_plugin_zip_path).parts[-2:]).as_posix()
        latter_icon_path = Path(*Path(old_plugin_icon_path).parts[-3:]).as_posix()

        new_plugin_zip_path = target_branch_dir + "/" + latter_plugin_path
        new_plugin_icon_path = target_branch_dir + "/" + latter_icon_path

        plugin.find("download_url").text = new_plugin_zip_path
        plugin.find("icon").text = new_plugin_icon_path


    tree.write(xml_file_path, pretty_print=True, xml_declaration=False, encoding="UTF-8")


if __name__ == "__main__":
    convert_xml_paths_to_branch()