import os
import shutil
import hashlib

file_to_spread = r"C:\Users\pyoty\OneDrive\Documents\GitHub\sharj0.github.io\TinkeringToolbox\PETER_ROSOR_lines_to_flights\plugin_settings_suffixes.py"
def calculate_file_hash(file_path):
    """Calculate the hash of a file."""
    hash_obj = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()

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

    # Calculate the hash of the file to spread
    source_file_hash = calculate_file_hash(file_to_spread)

    # Iterate through the directories in plugin_dir
    for root, dirs, files in os.walk(plugin_dir):
        for dir_name in dirs:
            if dir_name.startswith(plugin_prefix):
                print()
                plugin_path = os.path.join(root, dir_name)
                target_file_path = os.path.join(plugin_path, os.path.basename(file_to_spread))

                # If the target file exists and has the same content, skip it
                if os.path.isfile(target_file_path):
                    if os.path.samefile(file_to_spread, target_file_path):
                        print(f"SOURCE file being spread skipped {plugin_path}")
                        continue
                    target_file_hash = calculate_file_hash(target_file_path)
                    if source_file_hash == target_file_hash:
                        print(f"Skipping identical file in {plugin_path}")
                        continue

                # Replace the target file with file_to_spread
                shutil.copy2(file_to_spread, target_file_path)
                print(f"Replaced file in {plugin_path}")

replace_file_in_all_plugins(file_to_spread)
