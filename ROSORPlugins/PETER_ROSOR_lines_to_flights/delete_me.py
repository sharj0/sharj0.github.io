import numpy as np


def calculate_projection(point, angle):
    """Calculate the projection of a point on a line defined by an angle."""
    # Convert angle to radians
    angle_ccwE = 90 - angle
    angle_rad = np.deg2rad(angle_ccwE)

    # Direction vector of the line
    direction_vector = np.array([np.cos(angle_rad), np.sin(angle_rad)])

    # Calculate the dot product of the point and the direction vector
    projection = np.dot(point, direction_vector)

    return projection


def determine_sort_angle(ave_line_ang_cwN, line_flight_order_reverse):
    """Determine the sorting angle based on the average line angle and reverse flag."""
    if not line_flight_order_reverse:
        sort_angle = ave_line_ang_cwN + 90
    else:
        sort_angle = ave_line_ang_cwN - 90
    return sort_angle


def sort_lines_and_tofs(lines, tofs, line_flight_order_reverse, ave_line_ang_cwN):
    """Sort lines and tofs based on their projections on a line at a specified angle."""
    sort_angle = determine_sort_angle(ave_line_ang_cwN, line_flight_order_reverse)

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


# Example usage with provided data
class Line:
    def __init__(self, centroid_xy):
        self.centroid_xy = centroid_xy


class Tof:
    def __init__(self, xy):
        self.xy = xy


# Sample data
lines = [Line((363264.79224298295, 7060353.0112556685))]
tofs = [Tof((361901.957666634, 7059920.467250216))]
line_flight_order_reverse = False
ave_line_ang_cwN = 2.500000000001193

# Sorting lines and tofs
sorted_lines, sorted_tofs = sort_lines_and_tofs(lines, tofs, line_flight_order_reverse, ave_line_ang_cwN)

# Output sorted lines and tofs
print("Sorted Lines:")
for line in sorted_lines:
    print(line.centroid_xy)

print("\nSorted Tofs:")
for tof in sorted_tofs:
    print(tof.xy)
