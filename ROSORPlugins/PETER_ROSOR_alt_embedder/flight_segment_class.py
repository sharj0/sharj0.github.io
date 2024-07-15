import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import time

def extract_2D_subarray_with_buffer(array_2D, x_coords, y_coords, buffer, start_coord, end_coord):
    # Ensure start_coord and end_coord are in the right order for x and y
    x_start, x_end = sorted([start_coord[0], end_coord[0]])
    y_start, y_end = sorted([start_coord[1], end_coord[1]])

    # Find indices in the x and y coordinates for the start and end coordinates, considering the buffer
    x_start_idx = np.searchsorted(x_coords, x_start - buffer, side='left')
    x_end_idx = np.searchsorted(x_coords, x_end + buffer, side='right')

    y_start_idx = np.searchsorted(y_coords, y_start - buffer, side='left')
    y_end_idx = np.searchsorted(y_coords, y_end + buffer, side='right')

    # Adjust indices to add an extra pixel on each edge, ensuring they are within array bounds
    x_start_idx = max(x_start_idx - 2, 0)
    x_end_idx = min(x_end_idx + 2, array_2D.shape[1])

    y_start_idx = max(y_start_idx - 2, 0)
    y_end_idx = min(y_end_idx + 2, array_2D.shape[0])

    # Extract the sub-array and corresponding coordinate arrays
    sub_array = array_2D[y_start_idx:y_end_idx, x_start_idx:x_end_idx]
    sub_x_coords = x_coords[x_start_idx:x_end_idx]
    sub_y_coords = y_coords[y_start_idx:y_end_idx]

    return sub_array, sub_x_coords, sub_y_coords

def plot_segment_samples(array_2D,
                         x_coords,
                         y_coords,
                         output_mask_2D,
                         samples_sorted,
                         pixel_width,
                         pixel_height,
                         start_coord_extended,
                         end_coord_extended,
                         perpendicular,
                         rect_width,
                         start_coord,
                         end_coord):
    extent = (x_coords[0], x_coords[-1] + pixel_width, y_coords[0], y_coords[-1] + pixel_height)

    # Calculate the coordinates of the rectangle's corners
    corner_1 = start_coord_extended + perpendicular * (rect_width / 2)
    corner_2 = start_coord_extended - perpendicular * (rect_width / 2)
    corner_3 = end_coord_extended - perpendicular * (rect_width / 2)
    corner_4 = end_coord_extended + perpendicular * (rect_width / 2)

    # Combine the corner coordinates into an array for easy plotting
    rect_corners = np.vstack((corner_1, corner_2, corner_3, corner_4, corner_1))
    plt.figure(figsize=(12, 6))
    plt.subplot(2, 2, 1)
    plt.imshow(array_2D, cmap='viridis', extent=extent, origin='lower')
    plt.plot([start_coord[0], end_coord[0]], [start_coord[1], end_coord[1]], 'r-', lw=2)
    plt.plot(rect_corners[:, 0], rect_corners[:, 1], 'r-', lw=1)
    plt.title('2D Array 1 with Line')

    plt.subplot(2, 2, 2)
    plt.imshow(output_mask_2D, cmap='gray', extent=extent, origin='lower')
    plt.plot([start_coord[0], end_coord[0]], [start_coord[1], end_coord[1]], 'r-', lw=2)
    plt.plot(rect_corners[:, 0], rect_corners[:, 1], 'r-', lw=1)
    plt.plot(samples_sorted[:, 3], samples_sorted[:, 4], 'b.', lw=1)
    plt.title('Masked Rectangle')

    plt.subplot(2, 2, (3, 4))
    plt.plot(samples_sorted[:, 0], samples_sorted[:, 2], '.')
    plt.title('Sampled Data')
    plt.show()

