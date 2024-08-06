"""THIS FILE NEEDS TO BE ONE FOLDER BELOW THE XML FILE (i.e. sharj0.github.io/ROSORPlugins) OR ELSE IT WON"T FIND THE
XML FILE IN THE PARENT FOLDER"""

import os
import xml.etree.ElementTree as ET
import pathlib
from packaging.version import Version

import zipfile  #zipfile is STRONGER than shutil.make_archive (I tested it)
import filecmp  #compares file
import tempfile  #creates temp folder
import shutil  #used to delete temp folder

from datetime import date

#This defaults to only selecting "PETER_ROSOR" folders, but can be used for other things
#Default directory is the working one
def autozip_files_main(plugin_prefix="PETER_ROSOR", plugin_dir=os.path.dirname(__file__)):
    #I'm reusing Peter's code

    # Check if the provided plugin directory exists
    if not os.path.isdir(plugin_dir):
        print(f"The directory {plugin_dir} does not exist.")
        return

    #Iterate through all the folders in the current directory
    for root, dirs, files in os.walk(plugin_dir):
        for dir_name in dirs:
            #Check if directory has the prefix which is our indicator/standard for plugins
            if dir_name.startswith(plugin_prefix):

                #Calls separate function in file that checks whether there is a difference between the zipped plugin and the unzipped one in current directory
                if is_archive_folder_different(dir_name):
                    #uses the zipfile library to write the plugin folder into an archive with the plugin folder name
                    zip_file(dir_name)


#Compares a zipped folder to an unzipped folder and should return true if any file is different and false when it's compared all the files and fails to find a difference (the default path is current directory)
def is_archive_folder_different(folder, directory=os.path.dirname(__file__)):
    #Sets the path to the chosen folder and makes a reference to a .zip archive with the same name
    folder_path = os.path.join(directory, folder)
    zip_file = folder_path + ".zip"

    #If the referenced zip file does not exist that means main function should create a new zip, hence returns true
    if not os.path.isfile(zip_file):
        return True

    #If the zip file exists, need to compare its contents (I couldn't find a more elegant solution)
    else:

        #Creatign a temporary directory to temporarily store the contents of the existing zip file
        temp_dir = tempfile.mkdtemp()

        #Uses zipfile to store the contents of the referenced archive
        with zipfile.ZipFile(zip_file) as archive:
            archive.extractall(temp_dir)

        #Uses filecmp to compare the temporary stored folder with the one in the current/input directory
        comparison = filecmp.dircmp(folder_path, os.path.join(temp_dir, folder))

        #If any file is different, we need to overite it/rezip the file with updated contents so it returns true for the main function to proceed
        if comparison.left_only or comparison.right_only or comparison.diff_files:
            #Delete the temporary folder as it is not necessary at this point
            shutil.rmtree(temp_dir)

            return True
        #Delete the temporary folder as it is not necessary at this point
        shutil.rmtree(temp_dir)

        #If code gets to this point, it means its exhausted all the comparisons and both folders should be identical
        return False


#Created a dedicated function to zip files as it might be used later
#Defaults to the folder being in the working directory
def zip_file(folder, directory=os.path.dirname(__file__)):
    #Sets the path to the folder
    folder_path = os.path.join(directory, folder)

    #Creates a ZipFile instance that creates a .zip using the folder and path
    with zipfile.ZipFile(folder_path + ".zip", mode="w") as archive:

        #Goes through every file in the chosen folder
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                #writes the file and any parent folder if applicable to the new archive (I got this from stack overflow and it just worked)
                archive.write(os.path.join(root, file),
                              os.path.relpath(os.path.join(root, file), os.path.join(folder_path, "..")))

    #Prints out that its done its job
    print("zipped: " + folder)


