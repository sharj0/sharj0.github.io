
import os
import shutil

target_plugin = r"C:\Users\pyoty\Documents\GitHub\test_braaahnch\sharj0.github.io\ROSORPlugins\PETER_ROSOR_Ortho_Photo_Merger_exp"

# ------------------------------------------------------------------------------
# This function validates whether a string ends in "exp" or "experimental"
# (any case). If it does, returns True and the original string without
# that suffix (and any trailing underscores). Otherwise returns False, original.
#
# Examples:
#   parse_experimental("MyPlugin_exp")        -> (True, "MyPlugin")
#   parse_experimental("MyPlugin_ExPeriMenTal") -> (True, "MyPlugin")
#   parse_experimental("MyPlugin")            -> (False, "MyPlugin")
#
# The rules:
# 1) Check if the string ends with "exp" or "experimental" ignoring case.
# 2) Remove that suffix.
# 3) Remove trailing underscores after the suffix.
# ------------------------------------------------------------------------------
def parse_experimental(input_string: str):
    lowered = input_string.lower()
    # Possible suffixes
    valid_suffixes = ["exp", "experimental"]

    # Check which suffix is present (if any)
    for suffix in valid_suffixes:
        if lowered.endswith(suffix):
            # Identify the cut-off index
            cut_off = len(input_string) - len(suffix)
            # Remove suffix
            new_str = input_string[:cut_off]
            # Now remove any trailing underscores
            new_str = new_str.rstrip("_")
            return True, new_str
    # If none matched
    return False, input_string


