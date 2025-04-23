import numpy as np
import math
import pickle
import os
import math
import random
import copy

from .plugin_tools import show_error
from .new_classes.I_survey_area import SurveyArea
from .new_classes.II_strip import Strip
from .new_classes.III_tof_assignment import InitialTOFAssignment, TOFAssignment
from .new_classes.IIII_quadrant import Quadrant
from .new_classes.IIIII_flight import Flight


def filter_tof_name(tof_name):
    # List of prefixes to remove (in lowercase).
    prefixes = ['t', 'tof', 'take_off', 'take-off', 'takeoff']

    lowered = tof_name.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            # Remove the prefix from the original string (preserving case of the rest)
            tof_name = tof_name[len(prefix):]
            break

    # Remove any leading underscores or dashes.
    while tof_name.startswith('_') or tof_name.startswith('-'):
        tof_name = tof_name[1:]

    return tof_name



def assign_lines_to_TOFs(strip_lines, tofs):
    """
    Groups lines based on the closest TOF.

    Each line is assigned to the TOF (from the list `tofs`)
    whose location is closest to either the line's start or end coordinate.

    Returns:
        A list of lists, where each sublist contains the lines assigned
        to the corresponding TOF (in the same order as in the input list).
    """
    # Initialize a list of empty lists for each TOF.
    tof_assignments = [[] for _ in range(len(tofs))]

    # Iterate over each line to determine its closest TOF.
    for line in strip_lines:
        best_distance = float('inf')
        best_index = None

        # Determine the closest TOF by checking distances from both endpoints.
        for i, tof in enumerate(tofs):
            d_start = math.dist(line.start.xy, tof.xy)
            d_end = math.dist(line.end.xy, tof.xy)
            d = d_start if d_start < d_end else d_end

            if d < best_distance:
                best_distance = d
                best_index = i

        # Assign the line to the corresponding TOF's list.
        if best_index is not None:
            tof_assignments[best_index].append(line)

    return tof_assignments


def redistribute_lines_evenly_old(strip):
    """
    Redistributes lines among the initial TOF assignment nodes (strip.children)
    so that the number of assignments having an odd number of lines is minimized.

    The minimum possible is 0 if the number of assignments is even, or 1 if it is odd.

    The function works by:
      1. Identifying all initial TOF assignments with an odd number of lines.
      2. Pairing them up in a way that maximizes the number of adjacent (or nearly adjacent) pairs.
      3. For each pair, determining which assignment (the left or the right) has more lines
         and then cascading a trade along the chain between them:
           - If the donor is to the left of the receiver, then for each node between them
             (including the donor), call give_right().
           - If the donor is to the right, then cascade trading leftwards via give_left().
      4. Repeating the process until the number of odd assignments is minimized.

    Trading is performed using the existing methods:
       - give_right() and give_left()
       (The methods take_right() and take_left() are available if needed for other strategies.)
    """
    assignments = strip.children
    # Determine what the minimal number of odd assignments should be.
    desired_min = 0 if len(assignments) % 2 == 0 else 1

    # Continue trading until the number of odd assignments is as low as possible.
    while True:
        # Identify indices (and nodes) with an odd number of lines.
        odd_info = [(i, node) for i, node in enumerate(assignments) if len(node.children) % 2 != 0]
        odd_count = len(odd_info)
        if odd_count <= desired_min:
            # We've reached the minimum possible.
            break

        # Pair up the odd assignments.
        # (They are naturally in order since assignments is a list;
        #  we pair consecutive odd ones to prefer adjacent pairs.)
        pairs = []
        i = 0
        while i < len(odd_info) - 1:
            left_idx, left_node = odd_info[i]
            right_idx, right_node = odd_info[i + 1]
            pairs.append((left_idx, right_idx))
            i += 2

        # Process each pair by cascading a trade.
        for left_idx, right_idx in pairs:
            left_node = assignments[left_idx]
            right_node = assignments[right_idx]
            # Decide the donor: the one with more lines gives a line so that both become even.
            if len(left_node.children) >= len(right_node.children):
                # Donor is the left node; trade rightwards.
                # Cascade the trade from the donor to the receiver.
                for k in range(left_idx, right_idx):
                    # Each node passes a line to its right neighbour.
                    assignments[k].give_right()
            else:
                # Donor is the right node; trade leftwards.
                for k in range(right_idx, left_idx, -1):
                    # Each node passes a line to its left neighbour.
                    assignments[k].give_left()

