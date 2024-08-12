import os
from pathlib import Path
from lxml import etree

from convert_xml_paths_to_branch_Sharj import branch_name_string

MAIN_REPO_URI = "https://sharj0.github.io"

def revert_xml_paths_to_main(xml_file_path=(Path(__file__).parent / "plugins_leak.xml").as_posix(), repo_url=MAIN_REPO_URI):

    if not os.path.exists(xml_file_path):
        print("given plugin xml doesn't exist in the parent directory")
        return None

    tree = etree.parse(xml_file_path)
    root = tree.getroot()

    for plugin in root.findall("pyqgis_plugin"):

        old_name = plugin.get("name")

        if old_name.startswith(".DEV " + branch_name_string):
            new_name = old_name.replace(".DEV " + branch_name_string, ".ROSOR", 1)
            plugin.set("name", new_name)

        old_plugin_zip_path = plugin.find("download_url").text
        old_plugin_icon_path = plugin.find("icon").text

        latter_plugin_path = Path(*Path(old_plugin_zip_path).parts[-2:]).as_posix()
        latter_icon_path = Path(*Path(old_plugin_icon_path).parts[-3:]).as_posix()

        new_plugin_zip_path = repo_url + "/" + latter_plugin_path
        new_plugin_icon_path = repo_url + "/" + latter_icon_path

        plugin.find("download_url").text = new_plugin_zip_path
        plugin.find("icon").text = new_plugin_icon_path


    tree.write(xml_file_path, pretty_print=True, xml_declaration=False, encoding="UTF-8")
if __name__ == "__main__":
    revert_xml_paths_to_main()