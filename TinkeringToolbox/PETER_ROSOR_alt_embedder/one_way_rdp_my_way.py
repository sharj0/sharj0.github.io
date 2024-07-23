import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

def get_perp_dist(point, start_line, end_line):
    cross = np.cross(np.array(end_line) - np.array(start_line), np.array(start_line) - np.array(point))
    lin = np.linalg.norm(np.array(end_line) - np.array(start_line))
    perp_dist = cross/lin
    return perp_dist

# Function to get the coordinates of a parallel line at a given distance
def get_parallel_line_coords(start, end, distance):
    # Calculate the direction vector of the line
    direction = np.array(end) - np.array(start)
    length = np.linalg.norm(direction)
    unit_direction = direction / length

    # Calculate the normal vector to the line (90 degrees rotation)
    normal = np.array([-unit_direction[1], unit_direction[0]])

    # Calculate the parallel line coordinates
    start_parallel = np.array(start) + distance * normal
    end_parallel = np.array(end) + distance * normal
    return start_parallel, end_parallel

def plot_points(points_orig, points, start_index, end_index, max_delta_ind, keep_mask):
    # Plotting the current recursion iteration
    plt.figure()
    plt.plot(np.array(points_orig)[:, 0], np.array(points_orig)[:, 1], 'bo-', label='Original Points')
    plt.plot(np.array(points)[start_index:end_index+1, 0], np.array(points)[start_index:end_index+1, 1], 'ro-',
             label='Points under consideration')
    plt.plot(np.array(points)[keep_mask][:, 0], np.array(points)[keep_mask][:, 1], 'ko-', label='kept Points')

    plt.plot([points[start_index][0], points[end_index][0]], [points[start_index][1], points[end_index][1]], 'g--')
    # Get and plot the parallel line coordinates
    start_parallel, end_parallel = get_parallel_line_coords(points[start_index], points[end_index], -epsilon)
    plt.plot([start_parallel[0], end_parallel[0]], [start_parallel[1], end_parallel[1]], 'm--')
    start_parallel, end_parallel = get_parallel_line_coords(points[start_index], points[end_index], epsilon)
    plt.plot([start_parallel[0], end_parallel[0]], [start_parallel[1], end_parallel[1]], 'm--')
    plt.scatter(points[max_delta_ind][0], points[max_delta_ind][1], c='k', s=300, label='Max Delta Point')
    plt.legend()
    plt.show()

def sort_points_by_x(points):
    return sorted(points, key=lambda point: point[0])


def interpolate_points(points, keep_mask):
    # Extract x and y coordinates from points
    x, y = zip(*points)
    x = np.array(x)
    y = np.array(y)

    # Create arrays of x and y where keep_mask is True
    x_keep = x[keep_mask]
    y_keep = y[keep_mask]

    # Create linear interpolation function
    f = interp1d(x_keep, y_keep, kind='linear', fill_value="extrapolate")

    # Interpolate y-values where keep_mask is False
    y_interp = y.copy()
    y_interp[~keep_mask] = f(x[~keep_mask])

    return list(zip(x, y_interp))

def my_simp(points, epsilon, debug_statements=True, plot_stuff=True):
    keep_mask = np.ones((len(points)), dtype=bool)
    points = sort_points_by_x(points)
    keep_mask = my_simp_recursion(points, epsilon, keep_mask, debug_statements=debug_statements, plot_stuff=plot_stuff)
    if plot_stuff:
        points_keep = interpolate_points(points, keep_mask)
        plot_points(points, points_keep, 0, len(points)-1, 0, keep_mask)
    return keep_mask

def check_for_removed_points(steep_turn_indx, keep_mask):
    removed_point_left, removed_point_right = None, None

    if not keep_mask[steep_turn_indx + 1]:
        removed_point_right = steep_turn_indx + 1
    if not keep_mask[steep_turn_indx - 1]:
        removed_point_left = steep_turn_indx - 1

    return removed_point_left, removed_point_right


# Algorithm to simplify a discrete curve recursively but should only create shortcuts to values below the curve
def my_simp_recursion(points, epsilon, keep_mask, debug_statements=True, plot_stuff=True):
    points_keep = interpolate_points(points, keep_mask)
    relative_angles = get_relative_angles(points_keep)
    steep_turn_sort = np.flip(np.argsort(relative_angles)) + 1
    changes_made = False
    for steep_turn_indx in steep_turn_sort:
        if relative_angles[steep_turn_indx-1] <= 0:
            continue

        perp_dist = get_perp_dist(points_keep[steep_turn_indx],
                                  points_keep[steep_turn_indx-1],
                                  points_keep[steep_turn_indx+1])
        removed_point_left, removed_point_right = check_for_removed_points(steep_turn_indx, keep_mask)
        if removed_point_left:
            print(f'{perp_dist=}, {removed_point_left=}')
            print(f'{perp_dist=}, {points[removed_point_left]=}')
            perp_old_left = get_perp_dist(points[removed_point_left],
                                      points_keep[steep_turn_indx - 1],
                                      points_keep[steep_turn_indx + 1])
            print(f'{perp_dist=}, {perp_old_left=}')
            if perp_old_left > perp_dist:
                perp_dist = perp_old_left

        if removed_point_right:
            print(f'{perp_dist=}, {removed_point_right=}')
            print(f'{perp_dist=}, {points[removed_point_right]=}')
            perp_old_right = get_perp_dist(points[removed_point_right],
                                      points_keep[steep_turn_indx - 1],
                                      points_keep[steep_turn_indx + 1])
            print(f'{perp_dist=}, {perp_old_right=}')
            if perp_old_right > perp_dist:
                perp_dist = perp_old_right

        if debug_statements:
            print(f'{steep_turn_indx=} {relative_angles[steep_turn_indx-1]=} {perp_dist=} {epsilon=} ')
        if plot_stuff:
            plot_points(points, points_keep, steep_turn_indx - 1, steep_turn_indx + 1, steep_turn_indx, keep_mask)
        if perp_dist < epsilon:
            keep_mask[steep_turn_indx] = 0
            changes_made = True

    if changes_made:
        if debug_statements:
            print(f'recursion ! {keep_mask=}')
        my_simp_recursion(points, epsilon, keep_mask, debug_statements=debug_statements, plot_stuff=plot_stuff)

    return keep_mask


def get_relative_angles(points):
    angles = []

    for i in range(1, len(points) - 1):
        # Calculate vectors
        vec1 = np.array(points[i]) - np.array(points[i - 1])
        vec2 = np.array(points[i + 1]) - np.array(points[i])

        # Calculate angle between vec1 and vec2
        unit_vec1 = vec1 / np.linalg.norm(vec1)
        unit_vec2 = vec2 / np.linalg.norm(vec2)
        dot_product = np.dot(unit_vec1, unit_vec2)
        angle = np.arccos(np.clip(dot_product, -1.0, 1.0))

        # Determine the sign of the angle using the cross product
        cross_product = np.cross(unit_vec1, unit_vec2)
        if cross_product < 0:
            angle = -angle  # Right turn
        else:
            angle = angle  # Left turn

        # Convert angle from radians to degrees
        angle_degrees = np.degrees(angle)
        angles.append(angle_degrees)

    return angles



if __name__ == "__main__":
    points = [(0, 0), (1, 0.1), (2, -0.1), (3, 5), (4, 5.4), (5, 7), (6, 8.1), (7, 9), (8, 9)]
    epsilon = 1.1
    keep_mask = my_simp(points, epsilon)