import logging # Optional: For logging warnings/errors if preferred over print

import logging
import math # Import math for isinf and isnan if needed later, though unlikely here

# Set up basic logging if you want warnings instead of prints
# logging.basicConfig(level=logging.WARNING)

def redistribute_lines_evenly(strip):
    """
    Redistributes lines among the initial TOF assignment nodes (strip.children)
    so that the number of assignments having an odd number of lines is minimized.

    The minimum possible is 0 if the number of assignments is even, or 1 if it is odd.

    This function attempts to resolve pairs of odd-count assignments by trading
    lines between them. It includes protection against infinite loops and handles
    cases where the absolute minimum might be locally unreachable via pairing.

    Args:
        strip: An object representing the strip, expected to have attributes:
               - children: A list of assignment nodes. Each node should have:
                   - children: A list representing the lines assigned to it.
                   - give_right(): Method to pass one line to the right neighbor.
                                   Should ideally handle cases where the node
                                   has 0 children (e.g., by doing nothing).
                   - give_left(): Method to pass one line to the left neighbor.
                                  Should ideally handle cases where the node
                                  has 0 children (e.g., by doing nothing).
               - end_point_list: A list used to calculate the loop limit.

    Raises:
        RuntimeError: If the loop iterates more than the calculated limit,
                      indicating a non-terminating state despite the fixes.
        AttributeError: If 'strip' does not have 'end_point_list'.

    Returns:
        int: The final count of assignments with an odd number of lines.
             This might be > desired_min if the target was unreachable.
    """
    assignments = strip.children
    num_assignments = len(assignments)
    if num_assignments < 2:
        # Nothing to redistribute if 0 or 1 assignment
        return 0 if num_assignments == 0 else len(assignments[0].children) % 2

    # Determine the theoretical minimum number of odd assignments.
    desired_min = 0 if num_assignments % 2 == 0 else 1

    # --- Loop Protection Setup ---
    try:
        # Use float('inf') if end_point_list is unexpectedly huge to avoid OverflowError
        limit_base = len(strip.end_point_list) * 2
        if limit_base == float('inf') or limit_base > 10000: # Safety cap if base is enormous
             loop_limit = 10000**2 # A very large but bounded number
             logging.warning(f"Calculated loop limit base ({limit_base}) was excessive; capping limit.")
        else:
             loop_limit = limit_base ** 2
        # Ensure loop_limit is not excessively large or non-finite
        if loop_limit <= 0 or math.isinf(loop_limit) or math.isnan(loop_limit):
            logging.warning(f"Invalid calculated loop limit ({loop_limit}). Setting a default limit.")
            loop_limit = 100000 # Default large limit
    except AttributeError:
        raise AttributeError("The 'strip' object must have an 'end_point_list' attribute.")
    except Exception as e:
        logging.error(f"Error calculating loop limit: {e}. Setting a default limit.")
        loop_limit = 100000 # Default large limit

    iteration_count = 0
    # --- End Loop Protection Setup ---

    while True:
        # --- Loop Protection Check ---
        iteration_count += 1
        if iteration_count > loop_limit:
            odd_info_for_log = [(i, len(node.children)) for i, node in enumerate(assignments) if len(node.children) % 2 != 0]
            logging.error(f"Loop limit ({loop_limit}) exceeded in redistribute_lines_evenly. "
                          f"Current odd assignments (index, count): {odd_info_for_log}")
            raise RuntimeError(
                f"Loop limit ({loop_limit}) exceeded in redistribute_lines_evenly. "
                f"Check for potential infinite loop or complex oscillation. "
                f"Number of assignments: {num_assignments}. Current odd count: {len(odd_info_for_log)}."
            )
        # --- End Loop Protection Check ---

        # Identify indices (and nodes) with an odd number of lines.
        odd_info = [(i, node) for i, node in enumerate(assignments) if len(node.children) % 2 != 0]
        odd_count = len(odd_info)

        # --- Termination Checks ---
        if odd_count <= desired_min:
            # Successfully reached the target minimum (or better).
            # logging.info(f"Redistribution complete in {iteration_count} iterations. Final odd count: {odd_count}")
            return odd_count # Return the final count

        # --- Check for Unresolvable State (Stagnation) ---
        # If the number of odd nodes is odd and > desired_min, the pairing
        # logic will leave one node out. If odd_count is 1 and desired_min is 0,
        # we are stuck because no pairs can be formed.
        if odd_count == 1 and desired_min == 0:
            logging.warning(
                f"Redistribution stuck with {odd_count} odd assignment "
                f"(target was {desired_min}). Cannot resolve further with pairing. "
                f"Stopping after {iteration_count} iterations."
            )
            return odd_count # Return the current count

        # --- Pair Up Odd Assignments ---
        # Pair consecutive odd assignments to prioritize local trades.
        pairs = []
        i = 0
        while i < odd_count - 1: # Important: stops before the last one if odd_count is odd
            left_idx, _ = odd_info[i]
            right_idx, _ = odd_info[i+1]
            pairs.append((left_idx, right_idx))
            i += 2

        # If pairs list is empty here, it implies odd_count was 1,
        # which should have been caught by the stagnation check above.
        # Add an assertion for safety, though it shouldn't be triggered.
        if not pairs and odd_count > desired_min:
             # This should not happen due to the check above
             logging.error(f"Inconsistent state: odd_count={odd_count}, desired_min={desired_min}, but no pairs formed. Breaking.")
             return odd_count


        # --- Process Pairs ---
        traded_in_iteration = False
        for left_idx, right_idx in pairs:
            # Re-fetch nodes in case previous trades affected them, although indices are fixed
            if left_idx >= num_assignments or right_idx >= num_assignments:
                 logging.warning(f"Invalid indices ({left_idx}, {right_idx}) encountered in pairs. Skipping pair.")
                 continue

            left_node = assignments[left_idx]
            right_node = assignments[right_idx]

            # Check current lengths *before* deciding trade direction
            len_left = len(left_node.children)
            len_right = len(right_node.children)

            # Ensure both are still odd (a previous trade in the same iteration *could* have fixed one)
            # This check is technically redundant if pairing is done once per iteration, but adds safety.
            if len_left % 2 == 0 or len_right % 2 == 0:
                # logging.debug(f"Skipping pair ({left_idx}, {right_idx}): one or both are now even.")
                continue

            # Decide the donor: the one with more lines gives. If equal, left gives.
            if len_left >= len_right:
                # Donor is left node; trade rightwards.
                # Cascade from donor (inclusive) to receiver (exclusive).
                # logging.debug(f"Trading Right: {left_idx} ({len_left}) -> {right_idx} ({len_right})")
                for k in range(left_idx, right_idx):
                    try:
                        # Assume give_right() returns True on success/action, False/None otherwise
                        # Or simply call it and trust it handles empty state.
                        # We need some way to know if *any* trade happened in the iteration
                        # Let's assume calling it implies intent/potential trade
                        assignments[k].give_right()
                        traded_in_iteration = True # Mark that a trade attempt occurred
                    except IndexError:
                         logging.error(f"IndexError during rightward trade at index {k}. Aborting trade for this pair.")
                         break # Stop trading for this pair
                    except Exception as e:
                         logging.error(f"Unexpected error during give_right at index {k}: {e}. Aborting trade for this pair.")
                         # Depending on severity, might want to raise e or just break
                         break # Stop trading for this pair
            else:
                # Donor is right node; trade leftwards.
                # Cascade from donor (inclusive) down to receiver (exclusive).
                # logging.debug(f"Trading Left: {right_idx} ({len_right}) -> {left_idx} ({len_left})")
                for k in range(right_idx, left_idx, -1):
                    try:
                        assignments[k].give_left()
                        traded_in_iteration = True # Mark that a trade attempt occurred
                    except IndexError:
                         logging.error(f"IndexError during leftward trade at index {k}. Aborting trade for this pair.")
                         break # Stop trading for this pair
                    except Exception as e:
                         logging.error(f"Unexpected error during give_left at index {k}: {e}. Aborting trade for this pair.")
                         break # Stop trading for this pair

        # --- Add a check for overall stagnation ---
        # If we went through an iteration, calculated pairs, attempted trades,
        # but nothing actually happened (e.g., all potential donors were empty),
        # then we are also stuck.
        # This is a secondary check; the primary issue was the odd_count == 1 case.
        # if not traded_in_iteration and odd_count > desired_min:
        #      logging.warning(f"Redistribution stalled: No effective trades occurred in iteration {iteration_count} "
        #                      f"despite {odd_count} odd assignments > desired_min {desired_min}. Stopping.")
        #      return odd_count


    # This point should technically be unreachable due to the return statements
    # inside the loop, but added for completeness.
    # final_odd_count = sum(1 for node in assignments if len(node.children) % 2 != 0)
    # logging.info(f"Redistribution loop exited unexpectedly. Final odd count: {final_odd_count}")
    # return final_odd_count



