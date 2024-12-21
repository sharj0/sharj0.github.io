import os
import shutil

target_plugin = r"C:\Users\pyoty\Documents\GitHub\test_braaahnch\sharj0.github.io\ROSORPlugins\PETER_ROSOR_lines_to_flights"

# ------------------------------------------------------------------------------
# This function checks if a string ends in "exp" or "experimental" (any case).
# Returns (True, <base_string>) if it does, otherwise (False, <original_string>).
#
# If the string ends with "exp" / "experimental", we remove that suffix and
# any trailing underscores. We can re-use this or just note it's helpful.
# In this "make-experimental" script, we'll actually *reject* the folder if
# it's already experimental. But let's keep this function for completeness.
# ------------------------------------------------------------------------------
def parse_experimental(input_string: str):
    lowered = input_string.lower()
    valid_suffixes = ["exp", "experimental"]

    for suffix in valid_suffixes:
        if lowered.endswith(suffix):
            cut_off = len(input_string) - len(suffix)
            new_str = input_string[:cut_off].rstrip("_")
            return True, new_str
    return False, input_string


def main(target_plugin):

    # 1) Basic checks on the folder
    if not os.path.exists(target_plugin):
        print(f"Path does not exist: {target_plugin}")
        return

    # Extract base folder name
    base_folder = os.path.basename(os.path.normpath(target_plugin))

    # a) Check that it starts with "PETER_ROSOR"
    if not base_folder.startswith("PETER_ROSOR"):
        print(f"Invalid plugin name. Must start with 'PETER_ROSOR', got: {base_folder}")
        return

    # b) Check that it does NOT end with "exp" or "experimental"
    is_exp, _ = parse_experimental(base_folder)
    if is_exp:
        print(f"This folder already appears to be experimental: {base_folder}")
        print("Cannot convert a folder that is already experimental.")
        return

    print(f"Validated non-experimental plugin: {base_folder}")

    # 2) Determine the new experimental folder name
    #    For instance, if the folder is "PETER_ROSOR_lines_to_flights",
    #    we want "PETER_ROSOR_lines_to_flights_exp"
    experimental_name = base_folder + "_exp"
    parent_dir = os.path.dirname(os.path.normpath(target_plugin))
    experimental_folder = os.path.join(parent_dir, experimental_name)
    print(f"Proposed experimental folder: {experimental_folder}")

    # 3) Check if experimental folder already exists
    if os.path.exists(experimental_folder):
        answer = input(
            f"Experimental folder already exists at:\n  {experimental_folder}\n"
            "Would you like to delete it? (Y/N): "
        ).strip().lower()
        if answer != "y":
            print("User chose not to delete the existing folder. Exiting.")
            return
        else:
            try:
                shutil.rmtree(experimental_folder)
                print("Deleted existing experimental folder.")
            except Exception as e:
                print(f"Could not delete folder {experimental_folder}: {e}")
                return

    # 4) Ask user if they want to keep the old non-experimental version
    keep_non_exp_answer = input(
        "Do you want to keep the old non-experimental folder? (Y/N): "
    ).strip().lower()

    if keep_non_exp_answer == "y":
        # Copy the entire non-experimental folder to the new experimental folder
        try:
            shutil.copytree(target_plugin, experimental_folder)
            print("Copied non-experimental folder to experimental folder.")
        except Exception as e:
            print(f"Failed to copy folder: {e}")
            return
    else:
        # Rename (move) the folder from non-experimental to experimental
        try:
            os.rename(target_plugin, experimental_folder)
            print("Renamed non-experimental folder to experimental folder.")
        except Exception as e:
            print(f"Failed to rename folder: {e}")
            return

    # --------------------------------------------------------------------------
    # At this point, we have an experimental folder to work with (experimental_folder).
    # We'll proceed to update its contents:
    #  - metadata.txt: set experimental=True
    #  - Append " Experimental" to the name= line (with a leading space, capital 'E').
    # --------------------------------------------------------------------------
    metadata_path = os.path.join(experimental_folder, "metadata.txt")
    if not os.path.exists(metadata_path):
        print(f"metadata.txt not found in {experimental_folder}, cannot update metadata.")
    else:
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                stripped_line = line.strip()

                # If it starts with "experimental=" in any case
                if stripped_line.lower().startswith("experimental="):
                    # Force it to be "experimental=True"
                    new_lines.append("experimental=True\n")
                    continue

                # If it starts with "name="
                if stripped_line.lower().startswith("name="):
                    # For example "name= Lines to Flights"
                    # We want to add " Experimental" at the end if it isn't already there.
                    #   e.g. "Lines to Flights" -> "Lines to Flights Experimental"
                    prefix, value = line.split("=", 1)
                    name_value = value.strip()

                    # In case the user previously appended something, let's be safe:
                    # We'll only add " Experimental" if it doesn't already have it
                    # ignoring case. But the instructions explicitly say to add
                    # " Experimental" with a leading space and capital E at the end.
                    # We'll do that unconditionally, as we know it's non-exp right now.

                    # Just ensure we don't double-add if the user typed something weird:
                    # e.g. "Experimental" might exist. We'll only add if not present:

                    if name_value.lower().endswith("experimental"):
                        # If, for some reason, the word "Experimental" is already there,
                        # do nothing. But this is an edge case.
                        new_lines.append(f"name= {name_value}\n")
                    else:
                        new_lines.append(f"name= {name_value} Experimental\n")
                    continue

                # Otherwise keep the line
                new_lines.append(line)

            # Write back the updated lines
            with open(metadata_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print("Updated metadata.txt successfully.")

        except Exception as e:
            print(f"Could not update metadata.txt: {e}")

    # --------------------------------------------------------------------------
    # Next, deal with the plugin_icon.png swapping. We'll do the same logic in reverse:
    # We want to see if the folder has all three icons:
    #   plugin_icon.png
    #   plugin_icon_exp.png  (or plugin_icon_experimental.png, any case)
    #   plugin_icon_non_exp.png (or plugin_icon_non_experimental.png, any case)
    #
    # If all three are present, we do the swap so that plugin_icon.png
    # is replaced with the *experimental* version (plugin_icon_exp.png).
    # Otherwise, we skip it and inform the user.
    # --------------------------------------------------------------------------

    def find_experimental_icon(folder):
        # Return the path if we found plugin_icon_??? (exp or experimental)
        # ignoring case. Return None if not found.
        for f in os.listdir(folder):
            if f.lower() in ["plugin_icon_exp.png", "plugin_icon_experimental.png"]:
                return os.path.join(folder, f)
        return None

    def find_non_experimental_icon(folder):
        # Return the path if we found plugin_icon_non_exp.png or
        # plugin_icon_non_experimental.png ignoring case.
        for f in os.listdir(folder):
            if f.lower() in [
                "plugin_icon_non_exp.png",
                "plugin_icon_non_experimental.png"
            ]:
                return os.path.join(folder, f)
        return None

    plugin_icon_path = os.path.join(experimental_folder, "plugin_icon.png")
    exp_icon_path = find_experimental_icon(experimental_folder)
    non_exp_icon_path = find_non_experimental_icon(experimental_folder)

    all_three_present = (
            os.path.isfile(plugin_icon_path)
            and exp_icon_path and os.path.isfile(exp_icon_path)
            and non_exp_icon_path and os.path.isfile(non_exp_icon_path)
    )

    if not all_three_present:
        print(
            "Not all three icons (plugin_icon.png, plugin_icon_exp.png, plugin_icon_non_exp.png) "
            "were found in the folder. Not performing the icon swap."
        )
    else:
        # Swap to the experimental icon
        try:
            os.remove(plugin_icon_path)
            print("Deleted plugin_icon.png")
        except Exception as e:
            print(f"Could not delete {plugin_icon_path}: {e}")
            return

        try:
            shutil.copy2(exp_icon_path, plugin_icon_path)
            print("Copied experimental icon over to plugin_icon.png")
        except Exception as e:
            print(f"Could not copy {exp_icon_path} to plugin_icon.png: {e}")
            return

    print("\nConversion to experimental plugin completed successfully.")
    print('--- DONT FORGET TO MATCH VERSIONS AND ZIP ---')


if __name__ == "__main__":
    main(target_plugin)

r"""
chat gpt prompt
okay! this seems to work great! (reffering to the De-Experimentalize script)
Now I want you to make a different skript that does the opposite. 
it takes a non-experimental plugin and makes it experimental. 
The user should be asked at all the same stages for thier inputs. 
Make sure that the input path does not contain _exp and its varents before starting. 
for the plugin folder add a "_exp" to it. for the meta data where the "name=" this is supposed 
to be for normal users to read so use the full word " Experimental" with the capital letter in the 
beginning and separated with a space. If you need clarification on anything let me know. 
"""


