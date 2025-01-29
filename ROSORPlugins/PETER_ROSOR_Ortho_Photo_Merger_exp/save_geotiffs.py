from osgeo import gdal
import os
import re
import shutil
import numpy as np
import math
import tempfile
import subprocess
import sys
import xml.etree.ElementTree as ET

def save_vrt_as_tiff(vrt_path, output_tiff_path, nodata_value=0):
    """
    Save a VRT as a GeoTIFF with LZW compression and uint8 data type,
    and set a NoData value for each band.

    Args:
        vrt_path (str): Path to the input VRT file.
        output_tiff_path (str): Path to save the output GeoTIFF file.
        nodata_value (int or float, optional): The NoData value to set for the output bands. Default is 0.

    Returns:
        None
    """

    # Open the VRT file
    vrt_ds = gdal.Open(vrt_path)
    if vrt_ds is None:
        raise RuntimeError(f"Could not open VRT file: {vrt_path}")

    # Define options for GeoTIFF creation
    options = [
        "COMPRESS=LZW",  # Apply LZW compression
        "TILED=YES",      # Enable tiling for better performance
        "BIGTIFF=YES"
    ]

    # Create the GeoTIFF
    driver = gdal.GetDriverByName("GTiff")
    tiff_ds = driver.CreateCopy(output_tiff_path, vrt_ds, options=options)

    if tiff_ds is None:
        raise RuntimeError(f"Could not save GeoTIFF file: {output_tiff_path}")

    # Set NoData value for each band
    for band_index in range(1, tiff_ds.RasterCount + 1):
        band = tiff_ds.GetRasterBand(band_index)
        band.SetNoDataValue(nodata_value)

    # Flush cache to ensure NoData values are written
    tiff_ds.FlushCache()

    # Close datasets
    tiff_ds = None
    vrt_ds = None

    print(f"GeoTIFF saved successfully at: {output_tiff_path}")

def create_wide_ext_overlap_vrt(raster1_path, raster2_path, output_vrt_path):
    """
    Create a VRT that computes the logical "AND" of two aligned rasters
    with different extents, minimizing the output extent to encompass only
    the overlapping area.

    Args:
        raster1_path (str): Path to the first raster.
        raster2_path (str): Path to the second raster.
        output_vrt_path (str): Path to save the output VRT file.

    Returns:
        None
    """

    # Open the rasters
    ds1 = gdal.Open(raster1_path)
    ds2 = gdal.Open(raster2_path)

    if ds1 is None or ds2 is None:
        raise RuntimeError("One or both rasters could not be opened.")

    # Get geotransforms and CRS
    gt1 = ds1.GetGeoTransform()
    gt2 = ds2.GetGeoTransform()
    proj1 = ds1.GetProjectionRef()

    if proj1 != ds2.GetProjectionRef():
        raise RuntimeError("Input rasters have different projections.")

    # Calculate the extents of both rasters
    minx1, maxy1, maxx1, miny1 = gt1[0], gt1[3], gt1[0] + gt1[1] * ds1.RasterXSize, gt1[3] + gt1[5] * ds1.RasterYSize
    minx2, maxy2, maxx2, miny2 = gt2[0], gt2[3], gt2[0] + gt2[1] * ds2.RasterXSize, gt2[3] + gt2[5] * ds2.RasterYSize

    # Calculate the intersection of extents
    overlap_minx = max(minx1, minx2)
    overlap_miny = max(miny1, miny2)
    overlap_maxx = min(maxx1, maxx2)
    overlap_maxy = min(maxy1, maxy2)

    if overlap_minx >= overlap_maxx or overlap_miny >= overlap_maxy:
        raise RuntimeError("The rasters do not overlap.")

    # Define the resolution (assume both rasters have the same pixel size)
    pixel_width, pixel_height = gt1[1], abs(gt1[5])

    # Calculate the output size
    x_size = int((overlap_maxx - overlap_minx) / pixel_width)
    y_size = int((overlap_maxy - overlap_miny) / pixel_height)

    # Compute offsets for each raster
    x_offset1 = int(round((overlap_minx - minx1) / pixel_width))
    y_offset1 = int(round((maxy1 - overlap_maxy) / pixel_height))

    x_offset2 = int(round((overlap_minx - minx2) / pixel_width))
    y_offset2 = int(round((maxy2 - overlap_maxy) / pixel_height))

    # Define the VRT
    vrt_template = f"""<VRTDataset rasterXSize="{x_size}" rasterYSize="{y_size}">
    <SRS>{proj1}</SRS>
    <GeoTransform>{overlap_minx}, {pixel_width}, 0, {overlap_maxy}, 0, -{pixel_height}</GeoTransform>
    <VRTRasterBand dataType="Byte" band="1" subClass="VRTDerivedRasterBand">
        <PixelFunctionType>mul</PixelFunctionType>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{raster1_path}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="{x_offset1}" yOff="{y_offset1}" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{raster2_path}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="{x_offset2}" yOff="{y_offset2}" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
    </VRTRasterBand>
</VRTDataset>
"""

    # Write the VRT file
    with open(output_vrt_path, "w") as vrt_file:
        vrt_file.write(vrt_template)

    print(f"Minimized extent overlap VRT created successfully at: {output_vrt_path}")


