import math
from qgis.core import QgsGeometry, QgsPoint, QgsLineString, QgsVectorLayer, QgsWkbTypes, QgsPointXY, QgsGeometry
import matplotlib.pyplot as plt

def merge_multiline_segments(multiline, merge_gaps):
    merged_segments = []
    current_segment = []

    can_remove_points_list = []
    for i in range(len(multiline) - 1):
        current_segment.extend(multiline[i])
        end_point = multiline[i][-1]
        start_point = multiline[i + 1][0]

        # Calculate the gap using Euclidean distance
        gap = math.sqrt((end_point.x() - start_point.x()) ** 2 + (end_point.y() - start_point.y()) ** 2)

        if gap > merge_gaps:
            # Add the current segment and start a new one
            merged_segments.append(current_segment)
            current_segment = []
            can_remove_points_list.extend([False, False])
        else:
            can_remove_points_list.extend([False, True])
    can_remove_points_list.extend([False, False])

    can_remove_points_list_extended = can_remove_points_list.copy()
    for i in range(len(can_remove_points_list) - 1):
        if can_remove_points_list[i]:
            can_remove_points_list_extended[i + 1] = True

    # Flatten the list using a list comprehension
    flat_list = [point for sublist in multiline for point in sublist]
    keep_points_mask = [not x for x in can_remove_points_list_extended]
    keep_points = [point for point, keep in zip(flat_list, keep_points_mask) if keep]
    assert len(keep_points) % 2 == 0, "The list 'keep_points' does not contain an even number of elements."
    # Pair up the points into sub-lists
    paired_points = [keep_points[i:i + 2] for i in range(0, len(keep_points), 2)]

    # Add the last segment
    #current_segment.extend(multiline[-1])
    #merged_segments.append(current_segment)
    return paired_points


def merge_gaps_function(processed_lines, merge_gaps):
    processed_for_plotting = []

    for indxxe, line in enumerate(processed_lines):
        if QgsWkbTypes.isMultiType(line.wkbType()):
            # Handle MultiLineString
            multiline = line.asMultiPolyline()

            merged = merge_multiline_segments(multiline, merge_gaps)


            if len(merged) == 1:
                # Convert to LineString if only one segment remains
                # but first make sure single line string does not have more than two points
                assert len(merged[0]) <= 2
                linestring = QgsLineString([QgsPointXY(point.x(), point.y()) for point in merged[0]])
                processed_for_plotting.append(QgsGeometry(linestring))
            else:
                # Keep as MultiLineString
                merged_lines = [[QgsPointXY(point.x(), point.y()) for point in segment] for segment in merged]
                processed_for_plotting.append(QgsGeometry.fromMultiPolylineXY(merged_lines))
        else:
            # Single LineStrings remain unchanged
            processed_for_plotting.append(line)

    return processed_for_plotting


def plot_lines(processed_lines, merge_gaps):
    fig, ax = plt.subplots()
    for indx, line in enumerate(processed_lines):
        if QgsWkbTypes.isMultiType(line.wkbType()):


            '''.......temp...........'''

            continue

            '''.......temp...........'''

            # Handle MultiLineString
            num_parts = len(line.asMultiPolyline())
            for i, part in enumerate(line.asMultiPolyline()):
                x = [point.x() for point in part]
                y = [point.y() for point in part]
                # Calculate color intensity based on the segment index
                intensity = (i + 1) / num_parts
                color = (1, 0, 0, intensity)  # Red color with varying alpha
                ax.plot(x, y, color=color)
                # Plotting the gaps in purple
                if i < num_parts - 1:
                    next_part = line.asMultiPolyline()[i + 1]
                    start_point = QgsPoint(part[-1])
                    end_point = QgsPoint(next_part[0])
                    gap = math.sqrt((end_point.x() - start_point.x()) ** 2 + (end_point.y() - start_point.y()) ** 2)
                    if gap < merge_gaps:
                        ax.plot([start_point.x(), end_point.x()], [start_point.y(), end_point.y()], ':',
                                color='purple')
                    else:
                        ax.plot([start_point.x(), end_point.x()], [start_point.y(), end_point.y()], ':',
                                color='green')

        elif QgsWkbTypes.isSingleType(line.wkbType()):
            # Handle single LineString
            polyline = line.asPolyline()
            x = [point.x() for point in polyline]
            y = [point.y() for point in polyline]
            ax.plot(x, y, 'b')
    ax.set_aspect('equal', adjustable='box')
    plt.show()

def get_rotated_line(input_angle_ccwE, anchor_x, anchor_y, x1, y1, x2, y2):
    angle_radians = math.radians(input_angle_ccwE)

    # Rotate around the anchor point
    x1_rot = (x1 - anchor_x) * math.cos(angle_radians) - (y1 - anchor_y) * math.sin(angle_radians) + anchor_x
    y1_rot = (x1 - anchor_x) * math.sin(angle_radians) + (y1 - anchor_y) * math.cos(angle_radians) + anchor_y
    x2_rot = (x2 - anchor_x) * math.cos(angle_radians) - (y2 - anchor_y) * math.sin(angle_radians) + anchor_x
    y2_rot = (x2 - anchor_x) * math.sin(angle_radians) + (y2 - anchor_y) * math.cos(angle_radians) + anchor_y

    line = QgsGeometry(QgsLineString([QgsPoint(x1_rot, y1_rot), QgsPoint(x2_rot, y2_rot)]))
    return line

