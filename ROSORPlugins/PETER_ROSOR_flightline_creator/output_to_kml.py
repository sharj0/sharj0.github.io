from qgis.core import QgsGeometry, QgsVectorLayer, QgsWkbTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
import os

def get_swath_kml_representation(indx, coords_lonlat):
    kml_text = f'\n    <Placemark> <name> swath_{indx} </name> ' \
               f'\n    <open> 1 </open> ' \
               f'\n    <styleUrl> #msn_ylw-pushpin</styleUrl>' \
               f'\n    <Polygon> <outerBoundaryIs> <LinearRing> <coordinates> ' \
               f'\n    {coords_lonlat[0][0]},{coords_lonlat[0][1]} ' \
               f'\n    {coords_lonlat[1][0]},{coords_lonlat[1][1]} ' \
               f'\n    {coords_lonlat[2][0]},{coords_lonlat[2][1]} ' \
               f'\n    {coords_lonlat[3][0]},{coords_lonlat[3][1]} ' \
               f'\n    {coords_lonlat[0][0]},{coords_lonlat[0][1]} ' \
               f'\n    </coordinates> </LinearRing> </outerBoundaryIs> </Polygon> </Placemark>'
    return kml_text

def output_swaths_to_kml(swaths_shp_path, output_swaths_kml_path):
    # Load the shapefile
    layer = QgsVectorLayer(swaths_shp_path, "rectangle_layer", "ogr")

    # Check if the layer is valid
    if not layer.isValid():
        print("Layer failed to load!")
    else:
        print("Layer was loaded successfully!")

    sourceCrs = layer.crs()
    targetCrs = QgsCoordinateReferenceSystem("EPSG:4326")

    # Create a transform function between the source and target CRS
    transform = QgsCoordinateTransform(sourceCrs, targetCrs, QgsProject.instance())

    coords_lonlat_list = []
    # Transform each feature in the layer
    for feature in layer.getFeatures():
        geom = feature.geometry()
        geom.transform(transform)

        coords_lonlat_list.append([[point.x(), point.y()] for point in geom.asMultiPolygon()[0][0]])

    internal_name = os.path.basename(output_swaths_kml_path[:-4])

    kml_header = f'<?xml version="1.0" encoding="UTF-8"?>' \
                 f'\n<kml xmlns="http://www.opengis.net/kml/2.2" ' \
                 f'xmlns:gx="http://www.google.com/kml/ext/2.2" ' \
                 f'xmlns:kml="http://www.opengis.net/kml/2.2" ' \
                 f'xmlns:atom="http://www.w3.org/2005/Atom"> ' \
                 f'\n<Document>' \
                 f'\n   <name> {internal_name} </name>' \
                 f'\n	<StyleMap id="msn_ylw-pushpin">' \
                 f'\n		<Pair>' \
                 f'\n			<key>normal</key>' \
                 f'\n			<styleUrl>#sn_ylw-pushpin</styleUrl>' \
                 f'\n		</Pair>' \
                 f'\n		<Pair>' \
                 f'\n			<key>highlight</key>' \
                 f'\n			<styleUrl>#sh_ylw-pushpin</styleUrl>' \
                 f'\n		</Pair>' \
                 f'\n	</StyleMap>' \
                 f'\n	<Style id="sh_ylw-pushpin">' \
                 f'\n		<IconStyle>' \
                 f'\n			<scale>1.3</scale>' \
                 f'\n			<Icon>' \
                 f'\n				<href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href>' \
                 f'\n			</Icon>' \
                 f'\n			<hotSpot x="20" y="2" xunits="pixels" yunits="pixels"/>' \
                 f'\n		</IconStyle>' \
                 f'\n		<BalloonStyle>' \
                 f'\n		</BalloonStyle>' \
                 f'\n		<LineStyle>' \
                 f'\n			<color>8000ffff</color>' \
                 f'\n		</LineStyle>' \
                 f'\n		<PolyStyle>' \
                 f'\n			<color>3300ffff</color>' \
                 f'\n		</PolyStyle>' \
                 f'\n	</Style>' \
                 f'\n	<Style id="sn_ylw-pushpin">' \
                 f'\n		<IconStyle>' \
                 f'\n			<scale>1.1</scale>' \
                 f'\n			<Icon>' \
                 f'\n				<href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href>' \
                 f'\n			</Icon>' \
                 f'\n			<hotSpot x="20" y="2" xunits="pixels" yunits="pixels"/>' \
                 f'\n		</IconStyle>' \
                 f'\n		<BalloonStyle>' \
                 f'\n		</BalloonStyle>' \
                 f'\n		<LineStyle>' \
                 f'\n			<color>ff00ff00</color>' \
                 f'\n		</LineStyle>' \
                 f'\n		<PolyStyle>' \
                 f'\n			<color>4500ffff</color>' \
                 f'\n		</PolyStyle>' \
                 f'\n	</Style>'
    kml_body = ''
    for indx, coords_lonlat in enumerate(coords_lonlat_list):
        kml_body += get_swath_kml_representation(indx, coords_lonlat)
    kml_footer = f'\n</Document> \n</kml>'
    kml_text = kml_header + kml_body + kml_footer
    with open(str(output_swaths_kml_path), 'w') as f:
        f.write(kml_text)
    print(f'success swath kml written{output_swaths_kml_path}')