#def get_color_similarity(rgb_rast_path_1, rgb_rast_path_2, color_similarity_tiff):
#    """
#    Create a GeoTIFF that calculates the pixel-wise Euclidean distance between two input RGB rasters.
#
#    Args:
#        rgb_rast_path_1 (str): Path to the first RGB raster (assumed to have 3 bands).
#        rgb_rast_path_2 (str): Path to the second RGB raster (assumed to have 3 bands).
#        color_similarity_tiff (str): Path to save the output GeoTIFF file.
#
#    Returns:
#        None
#    """
#    gdal_calc_path = os.path.join(os.path.dirname(__file__), "gdal_calc.py")
#
#    # Ensure gdal_calc.py exists at the specified path
#    if not os.path.exists(gdal_calc_path):
#        # Fallback: Assume gdal_calc.py is in the system PATH
#        gdal_calc_path = 'gdal_calc.py'
#
#    # Build the command to calculate the Euclidean distance between the two RGB rasters
#    command = [
#        sys.executable, gdal_calc_path,
#        '-A', rgb_rast_path_1, '--A_band', '1',
#        '-B', rgb_rast_path_1, '--B_band', '2',
#        '-C', rgb_rast_path_1, '--C_band', '3',
#        '-D', rgb_rast_path_2, '--D_band', '1',
#        '-E', rgb_rast_path_2, '--E_band', '2',
#        '-F', rgb_rast_path_2, '--F_band', '3',
#        '--calc=sqrt((A-D)**2 + (B-E)**2 + (C-F)**2)',
#        '--outfile', color_similarity_tiff,
#        '--NoDataValue', '0',
#        '--overwrite'
#    ]
#
#    # Execute the command using subprocess
#    try:
#        subprocess.run(command, check=True)
#        print(f"Difference raster TIFF created successfully at: {color_similarity_tiff}")
#    except subprocess.CalledProcessError as e:
#        print(f"An error occurred while running gdal_calc.py: {e}")