def generate_sample_points_along_fltline(start_coord, end_coord, sample_dist):
    """
    Generates points along a line defined by start and end coordinates at a given sampling distance.

    Args:
    start_coord (np.array): The starting coordinates [x, y].
    end_coord (np.array): The ending coordinates [x, y].
    sample_dist (float): The distance between each sampled point along the line.

    Returns:
    np.array: Array of sampled points along the line.
    """
    # Calculate the total distance between the start and end points
    total_dist = np.linalg.norm(end_coord - start_coord)

    # Calculate the number of points to be generated
    num_points = int(np.ceil(total_dist / sample_dist)) + 1

    # Create a vector from start to end
    vector = end_coord - start_coord

    # Normalize the vector
    unit_vector = vector / np.linalg.norm(vector)

    # Generate points
    points = np.array([start_coord + i * sample_dist * unit_vector for i in range(num_points)])
    x_coords = points[:, 0]
    y_coords = points[:, 1]
    return x_coords, y_coords

def sample_inline_points(array_2D, coords_bottom_left_of_pix, x_inline_sample, y_inline_sample):
    """
    Create a 1D mask array based on whether the points (x_inline_sample, y_inline_sample)
    are within the pixel coordinates defined by coords_bottom_left_of_pix.

    Args:
    array_2D (np.array): 2D NumPy array representing some data on a grid.
    coords_bottom_left_of_pix (np.array): 3D NumPy array with the bottom-left coordinates of each pixel.
    x_inline_sample (np.array): 1D array of x-coordinates of the points.
    y_inline_sample (np.array): 1D array of y-coordinates of the points.

    Returns:
    np.array: A 1D mask array of shape (n, ), where n is the total number of elements in array_2D.
    """
    # Flatten the 2D array to 1D
    flat_array = array_2D.flatten()

    # Initialize the mask with zeros
    mask_1d = np.zeros(flat_array.shape, dtype=bool)

    # Pixel dimensions (assuming uniform grid and square pixels)
    pixel_height = abs(coords_bottom_left_of_pix[0, 0, 1] - coords_bottom_left_of_pix[1, 0, 1])
    pixel_width = abs(coords_bottom_left_of_pix[0, 0, 0] - coords_bottom_left_of_pix[0, 1, 0])

    # Iterate over each point
    for x, y in zip(x_inline_sample, y_inline_sample):
        # Find the pixel that contains this point
        row = int((y - coords_bottom_left_of_pix[0, 0, 1]) / pixel_height)
        col = int((x - coords_bottom_left_of_pix[0, 0, 0]) / pixel_width)

        # Check bounds
        if 0 <= row < coords_bottom_left_of_pix.shape[0] and 0 <= col < coords_bottom_left_of_pix.shape[1]:
            # Set the corresponding position in the mask to True
            mask_1d[row * coords_bottom_left_of_pix.shape[1] + col] = True

    return mask_1d


def sample_by_pix_corners():
    pass

