import numpy as np
import matplotlib.pyplot as plt

def just_perp_dist(point, start_line, end_line):
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

def plot_points(points, start_index, end_index, max_delta_ind, keep_mask):
    # Plotting the current recursion iteration
    plt.figure()
    plt.plot(np.array(points)[:, 0], np.array(points)[:, 1], 'bo-', label='Original Points')
    plt.plot(np.array(points)[keep_mask][:, 0], np.array(points)[keep_mask][:, 1], 'ko-', label='kept Points')
    plt.plot(np.array(points)[start_index:end_index+1, 0], np.array(points)[start_index:end_index+1, 1], 'ro-',
             label='Points under consideration')
    plt.plot([points[start_index][0], points[end_index][0]], [points[start_index][1], points[end_index][1]], 'g--')
    # Get and plot the parallel line coordinates
    start_parallel, end_parallel = get_parallel_line_coords(points[start_index], points[end_index], -epsilon)
    plt.plot([start_parallel[0], end_parallel[0]], [start_parallel[1], end_parallel[1]], 'm--')
    start_parallel, end_parallel = get_parallel_line_coords(points[start_index], points[end_index], epsilon)
    plt.plot([start_parallel[0], end_parallel[0]], [start_parallel[1], end_parallel[1]], 'm--')
    plt.scatter(points[max_delta_ind][0], points[max_delta_ind][1], c='k', s=300, label='Max Delta Point')
    plt.legend()
    plt.show()


def get_max_delta(points, start_index, end_index):
    delta_max = 0
    index = start_index
    print(points)
    # Iterates through each point
    print(f'for i in range {start_index=} {end_index=}')
    for i in range(start_index+1, end_index):
        # Calculates the difference between the current point and the start and end of the input array (which changes due to recursion)
        perp_dist = just_perp_dist(points[i], points[start_index], points[end_index])
        print(f'{i=} {perp_dist=}')
        if np.abs(perp_dist) > np.abs(delta_max):
            index = i
            delta_max = perp_dist
    print(f'selected {index=} {delta_max=}')
    return index, delta_max


def my_rdp(points, epsilon):
    start_index = 0
    end_index = len(points) - 1
    delta_max_index = 0
    keep_mask = np.ones((len(points)), dtype=bool)
    keep_mask = my_rdp_recursion(points, epsilon, start_index, end_index, keep_mask)
    plot_points(points, start_index, end_index, delta_max_index, keep_mask)
    return keep_mask


# Algorithm to simplify a discrete curve recursively but should only create shortcuts to values below the curve
def my_rdp_recursion(points, epsilon, start_index, end_index, keep_mask):
    delta_max_index, delta_max = get_max_delta(points, start_index, end_index)
    plot_points(points, start_index, end_index, delta_max_index, keep_mask)
    if np.abs(delta_max) > epsilon:
        keep_mask = my_rdp_recursion(points, epsilon, start_index, delta_max_index, keep_mask)
        keep_mask = my_rdp_recursion(points, epsilon, delta_max_index, end_index, keep_mask)
    else:
        keep_mask[start_index+1:end_index] = 0
        print(f'{keep_mask=}')

    return keep_mask




if __name__ == "__main__":
    points = [(0, 0), (1, 0.1), (2, -0.1), (3, 5), (4, 5.4), (5, 7), (6, 8.1), (7, 9), (8, 9)]
    epsilon = 0.6
    keep_mask = my_rdp(points, epsilon)
