import numpy as np
import matplotlib.pyplot as plt

def clip_ends(drape_onto, x_coords, plot=False):
    x_max = np.max(x_coords)
    x_min = np.min(x_coords)

    # Insert point for x_max
    idx_max = np.searchsorted(drape_onto[0], x_max)
    y_max = np.interp(x_max, [drape_onto[0][idx_max - 1], drape_onto[0][idx_max]],
                              [drape_onto[1][idx_max - 1], drape_onto[1][idx_max]])

    # Insert point for x_min
    idx_min = np.searchsorted(drape_onto[0], x_min)
    y_min = np.interp(x_min, [drape_onto[0][idx_min - 1], drape_onto[0][idx_min]],
                              [drape_onto[1][idx_min - 1], drape_onto[1][idx_min]])

    # Insert the new points into drape_onto
    new_x = np.insert(drape_onto[0], [idx_min, idx_max], [x_min, x_max])
    new_y = np.insert(drape_onto[1], [idx_min, idx_max], [y_min, y_max])

    # Sort by x-values to ensure that the x-values are in ascending order
    sort_order = np.argsort(new_x)
    new_x = new_x[sort_order]
    new_y = new_y[sort_order]

    # Remove the points before x_min and after x_max
    start_idx = np.where(new_x == x_min)[0][0]
    end_idx = np.where(new_x == x_max)[0][0]
    new_x = new_x[start_idx:end_idx+1]
    new_y = new_y[start_idx:end_idx+1]
    drape_onto_clipped = np.array([new_x, new_y])
    if plot:
        plot_clip(drape_onto, drape_onto_clipped)
    return drape_onto_clipped


def plot_clip(original_data, clipped_data):
    plt.figure(figsize=(10, 6))

    # Plot original data
    plt.plot(original_data[0], original_data[1], linestyle='-', marker='o', color='blue', markersize=8, label="Original Data")

    # Plot clipped data
    plt.plot(clipped_data[0], clipped_data[1], linestyle='-', marker='o', markersize=4, color='orange', label="Clipped Data")

    plt.legend()
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.title("Original vs Clipped Data")
    plt.grid(True)
    plt.tight_layout()
    plt.show()



def adjust_drape(x_coords, y_coords, drape_onto, plot=False):
    drape_x = drape_onto[0]
    drape_alt = drape_onto[1]
    ydiff = np.interp(drape_x, x_coords, y_coords) - drape_alt

    # Use broadcasting to create an array of shape (len(drape_onto[0]), len(x_coords)-1) where each row represents
    # whether a drape_onto x-value is between each segment of x_coords.
    within_segments = (drape_onto[0][:, np.newaxis] >= x_coords[:-1]) & (drape_onto[0][:, np.newaxis] <= x_coords[1:])

    # Using the above mask, select ydiff values for each segment and get their minimum.
    # This results in an array of minimum ydiff values for each segment.
    segment_mins = np.where(within_segments, ydiff[:, np.newaxis], float('inf')).min(axis=0)

    # Find the segment index with the most negative ydiff.
    lowest_seg_idx = np.argmin(segment_mins)
    lowest_seg_diff = segment_mins[lowest_seg_idx]

    # Adjust y-coordinates for the segment with the most negative ydiff.
    new_y_coords = y_coords.copy()
    new_y_coords[lowest_seg_idx:lowest_seg_idx+2] += abs(lowest_seg_diff) + 0.01

    if plot:
        plot_adjusted_drape(x_coords, y_coords, new_y_coords, drape_onto, ydiff)

    return new_y_coords, lowest_seg_diff


def plot_adjusted_drape(x_coords, old_y_coords, new_y_coords, drape_onto, old_ydiff):
    fig, ax1 = plt.subplots(figsize=(15, 8))

    # Plot old y_coords on ax1
    ax1.plot(x_coords, old_y_coords, linestyle='-', marker='o', color='blue', markersize=8, label="Old y_coords")

    # Plot new y_coords on ax1
    ax1.plot(x_coords, new_y_coords, linestyle='-', marker='o', color='red', markersize=8, label="New y_coords")

    # Plot drape_onto on ax1
    ax1.plot(drape_onto[0], drape_onto[1], linestyle='-', marker='.', markersize=4, color='green', label="Drape Onto")

    ax1.set_xlabel("X")
    ax1.set_ylabel("Y")
    ax1.set_title("Old vs New y_coords & Drape Onto")

    ax1.legend(loc='upper left')

    # Create a second y-axis to plot old and new ydiff
    ax2 = ax1.twinx()

    # Calculate new ydiff using new_y_coords
    new_ydiff = np.interp(drape_onto[0], x_coords, new_y_coords) - drape_onto[1]

    # Plot old ydiff on ax2
    ax2.plot(drape_onto[0], old_ydiff, '--', color='cyan', label="Old ydiff")

    # Plot new ydiff on ax2
    ax2.plot(drape_onto[0], new_ydiff, '--', color='magenta', label="New ydiff")

    ax2.set_ylabel("Y Difference")
    ax2.legend(loc='upper right')
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5)
    ax2.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.6)

    plt.tight_layout()
    plt.show()


def run(drape_onto, x_coords, plot=False):
    clipped_drape_onto = clip_ends(drape_onto, x_coords)
    y_coords_init = np.interp(x_coords, clipped_drape_onto[0], clipped_drape_onto[1]) + 0.01

    plot_adjustments_per_wp = False
    adjusted_y_coords, lowest_seg_diff = adjust_drape(x_coords, y_coords_init,
                                                      clipped_drape_onto, plot=plot_adjustments_per_wp)

    # Loop until lowest_seg_diff becomes positive
    while lowest_seg_diff < 0:
        adjusted_y_coords, lowest_seg_diff = adjust_drape(x_coords, adjusted_y_coords,
                                                          clipped_drape_onto, plot=plot_adjustments_per_wp)

    if plot:
        plot_final_stuff(x_coords, adjusted_y_coords, clipped_drape_onto)

    return adjusted_y_coords

def plot_final_stuff(x_coords, y_coords, clipped_drape_onto):

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(clipped_drape_onto[0], clipped_drape_onto[1], linestyle='-', marker='.', markersize=4, color='black')
    ax.plot(x_coords, y_coords, linestyle='-', marker='.', color='purple', markersize=8)
    ax.set_aspect('equal')
    plt.show()

if __name__ == '__main__':
    drape_onto = get_drape_onto() # or use your provided data
    x_coords = np.array([505.0, 535.8, 560.0, 596, 649.30847358, 695])
    draped_y = run(drape_onto, x_coords, plot=True)
