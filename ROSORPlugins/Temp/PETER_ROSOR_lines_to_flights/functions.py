import numpy as np

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