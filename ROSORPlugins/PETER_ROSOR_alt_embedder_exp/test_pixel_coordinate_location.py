"""this file is not called from the rest of the plugin. It is just a place to test things out"""

import numpy as np
import rasterio # not part of the qgis libraries so goota use a different interpreter
from rasterio.plot import show
import matplotlib.pyplot as plt

def test_geotiff_and_x_y_coords(rast_path, x_coords, y_coords):
    """Plot the GeoTIFF and overlay x and y coordinates as points."""
    """ im was not sure if the output coordinates represent the middle or corners of the pixels. 
    I made a function to plot things so I can see"""
    # for this particular raster, the coordinates are the top left of the pixels

    # Generate 2D coordinate arrays from 1D coordinate arrays
    x_grid, y_grid = np.meshgrid(x_coords, y_coords)

    # Open the raster with rasterio
    with rasterio.open(rast_path) as src:
        # Read the band data
        band1 = src.read(1)

        # Replace band data with random values
        band1_random = np.random.rand(*band1.shape)

        # Plotting the raster data with random values
        fig, ax = plt.subplots(figsize=(10, 10))
        show(band1_random, ax=ax, cmap='gray', transform=src.transform)

        # Plotting the x and y coordinates as points
        ax.scatter(x_grid, y_grid, color='red', s=2)  # s is size of the points

        ax.set_title("GeoTIFF with Coordinates")
        plt.show()

# GeoTIFF path
rast_path = "I:/Qgis_discovering/qgis_alt_embedder/DSM.tif"

# Generate surf_x_coords based on provided information
start_x = 428299.2653
increment_x = 0.86  # Difference between two consecutive values
length_x = 7393

start_y = 6234620.1044
increment_y = 0.86  # Difference between two consecutive values
length_y = 5431

surf_x_coords = np.linspace(start_x, start_x + (length_x - 1) * increment_x, length_x)
surf_y_coords = np.linspace(start_y, start_y + (length_y - 1) * increment_y, length_y)


# Print the generated arrays and their shapes
print("surf_x_coords")
print(surf_x_coords)
print("surf_x_coords.shape")
print(surf_x_coords.shape)

print("\nsurf_y_coords")
print(surf_y_coords)
print("surf_y_coords.shape")
print(surf_y_coords.shape)

test_geotiff_and_x_y_coords(rast_path, surf_x_coords, surf_y_coords)