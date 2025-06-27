'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
'''
from qgis.core import (
    QgsRasterLayer,
    QgsVectorLayer,
    QgsPointXY,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRaster,
)
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os, json
import os
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt, QUrl
from PyQt5.Qt import QDesktopServices

def add_custom_buttons(guiz, plugin_dir):
    # Swath FOV Line-Spacing solver START
    LineSpace_icon_path = os.path.join(plugin_dir, 'Polygon_converter.png')
    button_font = QFont()
    button_font.setPointSize(12)
    run_button = QPushButton("Convert Polygon to Headwall kml format")
    run_button.setFont(button_font)
    run_button.setIcon(QIcon(LineSpace_icon_path))
    guiz.mainLayout.addWidget(run_button, 0, Qt.AlignLeft)
    run_button.clicked.connect(lambda: convert_poly_to_headwall_format())
    # Swath FOV Line-Spacing solver END


def convert_poly_to_headwall_format():

    # ─── USER PARAMETER ─────────────────────────────────────────────────────────────
    add_to_project = False  # True → layers appear in QGIS; False → stay hidden
    # ────────────────────────────────────────────────────────────────────────────────

    # Path to your JSON config (in your project folder)
    config_path = "poly_converter_previous_selection.json"

    # 1️⃣ Create or load the config file
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {
            "input_vector_path": r"Z:\Rosor\2024 - 2025\Projects\2502-58-3-dlmrh-teck-white-earth\3.Planning\Data_Collection_Polygon\West_Data_Poly.shp",
            "dem_path": r"Z:\Rosor\2024 - 2025\Projects\2502-58-3-dlmrh-teck-white-earth\3.Planning\handing_over_to_pyotyr\DSM_DEM_Teck_white_earth_TIF\DEM.tif"
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    # 2️⃣ Ask for vector, pre-loading last choice
    vector_filter = "Vector files (*.shp *.kml *.kmz)"
    input_vector_path, _ = QFileDialog.getOpenFileName(
        None,
        "Select a polygon vector (shp, kml, kmz)",
        config["input_vector_path"],
        vector_filter
    )
    if not input_vector_path:
        raise RuntimeError("No vector file selected.")

    # 3️⃣ Ask for DEM, pre-loading last choice
    dem_filter = "DEM files (*.tif *.tiff)"
    dem_path, _ = QFileDialog.getOpenFileName(
        None,
        "Select DEM raster (tif, tiff)",
        config["dem_path"],
        dem_filter
    )
    if not dem_path:
        raise RuntimeError("No DEM file selected.")

    # 4️⃣ Save back your selection for next time
    config["input_vector_path"] = input_vector_path
    config["dem_path"] = dem_path
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    # 5️⃣ Build a unique output KML path next to the vector
    base = os.path.splitext(os.path.basename(input_vector_path))[0]
    suffix = "_HW_format"
    folder = os.path.dirname(input_vector_path)

    def make_unique_path(base, suffix, folder, ext=".kml"):
        name = f"{base}{suffix}{ext}"
        full = os.path.join(folder, name)
        i = 2
        while os.path.exists(full):
            name = f"{base}{suffix}_v{i}{ext}"
            full = os.path.join(folder, name)
            i += 1
        return full

    output_kml = make_unique_path(base, suffix, folder)

    # 6️⃣ XML pretty‐print helper
    def prettify(elem):
        rough = ET.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough)
        return reparsed.toprettyxml(indent="  ")

    # 7️⃣ Load DEM (for sampling)
    dem_layer = QgsRasterLayer(dem_path, "DEM")
    if not dem_layer.isValid():
        raise RuntimeError(f"Could not load DEM: {dem_path}")
    if add_to_project:
        QgsProject.instance().addMapLayer(dem_layer)

    # 8️⃣ Load vector (any CRS)
    vlayer = QgsVectorLayer(input_vector_path, "input", "ogr")
    if not vlayer.isValid():
        raise RuntimeError(f"Could not load vector: {input_vector_path}")
    if add_to_project:
        QgsProject.instance().addMapLayer(vlayer)

    # 9️⃣ Prepare coordinate transforms
    crs_src = vlayer.crs()
    crs_dem = dem_layer.crs()
    crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

    xform_to_dem = QgsCoordinateTransform(crs_src, crs_dem, QgsProject.instance())
    xform_to_wgs84 = QgsCoordinateTransform(crs_src, crs_wgs84, QgsProject.instance())

    # 🔟 Extract exterior rings from all polygon features
    poly_list = []
    for feat in vlayer.getFeatures():
        geom = feat.geometry()
        if geom.isEmpty(): continue
        if geom.isMultipart():
            for mp in geom.asMultiPolygon():
                if mp and mp[0]:
                    poly_list.append(mp[0])
        else:
            poly = geom.asPolygon()
            if poly and poly[0]:
                poly_list.append(poly[0])

    if not poly_list:
        raise RuntimeError("No polygon geometries found in the input layer.")

    # 1️⃣1️⃣ Build and populate the 3D KML
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    ET.register_namespace("", ns["kml"])
    kml_doc = ET.Element("kml", xmlns=ns["kml"])
    doc = ET.SubElement(kml_doc, "Document")

    for idx, ring in enumerate(poly_list):
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = f"Polygon_{idx}"
        ET.SubElement(pm, "description").text = "Sampled Z from local DEM. Coordinates: lon,lat,alt (m)."

        poly = ET.SubElement(pm, "Polygon")
        ET.SubElement(poly, "extrude").text = "1"
        ET.SubElement(poly, "tessellate").text = "1"
        ET.SubElement(poly, "altitudeMode").text = "absolute"

        outer = ET.SubElement(poly, "outerBoundaryIs")
        ring_elem = ET.SubElement(outer, "LinearRing")
        coords = ET.SubElement(ring_elem, "coordinates")

        lines = []
        for pt in ring:
            ll = xform_to_wgs84.transform(pt)  # lon/lat output
            dm_pt = xform_to_dem.transform(pt)  # DEM sampling
            res = dem_layer.dataProvider() \
                .identify(QgsPointXY(dm_pt), QgsRaster.IdentifyFormatValue) \
                .results()
            elev = res.get(1, None)
            if elev is None:
                raise RuntimeError(f"No DEM value at {ll.x()},{ll.y()}")
            lines.append(f"{ll.x():.6f},{ll.y():.6f},{elev:.3f}")

        coords.text = "\n  " + "\n  ".join(lines) + "\n"

    # 1️⃣2️⃣ Write the output KML
    with open(output_kml, "w", encoding="utf-8") as f:
        f.write(prettify(kml_doc))

    # 1️⃣3️⃣ Show success popup
    QMessageBox.information(
        None,
        "Poly Converter",
        f"Success!\n\nFile:\n{os.path.basename(output_kml)}\n\nSaved to:\n{folder}"
    )