def apply_mask_rel_path_to_rgb_rast(rgb_raster_path, mask_path, output_vrt_path, nodata_value=0):
    """
    Apply a mask to an RGB raster, outputting the RGB raster only where the mask is '1'.
    The output raster will have the extent of the mask and include a NoData value.

    Args:
        rgb_raster_path (str): Path to the RGB raster (assumed to have 3 bands).
        mask_path (str): Path to the mask raster (assumed to be a single-band raster with values 0 or 1).
        output_vrt_path (str): Path to save the output VRT file.
        nodata_value (int): The NoData value to apply to the output VRT.

    Returns:
        None
    """

    # Open the RGB raster and the mask raster
    rgb_ds = gdal.Open(rgb_raster_path)
    mask_ds = gdal.Open(mask_path)

    if rgb_ds is None or mask_ds is None:
        raise RuntimeError("RGB raster or mask raster could not be opened.")

    # Get projections
    rgb_proj = rgb_ds.GetProjectionRef()
    mask_proj = mask_ds.GetProjectionRef()

    if rgb_proj != mask_proj:
        raise RuntimeError("RGB raster and mask raster have different projections.")

    # Get geotransforms
    rgb_gt = rgb_ds.GetGeoTransform()
    mask_gt = mask_ds.GetGeoTransform()

    # Get pixel sizes
    rgb_pixel_width = rgb_gt[1]
    rgb_pixel_height = rgb_gt[5]
    mask_pixel_width = mask_gt[1]
    mask_pixel_height = mask_gt[5]

    threshold = 1e-8

    # Check using math.isclose with the threshold
    pixel_size_x_matches_target_GSD = math.isclose(rgb_pixel_width, mask_pixel_width, rel_tol=threshold, abs_tol=threshold)
    pixel_size_y_matches_target_GSD = math.isclose(rgb_pixel_height, mask_pixel_height, rel_tol=threshold, abs_tol=threshold)

    # Check that the pixel sizes are the same
    if not pixel_size_x_matches_target_GSD or not pixel_size_y_matches_target_GSD:
        raise RuntimeError("RGB raster and mask raster have different pixel sizes.")

    # Get extents
    rgb_minx = rgb_gt[0]
    rgb_maxx = rgb_gt[0] + rgb_pixel_width * rgb_ds.RasterXSize
    rgb_miny = rgb_gt[3] + rgb_pixel_height * rgb_ds.RasterYSize
    rgb_maxy = rgb_gt[3]

    mask_minx = mask_gt[0]
    mask_maxx = mask_gt[0] + mask_pixel_width * mask_ds.RasterXSize
    mask_miny = mask_gt[3] + mask_pixel_height * mask_ds.RasterYSize
    mask_maxy = mask_gt[3]

    # Ensure the mask extent is within the RGB raster extent
    if not (mask_minx >= rgb_minx and mask_maxx <= rgb_maxx and
            mask_miny >= rgb_miny and mask_maxy <= rgb_maxy):
        raise RuntimeError("Mask raster extent is outside the bounds of the RGB raster.")

    # Compute offsets and sizes
    x_offset_rgb = int(round((mask_minx - rgb_minx) / rgb_pixel_width))
    y_offset_rgb = int(round((mask_maxy - rgb_maxy) / rgb_pixel_height))
    x_size = mask_ds.RasterXSize
    y_size = mask_ds.RasterYSize

    # Build the VRT
    vrt_template = f"""<VRTDataset rasterXSize="{x_size}" rasterYSize="{y_size}">
    <SRS>{mask_proj}</SRS>
    <GeoTransform>{mask_minx}, {mask_pixel_width}, 0, {mask_maxy}, 0, {mask_pixel_height}</GeoTransform>
    """

    for band in range(1, 4):  # Assuming RGB raster has 3 bands
        vrt_template += f"""
    <VRTRasterBand dataType="Byte" band="{band}" subClass="VRTDerivedRasterBand">
        <NoDataValue>{nodata_value}</NoDataValue>
        <PixelFunctionType>mul</PixelFunctionType>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{rgb_raster_path}</SourceFilename>
            <SourceBand>{band}</SourceBand>
            <SrcRect xOff="{x_offset_rgb}" yOff="{y_offset_rgb}" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
        <SimpleSource>
            <SourceFilename relativeToVRT="1">{os.path.basename(mask_path)}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
    </VRTRasterBand>
    """
    vrt_template += """
</VRTDataset>
"""

    # Write the VRT file
    with open(output_vrt_path, "w") as vrt_file:
        vrt_file.write(vrt_template)

    print(f"Mask applied to RGB raster successfully. Output VRT saved at: {output_vrt_path}")


