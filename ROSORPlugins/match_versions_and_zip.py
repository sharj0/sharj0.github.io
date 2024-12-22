"""THIS FILE NEEDS TO BE ONE FOLDER BELOW THE XML FILE (i.e. sharj0.github.io/ROSORPlugins) OR ELSE IT WON"T FIND THE
XML FILE IN THE PARENT FOLDER"""

import os
import xml.etree.ElementTree as ET
from packaging.version import Version

import zipfile  #zipfile is STRONGER than shutil.make_archive (I tested it)
import filecmp  #compares file
import tempfile  #creates temp folder
import shutil  #used to delete temp folder

from datetime import date

import hashlib
import json
from pathlib import Path
from pathspec import PathSpec

#made by sharj mostly😀 << peter wrote this

HASH_FILE = "detect_changes_with_folder_hashes.json"

# Function to calculate the hash of a folder
def calculate_folder_hash_old(folder_path):
    sha256 = hashlib.sha256()
    for root, dirs, files in os.walk(folder_path):
        for file in sorted(files):  # Sort files to ensure consistent order
            file_path = os.path.join(root, file)
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    sha256.update(chunk)
    return sha256.hexdigest()


def calculate_folder_hash(folder_path):
    # Initialize SHA256 hash object
    sha256 = hashlib.sha256()

    # Find and parse `.gitignore` files
    ignore_patterns = []
    for path in [folder_path, os.path.dirname(folder_path)]:
        gitignore_path = os.path.join(path, '.gitignore')
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                ignore_patterns.extend(f.readlines())

    # Compile the patterns into a PathSpec object
    spec = PathSpec.from_lines('gitwildmatch', ignore_patterns)

    # Walk through the folder and hash files
    for root, dirs, files in os.walk(folder_path):
        # Filter directories and files based on .gitignore rules
        dirs[:] = [d for d in dirs if not spec.match_file(os.path.relpath(os.path.join(root, d), folder_path))]
        for file in sorted(files):  # Sort files for consistent order
            file_path = os.path.relpath(os.path.join(root, file), folder_path)
            if not spec.match_file(file_path):
                # Read and hash the file
                full_file_path = os.path.join(root, file)
                with open(full_file_path, 'rb') as f:
                    while chunk := f.read(4096):
                        sha256.update(chunk)

    return sha256.hexdigest()

# Function to get all current hashes for folders that start with plugin_prefix
def get_all_current_hashes(plugin_prefix="PETER_ROSOR", plugin_dir=os.path.dirname(__file__)):
    current_hashes = {}

    # Iterate through all the folders in the directory
    for root, dirs, files in os.walk(plugin_dir):
        for dir_name in dirs:
            if dir_name.startswith(plugin_prefix):
                folder_path = os.path.join(root, dir_name)

                # Calculate current hash for the folder
                current_hash = calculate_folder_hash(folder_path)
                current_hashes[dir_name] = current_hash

    return current_hashes

# Function to load saved hashes from a file
def load_saved_hashes(hash_file):
    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            outp = json.load(f)
            print(f"loaded hashes from '{os.path.basename(hash_file)}'")
            print()
            return outp

    return {}

# Function to save hashes to a file
def save_hashes(hashes, hash_file):
    print(f"updating '{os.path.basename(hash_file)}'")
    with open(hash_file, 'w') as f:
        json.dump(hashes, f, indent=4)

# Function to check for changes and update versions if needed
def check_for_changes_and_update_versions(plugin_prefix="PETER_ROSOR"):
    saved_hashes = load_saved_hashes(HASH_FILE)

    # Get all current hashes for the relevant folders
    current_hashes = get_all_current_hashes()

    folders_that_need_updating = []

    # Compare saved hashes with current hashes
    for dir_name, current_hash in current_hashes.items():
        if saved_hashes.get(dir_name) != current_hash:
            print(f"Changes detected in {dir_name}. Need to update version")
            folders_that_need_updating.append(dir_name)
        else:
            print(f"No changes detected in {dir_name}.")

    return folders_that_need_updating

#This defaults to only selecting "PETER_ROSOR" folders, but can be used for other things
#Default directory is the working one
def autozip_files_main(folders_that_need_updating,
                       plugin_prefix="PETER_ROSOR",
                       plugin_dir=os.path.dirname(__file__)):
    #I'm reusing Peter's code


    if not os.path.isdir(plugin_dir):

        print(f"The directory {plugin_dir} does not exist.")

        return


    for root, dirs, files in os.walk(plugin_dir):

        for dir_name in dirs:

            #Check if directory has the prefix which is our indicator/standard for plugins
            if dir_name.startswith(plugin_prefix):

                if dir_name in folders_that_need_updating:

                    print(f'zipping folder {dir_name} ... ')

                    if is_archive_folder_different(dir_name):

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

    folder_path = os.path.join(directory, folder)

    #Creates a ZipFile instance that creates a .zip using the folder and path
    with zipfile.ZipFile(folder_path + ".zip", mode="w", compression=zipfile.ZIP_LZMA) as archive:

        for root, dirs, files in os.walk(folder_path):
            for file in files:
                #writes the file and any parent folder if applicable to the new archive (I got this from stack overflow and it just worked)
                archive.write(os.path.join(root, file),
                              os.path.relpath(os.path.join(root, file), os.path.join(folder_path, "..")))

    print("zipped: " + folder)