#@profile
def sample_Segment_rast(start_coord, end_coord, array_2D, x_coords, y_coords, rect_width):
    """
    its critical that if any part of the pixel is inside the buffer zone around the flightline that the pixel is sampled
    there are two sampling methods that together can unsure that no pixel is missed.
    The first method is to take the bottom left corner of each pixel and to see if it is inside the buffer zone.
    if that corner is inside the buffer zone then the pixel is sampled. but since a corner is a meeting of 4 pixels, the
    other 3 pixels are sampled as well.

    If the pixels are larger than width of the buffer zone then there will be pixels where buffer passes through the
    pixel without touching the corners, so it won't be sampled. This leads to the necessity of the second method.
    To sample large pixels correctly, we assume a worst-case scenario where the drone's path flies
    at a 45-degree angle to the pixel boundary.
    The drone flies over the pixel such that the pixel corner is infinitesimally past the sampling
    rectangle of the segment.
    In this scenario, the drone has the shortest path that flies over the pixel without being sampled.
    Assuming HORIZONTAL_SAFETY_BUFFER_PER_SIDE equals 1 unit, the math works out that as long as the
    segment is sampled less than 2 units apart, at least one sample will always land in the pixel.
    This is because a 45-degree angle creates a 90-45-45 triangle where the base is twice the height,
    and the height is HORIZONTAL_SAFETY_BUFFER_PER_SIDE.
    Therefore, 1.98 times HORIZONTAL_SAFETY_BUFFER_PER_SIDE is a good sampling distance.
    That's 0.99 rect_width.

    So sampling the pixle corners and the flightpath at 0.99 rect_width will ensure that
    no pixel is missed.
    """

    length = np.linalg.norm(end_coord - start_coord)
    direction = (end_coord - start_coord) / length
    perpendicular = np.array([-direction[1], direction[0]])
    # Extend the start and end coordinates
    extension_length = rect_width
    start_coord_extended = start_coord - direction * extension_length
    end_coord_extended = end_coord + direction * extension_length

    sample_dist_along_flt_path = 0.99 * rect_width

    x_inline_sample, y_inline_sample = generate_sample_points_along_fltline(start_coord_extended,
                                                                            end_coord_extended,
                                                                            sample_dist_along_flt_path)

    # Create a meshgrid
    x_bottom_left_of_pix, y_bottom_left_of_pix = np.meshgrid(x_coords, y_coords)
    coords_bottom_left_of_pix = np.stack((x_bottom_left_of_pix, y_bottom_left_of_pix), axis=-1)
    sample_shape = x_bottom_left_of_pix.shape

    mask_1d_inline_sample = sample_inline_points(array_2D, coords_bottom_left_of_pix, x_inline_sample, y_inline_sample)
    mask_2d_inline_sample = mask_1d_inline_sample.reshape(sample_shape)

    # Project each point (pix bottom left corner) onto the line and compute the distances
    # projections is the distance along the line, distances is the distance perpendicular to the line
    projections_bottom_left_of_pix = np.dot((coords_bottom_left_of_pix - start_coord_extended).reshape(-1, 2),
                                            direction)
    distances_bottom_left_of_pix = np.dot((coords_bottom_left_of_pix - start_coord_extended).reshape(-1, 2),
                                          perpendicular)

    # Create a mask for the end_points inside the rectangle
    mask_1d = (projections_bottom_left_of_pix >= 0) & \
              (projections_bottom_left_of_pix <= length + 2 * extension_length) & \
              (np.abs(
                  distances_bottom_left_of_pix) <= rect_width / 2)  # (start_of_line)AND(end_of_line)AND(right and left of the line)
    mask_2d = mask_1d.reshape(sample_shape)
    pad_around = True  # only set to False for debugging purposes
    if not pad_around:
        corner_samp_mask_1D = mask_1d
        corner_samp_mask_2D = mask_2d
    else:
        left = np.pad(mask_2d[:, 1:], ((0, 0), (0, 1)), mode='constant', constant_values=False)
        down = np.pad(mask_2d[1:, :], ((0, 1), (0, 0)), mode='constant', constant_values=False)
        diagonally_down_left = np.pad(mask_2d[1:, 1:], ((0, 1), (0, 1)), mode='constant', constant_values=False)
        corner_samp_array = mask_2d | left | down | diagonally_down_left
        corner_samp_mask_1D = corner_samp_array.reshape(-1)
        corner_samp_mask_2D = corner_samp_array


    output_mask_1D = mask_1d_inline_sample | corner_samp_mask_1D
    output_mask_2D = mask_2d_inline_sample | corner_samp_mask_2D

    # TEMP test debug
    #output_mask_1D = corner_samp_mask_1D
    #output_mask_2D = corner_samp_mask_2D

    # TEMP test debug
    #output_mask_1D = mask_1d_inline_sample
    #output_mask_2D = mask_2d_inline_sample

    pixel_width = x_coords[1] - x_coords[0]
    pixel_height = y_coords[1] - y_coords[0]

    # convert to center of pixel
    coords = coords_bottom_left_of_pix + np.array([pixel_width / 2, pixel_height / 2])
    x = x_bottom_left_of_pix + pixel_width / 2
    y = y_bottom_left_of_pix + pixel_height / 2

    # Project each point (pix centre) onto the line and compute the distances
    projections = np.dot((coords - start_coord_extended).reshape(-1, 2), direction)
    distances = np.dot((coords - start_coord_extended).reshape(-1, 2), perpendicular)

    # Extract the pixel values and coordinates for both arrays
    samples = np.vstack((projections[output_mask_1D]-extension_length,
                         distances[output_mask_1D],
                         array_2D.reshape(-1)[output_mask_1D],
                         x.reshape(-1)[output_mask_1D],
                         y.reshape(-1)[output_mask_1D],
                         )).T
    #0-dist_allong_seg,
    #1-dist_to each side_of_seg,
    #2-alt,
    #UTME
    #UTMN
    # where UTME, UTMN are at the centre of the sampled pixel

    samples_sorted = samples[np.argsort(samples[:, 0])]
    telem = (array_2D,
            x_coords,
            y_coords,
            output_mask_2D,
            samples_sorted,
            pixel_width,
            pixel_height,
            start_coord_extended,
            end_coord_extended,
            perpendicular,
            rect_width,
            start_coord,
            end_coord)
    return samples_sorted, telem


