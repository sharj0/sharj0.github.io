"""THIS FILE NEEDS TO BE ONE FOLDER BELOW THE XML FILE (i.e. sharj0.github.io/ROSORPlugins) OR ELSE IT WON"T FIND THE XML FILE IN THE PARENT FOLDER"""

import os
import xml.etree.ElementTree as ET
import pathlib
from packaging.version import Version
import autozip_plugins_Sharj

#This function checks the xml stated version for each plugin in the xml and check each the corresponding plugin's metadata version to match them
#Defaults to plugins_leak xml file name, the current working directory, and no incrementing (note that the plugin folders MUST be in the directory and xml file MUST be in the parent folder/one above)
def match_xml_version_main(xml_file_name="plugins_leak.xml", current_path=os.path.dirname(__file__), increment_all=False):

    #gets parent directory for xml file path
    parent_dir = os.path.dirname(current_path)
    xml_file_path = os.path.join(parent_dir, xml_file_name)

    #ends function early if it cannot find the xml file in the parent folder
    if not os.path.isfile(xml_file_path):
        print("given plugin xml doesn't exist in the parent directory")
        return None

    #uses elementree to read xml data
    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    #setting up a conditional boolean on whether to write to the xml file
    change_xml = False

    #increments through all plugins in the xml file
    for plugin in root.findall("pyqgis_plugin"):

        #obtains the download url (used to identify the plugin name) and its corresponding version in the xml file
        plugin_zip_path = plugin.find('download_url').text
        xml_version = plugin.find('version').text

        #uses the download url zip file name to correspond to the plugin and gets creates a path to it in the current directory
        plugin_folder = pathlib.Path(plugin_zip_path).stem
        plugin_folder_path = os.path.join(current_path, plugin_folder)

        # creates a metadata.txt path by appending it to the plugin folder path above as every plugin should have a metadata text file
        metadata_path = os.path.join(plugin_folder_path, "metadata.txt")

        # prints out plugin name and xml version in the console
        print(f"xml version for {plugin_folder}: {xml_version}")

        #setting up a conditional boolean on whether to write to the metadata file
        change_metadata = False

        #checks if metadata.txt exists in the plugin folder (if it fails it means either metadata.txt is missing or the plugin folder is missing) (two birds one stone, but bad for debugging)
        if os.path.exists(metadata_path):

            #opening the metadata text file in reading mode (I tried using read and write at once, but was unable to replace the original text)
            with open(metadata_path, mode="r") as metadata_file:

                #stores each line into a list called metadata
                metadata = metadata_file.readlines()

                #isolates the line with the plugin's version that we want to check
                metadata_version = metadata[4][8:-1]

                #prints the plugin name and metadata version in the console
                print(f"metadata version for {plugin_folder}: {metadata_version}")

                #if deciding to increment each plugin to save time this calls the function to add one to the right most decimal
                if increment_all:
                    increment_two_decimal_version_string(metadata_version, target_index=2)
                    increment_two_decimal_version_string(xml_version, target_index=2)

                #This if statement compares the versions using packaging.version library and decides which value to change based on the larger version
                if Version(metadata_version) < Version(xml_version):

                    # If metadata's version is less than the xml one, then metadata needs to change
                    change_metadata = True

                    #Alters the 4th line in metadata (which should be version=x.x.x in the current template) to match xml version
                    metadata[4] = metadata[4][:8] + xml_version + "\n"

                    #statement in console to show user that the metadata is changed to match the xml
                    print(f"modified metadata for {plugin_folder}\n")


                elif Version(metadata_version) > Version(xml_version):

                    #If xml's version is less than the metadata one, then xml needs to change
                    change_xml = True

                    #alters the text in the xml "version" attribute to match the metadata version
                    plugin.find('version').text = metadata_version

                    # statement in console to show user that the xml is changed to match the metadata
                    print(f"modified xml for {plugin_folder}\n")

                else:

                    #If both version are the same, then do nothing and print to console that nothing was modified (both booleans stay false)
                    print(f"versions match for {plugin_folder}\n")

                    pass

            #Checks boolean to change metadata
            if change_metadata:

                # Overwrites the whole metadata text file with a matched version to the xml using the metadata list from earlier
                with open(metadata_path, mode="w") as metadata_file:
                    metadata_file.writelines(metadata)

        else:
            #If metadata file doesn't exist, then move on (this else can be omitted)
            pass

        #Checks boolean to change xml
        if change_xml:
            #Overwrites xml file with modified versions for all plugins that have changed (I think this can go outside the for loop so it only writes once, but oh well, I can't be bothered to try and debug)
            tree.write(xml_file_path)


#This function increments a given two decimal version in x.x.x format
#Defaults to 1.0.0 as the version and target index as the right most value (index 2 as its starts at 0)
def increment_two_decimal_version_string(version="1.0.0", target_index=2):

    #ensures the given string is a version (this might cause isssues with different formatted versions)
    if (not Version(version)) or len(version.split(".")) != 3:
        return None

    #splits the version string into three variables based on index
    major, minor, micro = version.split(".")

    #An if tree (similar to switch case) where the code changes a bit based on which index to increment (there might be a more elegant solution but this is the one I came up with)
    #It takes the target index (major, minor or micro), converts it to an integer, adds 1 to it, converts it back to a string and stitches it together with the rest using periods
    if target_index == 2:
        incremented_value = str(int(micro) + 1)
        version = major + "." + minor + "." + incremented_value
    elif target_index == 1:
        incremented_value = str(int(minor) + 1)
        version = major + "." + incremented_value + "." + micro
    elif target_index == 0:
        incremented_value = str(int(major) + 1)
        version = incremented_value + "." + minor + "." + micro
    else:
        #if target index is not within the range or right type, then return nothing
        return None

    #return the incremented version
    return version


if __name__ == "__main__":
    match_xml_version_main(xml_file_name="plugins_development.xml")
    autozip_plugins_Sharj.autozip_files_main()