def apply_mask_to_rgb_rast(rgb_raster_path, mask_path, output_vrt_path, nodata_value=0):
    """
    Apply a mask to an RGB raster, outputting the RGB raster only where the mask is '1'.
    The output raster will have the extent of the mask and include a NoData value.

    Args:
        rgb_raster_path (str): Path to the RGB raster (assumed to have 3 bands).
        mask_path (str): Path to the mask raster (assumed to be a single-band raster with values 0 or 1).
        output_vrt_path (str): Path to save the output VRT file.
        nodata_value (int): The NoData value to apply to the output VRT.

    Returns:
        None
    """

    # Open the RGB raster and the mask raster
    rgb_ds = gdal.Open(rgb_raster_path)
    mask_ds = gdal.Open(mask_path)

    if rgb_ds is None or mask_ds is None:
        raise RuntimeError("RGB raster or mask raster could not be opened.")

    # Get projections
    rgb_proj = rgb_ds.GetProjectionRef()
    mask_proj = mask_ds.GetProjectionRef()

    if rgb_proj != mask_proj:
        raise RuntimeError("RGB raster and mask raster have different projections.")

    # Get geotransforms
    rgb_gt = rgb_ds.GetGeoTransform()
    mask_gt = mask_ds.GetGeoTransform()

    # Get pixel sizes
    rgb_pixel_width = rgb_gt[1]
    rgb_pixel_height = rgb_gt[5]
    mask_pixel_width = mask_gt[1]
    mask_pixel_height = mask_gt[5]

    threshold = 1e-8

    # Check using math.isclose with the threshold
    pixel_size_x_matches_target_GSD = math.isclose(rgb_pixel_width, mask_pixel_width, rel_tol=threshold, abs_tol=threshold)
    pixel_size_y_matches_target_GSD = math.isclose(rgb_pixel_height, mask_pixel_height, rel_tol=threshold, abs_tol=threshold)

    # Check that the pixel sizes are the same
    if not pixel_size_x_matches_target_GSD or not pixel_size_y_matches_target_GSD:
        raise RuntimeError("RGB raster and mask raster have different pixel sizes.")

    # Get extents
    rgb_minx = rgb_gt[0]
    rgb_maxx = rgb_gt[0] + rgb_pixel_width * rgb_ds.RasterXSize
    rgb_miny = rgb_gt[3] + rgb_pixel_height * rgb_ds.RasterYSize
    rgb_maxy = rgb_gt[3]

    mask_minx = mask_gt[0]
    mask_maxx = mask_gt[0] + mask_pixel_width * mask_ds.RasterXSize
    mask_miny = mask_gt[3] + mask_pixel_height * mask_ds.RasterYSize
    mask_maxy = mask_gt[3]

    # Ensure the mask extent is within the RGB raster extent
    if not (mask_minx >= rgb_minx and mask_maxx <= rgb_maxx and
            mask_miny >= rgb_miny and mask_maxy <= rgb_maxy):
        raise RuntimeError("Mask raster extent is outside the bounds of the RGB raster.")

    # Compute offsets and sizes
    x_offset_rgb = int(round((mask_minx - rgb_minx) / rgb_pixel_width))
    y_offset_rgb = int(round((mask_maxy - rgb_maxy) / rgb_pixel_height))
    x_size = mask_ds.RasterXSize
    y_size = mask_ds.RasterYSize

    # Build the VRT
    vrt_template = f"""<VRTDataset rasterXSize="{x_size}" rasterYSize="{y_size}">
    <SRS>{mask_proj}</SRS>
    <GeoTransform>{mask_minx}, {mask_pixel_width}, 0, {mask_maxy}, 0, {mask_pixel_height}</GeoTransform>
    """

    for band in range(1, 4):  # Assuming RGB raster has 3 bands
        vrt_template += f"""
    <VRTRasterBand dataType="Byte" band="{band}" subClass="VRTDerivedRasterBand">
        <NoDataValue>{nodata_value}</NoDataValue>
        <PixelFunctionType>mul</PixelFunctionType>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{rgb_raster_path}</SourceFilename>
            <SourceBand>{band}</SourceBand>
            <SrcRect xOff="{x_offset_rgb}" yOff="{y_offset_rgb}" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{mask_path}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
    </VRTRasterBand>
    """
    vrt_template += """
</VRTDataset>
"""

    # Write the VRT file
    with open(output_vrt_path, "w") as vrt_file:
        vrt_file.write(vrt_template)

    print(f"Mask applied to RGB raster successfully. Output VRT saved at: {output_vrt_path}")


