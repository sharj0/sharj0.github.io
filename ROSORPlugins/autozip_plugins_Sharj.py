import os
import zipfile #zipfile is STRONGER than shutil.make_archive (I tested it)

def autozip_files(plugin_prefix="PETER_ROSOR",plugin_dir=os.path.dirname(__file__)):

    #I'm reusing Peter's code

    # Check if the provided plugin directory exists
    if not os.path.isdir(plugin_dir):
        print(f"The directory {plugin_dir} does not exist.")
        return

    #Iterate through all the folders in the current directory
    for root, dirs,files in os.walk(plugin_dir):
        for dir_name in dirs:
            #Check if directory has the prefix which is our indicator/standard for plugins
            if dir_name.startswith(plugin_prefix):
                #uses the zipfile library to write the plugin folder into an archive with the plugin folder name
                with zipfile.ZipFile(dir_name+".zip",mode="w") as archive:
                    archive.write(dir_name)
                print("zipped: " + dir_name)

if __name__ == "__main__":
    autozip_files()