def construct_the_upper_hierarchy(lines, tofs, unique_strip_letters, prefer_even_number_of_lines):
    survey = SurveyArea("SurveyArea")
    if len(unique_strip_letters) == 0:
        txt = 'No strips have been assigned'
        show_error(txt)
        raise ValueError(txt)

    for strip_letter in unique_strip_letters:

        strip = Strip(f"Strip-{strip_letter}")
        survey.add_child_to_right(strip)

        strip_lines = [line for line in lines if line.strip_letter == strip_letter]
        strip_tof_assignment_lines = assign_lines_to_TOFs(strip_lines, tofs)

        # making temporary INITIAL tof_assignment objs. their direct children are lines.
        for tof, initial_tof_assignment_lines in zip(tofs, strip_tof_assignment_lines):
            tof.filtered_name = filter_tof_name(tof.tof_name)
            if not initial_tof_assignment_lines:
                continue
            prefix = "TEMP INITIAL "
            tof_assignment_name = f"{prefix}TOF{tof.filtered_name}-asmt-S{strip_letter}"
            initial_tof_assignment = InitialTOFAssignment(tof_assignment_name, tof)
            initial_tof_assignment.prefix = prefix
            for line in initial_tof_assignment_lines:
                initial_tof_assignment.add_child_to_right(line)

            strip.add_child_to_right(initial_tof_assignment)

        if prefer_even_number_of_lines:
            redistribute_lines_evenly(strip)

        for initial_tof_assignment in strip.children:
            initial_tof_assignment = strip.remove_left_child()
            prefix = initial_tof_assignment.prefix
            if initial_tof_assignment.name.startswith(prefix):
                new_name = initial_tof_assignment.name[len(prefix):]
            tof_assignment = TOFAssignment(new_name,
                                           initial_tof_assignment.tof,
                                           initial_tof_assignment.children)
            tof_assignment.tof.children.append(tof_assignment)
            strip.add_child_to_right(tof_assignment)
            #right now, we are not making the quad any different form tof_assignment
            quad = Quadrant(f"Quadrant-S{strip_letter}-T{tof_assignment.tof.filtered_name}")
            quad.initial_lines = tof_assignment.initial_lines
            tof_assignment.add_child_to_right(quad)
            print(f'done {strip_letter =} {tof_assignment} out of {len(strip.children)}')

    return survey