def plot_subarray(array_2D, sub_array, x_coords, y_coords, sub_x_coords, sub_y_coords, start_coord, end_coord):
    print("Sub-array shape:", sub_array.shape)
    print("Sub x-coords shape:", sub_x_coords.shape)
    print("Sub y-coords shape:", sub_y_coords.shape)

    # Determine color scale limits for both arrays
    vmin = min(array_2D.min(), sub_array.min())
    vmax = max(array_2D.max(), sub_array.max())

    # Plot entire array with specified color scale limits
    im_main = plt.imshow(array_2D, extent=[x_coords.min(), x_coords.max(), y_coords.min(), y_coords.max()],
                         origin='lower', vmin=vmin, vmax=vmax)

    # Overlay subsampled region with alpha transparency, also with the same color scale limits
    plt.imshow(sub_array, extent=[sub_x_coords.min(), sub_x_coords.max(), sub_y_coords.min(), sub_y_coords.max()],
               origin='lower', alpha=0.7, vmin=vmin, vmax=vmax)

    # Add a rectangle around the subsampled area
    rect = Rectangle((sub_x_coords.min(), sub_y_coords.min()),
                     sub_x_coords.max() - sub_x_coords.min(),
                     sub_y_coords.max() - sub_y_coords.min(),
                     linewidth=2, edgecolor='r', facecolor='none')
    plt.gca().add_patch(rect)

    # Add colorbar for the combined scale
    plt.colorbar(im_main, label="Elevation (m)")

    # Plot line from start_coord to end_coord
    plt.plot([start_coord[0], end_coord[0]], [start_coord[1], end_coord[1]], 'r-', linewidth=2)

    # Annotate start and end coords
    plt.annotate('Start', (start_coord[0], start_coord[1]), color='blue', fontsize=10, xytext=(0, 10),
                 textcoords='offset points', arrowprops=dict(facecolor='blue', arrowstyle='->'))
    plt.annotate('End', (end_coord[0], end_coord[1]), color='green', fontsize=10, xytext=(0, 10),
                 textcoords='offset points', arrowprops=dict(facecolor='green', arrowstyle='->'))

    # Display the plot
    plt.title("Array with Subsampled Region Highlighted")
    plt.xlabel("X-coordinates")
    plt.ylabel("Y-coordinates")
    plt.show()

def merge_segments(surf_samples, segs_lengths, plot=False):
    # get the sum lengths of all previous segments
    add_to_dist = np.insert(np.cumsum(np.array(segs_lengths[:-1])), 0, 0)
    segs_samples_with_ind_col = []
    for ind, seg in enumerate(surf_samples):
        # coppy the dist along the segment
        seg = np.c_[seg[:, 0], seg]
        # Add a column to the samples array that indicates which segment the sample belongs to
        samples_with_ind = np.c_[seg, np.full(seg.shape[0], ind)]
        samples_with_ind[:, 0] += add_to_dist[ind]
        segs_samples_with_ind_col.append(samples_with_ind)
    all_samples = np.concatenate(segs_samples_with_ind_col)
    # Sort all samples by distance
    all_samples = all_samples[all_samples[:, 0].argsort()]

    #this is what each col is in all_samples
    # 0-dist_allong_whole_flight,
    # 1-dist_allong_seg,
    # 2-dist_to each side_of flight path,
    # 3-alt,
    # 4-UTME
    # 5-UTMN
    # 6-seg_number

    if plot:
        import matplotlib.pyplot as plt
        for i in range(int(all_samples[:, -1].max()) + 1):
            seg_samples = all_samples[all_samples[:, -1] == i]
            plt.plot(seg_samples[:, 0], seg_samples[:, 2], '.')
        plt.show()

    return all_samples

