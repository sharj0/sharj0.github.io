import math
from qgis.core import QgsVectorLayer, QgsFeature

def calculate_line_angle(start_point, end_point):
    dx = end_point.x() - start_point.x()
    dy = end_point.y() - start_point.y()
    angle = math.degrees(math.atan2(dy, dx))
    if angle < 0:
        angle += 360
    if angle >= 180:
        angle -= 180
    return angle

def angle_difference(a1, a2):
    diff = abs(a1 - a2)
    return min(diff, 180 - diff)

def feature_rep_angle(feat):
    geom = feat.geometry()
    if geom is None or geom.isNull():
        return None
    if geom.isMultipart():
        parts = geom.asMultiPolyline()
        if not parts or len(parts[0]) < 2:
            return None
        pts = parts[0]
        return calculate_line_angle(pts[0], pts[-1])
    else:
        pts = geom.asPolyline()
        if not pts or len(pts) < 2:
            return None
        return calculate_line_angle(pts[0], pts[-1])

def classify_flight_and_tie(input_layer: QgsVectorLayer, angle_tolerance: float = 10.0):

    features = list(input_layer.getFeatures())
    if not features:
        raise ValueError("Cannot classify: input layer has no features.")

    feat_angles = []
    for f in features:
        ang = feature_rep_angle(f)
        if ang is not None:
            feat_angles.append((f, ang))

    if not feat_angles:
        raise ValueError("Cannot classify: no feature has a valid line geometry.")

    first_angle = feat_angles[0][1]

    group_A = []
    group_B = []

    for f, ang in feat_angles:
        if angle_difference(ang, first_angle) <= angle_tolerance:
            group_A.append(f)
        else:
            group_B.append(f)

    if len(group_A) >= len(group_B):
        flt_feats = group_A
        tie_feats = group_B
    else:
        flt_feats = group_B
        tie_feats = group_A

    print(f"Classified: {len(flt_feats)} flight lines, {len(tie_feats)} tie lines.")
    return flt_feats, tie_feats

def filter_lines_by_type(input_layer: QgsVectorLayer, want_tie: bool, angle_tolerance: float = 10.0) -> QgsVectorLayer:
    """
    Returns a new memory layer containing only flight lines or tie lines.
    Never modifies input_layer.
    """
    flt_feats, tie_feats = classify_flight_and_tie(input_layer, angle_tolerance=angle_tolerance)

    if want_tie:
        selected_feats = tie_feats
        type_str = "tie"
    else:
        selected_feats = flt_feats
        type_str = "flt"

    print(f"Creating filtered memory layer with {len(selected_feats)} features ({type_str}).")

    # Create memory layer with same CRS and fields as input
    crs_wkt = input_layer.crs().toWkt()
    mem_layer = QgsVectorLayer(f"LineString?crs={crs_wkt}", "filtered_lines", "memory")
    mem_provider = mem_layer.dataProvider()
    mem_provider.addAttributes(input_layer.fields())
    mem_layer.updateFields()

    new_features = []
    for feat in selected_feats:
        new_feat = QgsFeature()
        new_feat.setGeometry(feat.geometry())
        new_feat.setFields(mem_layer.fields())
        for i, field in enumerate(input_layer.fields()):
            new_feat.setAttribute(i, feat.attribute(i))
        new_features.append(new_feat)

    mem_provider.addFeatures(new_features)
    mem_layer.updateExtents()

    return mem_layer