#This function checks the xml stated version for each plugin in the xml and check each the corresponding plugin's metadata version to match them
#Defaults to plugins_leak xml file name, the current working directory, and no incrementing (note that the plugin folders MUST be in the directory and xml file MUST be in the parent folder/one above)
def match_xml_version_main(folders_that_need_updating,
                           xml_file_name="plugins_leak.xml",
                           current_path=os.path.dirname(__file__),
                           update_date=False,
                           increment_all=False):

    parent_dir = os.path.dirname(current_path)
    xml_file_path = os.path.join(parent_dir, xml_file_name)

    if not os.path.isfile(xml_file_path):
        print("given plugin xml doesn't exist in the parent directory")
        return None

    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    #setting up a conditional boolean on whether to write to the xml file
    change_xml = False

    plugin_folders_in_dir = check_plugin_folders()

    poppable_folder_list = list(plugin_folders_in_dir.keys())

    # if len(plugin_folders_in_dir) > len(no_of_fields):
    #     poppable_

    for plugin in root.findall("pyqgis_plugin"):

        plugin_zip_path = plugin.find('download_url').text
        xml_version = plugin.attrib['version']

        #uses the download url zip file name to correspond to the plugin and gets creates a path to it in the current directory
        plugin_folder = Path(plugin_zip_path).stem

        if not plugin_folder in plugin_folders_in_dir:
            root.remove(plugin)
            tree.write(xml_file_path)
            continue
        else:
            poppable_folder_list.remove(plugin_folder)

        if not plugin_folder in folders_that_need_updating:
            continue

        plugin_folder_path = os.path.join(current_path, plugin_folder)


        metadata_path = os.path.join(plugin_folder_path, "metadata.txt")


        print(f"xml version for {plugin_folder}: {xml_version}")

        #creates a version string with today's date using the make_version_todays_date function
        xml_date_version = make_version_todays_date(xml_version)


        if update_date and Version(xml_version) != Version(xml_date_version):


            change_xml = True


            xml_version = xml_date_version


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

                print(f"metadata version for {plugin_folder}: {metadata_version}")

                # creates a version string with today's date using the make_version_todays_date function
                metadata_date_version = make_version_todays_date(metadata_version)


                if update_date and Version(metadata_version) != Version(metadata_date_version):

                    # since the metadata is different, then the new one needs to be written (setting the boolean to true)
                    change_metadata = True

                    metadata_version = metadata_date_version

                    print(f"updated xml version to todays date: {metadata_version}")

                #if deciding to increment each plugin to save time this calls the function to add one to the right most decimal
                if increment_all:

                    metadata_version = increment_two_decimal_version_string(metadata_version, target_index=-1)

                    xml_version = increment_two_decimal_version_string(xml_version, target_index=-1)

                    change_xml = True

                    change_metadata = True

                    print(f"xml incremented: {xml_version} | metadata incremented: {metadata_version} | (highest is used to write)")


                #This if statement compares the versions using packaging.version library and decides which value to change based on the larger version
                if Version(metadata_version) < Version(xml_version):

                    change_metadata = True

                    metadata_version = xml_version

                    print(f"modified metadata for {plugin_folder}\n")


                elif Version(metadata_version) > Version(xml_version):

                    change_xml = True

                    xml_version = metadata_version

                    print(f"modified xml for {plugin_folder}\n")

                else:

                    #If both version are the same, then do nothing and print to console that nothing was modified (both booleans stay false)
                    print(f"versions match for {plugin_folder}\n")

                    pass

            if change_metadata:

                # Alters the 4th line in metadata (which should be version=x.x.x in the current template) to match xml version
                metadata[4] = metadata[4][:8] + metadata_version + "\n"

                # Overwrites the whole metadata text file with a matched version to the xml using the metadata list from earlier
                with open(metadata_path, mode="w") as metadata_file:
                    metadata_file.writelines(metadata)

        else:
            #If metadata file doesn't exist, then move on (this else can be omitted)
            pass


        if change_xml:

            #Alters the text in the xml "version" attribute to match the metadata version
            plugin.set('version', xml_version)

            #Overwrites xml file with modified versions for all plugins that have changed (I think this can go outside the for loop so it only writes once, but oh well, I can't be bothered to try and debug)
            tree.write(xml_file_path)



    for plugin in poppable_folder_list:
        print(f"Plugin added to xml: {poppable_folder_list}")
        plugin_folder_path = Path(plugin_folders_in_dir[plugin]).as_posix()
        add_plugin_in_xml(xml_file_path=xml_file_path, plugin=plugin, plugin_folder_path=plugin_folder_path)