def apply_mask_to_mask(mask_path_0, mask_path, output_vrt_path, nodata_value=0):
    """
    Apply a mask to an RGB raster, outputting the RGB raster only where the mask is '1'.
    The output raster will have the extent of the mask and include a NoData value.

    Args:
        mask_path_0 (str): Path to the RGB raster (assumed to have 3 bands).
        mask_path (str): Path to the mask raster (assumed to be a single-band raster with values 0 or 1).
        output_vrt_path (str): Path to save the output VRT file.
        nodata_value (int): The NoData value to apply to the output VRT.

    Returns:
        None
    """

    # Open the RGB raster and the mask raster
    mask_0_ds = gdal.Open(mask_path_0)
    mask_ds = gdal.Open(mask_path)

    if mask_0_ds is None or mask_ds is None:
        raise RuntimeError("RGB raster or mask raster could not be opened.")

    # Get projections
    mask_0_proj = mask_0_ds.GetProjectionRef()
    mask_proj = mask_ds.GetProjectionRef()

    if mask_0_proj != mask_proj:
        raise RuntimeError("RGB raster and mask raster have different projections.")

    # Get geotransforms
    mask_0_gt = mask_0_ds.GetGeoTransform()
    mask_gt = mask_ds.GetGeoTransform()

    # Get pixel sizes
    mask_0_pixel_width = mask_0_gt[1]
    mask_0_pixel_height = mask_0_gt[5]
    mask_pixel_width = mask_gt[1]
    mask_pixel_height = mask_gt[5]

    threshold = 1e-8

    # Check using math.isclose with the threshold
    pixel_size_x_matches_target_GSD = math.isclose(mask_0_pixel_width, mask_pixel_width, rel_tol=threshold, abs_tol=threshold)
    pixel_size_y_matches_target_GSD = math.isclose(mask_0_pixel_height, mask_pixel_height, rel_tol=threshold, abs_tol=threshold)

    # Check that the pixel sizes are the same
    if not pixel_size_x_matches_target_GSD or not pixel_size_y_matches_target_GSD:
        raise RuntimeError("RGB raster and mask raster have different pixel sizes.")

    # Get extents
    mask_0_minx = mask_0_gt[0]
    mask_0_maxx = mask_0_gt[0] + mask_0_pixel_width * mask_0_ds.RasterXSize
    mask_0_miny = mask_0_gt[3] + mask_0_pixel_height * mask_0_ds.RasterYSize
    mask_0_maxy = mask_0_gt[3]

    mask_minx = mask_gt[0]
    mask_maxx = mask_gt[0] + mask_pixel_width * mask_ds.RasterXSize
    mask_miny = mask_gt[3] + mask_pixel_height * mask_ds.RasterYSize
    mask_maxy = mask_gt[3]

    # Ensure the mask extent is within the RGB raster extent
    if not (mask_minx >= mask_0_minx and mask_maxx <= mask_0_maxx and
            mask_miny >= mask_0_miny and mask_maxy <= mask_0_maxy):
        raise RuntimeError("Mask raster extent is outside the bounds of the RGB raster.")

    # Compute offsets and sizes
    x_offset_mask_0 = int(round((mask_minx - mask_0_minx) / mask_0_pixel_width))
    y_offset_mask_0 = int(round((mask_maxy - mask_0_maxy) / mask_0_pixel_height))
    x_size = mask_ds.RasterXSize
    y_size = mask_ds.RasterYSize

    # Build the VRT
    vrt_template = f"""<VRTDataset rasterXSize="{x_size}" rasterYSize="{y_size}">
    <SRS>{mask_proj}</SRS>
    <GeoTransform>{mask_minx}, {mask_pixel_width}, 0, {mask_maxy}, 0, {mask_pixel_height}</GeoTransform>
    """

    vrt_template += f"""
    <VRTRasterBand dataType="Byte" band="1" subClass="VRTDerivedRasterBand">
        <NoDataValue>{nodata_value}</NoDataValue>
        <PixelFunctionType>mul</PixelFunctionType>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{mask_path_0}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="{x_offset_mask_0}" yOff="{y_offset_mask_0}" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{mask_path}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
            <DstRect xOff="0" yOff="0" xSize="{x_size}" ySize="{y_size}"/>
        </SimpleSource>
    </VRTRasterBand>
    """
    vrt_template += """
</VRTDataset>
"""

    # Write the VRT file
    with open(output_vrt_path, "w") as vrt_file:
        vrt_file.write(vrt_template)

    print(f"Mask applied to mask  successfully. Output VRT saved at: {output_vrt_path}")



