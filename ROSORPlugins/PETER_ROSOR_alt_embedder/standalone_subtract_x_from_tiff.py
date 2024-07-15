import rasterio
import numpy as np

# Input GeoTIFF file
input_file = r"I:\CONTRACT_Senoa\Ram\Arctic_DEM.tif"


subtract_by = 100
remove_negatives = True
set_negatives_to = 600

# Open the input file
with rasterio.open(input_file) as src:
    # Read the raster data
    data = src.read(1)

    ##set all to 5
    #subtracted_data = np.full_like(data, 5)
    # Subtract 1 from all pixels
    subtracted_data = data - subtract_by

    if remove_negatives:
        subtracted_data[np.where(subtracted_data < 0)] = set_negatives_to

    # Get the metadata from the source file
    meta = src.meta

# Update the metadata
meta.update({'count': 1})

# Output GeoTIFF file
output_file = input_file.replace('.tif', f'-{subtract_by}.tif')

# Write the subtracted data to the output file
with rasterio.open(output_file, 'w', **meta) as dst:
    dst.write(subtracted_data, 1)

print(f"Subtracted data saved to: {output_file}")
