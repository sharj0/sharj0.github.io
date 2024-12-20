#! C:\PROGRA~1\QGIS33~1.0\apps\Python312\python3.exe

import sys

from osgeo.gdal import UseExceptions, deprecation_warn

# import osgeo_utils.gdal_calc as a convenience to use as a script
from osgeo_utils.gdal_calc import *  # noqa
from osgeo_utils.gdal_calc import main

UseExceptions()

deprecation_warn("gdal_calc")
sys.exit(main(sys.argv))
