from pm_utils import binary_fill_holes_on_tiff

from save_geotiffs import save_bit_mask_with_gdal

input_tiff_bitmask = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\2,1mr_10_GSD_v2\aurora_mid_w-orthomosaic.mask.tiff"
output_tiff_bitmask = r"R:\ORTHO_STUFF\Aurora_ortho_chunks\2,1mr_10_GSD_v2\aurora_mid_w-orthomosaic_filled.mask.tiff"
binary_fill_holes_on_tiff(input_tiff_bitmask, output_tiff_bitmask, save_bit_mask_with_gdal)