def validate_flight(flight, max_number_of_lines, prefer_even, max_flt_size):
    """
    Checks if a flight meets three criteria:
      1. Its number of lines is <= max_number_of_lines.
      2. If prefer_even is True, the number of lines must be even.
      3. The drone path length (computed by generate_drone_path()) is less than max_flt_size.
         (generate_drone_path() works only because the flight is assigned to a quadrant.)
    """
    num_lines = len(flight.children)

    #quad = flight.parent
    #num_lines_per_flight = [len(flight.children) for flight in quad.flight_list]
    #print(f'lines in quad {len(quad.line_list)}, {num_lines_per_flight =}')
    #line_assignment = [line.parent for line in quad.line_list]
    #print(f'{line_assignment =}')

    if num_lines > max_number_of_lines:
        return False
    # Only enforce even-number check if there's more than one line.
    if prefer_even and (num_lines % 2 != 0):
        # we make an exception if this is the last flight of the quadrant
        if flight.right_neighbour:
            return False
        else:
            #last flight of the quadrant it's okay to be odd
            pass

    if flight.generate_drone_path() > max_flt_size:
        return False
    if not hasattr(flight, 'utm_fly_list'):
        print('somthing is wrong with "generate_drone_path"')
    return True


def split_flight(flight, max_number_of_lines, prefer_even, max_flt_size, flight_settings):
    """
    Splits a flight into two parts by moving its rightmost lines.
    The rightmost line is removed from the flight (which remains in the quadrant)
    and assigned to a new flight (the "split_right" flight).
    This is repeated until the left flight (the original) meets the criteria.
    Returns a tuple: (left_flight, right_flight)
    """
    right_flight = Flight(f"{flight.name}_split_right")
    right_flight.flight_settings = flight_settings
    quadrant = flight.parent
    quadrant.add_child_to_right(right_flight)
    line = flight.remove_right_child()
    right_flight.add_child_to_left(line)
    while len(flight.children) > 1 and not validate_flight(flight, max_number_of_lines, prefer_even, max_flt_size):
        line = flight.remove_right_child()
        right_flight.add_child_to_left(line)
    return flight, right_flight


