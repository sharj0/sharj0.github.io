import numpy as np
from .loading_functions import utm_point_to_lat_lon

def extract_coords_from_array_list(array_list, epsg_int):
    coord_lat_lon_list = []
    for _regular_spaced in array_list:
        print("rrefgasfqe")
        for seg_ind in np.where(_regular_spaced[:, 5] == 1)[0]:
            seg = _regular_spaced[seg_ind:seg_ind + 2, :]
            if not seg.shape == (2, 6):
                continue
            lat1, lon1 = utm_point_to_lat_lon(easting=seg[:, 3:5][0][0], northing=seg[:, 3:5][0][1], crs=epsg_int)
            lat2, lon2 = utm_point_to_lat_lon(easting=seg[:, 3:5][1][0], northing=seg[:, 3:5][1][1], crs=epsg_int)
            coord_lat_lon_list.append(((lat1, lon1), (lat2, lon2)))
    return coord_lat_lon_list

def buffer_extent(extent: dict[str, float], buffer_percent: float) -> dict[str, float]:
    """
    Expands the given extent by a specified percentage.

    Parameters:
    - extent: A dictionary with keys 'x_min', 'x_max', 'y_min', 'y_max' representing the bounding box.
    - buffer_percent: The percentage by which to expand the bounding box.

    Returns:
    - A dictionary with the same structure as the input, representing the buffered bounding box.
    """
    # Calculate the width and height of the original extent
    width = extent['x_max'] - extent['x_min']
    height = extent['y_max'] - extent['y_min']

    # Calculate the buffer values for width and height
    buffer_width = width * (buffer_percent / 100)
    buffer_height = height * (buffer_percent / 100)

    # Create the new extent dictionary
    buffered_extent = {
        'x_min': extent['x_min'] - buffer_width / 2,
        'x_max': extent['x_max'] + buffer_width / 2,
        'y_min': extent['y_min'] - buffer_height / 2,
        'y_max': extent['y_max'] + buffer_height / 2
    }

    return buffered_extent

def extract_coords_from_line_layer(flight_lines_layer):
    lisst = []
    for feature in flight_lines_layer.getFeatures():
        # Get the geometry of the feature
        geom = feature.geometry()
        # Extract the coordinates from the geometry
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            lines = [geom.asPolyline()]

        for line in lines:
            x, y = zip(*line)  # This separates the x and y coordinates
            lisst.append(((x[0],y[0]), (x[1],y[1])))
    return lisst

def group_segments(regular_spaced):
    # Return the original if there's not enough data to group
    if regular_spaced.shape[0] < 2:
        return regular_spaced.copy()
    # Initialize the list to hold the grouped segments
    grouped_segments = []
    # Start with the first segment
    grouped_segments.append(regular_spaced[0].copy())  # Append the first segment
    # Start grouping from the second segment
    current_segment = regular_spaced[1].copy()  # Initialize current_segment with the second element
    # Iterate over the segments starting from the third one
    for next_segment in regular_spaced[2:]:
        # Check if the current and next segments have the same value in the 5th index
        if current_segment[5] == next_segment[5]:
            # Extend the current segment to the end of the next segment
            current_segment[3:5] = next_segment[3:5]  # Update the end coordinate to the next segment's end
        else:
            # Append the current segment to the grouped list
            grouped_segments.append(current_segment)
            current_segment = next_segment.copy()  # Start new group with a copy of next segment
    # Append the last processed segment group to ensure it's not missed
    grouped_segments.append(current_segment)
    grouped_segments = np.array(grouped_segments)
    grouped_segments[:-1, 5] = grouped_segments[1:, 5]
    # Convert to a numpy array for consistency with the input format
    return grouped_segments