def check_plugin_folders(xml_file_name="plugins_leak.xml", current_path=os.path.dirname(__file__), precursor = "PETER_ROSOR"):

    current_path = Path(current_path).as_posix()
    parent_dir = Path(Path(current_path).parent).as_posix()

    xml_file_path = Path(parent_dir, xml_file_name).as_posix()

    if not os.path.isfile(xml_file_path):
        print("given plugin xml doesn't exist in the parent directory")
        return None

    plugin_folders_in_dir = {file.name: file for file in Path(current_path).glob(f"{precursor}*") if file.is_dir()}

    return plugin_folders_in_dir


def add_plugin_in_xml(xml_file_path, plugin, plugin_folder_path):
    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    metadata_file_path = Path(plugin_folder_path, "metadata.txt").as_posix()

    if not os.path.exists(metadata_file_path):
        print(f"metadata file not found for: {plugin}")
        return None

    with open(metadata_file_path, "r") as file:
        lines = file.readlines()

    name_index = next((i for i, line in enumerate(lines) if line.startswith("name")), None)
    desc_index = next((i for i, line in enumerate(lines) if line.startswith("description")), None)
    exp_index = next((i for i, line in enumerate(lines) if line.startswith("experimental")), None)


    #this is assuming "name=" takes up 6 characters and \n is always present (I think this can be modular instead of hard coded)
    plugin_name = lines[name_index][6:-1]
    plugin_description = lines[desc_index][12:-1]
    if not exp_index is None:
        experimental = lines[exp_index][13:]
    else:
        experimental = "False"

    temp_name = ".ROSOR " + plugin_name
    temp_version = make_version_todays_date()

    new_plugin = ET.Element("pyqgis_plugin", {
        "name": temp_name,
        "version": temp_version
    })

    MAIN_REPO_URI = "https://sharj0.github.io"
    download_zip_path = MAIN_REPO_URI + "/ROSORPlugins/" + plugin + ".zip"
    plugin_icon_path = MAIN_REPO_URI + "/ROSORPlugins/" + plugin + "/plugin_icon.png"

    ET.SubElement(new_plugin, "qgis_minimum_version").text = "3.0.0"
    ET.SubElement(new_plugin, "author_name").text = "Pyotyr Young and Sharjeel Awon"
    ET.SubElement(new_plugin, "icon").text = plugin_icon_path
    ET.SubElement(new_plugin, "description").text = plugin_description
    ET.SubElement(new_plugin, "download_url").text = download_zip_path
    ET.SubElement(new_plugin, "experimental").text = experimental

    root.append(new_plugin)

    tree.write(xml_file_path)

#This function increments numerical version strings with periods as delimiters, the default target increment is the right most value
def increment_two_decimal_version_string(version="1.0.0", target_index=-1):

    # ensures the given string is a version (this might cause isssues with different formatted versions)
    if (not Version(version)) or target_index > len(version.split(".")):
        return None

    version_ints = [int(split_number) for split_number in version.split(".")]

    version_ints[target_index] += 1

    new_version_str = [str(new_split_number) for new_split_number in version_ints]

    new_version = '.'.join(new_version_str)

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
            version_ints[1:5] = [todays_date.year, todays_date.month, todays_date.day, 0]

    else:

        #if the version does not have enough slots to allocate the [1, yyyy, mm, dd, version] format (an array length of 5 or 4 decimals in the string) then append to increase the array size
        version_ints.append(0)

        #create the larger array into a an array full of strings
        new_version_str = [str(new_split_number) for new_split_number in version_ints]

        new_version = ".".join(new_version_str)

        #recurse the appended string through until it meets the array size of 5 (it will continue appending zeros until it meets the first if statement in this nest)
        return make_version_todays_date(new_version)

    # converts the integer array into a string array with the incremented numerical
    new_version_str = [str(new_split_number) for new_split_number in version_ints]

    new_version = ".".join(new_version_str)

    return new_version

# Sample function for version update logic
def update_version_logic(plugin_folder):
    print(f"Running version update logic for {plugin_folder}")

if __name__ == "__main__":
    folders_that_need_updating = check_for_changes_and_update_versions()
    print()
    match_xml_version_main(folders_that_need_updating, xml_file_name="plugins_leak.xml", update_date=True, increment_all=True)

    autozip_files_main(folders_that_need_updating)
    print()
    if folders_that_need_updating:
        save_hashes(get_all_current_hashes(), HASH_FILE)
        print("\n DON'T FORGET TO PUSH TO MAIN")
    else:
        print("\n No changes detected in any of the input folders.")

    check_plugin_folders()