def process_flight(flight, max_number_of_lines, prefer_even, max_flt_size, flight_settings):
    """
    Assumes the flight is already assigned to the quadrant.
    If the flight passes validation, it is accepted.
    Otherwise, the flight is split—leaving the left flight (which remains in the quadrant)
    and generating a right split flight. If the right flight has any lines, it is added to the quadrant
    and then processed recursively (same checks, and possibly further splits).
    """
    if validate_flight(flight, max_number_of_lines, prefer_even, max_flt_size):
        print("accepted")
        return

    # Flight fails validation; split it.
    left_flight, right_flight = split_flight(flight, max_number_of_lines, prefer_even, max_flt_size, flight_settings)

    # Process the right flight (if any) with the same treatment.
    if right_flight.children:
        process_flight(right_flight, max_number_of_lines, prefer_even, max_flt_size, flight_settings)


def construct_the_lower_hierarchy(survey_area,
                                  max_flt_size,
                                  max_number_of_lines_per_flight,
                                  prefer_even_number_of_lines):

    """
    For each quadrant in the survey_area:
      1. Create a prototype flight by adding all its initial lines.
      2. Immediately assign this flight to the quadrant (so generate_drone_path() works).
      3. Validate the flight; if it fails, split it.
         Each split-off (right) flight is added to the quadrant and processed recursively.
      This guarantees that the quadrant ends up with at least one flight.
    """
    for quadrant in survey_area.quadrant_list:
        if not quadrant.initial_lines:
            continue

        # Create the prototype flight and add all initial lines.
        prototype_flight = Flight('prototype')
        prototype_flight.flight_settings = copy.copy(survey_area.flight_settings)
        for line in quadrant.initial_lines:
            prototype_flight.add_child_to_right(line)

        # Immediately assign the prototype flight to the quadrant.
        quadrant.add_child_to_right(prototype_flight)

        # Process the prototype flight.
        process_flight(prototype_flight,
                       max_number_of_lines_per_flight,
                       prefer_even_number_of_lines,
                       max_flt_size,
                       survey_area.flight_settings)

        for flight in quadrant.children:
            if not hasattr(flight, 'utm_fly_list'):
                print('unvalidated flight still exists in quadrant')