#This function checks the xml stated version for each plugin in the xml and check each the corresponding plugin's metadata version to match them
#Defaults to plugins_leak xml file name, the current working directory, and no incrementing (note that the plugin folders MUST be in the directory and xml file MUST be in the parent folder/one above)
def match_xml_version_main(xml_file_name="plugins_leak.xml", current_path=os.path.dirname(__file__),
                           increment_all=False):
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
        xml_version = plugin.attrib['version']

        #uses the download url zip file name to correspond to the plugin and gets creates a path to it in the current directory
        plugin_folder = pathlib.Path(plugin_zip_path).stem
        plugin_folder_path = os.path.join(current_path, plugin_folder)

        # creates a metadata.txt path by appending it to the plugin folder path above as every plugin should have a metadata text file
        metadata_path = os.path.join(plugin_folder_path, "metadata.txt")

        # prints out plugin name and xml version in the console
        print(f"xml version for {plugin_folder}: {xml_version}")

        #creates a version string with today's date using the make_version_todays_date function
        xml_date_version = make_version_todays_date(xml_version)

        #checks if the written xml_version is different from the todays
        if Version(xml_version) != Version(xml_date_version):

            #since the xml is different, then the new one needs to be written (setting the boolean to true)
            change_xml = True

            #replaces the xml version with current date
            xml_version = xml_date_version

            #notifies user about the updated date version
            print(f"updated xml version to todays date: {xml_version}")

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

                # prints the plugin name and metadata version in the console
                print(f"metadata version for {plugin_folder}: {metadata_version}")

                # creates a version string with today's date using the make_version_todays_date function
                metadata_date_version = make_version_todays_date(metadata_version)

                # checks if the written metadata_version is different from the todays
                if Version(metadata_version) != Version(metadata_date_version):

                    # since the metadata is different, then the new one needs to be written (setting the boolean to true)
                    change_metadata = True

                    # replaces the xml version with current date
                    metadata_version = metadata_date_version

                    # notifies user about the updated date version
                    print(f"updated xml version to todays date: {metadata_version}")

                #if deciding to increment each plugin to save time this calls the function to add one to the right most decimal
                if increment_all:
                    metadata_version = increment_two_decimal_version_string(metadata_version, target_index=-1)
                    xml_version = increment_two_decimal_version_string(xml_version, target_index=-1)
                    print(f"xml incremented: {xml_version} | metadata incremented: {metadata_version} | (highest is used to write)")


                #This if statement compares the versions using packaging.version library and decides which value to change based on the larger version
                if Version(metadata_version) < Version(xml_version):

                    # If metadata's version is less than the xml one, then metadata needs to change
                    change_metadata = True

                    #sets metadata version the the greater to match
                    metadata_version = xml_version

                    #statement in console to show user that the metadata is changed to match the xml
                    print(f"modified metadata for {plugin_folder}\n")


                elif Version(metadata_version) > Version(xml_version):

                    #If xml's version is less than the metadata one, then xml needs to change
                    change_xml = True

                    #sets xml version to the greater to match
                    xml_version = metadata_version

                    # statement in console to show user that the xml is changed to match the metadata
                    print(f"modified xml for {plugin_folder}\n")

                else:

                    #If both version are the same, then do nothing and print to console that nothing was modified (both booleans stay false)
                    print(f"versions match for {plugin_folder}\n")

                    pass

            #Checks boolean to change metadata
            if change_metadata:

                # Alters the 4th line in metadata (which should be version=x.x.x in the current template) to match xml version
                metadata[4] = metadata[4][:8] + metadata_version + "\n"

                # Overwrites the whole metadata text file with a matched version to the xml using the metadata list from earlier
                with open(metadata_path, mode="w") as metadata_file:
                    metadata_file.writelines(metadata)

        else:
            #If metadata file doesn't exist, then move on (this else can be omitted)
            pass

        #Checks boolean to change xml
        if change_xml:

            # alters the text in the xml "version" attribute to match the metadata version
            plugin.set('version', xml_version)

            #Overwrites xml file with modified versions for all plugins that have changed (I think this can go outside the for loop so it only writes once, but oh well, I can't be bothered to try and debug)
            tree.write(xml_file_path)


#This function increments numerical version strings with periods as delimiters, the default target increment is the right most value
def increment_two_decimal_version_string(version="1.0.0", target_index=-1):

    # ensures the given string is a version (this might cause isssues with different formatted versions)
    if (not Version(version)) or target_index > len(version.split(".")):
        return None

    # splits the version string based on the delimiter "." and converts them into an integer array
    version_ints = [int(split_number) for split_number in version.split(".")]

    # incremets the targeted value in the integer array
    version_ints[target_index] += 1

    # converts the integer array into a string array with the incremented numerical
    new_version_str = [str(new_split_number) for new_split_number in version_ints]

    # joins the string array for the new incremented version
    new_version = '.'.join(new_version_str)

    # return the incremented version
    return new_version


def make_version_todays_date(version="1.0.0"):

    # ensures the given string is a version (this might cause isssues with different formatted versions)
    if not Version(version):
        return None

    # splits the version string based on the delimiter "." and converts them into an integer array
    version_ints = [int(split_number) for split_number in version.split(".")]

    #gets todays date as a datetime object
    todays_date = date.today()

    #checks if the string has at least 4 slots indicating there is a starter and 3 allocations for the date [1, yyyy, mm, dd, version number]
    if len(version_ints) > 4:

        #if there version has a date, check if its current
        if version_ints[1:4] == [todays_date.year, todays_date.month, todays_date.day]:

            # #if the version is current then increment the right most version number
            # new_version = increment_two_decimal_version_string(version)

            #return to stop the function early
            return version
        else:

            #if the the date is incorrect, then change year, month and day indexes to todays date and set the right most (array index 4 or the 5th number) to 1 as it is the first instance of todays update
            version_ints[1:5] = [todays_date.year, todays_date.month, todays_date.day, 1]

    else:

        #if the version does not have enough slots to allocate the [1, yyyy, mm, dd, version] format (an array length of 5 or 4 decimals in the string) then append to increase the array size
        version_ints.append(0)

        #create the larger array into a an array full of strings
        new_version_str = [str(new_split_number) for new_split_number in version_ints]

        #join the string array with "." as a delimiter
        new_version = ".".join(new_version_str)

        #recurse the appended string through until it meets the array size of 5 (it will continue appending zeros until it meets the first if statement in this nest)
        return make_version_todays_date(new_version)

    # converts the integer array into a string array with the incremented numerical
    new_version_str = [str(new_split_number) for new_split_number in version_ints]

    # joins the string array for the new incremented version
    new_version = ".".join(new_version_str)

    # return the incremented version
    return new_version


if __name__ == "__main__":
    match_xml_version_main(xml_file_name="plugins_development.xml", increment_all=False)
    autozip_files_main()
    # print("don't forget to push to main")