def get_footprint_mask(raster1_path, raster2_path, output_vrt_path):
    """
    Create a VRT that computes the logical "OR" of two aligned rasters
    with different extents.

    Args:
        raster1_path (str): Path to the first raster.
        raster2_path (str): Path to the second raster.
        output_vrt_path (str): Path to save the output VRT file.

    Returns:
        tuple: Geotransform for the combined "OR" raster.
    """

    # Open the rasters
    ds1 = gdal.Open(raster1_path)
    ds2 = gdal.Open(raster2_path)

    if ds1 is None or ds2 is None:
        raise RuntimeError("One or both rasters could not be opened.")

    # Get geotransforms and CRS
    gt1 = ds1.GetGeoTransform()
    proj1 = ds1.GetProjectionRef()

    if proj1 != ds2.GetProjectionRef():
        raise RuntimeError("Input rasters have different projections.")

    # Calculate the extents of both rasters
    minx1, maxy1, maxx1, miny1 = gt1[0], gt1[3], gt1[0] + gt1[1] * ds1.RasterXSize, gt1[3] + gt1[5] * ds1.RasterYSize
    gt2 = ds2.GetGeoTransform()
    minx2, maxy2, maxx2, miny2 = gt2[0], gt2[3], gt2[0] + gt2[1] * ds2.RasterXSize, gt2[3] + gt2[5] * ds2.RasterYSize

    # Calculate the union of extents
    union_minx = min(minx1, minx2)
    union_miny = min(miny1, miny2)
    union_maxx = max(maxx1, maxx2)
    union_maxy = max(maxy1, maxy2)

    # Define the resolution (assume both rasters have the same pixel size)
    pixel_width, pixel_height = gt1[1], abs(gt1[5])

    # Calculate the output size
    x_size = int((union_maxx - union_minx) / pixel_width)
    y_size = int((union_maxy - union_miny) / pixel_height)

    # Compute offsets for each raster
    x_offset1 = int(round((minx1 - union_minx) / pixel_width))
    y_offset1 = int(round((union_maxy - maxy1) / pixel_height))
    x_offset2 = int(round((minx2 - union_minx) / pixel_width))
    y_offset2 = int(round((union_maxy - maxy2) / pixel_height))

    # Define the VRT
    vrt_template = f"""<VRTDataset rasterXSize="{x_size}" rasterYSize="{y_size}">
    <SRS>{proj1}</SRS>
    <GeoTransform>{union_minx}, {pixel_width}, 0, {union_maxy}, 0, -{pixel_height}</GeoTransform>
    <VRTRasterBand dataType="Byte" band="1" subClass="VRTDerivedRasterBand">
        <PixelFunctionType>sum</PixelFunctionType>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{raster1_path}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="0" yOff="0" xSize="{ds1.RasterXSize}" ySize="{ds1.RasterYSize}"/>
            <DstRect xOff="{x_offset1}" yOff="{y_offset1}" xSize="{ds1.RasterXSize}" ySize="{ds1.RasterYSize}"/>
        </SimpleSource>
        <SimpleSource>
            <SourceFilename relativeToVRT="0">{raster2_path}</SourceFilename>
            <SourceBand>1</SourceBand>
            <SrcRect xOff="0" yOff="0" xSize="{ds2.RasterXSize}" ySize="{ds2.RasterYSize}"/>
            <DstRect xOff="{x_offset2}" yOff="{y_offset2}" xSize="{ds2.RasterXSize}" ySize="{ds2.RasterYSize}"/>
        </SimpleSource>
    </VRTRasterBand>
</VRTDataset>
"""

    # Write the VRT file
    with open(output_vrt_path, "w") as vrt_file:
        vrt_file.write(vrt_template)

    # Return the geotransform of the union raster
    return (union_minx, pixel_width, 0, union_maxy, 0, -pixel_height)

def get_extent(ds):
    gt = ds.GetGeoTransform()
    x_size = ds.RasterXSize
    y_size = ds.RasterYSize
    minx = gt[0]
    maxy = gt[3]
    maxx = minx + gt[1] * x_size
    miny = maxy + gt[5] * y_size
    # Ensure min values are less than max values
    minx, maxx = sorted([minx, maxx])
    miny, maxy = sorted([miny, maxy])
    return (minx, miny, maxx, maxy)

def get_masks_on_footprint_gt(first_raster_path, second_raster_path, out_mask_1_path, out_mask_2_path,
                              footprint_mask_path):
    # Open the datasets
    first_ds = gdal.Open(first_raster_path)
    second_ds = gdal.Open(second_raster_path)

    # Get extents
    extent1 = get_extent(first_ds)
    extent2 = get_extent(second_ds)

    # Calculate the full footprint extent
    footprint_minx = min(extent1[0], extent2[0])
    footprint_miny = min(extent1[1], extent2[1])
    footprint_maxx = max(extent1[2], extent2[2])
    footprint_maxy = max(extent1[3], extent2[3])

    # Calculate the size of the footprint in pixels
    gt1 = first_ds.GetGeoTransform()
    pixel_width = gt1[1]
    pixel_height = abs(gt1[5])

    # Align the first raster to the footprint
    warp_options = gdal.WarpOptions(
        format="GTiff",
        outputBounds=(footprint_minx, footprint_miny, footprint_maxx, footprint_maxy),
        xRes=pixel_width,
        yRes=pixel_height,
        resampleAlg="nearest",
        dstNodata=0,
        creationOptions = ["NBITS=1", "COMPRESS=LZW"]
    )
    print('creating first fp mask...')
    result = gdal.Warp(out_mask_1_path, first_raster_path, options=warp_options)
    if result is None:
        raise RuntimeError("gdal.Warp failed for the first raster.")

    print('creating second fp mask...')

    # Align the second raster to the footprint
    result = gdal.Warp(out_mask_2_path, second_raster_path, options=warp_options)
    if result is None:
        raise RuntimeError("gdal.Warp failed for the second raster.")

    gdal_calc_path = os.path.join(os.path.dirname(__file__), "gdal_calc.py")

    # Use subprocess to call gdal_calc.py
    command = [
        sys.executable, gdal_calc_path,
        "-A", out_mask_1_path,
        "-B", out_mask_2_path,
        "--calc=1*((A>0)|(B>0))",
        "--NoDataValue=0",
        "--outfile", footprint_mask_path,
        "--co", "NBITS=1",
        "--co", "COMPRESS=LZW"
    ]

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        print(f"Error running gdal_calc.py:\n{result.stderr}")
    else:
        print(f"Footprint mask created successfully at: {footprint_mask_path}")


