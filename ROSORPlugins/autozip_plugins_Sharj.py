import os #handles paths
import zipfile #zipfile is STRONGER than shutil.make_archive (I tested it)
import filecmp #compares file
import tempfile #creates temp folder
import shutil #used to delete temp folder


#This defaults to only selecting "PETER_ROSOR" folders, but can be used for other things
#Default directory is the working one
def autozip_files_main(plugin_prefix="PETER_ROSOR",plugin_dir=os.path.dirname(__file__)):

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

#Compares a zipped folder to an unzipped folder and should return true if any file is different and false when it's compared all the files and fails to find a difference (the default path is current directory and both archive and folder need to be in the same directory)
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
    folder_path = os.path.join(directory,folder)

    #Creates a ZipFile instance that creates a .zip using the folder and path
    with zipfile.ZipFile(folder_path + ".zip", mode="w") as archive:

        #Goes through every file in the chosen folder
        for root, dirs, files in os.walk(folder_path):
            for file in files:

                #writes the file and any parent folder if applicable to the new archive (I got this from stack overflow and it just worked)
                archive.write(os.path.join(root,file),os.path.relpath(os.path.join(root,file),os.path.join(folder_path, "..")))

    #Prints out that its done its job
    print("zipped: " + folder)


if __name__ == "__main__":
    autozip_files_main()