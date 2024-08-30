import os
import shutil

file_to_spread = r"C:\Users\pyoty\Documents\GitHub\sharj0.github.io\ROSORPlugins\PETER_ROSOR_import_kml\plugin_change_settings.py"

def replace_file_in_all_plugins(file_to_spread,
                                plugin_prefix='PETER_ROSOR_',
                                plugin_dir=os.path.dirname(__file__)):
    print(f'Spreading: {file_to_spread}')
    print()

    # Check if the provided plugin directory exists
    if not os.path.isdir(plugin_dir):
        print(f"The directory {plugin_dir} does not exist.")
        return

    # Check if the file to spread exists
    if not os.path.isfile(file_to_spread):
        print(f"The file {file_to_spread} does not exist.")
        return

    # Iterate through the directories in plugin_dir
    for root, dirs, files in os.walk(plugin_dir):
        for dir_name in dirs:
            if dir_name.startswith(plugin_prefix):
                plugin_path = os.path.join(root, dir_name)
                target_file_path = os.path.join(plugin_path, os.path.basename(file_to_spread))

                # If the target file exists and is the same as file_to_spread, skip it
                if os.path.isfile(target_file_path):
                    if os.path.samefile(file_to_spread, target_file_path):
                        print(f"Skipping identical file in {plugin_path}")
                        continue

                # Replace the target file with file_to_spread
                shutil.copy2(file_to_spread, target_file_path)
                print(f"Replaced file in {plugin_path}")

replace_file_in_all_plugins(file_to_spread)