def line_geometries_to_kml(geometries, output_kml_path, crs):
    # Define the target CRS as WGS 84 (EPSG:4326)
    target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(crs), target_crs, QgsProject.instance())

    # Start the KML file
    kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <Style id="redLine">
        <LineStyle>
            <color>ff0000ff</color>
            <width>4</width>
        </LineStyle>
    </Style>'''

    for geom in geometries:
        # Transform the geometry to EPSG:4326
        geom.transform(transform)

        # Extract the points from the transformed geometry
        points = geom.asPolyline()
        coords_str = " ".join([f"{point.x()},{point.y()}" for point in points])  # Note: KML uses y,x ordering

        # Add the line to the KML content
        kml_content += f'''
    <Placemark>
        <styleUrl>#redLine</styleUrl>
        <LineString>
            <tessellate>1</tessellate>
            <coordinates>{coords_str}</coordinates>
        </LineString>
    </Placemark>'''

    # Close the KML tags
    kml_content += '''
</Document>
</kml>'''

    # Write the KML content to a file
    with open(output_kml_path, 'w') as file:
        file.write(kml_content)



def save_kml_polygon(new_poly_shapley, output_kml_path, crs):
    new_poly = QgsGeometry.fromWkt(new_poly_shapley.wkt)

    # Set up the coordinate transformation
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(crs), QgsCoordinateReferenceSystem("EPSG:4326"),
                                       QgsProject.instance())

    # Transform the polygon geometry to EPSG:4326
    new_poly.transform(transform)

    # Extract the points from the transformed polygon's exterior ring
    exterior_ring = new_poly.asPolygon()[0]
    coords_str = " ".join([f"{point.x()},{point.y()}" for point in exterior_ring])  # KML uses y,x ordering

    # Start building the KML content
    kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <Style id="orangeOutline">
        <LineStyle>
            <color>ff00a5ff</color> <!-- Orange color -->
            <width>4</width>
        </LineStyle>
        <PolyStyle>
            <fill>0</fill> <!-- No fill -->
        </PolyStyle>
    </Style>
    <Placemark>
        <styleUrl>#orangeOutline</styleUrl>
        <Polygon>
            <outerBoundaryIs>
                <LinearRing>
                    <coordinates>{coords_str}</coordinates>
                </LinearRing>
            </outerBoundaryIs>
        </Polygon>
    </Placemark>
</Document>
</kml>'''

    # Write the KML content to the specified file
    with open(output_kml_path, 'w') as file:
        file.write(kml_content)