def main(target_plugin):

    # 1) Basic checks on the folder name
    if not os.path.exists(target_plugin):
        print(f"Path does not exist: {target_plugin}")
        return

    # Extract base folder name
    base_folder = os.path.basename(os.path.normpath(target_plugin))

    # a) Check that it starts with "PETER_ROSOR"
    if not base_folder.startswith("PETER_ROSOR"):
        print(f"Invalid plugin name. Must start with 'PETER_ROSOR', got: {base_folder}")
        return

    # b) Check that it ends with "exp" or "experimental" (any case)
    is_exp, non_exp_name = parse_experimental(base_folder)
    if not is_exp:
        print(
            "The folder does not end with 'exp' or 'experimental' "
            "in any case. Cannot continue."
        )
        return

    print(f"Validated experimental plugin: {base_folder}")

    # 2) Determine the non-experimental path
    parent_dir = os.path.dirname(os.path.normpath(target_plugin))
    non_exp_folder = os.path.join(parent_dir, non_exp_name)
    print(f"Proposed non-experimental folder: {non_exp_folder}")

    # 3) Check if non-experimental folder already exists
    if os.path.exists(non_exp_folder):
        answer = input(
            f"Non-experimental folder already exists at:\n  {non_exp_folder}\n"
            "Would you like to delete it? (Y/N): "
        ).strip().lower()
        if answer != "y":
            print("User chose not to delete the existing folder. Exiting.")
            return
        else:
            try:
                shutil.rmtree(non_exp_folder)
                print("Deleted existing non-experimental folder.")
            except Exception as e:
                print(f"Could not delete folder {non_exp_folder}: {e}")
                return

    # 4) Ask user if they want to keep the old experimental version
    keep_exp_answer = input(
        "Do you want to keep the old experimental folder? (Y/N): "
    ).strip().lower()

    if keep_exp_answer == "y":
        # Copy the entire experimental folder to the non-experimental folder
        try:
            shutil.copytree(target_plugin, non_exp_folder)
            print("Copied experimental folder to non-experimental folder.")
        except Exception as e:
            print(f"Failed to copy folder: {e}")
            return
    else:
        # Rename (move) the folder from experimental to non-experimental
        try:
            os.rename(target_plugin, non_exp_folder)
            print("Renamed experimental folder to non-experimental folder.")
        except Exception as e:
            print(f"Failed to rename folder: {e}")
            return

    # --------------------------------------------------------------------------
    # At this point, we have a non-experimental folder to work with. We'll
    # proceed to do the conversion within the new folder: non_exp_folder.
    # --------------------------------------------------------------------------
    metadata_path = os.path.join(non_exp_folder, "metadata.txt")
    if not os.path.exists(metadata_path):
        print(f"metadata.txt not found in {non_exp_folder}, cannot update metadata.")
    else:
        # We must:
        # 1) set experimental=False
        # 2) remove "Experimental" or "exp" (any case) from the end of the name= line
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                # Strip for easy comparisons, but we'll keep the newline
                stripped_line = line.strip()

                # If it starts with "experimental=" in any case
                if stripped_line.lower().startswith("experimental="):
                    # Force it to be "experimental=False"
                    new_lines.append("experimental=False\n")
                    continue

                # If it starts with "name="
                if stripped_line.lower().startswith("name="):
                    # For example "name= Lines to Flights Experimental"
                    # We want to remove trailing "exp" or "experimental" ignoring case
                    # and any trailing underscores or spaces
                    # We'll parse out the portion after 'name='
                    prefix, value = line.split("=", 1)
                    name_value = value.strip()

                    # check if name_value ends with exp or experimental
                    is_exp_name, new_name_value = parse_experimental(name_value.rstrip().rstrip("_ ").rstrip())
                    if is_exp_name:
                        # Remove any trailing underscores/spaces from new_name_value
                        new_name_value = new_name_value.rstrip("_ ").rstrip()
                        new_lines.append(f"name= {new_name_value}\n")
                    else:
                        # Keep as-is
                        new_lines.append(line)
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
    # Next, deal with the plugin_icon.png swapping.
    # We expect three files potentially:
    #   plugin_icon.png
    #   plugin_icon_exp.png (could be plugin_icon_experimental.png, any case)
    #   plugin_icon_non_exp.png (could be plugin_icon_non_experimental.png, any case)
    #
    # We want to see if all three exist with their correct names.
    # But the specification says "wherever there's an 'exp' at the end you should
    # also tolerate the whole word version 'experimental' and also any case".
    #
    # For the script: we only check if the following EXACT files exist:
    #   plugin_icon.png
    #   plugin_icon_exp.png
    #   plugin_icon_non_exp.png
    #
    # or we can do more flexible matching. The instructions say "Check to make sure
    # all three are present. If one is missing, continue without raising any errors.
    # Just print to the user that you are not doing anything and why."
    #
    # Because we might have "plugin_icon_experimental.png" or "plugin_icon_EXP.png"
    # we need to find them. We'll attempt to match them ignoring the suffix variants.
    # --------------------------------------------------------------------------

    # Utility to find potential experimental or non-experimental icons.
    def find_icon_variants(folder, base_icon_name):
        """
        Return a list of all files in 'folder' whose stem is 'plugin_icon_{suffix}'
        and suffix is .png, with case-insensitive suffix matching for "exp" or "experimental".
        For example: plugin_icon_exp.png, plugin_icon_EXPerimental.png, etc.
        """
        matched = []
        for item in os.listdir(folder):
            if not os.path.isfile(os.path.join(folder, item)):
                continue
            # We only want .png
            if not item.lower().endswith(".png"):
                continue
            if item.lower().startswith(base_icon_name):
                matched.append(item)
        return matched

    # We'll look for exactly:
    #   "plugin_icon.png" (the live icon),
    #   an 'exp' variant  -> plugin_icon_exp.png / plugin_icon_experimental.png / etc,
    #   a 'non_exp' variant -> plugin_icon_non_exp.png / plugin_icon_non_experimental.png / etc.

    # Because the user specifically wrote that the script expects these three names:
    #   plugin_icon.png
    #   plugin_icon_exp.png
    #   plugin_icon_non_exp.png
    # but also states they can be spelled "exp" or "experimental" in any case.
    # We'll do a small function to test that.

    def any_case_icon_exists(folder, prefix):
        """
        Return the actual filename if a file that matches prefix + 'exp' or 'experimental'
        + .png in any case is found. If multiple, return the first. If none, return None.

        Example:
          any_case_icon_exists('.', 'plugin_icon_') might return 'plugin_icon_EXP.png'
        """
        candidates = os.listdir(folder)
        for c in candidates:
            if c.lower().endswith(".png"):
                # e.g., c = "plugin_icon_EXPerimental.png"
                # we want to see if it starts with prefix (e.g. plugin_icon_) ignoring case
                # then see if the remainder is "exp.png" or "experimental.png" ignoring case
                if c.lower().startswith(prefix.lower()):
                    after_prefix = c[len(prefix):].lower()  # e.g. "experimental.png"
                    # remove extension
                    if after_prefix.endswith(".png"):
                        after_prefix_no_ext = after_prefix.replace(".png", "")
                        if after_prefix_no_ext in ["exp", "experimental"]:
                            return c
        return None

    # Check for plugin_icon.png
    plugin_icon_path = os.path.join(non_exp_folder, "plugin_icon.png")

    exp_variant_name = any_case_icon_exists(non_exp_folder, "plugin_icon_")
    non_exp_variant_name = any_case_icon_exists(non_exp_folder, "plugin_icon_non_")

    # We have to differentiate carefully. The instructions specify exactly:
    #   "plugin_icon.png"
    #   "plugin_icon_exp.png" (or experimental variant)
    #   "plugin_icon_non_exp.png" (or non_experimental variant)
    #
    # We'll handle it in a simpler manner:
    # 1) Check if plugin_icon.png is present (any case?). The instructions do not mention
    #    "plugin_icon.PNG", so let's assume the case is always the same for plugin_icon.png.
    # 2) We must find the "exp" variant in any case.
    # 3) We must find the "non_exp" variant in any case.

    # If one is missing, we do nothing except print a message:
    needed_files = []

    # 1) plugin_icon.png
    if not os.path.isfile(plugin_icon_path):
        needed_files.append("plugin_icon.png")

    # 2) "plugin_icon_exp(.png)" in any case
    #    We'll do a manual check for either plugin_icon_exp.png or plugin_icon_experimental.png
    #    The instructions say we want "plugin_icon_exp.png" or "plugin_icon_experimental.png" (any case).
    #    We'll see if we can find them, ignoring case.

    # Actually, let's define them more concretely:
    #   plugin_icon_exp.png or plugin_icon_experimental.png -> the 'exp' variant
    #   plugin_icon_non_exp.png or plugin_icon_non_experimental.png -> the 'non_exp' variant

    # We'll do direct searching in the folder:

    def find_experimental_icon(folder):
        # Return True if we found plugin_icon_??? (exp or experimental)
        for f in os.listdir(folder):
            if f.lower() in ["plugin_icon_exp.png", "plugin_icon_experimental.png"]:
                return os.path.join(folder, f)
        return None

    def find_non_experimental_icon(folder):
        # Return True if we found plugin_icon_non_exp.png or plugin_icon_non_experimental.png
        for f in os.listdir(folder):
            if f.lower() in [
                "plugin_icon_non_exp.png",
                "plugin_icon_non_experimental.png"
            ]:
                return os.path.join(folder, f)
        return None

    exp_icon_path = find_experimental_icon(non_exp_folder)
    non_exp_icon_path = find_non_experimental_icon(non_exp_folder)

    # Now check if we have them:
    if not plugin_icon_path or not os.path.isfile(plugin_icon_path):
        print("Could not find plugin_icon.png in the folder.")
    if not exp_icon_path:
        print("Could not find an 'experimental' icon variant (e.g. plugin_icon_exp.png).")
    if not non_exp_icon_path:
        print("Could not find a 'non-experimental' icon variant (e.g. plugin_icon_non_exp.png).")

    # According to the spec, we only do the swap if all three are present.
    # "If one is missing you can continue without raising any issues. Just print
    #  to the user that you are not doing anything and why."
    all_three_present = (
            plugin_icon_path
            and os.path.isfile(plugin_icon_path)
            and exp_icon_path
            and os.path.isfile(exp_icon_path)
            and non_exp_icon_path
            and os.path.isfile(non_exp_icon_path)
    )

    if not all_three_present:
        print(
            "Not all three icons (plugin_icon.png, plugin_icon_exp.png, plugin_icon_non_exp.png) "
            "were found in the folder. Not performing the icon swap."
        )
    else:
        # Perform the swap to non-exp icon
        # 1) Delete plugin_icon.png
        try:
            os.remove(plugin_icon_path)
            print("Deleted plugin_icon.png")
        except Exception as e:
            print(f"Could not delete {plugin_icon_path}: {e}")
            return

        # 2) Copy plugin_icon_non_exp.png to plugin_icon.png
        try:
            shutil.copy2(non_exp_icon_path, plugin_icon_path)
            print("Copied non-experimental icon over to plugin_icon.png")
        except Exception as e:
            print(f"Could not copy {non_exp_icon_path} to plugin_icon.png: {e}")
            return

    print("\nConversion to non-experimental plugin completed successfully.")
    print('--- DONT FORGET TO MATCH VERSIONS AND ZIP ---')