def create_mask_with_gdal_translate(input_raster, output_mask):
    """
    Create a valid-value mask using gdal_translate.

    Args:
        input_raster (str): Path to the input raster file.
        output_mask (str): Path to the output mask file.
    """
    try:
        # Construct the gdal_translate command
        command = [
            "gdal_translate",
            "-of", "GTiff",  # Output format
            "-b", "mask",  # Use the internal mask band
            "-co", "NBITS=1",  # Single bit per pixel
            "-co", "COMPRESS=LZW",  # Use LZW compression
            input_raster,  # Input raster file
            output_mask  # Output mask file
        ]

        # Run the command
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check for errors
        if result.returncode != 0:
            print(f"Error running gdal_translate:\n{result.stderr}")
        else:
            print(f"Mask created successfully at: {output_mask}")

    except Exception as e:
        print(f"An error occurred: {e}")

def save_bit_mask_with_gdal(mask, output_path, geotransform, projection, compress=True):
    """
    Save a binary mask as a single-bit raster with LZW compression using GDAL.

    Parameters:
        mask (numpy.ndarray): Binary mask (2D array with values 0 and 1).
        output_path (str): Path to save the raster file.
        geotransform (tuple): Geotransform tuple for the raster.
        projection (str): Projection in WKT format.
    """
    # Ensure the mask is uint8 with values 0 or 1
    mask = (mask > 0).astype(np.uint8)

    # Get dimensions
    rows, cols = mask.shape

    if compress:
        options = ["NBITS=1", "COMPRESS=LZW"]
    else:
        options = ["NBITS=1"]
    # Create a single-band raster dataset with 1-bit depth and LZW compression
    driver = gdal.GetDriverByName('GTiff')
    dataset = driver.Create(
        output_path,
        cols,
        rows,
        1,  # Number of bands
        gdal.GDT_Byte,  # Data type
        options=options
    )

    # Set geotransform and projection
    dataset.SetGeoTransform(geotransform)
    dataset.SetProjection(projection)

    # Write the mask to the band
    band = dataset.GetRasterBand(1)
    band.WriteArray(mask)

    # Set NoData value to 0
    band.SetNoDataValue(0)

    band.FlushCache()

    # Clean up
    band = None
    dataset = None
    print(f"Mask saved to {output_path}")
    copy_qml(output_path)

def copy_qml(output_path):
    """
    Copies a matching .qml file from style_file_folder to the directory of output_path, renaming it to match output_path.

    Parameters:
    - output_path: Full path of the output raster file.
    """
    # Define the folder containing the .qml style files
    style_file_folder = os.path.join(os.path.dirname(__file__), 'style_files')

    # Extract the base name of the output file (without extension)
    output_base_name = os.path.splitext(os.path.basename(output_path))[0]

    # Iterate through .qml files in the style folder
    for file_name in os.listdir(style_file_folder):
        if file_name.endswith('.qml'):
            # Extract the base name of the .qml file
            qml_base_name = os.path.splitext(file_name)[0]

            # Use regex to check if the .qml base name matches the suffix of the output file
            if re.search(re.escape(qml_base_name) + r'$', output_base_name):
                # Found a match: Copy and rename the .qml file
                source_qml_path = os.path.join(style_file_folder, file_name)
                target_qml_path = os.path.splitext(output_path)[0] + '.qml'

                # Copy the .qml file to the same folder as the output file
                shutil.copy2(source_qml_path, target_qml_path)

                #print(f"Copied style file {target_qml_path}")
                return  # Exit after finding the first match

from osgeo import gdal



def save_rast_as_geotiff(mask_array, output_path, geotransform, projection):
    from osgeo import gdal
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    driver = gdal.GetDriverByName('GTiff')
    xsize, ysize = mask_array.shape[1], mask_array.shape[0]
    # Specify LZW compression
    out_ds = driver.Create(output_path, xsize, ysize, 1, gdal.GDT_Byte, options=['COMPRESS=LZW'])
    out_ds.SetGeoTransform(geotransform)
    out_ds.SetProjection(projection)
    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(mask_array)
    out_band.SetNoDataValue(0)  # Set nodata to 0 for compatibility with QGIS
    out_ds.FlushCache()
    out_ds = None
    print(f"Mask saved to {output_path}")
    copy_qml(output_path)