class Segment:
    def __init__(self, start_utm, end_utm):
        self.start_utm = start_utm
        self.end_utm = end_utm
        self.length = np.linalg.norm(np.array(end_utm) - np.array(start_utm))

    def sample_rast(self, array_2D, x_coords, y_coords, rect_width):
        start_coord = np.array(self.start_utm)
        end_coord = np.array(self.end_utm)
        buffer = 2 * rect_width
        array_2D_smol, x_coords_smol, y_coords_smol = extract_2D_subarray_with_buffer(array_2D, x_coords, y_coords,
                                                                                      buffer, start_coord, end_coord)
        #plot_subarray(array_2D, array_2D_smol, x_coords, y_coords, x_coords_smol, y_coords_smol, start_coord, end_coord)
        samples_sorted, telem = sample_Segment_rast(start_coord, end_coord, array_2D_smol, x_coords_smol, y_coords_smol, rect_width)
        return samples_sorted, telem

    def regular_spacing(self, regular_dist, plot=False):
        end_points = np.array([self.start_utm, self.end_utm])
        num_points = int(np.floor(self.length / regular_dist) + 1)
        if num_points > 2:
            distances = np.linspace(0, 1, num_points)
        else:
            distances = np.array([0, 1])
        points_on_line = end_points[0] + distances[:, np.newaxis] * (end_points[1] - end_points[0])
        distances_along_line = distances * np.linalg.norm(end_points[1] - end_points[0])
        spacing = distances_along_line[1] - distances_along_line[0]
        self.base_wp_spacing = spacing
        if plot:
            # Plot the input line and output points
            plt.plot(end_points[:, 0], end_points[:, 1], label='Input Line')
            plt.scatter(points_on_line[:, 0], points_on_line[:, 1], label='Points on Line')
            plt.title(f'spacing = {regular_dist} -> {spacing}')
            plt.xlabel('X Coordinate')
            plt.ylabel('Y Coordinate')
            plt.legend()
            plt.show()
        merged_array = np.hstack((distances_along_line[:, np.newaxis], points_on_line))
        #match the format of the other data
        # 0-dist_allong_seg,
        # 1-dist_to each side_of_seg, <-- zero cuz on the line by definition
        # 2-alt, <-- N/A cuz will be calculated later
        # 3-UTME
        # 4-UTMN

        zeros_column = np.zeros((merged_array.shape[0], 1))
        na_column = np.full((merged_array.shape[0], 1), np.nan)
        merged_array = np.hstack((merged_array[:, 0:1], zeros_column, na_column, merged_array[:, 1:]))

        self.reg_dist_along = merged_array
        return merged_array

if __name__ == '__main__':
    test_sample_arrs = True

    start_coord = (400020.22, 5000030.3)
    end_coord = (400070.1, 5000080.443341)
    segment = Segment(start_coord, end_coord)

    if test_sample_arrs:
        #array_2D = np.random.random((100, 100))
        #x_coords = np.arange(400000, 400100)
        #y_coords = np.arange(5000000, 5000100)

        array_2D = np.random.random((10000, 10000))
        x_coords = np.arange(400000, 410000)
        y_coords = np.arange(5000000, 5010000)
        rect_width = 1.5

        plot_results = test_sample_arrs
        # Call the function
        samples, telem = segment.sample_rast(array_2D,
                                                    x_coords,
                                                    y_coords,
                                                    rect_width)