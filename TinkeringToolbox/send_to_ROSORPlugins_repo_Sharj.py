
import os
import re
import html
# import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from lxml import etree
import pathlib
from pathlib import Path
import shutil

from match_versions_and_zip_Sharj import match_xml_version_main, autozip_files_main

def copy_folder_to_another_folder(plugin_path,target_folder=os.path.join(Path(__file__).parent.parent,"ROSORPlugins")):
    if os.path.basename(plugin_path).startswith("PETER_ROSOR"):
        shutil.copytree(plugin_path, os.path.join(target_folder, os.path.basename(plugin_path)), dirs_exist_ok=True)
    else:
        for root, dirs, files in os.walk(plugin_path):
            for dir in dirs:
                if dir.startswith("PETER_ROSOR"):
                    plugin_path = os.path.join(root,dir)
                    shutil.copytree(plugin_path, os.path.join(target_folder, os.path.basename(plugin_path)), dirs_exist_ok=True)

def create_plugin_element_in_official_repo(plugin_name, xml_file_path=os.path.join(Path(__file__).parent.parent,"plugins_leak.xml",)):

    plugin_path = os.path.join(Path(__file__).parent, plugin_name)

    if not os.path.isfile(xml_file_path):
        print("given plugin xml doesn't exist in the parent directory")
        return None

    # uses elementree to read xml data
    tree = etree.parse(xml_file_path)
    root = tree.getroot()

    # setting up a conditional boolean on whether to write to the xml file
    create_xml_element = True

    # increments through all plugins in the xml file
    for plugin in root.findall("pyqgis_plugin"):

        # obtains the download url (used to identify the plugin name) and its corresponding version in the xml file
        plugin_zip_path = plugin.find('download_url').text

        if plugin_name == Path(plugin_zip_path).stem:
            create_xml_element = False

    copy_folder_to_another_folder(plugin_path)

    if create_xml_element:
        metadata_path = os.path.join(plugin_path, "metadata.txt")

        if not os.path.isfile(metadata_path):
            return None

        with open(metadata_path,mode="r") as metadata_file:

            metadata = metadata_file.readlines()

            name = ".ROSOR " + metadata[1][6:-1]#[line for line in metadata if line.startswith("name")]
            qgis_min_ver = metadata[2][19:-1]#[line for line in metadata if line.startswith("qgisMinimumVersion")]
            description = metadata[3][12:-1]#[line for line in metadata if line.startswith("description")]
            version = metadata[4][8:-1]#[line for line in metadata if line.startswith("version")]
            author = metadata[5][7:-1]#[line for line in metadata if line.startswith("author")]
            email = metadata[6][6:-1]#[line for line in metadata if line.startswith("email")]
            icon = (Path(__file__).parent.parent / "ROSORPlugins" / plugin_name / "plugin_icon.jpg").as_posix()
            # icon = os.path.join(os.path.join(Path(__file__).parent.parent, "ROSORPlugins", plugin_name, "plugin_icon"
            #                                                                                             ".jpg"))

            download_url = (Path(__file__).parent.parent / "ROSORPlugins" / f"{plugin_name}.zip").as_posix()
            # download_url = os.path.join(Path(__file__).parent.parent, "ROSORPlugins", plugin_name) + ".zip"

        new_xml_plugin = etree.Element("pyqgis_plugin", {
                "name": name,
                "version": version
        })
        etree.SubElement(new_xml_plugin, 'qgis_minimum_version').text = qgis_min_ver
        etree.SubElement(new_xml_plugin, 'author_name').text = author
        etree.SubElement(new_xml_plugin, 'icon').text = icon
        etree.SubElement(new_xml_plugin, 'email').text = email
        etree.SubElement(new_xml_plugin, 'description').text = description
        etree.SubElement(new_xml_plugin, 'download_url').text = download_url

        root.append(new_xml_plugin)
        write_path = Path(__file__).parent.parent / "plugin_test.xml"
        write_path = write_path.as_posix()
        tree.write(write_path, pretty_print=True, xml_declaration=False, encoding='UTF-8')


"""THIS CODE BELOW WAS TO AUTOSPACE/FORMAT THE XML TO BE READABLE BUT I HAD ISSUES BECAUSE OF SPECIAL CHARACTERS LIKE THE PERIOD IN .ROSOR AND & IN MAC CLIPPER"""
        # formatted = format_element(root)
        #
        # reparsed = minidom.parseString(formatted)
        # pretty_xml = reparsed.toprettyxml(indent="  ")
        #
        # # pretty_xml = etree.tostring(root, pretty_print=True, encoding="unicode")
        #
        # start_index = pretty_xml.find('>', pretty_xml.find('<?xml'))
        #
        # # If the XML declaration is present, remove it
        # if start_index != -1:
        #     final_xml_string = pretty_xml[start_index + 1:].lstrip()  # +1 to remove '>'
        # else:
        #     final_xml_string = pretty_xml
        #
        # if final_xml_string:
        #     with open(xml_file_path, "w") as file:
        #         file.write(final_xml_string)

"""THIS FUNCTION WAS ACCOMPANIED WITH THE CODE ABOVE TO ESSENTIALLY MAKE EVERYTHING INTO A ONE LINE STRING (SO IT ESSENTIALLY RESETS ALL FORMATTING) AND THEN FORMAT IT"""
# def format_element(elem):
#     """Recursively format an XML element with attributes into a single line."""
#     # Get attributes in the format 'key="value"'
#     attrs = ' '.join(f'{key}="{value}"' for key, value in elem.attrib.items())
#     if attrs:
#         attrs = ' ' + attrs
#
#     # Process children recursively
#     if not list(elem):  # If the element has no children
#         return f'<{elem.tag}{attrs}>{elem.text.strip() if elem.text else ""}</{elem.tag}>'
#
#     children = ''.join(format_element(child) for child in elem)
#     return f'<{elem.tag}{attrs}>{children}</{elem.tag}>'

if __name__ == "__main__":
    chosen_plugin_name = "PETER_ROSOR_plugin_template"
    create_plugin_element_in_official_repo(chosen_plugin_name)
    ROSORPlugins_path = (Path(__file__).parent.parent / "ROSORPlugins").as_posix()
    match_xml_version_main(xml_file_name="plugins_test.xml", update_date=True, increment_all=True)
    autozip_files_main(plugin_dir=ROSORPlugins_path)

    print("\nPlease format xml file to be more legible (either manually or automatically through an IDE like VSCode)")

    print("\nDON'T FORGET TO PUSH TO MAIN")


