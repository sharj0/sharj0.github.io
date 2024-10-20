import time
import os
from subprocess import Popen
from .plugin_tools import show_error

from pathlib import Path

import sys
# IMPORT 3rd PARTY libraries
plugin_dir = os.path.dirname(os.path.realpath(__file__))
# Path to the subdirectory containing the external libraries
lib_dir = os.path.join(plugin_dir, 'plugin_3rd_party_libs')
# Add this directory to sys.path so Python knows where to find the external libraries
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
from pyautogui import press, write
from pygetwindow import getAllWindows

def print_active_windows():
    # Get a list of all open windows
    open_windows = getAllWindows()
    # Print the title of each window
    for window in open_windows:
        print(window.title)

def close_all_windows(partial_window_title):
    # Get all open windows
    open_windows = getAllWindows()
    for win in open_windows:
        # Check if window title contains the partial title
        if partial_window_title.lower() in win.title.lower():
            win.close()  # Close the window
            print(f'Closed window "{win.title}"')

def wait_for_win_to_open_with_exception(partial_window_title, exception_window_title, ignore_list):
    while True:  # Keep trying to find either of the windows
        open_windows = getAllWindows()  # Get all open windows
        # Filter out windows that should be ignored
        filtered_windows = []
        for win in open_windows:
            ignored = False
            for ignore_title in ignore_list:
                if ignore_title.lower() in win.title.lower():
                    ignore_list.remove(ignore_title)  # Remove from ignore list to only ignore once
                    ignored = True
                    break  # Break inner loop if this window is to be ignored
            if not ignored:
                filtered_windows.append(win)

        exception_found = False
        target_found = False

        for win in filtered_windows:
            if exception_window_title.lower() in win.title.lower():  # Check if window title contains the exception title
                exception_found = True
                break  # Exit the loop since exception window has precedence

            elif partial_window_title.lower() in win.title.lower():  # Check if window title contains the partial title
                target_found = True

        if exception_found:
            return True  # Return True if the exception window was found and activated
        elif target_found:
            return False  # Return False if the target window was found but not the exception

        # If no matching window is found, wait a bit and try again
        print(f'Waiting for window containing "{partial_window_title}" or "{exception_window_title}" to open')
        time.sleep(0.1)

def wait_for_win_to_open(partial_window_title):
    while True:  # Keep trying to find the window
        open_windows = getAllWindows()  # Get all open windows
        for win in open_windows:
            if partial_window_title.lower() in win.title.lower():  # Check if window title contains the partial title
                return  # Exit the function once the desired window is activated
        # If no matching window is found, wait a bit and try again
        print(f'Waiting for window "{partial_window_title}" to open')
        time.sleep(0.1)

def automated_survey_manager(executable_path,magdata_path,export_file_path):

    # Close all 'Geometrics Survey Manager' windows before opening a new instance
    close_all_windows('Geometrics Survey Manager')

    if not os.path.exists(executable_path):
        installer_path = os.path.join(plugin_dir, 'SurveyManagerInstaller-3.0.1314.0.exe')
        Popen(installer_path)

    # Start the executable
    try:
        Popen(executable_path)
    except:
        mesage = 'COULD NOT FIND PROVIDED .EXE Make sure survey manager is installed and path is correct'
        retval = show_error(mesage)

    #print_active_windows()
    wait_for_win_to_open('Geometrics Survey Manager')


    # Simulate key presses: TAB, DOWN ARROW, ENTER
    press('tab')
    press('tab')
    press('enter')
    press('tab')
    press('tab')
    press('enter')
    press('tab')
    press('tab')
    press('enter')
    wait_for_win_to_open("Choose MagArrow data file")
    write(magdata_path)
    press('enter')
    wait_for_win_to_open("MagArrow Export Options")
    press('tab')
    press('home')
    press('enter')
    wait_for_win_to_open("Choose a name for the CSV file")
    write(Path(Path(export_file_path).stem + Path(export_file_path).suffix).as_posix())
    press('enter')
    exception = wait_for_win_to_open_with_exception('Completion',
                                                    'Choose a name for the CSV file',
                                                    ignore_list=["Choose a name for the CSV file"])
    if exception:
        print('clearing exception...')
        press('enter')
        wait_for_win_to_open('Completion')
        press('enter')

    close_all_windows('Geometrics Survey Manager')
    print(f'saved: {export_file_path}')
    return export_file_path