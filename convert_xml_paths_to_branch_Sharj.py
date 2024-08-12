import os
from pathlib import Path
import subprocess


def get_current_branch():
    try:
        # Run the git command to get the current branch name
        result = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check if the command was successful
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"Error: {result.stderr.strip()}")
            return None
    except Exception as e:
        print(f"An exception occurred: {str(e)}")
        return None

    # Example usage:
if __name__ == "__main__":
    branch_name = get_current_branch()
    if branch_name:
        print(f"Current branch is: {branch_name}")