r'''
Chat GPT prompt Generate a complete python script that follows the following description. Its ment to take an experimental plugin and make it into a non-experimental version.
This script will first validate the intput. The input should be a folder path staring with "PETER_ROSOR".
target_plugin = r"C:\Users\pyoty\Documents\GitHub\test_braaahnch\sharj0.github.io\ROSORPlugins\PETER_ROSOR_lines_to_flights_exp"
It should also end with the string "exp" or "experimental". Any case is valid. So "Exp" "eXp" are valid.
If the target is not valid, print and do not continue.
Next it will generate the non-experimental version of the path.
Remove whatever "exp" or "experimental" suffix defined eirlier along with any trailing underscores.
Next check if this path already exists. If it does ask the user if they would like to delete the old one. Y/N.
if no then exit the script. If yes then delete the existing path and continue.
Ask the user if they want to keep the old experimental version or not.
If they want to keep the old version then coppy the experimental path to the non-experimental path.
If they do not want to keep the old version then just re-name the folder from the experimental version to the non-experimental version.
Either way you should now have a none experimental folder path to continue working with.
Next is the conversion process, where we convert the contents from experimental to non experimental.
Within the folder there is a "metadata.txt". It's contents look like this:
[general]
name= Lines to Flights Experimental
qgisMinimumVersion=3.0
description= Takes parallel flight-lines and take-off location points and creates flights out of them
version=1.2024.11.12.1
author=Pyotyr Young and Sharjeel AWon
email=pyotyr@msn.com, pyotyr@rosor.ca
icon=plugin_icon.png
experimental=True

Change two lines. first set:
 experimental=False
secondly change the name by removing any reference to Experimental at the end of the string.
Similarly, as above where any case is valid and it can say "exp" or "experimental" and remove any trailing undersocres or spaces.
name= Lines to Flights
Next there should be 3 files called "plugin_icon.png" "plugin_icon_exp.png" "plugin_icon_non_exp.png".
again where ever theres a "exp" at the end you should also tolerate the whole word version of it and also any case.
So "plugin_icon_experimental.png" and "plugin_icon_EXPerimental.png" are also valid.
The different ways of formatting exp can be mixed. So "plugin_icon_non_EXP.png" "plugin_icon_EXPerimental.png" are valid together in the same folder.
Check to make sure all three are present. if one is missing you can contunue without rasing any issues.
Just print to the user that you are not doing anything and why.
If all three are present then you can swap the icon. for context.
The plugin always uses "plugin_icon.png" the contents of "plugin_icon.png" should change depending on if the app is experimental or not.
Thats where "plugin_icon_exp.png" and "plugin_icon_non_exp.png" come in.
They are the two different contents that "plugin_icon.png" can be. So when converting to the non-experimental version.
You have to delete "plugin_icon.png" and copy  "plugin_icon_non_exp.png", then re-name the copy to "plugin_icon.png" so that the plugin will use it.
Ensuring that "plugin_icon_exp.png" exists makes sure that the plugin can be converted back to experimental later if needed because there is no actual loss of data.

because detecting "exp" and its variants happens a lot in the script, and the rules are always the same:
Make a function that validates whether a string is or is not "experimental" and it also outputs what the string would be if it were not experimental.
'''



if __name__ == "__main__":
    main(target_plugin)