def save_to_wkt_for_debug(line_string_list, output_file_path = "I:\QGIS_PLUGINS\TEST_LINE_MAKER\TEST\wkt.txt"):
    line_string_list_wkt = [geom.asWkt() for geom in line_string_list]  # Convert to WKT
    # Write the WKT strings to a file
    with open(output_file_path, 'w') as file:
        for wkt in line_string_list_wkt:
            file.write(wkt + '\n')  # Write each WKT on a new line

def load_from_wkt_for_debug(input_file_path = "I:\QGIS_PLUGINS\TEST_LINE_MAKER\TEST\wkt.txt"):
    # Read WKT strings from the file
    with open(input_file_path, 'r') as file:
        wkt_list = file.readlines()

    # Convert each WKT string back to QgsGeometry
    line_string_list = [QgsGeometry.fromWkt(wkt.strip()) for wkt in wkt_list]
    return line_string_list

def generate_lines(poly_layer,
                   buffer_distance=25,
                   line_spacing=50,
                   input_angle_cwN=45,
                   shift_sideways=0,
                   merge_gaps=100,
                   delete_small_lines=1,
                   anchor_xy=(600000, 5390000)):

    if input_angle_cwN % 90 == 0: #band-aid fix
        input_angle_cwN += 1e-10

    anchor_x, anchor_y = anchor_xy

    extent = poly_layer.sourceExtent()
    delta_x = extent.xMaximum() - extent.xMinimum()
    delta_y = extent.yMaximum() - extent.yMinimum()
    delta = max(delta_x, delta_y) * 5
    extended_y_min = extent.yMinimum() - delta
    extended_x_min = extent.xMinimum() - delta
    extended_x_max = extent.xMaximum() + delta
    extended_y_max = extent.yMaximum() + delta


    # Calculate parallel lines above anchor_y
    lines = []
    y = anchor_y + shift_sideways
    while y <= extended_y_max:
        x1, y1 = extended_x_min, y
        x2, y2 = extended_x_max, y
        input_angle_ccwE = -(input_angle_cwN - 90)
        line = get_rotated_line(input_angle_ccwE, anchor_x, anchor_y, x1, y1, x2, y2)
        lines.append(line)
        y += line_spacing

    # Calculate parallel lines below anchor_y
    y = anchor_y - line_spacing + shift_sideways
    while y >= extended_y_min:
        x1, y1 = extended_x_min, y
        x2, y2 = extended_x_max, y
        input_angle_ccwE = -(input_angle_cwN - 90)
        line = get_rotated_line(input_angle_ccwE, anchor_x, anchor_y, x1, y1, x2, y2)
        lines.append(line)
        y -= line_spacing

    # Ensure there is exactly one polygon
    if poly_layer.featureCount() != 1:
        raise Exception("Input poly_layer must contain exactly one polygon")

    polygon_feature = next(poly_layer.getFeatures())
    polygon_geometry = polygon_feature.geometry()
    buffered_polygon = polygon_geometry.buffer(buffer_distance, 5, QgsGeometry.EndCapStyle.Flat, QgsGeometry.JoinStyle.Miter, line_spacing)
    #self, distance: float, segments: int, endCapStyle: Qgis.EndCapStyle, joinStyle: Qgis.JoinStyle, miterLimit: float

    # Clip the lines with the buffered polygon
    clipped_lines = []
    for line in lines:
        clipped_line = line.intersection(buffered_polygon)
        if not clipped_line.isEmpty():
            clipped_lines.append(clipped_line)

    # Processing lines to remove small lines
    processed_lines = []
    for line in clipped_lines:
        if line.length() >= delete_small_lines:
            processed_lines.append(line)


    processed_lines = merge_gaps_function(processed_lines, merge_gaps)

    # get rid of MultiLineString keep only LineString
    line_string_list = []
    for indxxx, line in enumerate(processed_lines):
        if line.isMultipart():
            multi_lines = line.asMultiPolyline()  # Extract as list of polylines (list of QgsPointXY)
            for polyline in multi_lines:
                # Convert each QgsPointXY to QgsPoint and then to QgsGeometry
                qgs_polyline = [QgsPoint(pt.x(), pt.y()) for pt in polyline]  # Convert QgsPointXY to QgsPoint
                line_string_list.append(QgsGeometry.fromPolyline(qgs_polyline))
        else:
            line_string_list.append(line)
            #print(f"{len(line.asPolyline())=},{indxxx}")


    #save_to_wkt_for_debug(line_string_list)
    #plot_lines(line_string_list, merge_gaps)

    return line_string_list

if __name__ == '__main__':
    #line_string_list = load_from_wkt_for_debug()
    layer = QgsVectorLayer(r"I:\QGIS_PLUGINS\TEST_LINE_MAKER\test_2_ab_lake_poly_UTM.shp", "poly_sqr", "ogr")
    generate_lines(layer)
    #plot_lines(line_string_list, 100)


