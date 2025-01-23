import numpy as np

def lon_lat_to_meters(coords):
    R = 6371000  # Radius of the Earth in meters
    coords_rad = np.radians(coords)

    # Calculate the midpoint
    mid_lon_rad = np.mean(coords_rad[:, 0])
    mid_lat_rad = np.mean(coords_rad[:, 1])
    mid_point = (np.degrees(mid_lon_rad), np.degrees(mid_lat_rad))

    # Convert coordinates to meters relative to the midpoint
    coords_meters = np.empty_like(coords_rad)
    coords_meters[:, 0] = R * (coords_rad[:, 0] - mid_lon_rad) * np.cos(mid_lat_rad)
    coords_meters[:, 1] = R * (coords_rad[:, 1] - mid_lat_rad)
    return coords_meters, mid_point

def meters_to_lon_lat(coords_meters, mid_point):
    R = 6371000  # Radius of the Earth in meters

    # Convert midpoint to radians
    mid_lon_rad = np.radians(mid_point[0])
    mid_lat_rad = np.radians(mid_point[1])

    # Convert coordinates back to radians
    coords_rad = np.empty_like(coords_meters)
    coords_rad[:, 0] = coords_meters[:, 0] / (R * np.cos(mid_lat_rad)) + mid_lon_rad
    coords_rad[:, 1] = coords_meters[:, 1] / R + mid_lat_rad

    # Convert back to degrees
    coords = np.degrees(coords_rad)

    return coords