class ColorCycler:
    """
    Cycles through a fixed list of colors, omitting exactly one
    randomly chosen color per cycle. The cycle length is always
    one less than the total number of available colors.
    The relative order of the non-omitted colors is preserved.
    """
    def __init__(self):
        # The master list of colors in their fixed order
        self._master_colors = [
            'ff5190c5',  # Brightened Blue
            'ff55b94e',  # Brightened Green
            'ffb084d2',  # Brightened Purple
            'ffa97a69',  # Brightened Brown
            'fff0a1d0',  # Brightened Pink
            'ff999999',  # Brightened Gray
            'ffcdd24c',  # Brightened Olive
            'ff49d8e2',  # Brightened Cyan
            'ffff9960',  # Brightened Orange
            #new ones
            'ffff0000',  # Bright Red
            'ff00ff7f',  # Chartreuse / Bright Lime
            'ffff00ff',  # Bright Magenta / Fuchsia
        ]
        self._num_master_colors = len(self._master_colors)
        self._cycle_length = self._num_master_colors - 1 # Cycle length is 8

        # State variables
        self._omitted_color_for_current_cycle = None
        self._master_index = 0 # Current position in the _master_colors list
        self._yielded_in_current_cycle = 0 # How many colors returned in this cycle

    def _start_new_cycle(self):
        """Selects a new color to omit for the upcoming cycle."""
        self._omitted_color_for_current_cycle = random.choice(self._master_colors)
        self._yielded_in_current_cycle = 0
        # print(f"--- Starting new cycle. Omitting: {self._omitted_color_for_current_cycle} ---") # Debug

    def __iter__(self):
        return self

    def __next__(self):
        """Returns the next color, skipping the omitted one for the current cycle."""
        if not self._master_colors:
            raise StopIteration("Master color list is empty.")

        # Check if we need to start a new cycle
        # This happens either initially or after _cycle_length colors were yielded
        if self._omitted_color_for_current_cycle is None:
            self._start_new_cycle()

        # Find the next valid color in the master list
        while True:
            current_color = self._master_colors[self._master_index]
            # Advance the master index for the *next* call, wrapping around
            self._master_index = (self._master_index + 1) % self._num_master_colors

            # Check if this color is the one omitted for this cycle
            if current_color == self._omitted_color_for_current_cycle:
                continue # Skip this color and check the next one in the master list

            # If the color is not omitted, yield it
            self._yielded_in_current_cycle += 1

            # Check if this color completes the current cycle
            if self._yielded_in_current_cycle == self._cycle_length:
                # Mark that the next call should start a new cycle
                self._omitted_color_for_current_cycle = None

            # Return the valid color
            return current_color

def calculate_projection(point, angle):
    """Calculate the projection of a point on a line defined by an angle."""
    angle_ccwE = 90 - angle
    # Convert angle to radians
    angle_rad = np.deg2rad(angle_ccwE)

    # Direction vector of the line
    direction_vector = np.array([np.cos(angle_rad), np.sin(angle_rad)])

    # Calculate the dot product of the point and the direction vector
    projection = np.dot(point, direction_vector)

    return projection


def sort_lines_and_tofs(lines, tofs, sort_angle):
    """Sort lines and tofs based on their projections on a line at a specified angle."""

    # Calculate projections for lines
    lines_with_projections = [(line, calculate_projection(line.centroid_xy, sort_angle)) for line in lines]
    # Sort lines by projection value
    lines_with_projections.sort(key=lambda x: x[1])

    # Extract sorted lines
    sorted_lines = [line for line, proj in lines_with_projections]

    # Calculate projections for tofs
    tofs_with_projections = [(tof, calculate_projection(tof.xy, sort_angle)) for tof in tofs]
    # Sort tofs by projection value
    tofs_with_projections.sort(key=lambda x: x[1])

    # Extract sorted tofs
    sorted_tofs = [tof for tof, proj in tofs_with_projections]

    return sorted_lines, sorted_tofs


def get_name_of_non_existing_output_file(base_filepath, additional_suffix='', new_extention=''):
    # Function to create a unique file path by adding a version number
    base, ext = os.path.splitext(base_filepath)
    if new_extention:
        ext = new_extention
    new_out_file_path = f"{base}{additional_suffix}{ext}"

    if not os.path.exists(new_out_file_path):
        return new_out_file_path

    version = 2
    while os.path.exists(f"{base}{additional_suffix}_v{version}{ext}"):
        version += 1
    return f"{base}{additional_suffix}_v{version}{ext}"


def load_pickle(pickle_path_in):
    with open(pickle_path_in, 'rb') as file:
        pickled_obj = pickle.load(file)
    return pickled_obj