def extract_raster_sources_from_vrt(vrt_path):
    """
    Extracts the file paths of constituent rasters from a VRT file, removing duplicates,
    and resolves them to full file paths.

    Parameters:
        vrt_path (str): Path to the input VRT file.

    Returns:
        list: List of unique, full file paths of constituent rasters.
    """
    # Parse the VRT file as XML
    tree = ET.parse(vrt_path)
    root = tree.getroot()

    # Get the directory of the VRT file
    vrt_dir = os.path.dirname(os.path.abspath(vrt_path))

    # Find all <SourceFilename> elements and extract their text
    source_files = []
    for source_filename in root.findall(".//SourceFilename"):
        relative_path = source_filename.text
        # Resolve relative path to absolute path
        full_path = os.path.abspath(os.path.join(vrt_dir, relative_path))
        source_files.append(full_path)

    # Remove duplicates
    unique_source_files = list(set(source_files))

    return unique_source_files

def extract_mask_and_rgb_from_vrt(vrt_path):
    """
    Extracts the full paths of the mask and aligned RGB TIFF from a VRT file.

    Parameters:
        vrt_path (str): Path to the input VRT file.

    Returns:
        tuple: A tuple containing the full paths of the mask (str) and the aligned RGB TIFF (str).
    """
    # Parse the VRT file as XML
    tree = ET.parse(vrt_path)
    root = tree.getroot()

    # Get the directory of the VRT file
    vrt_dir = os.path.dirname(os.path.abspath(vrt_path))

    mask_path = None
    rgb_tiff_path = None

    # Iterate over all <SimpleSource> elements in the VRT
    for simple_source in root.findall(".//SimpleSource"):
        # Get the file path and relativeToVRT attribute
        source_filename = simple_source.find("SourceFilename")
        relative_to_vrt = int(source_filename.attrib.get("relativeToVRT", "0"))
        source_band = int(simple_source.find("SourceBand").text)

        # Resolve the full file path
        file_path = source_filename.text
        if relative_to_vrt == 1:
            file_path = os.path.abspath(os.path.join(vrt_dir, file_path))

        # Determine if it's a mask or an aligned RGB TIFF
        if source_band == 1:
            mask_path = file_path  # Mask always has SourceBand 1
        else:
            rgb_tiff_path = file_path  # Aligned RGB TIFF has multiple bands

    # Ensure both paths are found
    if not mask_path or not rgb_tiff_path:
        raise ValueError("Could not determine both mask and aligned RGB TIFF paths from the VRT.")

    return mask_path, rgb_tiff_path

def merge_vrt_rasters(raster_paths, output_vrt_path):
    """
    Merges multiple rasters with a nodata value of 0 into a VRT file,
    where the nodata values are respected, i.e., pixels with value 0 are treated as transparent.

    Parameters:
        raster_paths (list of str): List of paths to input GeoTIFF files.
        output_vrt_path (str): Path where the output VRT file will be saved.
    """
    if len(raster_paths) < 2:
        raise ValueError("At least two raster paths are required for merging.")

    nodata_value = 0

    # Build VRT options with specified nodata values
    vrt_options = gdal.BuildVRTOptions(srcNodata=nodata_value, VRTNodata=nodata_value)

    # Build VRT by merging the input rasters
    gdal.BuildVRT(output_vrt_path, raster_paths, options=vrt_options)

    print(f"Output merged VRT saved at: {output_vrt_path}")



def get_file_size_in_gb(file_path):
    file_size_bytes = os.path.getsize(file_path)
    return file_size_bytes / (1024 ** 3)

def save_output_to_raster(stacked_data_out, stacked_data_out_path, gt, proj):
    """
    Saves the output data as a GeoTIFF raster.

    Parameters:
    - stacked_data_out: numpy array of shape (rows, cols, bands) containing output RGBA data.
    - stacked_data_out_path: path to save the output raster.
    - gt: geotransform of the raster.
    - proj: projection of the raster.
    """
    from osgeo import gdal

    # Get dimensions and number of bands
    rows, cols, bands = stacked_data_out.shape

    # Create the output dataset
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(stacked_data_out_path, cols, rows, bands, gdal.GDT_Byte, options=['COMPRESS=LZW','BIGTIFF=YES'])

    # Set geotransform and projection
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)

    # Write each band to the output file
    for i in range(bands):
        out_band = out_ds.GetRasterBand(i + 1)
        out_band.WriteArray(stacked_data_out[:, :, i])
        out_band.FlushCache()

    # Close the dataset
    out_ds = None

    gb = get_file_size_in_gb(stacked_data_out_path)

    print(f"Raster saved to {stacked_data_out_path}, {round(gb,4)} GB")