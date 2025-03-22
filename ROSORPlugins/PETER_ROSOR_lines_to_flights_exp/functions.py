import numpy as np
import pickle
import os

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
