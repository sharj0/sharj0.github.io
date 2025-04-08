# --- START OF REVISED FILE IIIII_flight.py ---

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Arc
import matplotlib.colors as mcolors

# Assuming these base classes exist in the specified locations
from .base_node_class import Node
from .III_tof_assignment import TOFAssignment
from .IIIIIII_end_point import EndPoint
# from .IIII_line import Line # Example import

# --- Geometry & Turn Helper Functions ---

def _calculate_offset_point(coord, angle_deg, distance):
    """Calculates a point offset from coord at a specific angle and distance."""
    rad = np.deg2rad(angle_deg % 360)
    dx = np.cos(rad) * distance
    dy = np.sin(rad) * distance
    return (coord[0] + dx, coord[1] + dy)

def _discretize_arc(center, radius, start_angle_deg, end_angle_deg, segment_length):
    """Generates points along a circular arc, excluding the start point."""
    # Normalize angles for consistent calculation
    start_angle_rad = np.deg2rad(start_angle_deg)
    end_angle_rad = np.deg2rad(end_angle_deg)

    # Calculate directed angle difference using atan2 (handles wrapping)
    # Angle from start to end
    delta_angle_rad = np.arctan2(np.sin(end_angle_rad - start_angle_rad),
                                 np.cos(end_angle_rad - start_angle_rad))

    if abs(radius) < 1e-6 or abs(delta_angle_rad) < 1e-6:
         return np.array([])

    arc_length = abs(delta_angle_rad * radius)
    if segment_length <= 1e-6: segment_length = 1.0
    num_segments = max(1, int(np.ceil(arc_length / segment_length)))

    # Generate angles ensuring correct direction
    angles_rad = np.linspace(start_angle_rad, start_angle_rad + delta_angle_rad, num_segments + 1)

    points_x = center[0] + radius * np.cos(angles_rad)
    points_y = center[1] + radius * np.sin(angles_rad)

    arc_points = np.vstack((points_x, points_y)).T
    return arc_points[1:] # Exclude the start point

def _get_turn_centres(coord, ang_deg, turn_radius):
    """Calculates the left (CCW) and right (CW) potential turn centers."""
    perp_angle_left = (ang_deg + 90) % 360
    perp_angle_right = (ang_deg - 90) % 360
    left_tc = _calculate_offset_point(coord, perp_angle_left, turn_radius)
    right_tc = _calculate_offset_point(coord, perp_angle_right, turn_radius)
    return left_tc, right_tc

def _calculate_tangent_point(turn_center, origin_point, turn_radius, turn_direction_ccw):
    """Calculates the tangent point on a circle from an external origin point."""
    # (Implementation remains the same as previous correct version)
    dist_xy = np.array(origin_point) - np.array(turn_center)
    dist_center_origin = np.linalg.norm(dist_xy)
    if dist_center_origin <= turn_radius + 1e-6: return None
    angle_center_origin_rad = np.arctan2(dist_xy[1], dist_xy[0])
    ratio = np.clip(turn_radius / dist_center_origin, -1.0, 1.0)
    angle_offset_rad = np.arccos(ratio)
    if turn_direction_ccw: tangent_angle_rad = angle_center_origin_rad + angle_offset_rad
    else: tangent_angle_rad = angle_center_origin_rad - angle_offset_rad
    tx = turn_center[0] + turn_radius * np.cos(tangent_angle_rad)
    ty = turn_center[1] + turn_radius * np.sin(tangent_angle_rad)
    return (tx, ty)

def _get_arc_angles(center, point1, point2, is_ccw):
    """
    Calculate start and end angles for an arc segment from point1 to point2
    around center, ensuring the turn direction matches is_ccw and the
    total angle is <= 180 degrees (for typical tangent connections).
    """
    vec_c_p1 = np.array(point1) - np.array(center)
    vec_c_p2 = np.array(point2) - np.array(center)

    start_angle = np.rad2deg(np.arctan2(vec_c_p1[1], vec_c_p1[0]))
    end_angle = np.rad2deg(np.arctan2(vec_c_p2[1], vec_c_p2[0]))

    # Calculate directed difference, result in [-180, 180]
    delta_angle = (end_angle - start_angle + 180) % 360 - 180

    # Adjust if the calculated shortest angle direction mismatches the required is_ccw
    if is_ccw and delta_angle < -1e-6: # Required CCW, but shortest is CW
        delta_angle += 360 # Use the longer CCW path angle
    elif not is_ccw and delta_angle > 1e-6: # Required CW, but shortest is CCW
        delta_angle -= 360 # Use the longer CW path angle

    # Recalculate end_angle based on the adjusted delta
    final_end_angle = start_angle + delta_angle

    return start_angle, final_end_angle


def _get_shortest_distance_between_parallel_lines(p1, a1_deg, p2):
    """Calculates shortest distance between point p2 and line (p1, a1_deg)."""
    vec12 = np.array(p2) - np.array(p1)
    perp_angle_rad = np.deg2rad(a1_deg + 90)
    perp_vec = np.array([np.cos(perp_angle_rad), np.sin(perp_angle_rad)])
    distance = abs(np.dot(vec12, perp_vec))
    return distance

def _calculate_inter_line_turn_points(p1, a1_deg, p2, a2_deg, segment_length):
    """
    Generates turn points between two parallel line segments using dynamic radius
    and ensuring the turn direction is outwards.
    Returns list of points for the turn, excluding p1, ending at p2.
    """
    # Calculate perpendicular distance for radius (minimum U-turn radius)
    perp_dist = _get_shortest_distance_between_parallel_lines(p1, a1_deg, p2)
    turn_radius = max(perp_dist / 2.0, 1e-3) # Avoid zero radius

    # Determine required turn direction (Left/CCW or Right/CW)
    # Vector from p1 to p2
    vec_p1_p2 = np.array(p2) - np.array(p1)
    # Perpendicular vector to the direction leaving p1 (points "left")
    perp_left_rad = np.deg2rad(a1_deg + 90)
    perp_left_vec = np.array([np.cos(perp_left_rad), np.sin(perp_left_rad)])
    # Dot product determines side: >0 means p2 is generally "left", <0 means "right"
    dot_prod = np.dot(vec_p1_p2, perp_left_vec)

    turn_is_ccw = dot_prod > 0 # If dot_prod is positive, turn Left (CCW)

    # --- Select appropriate turn centers and calculate tangents ---
    start_left_tc, start_right_tc = _get_turn_centres(p1, a1_deg, turn_radius) # Angle leaving p1
    end_left_tc, end_right_tc = _get_turn_centres(p2, a2_deg, turn_radius)     # Angle arriving at p2

    tc1, tc2 = None, None
    arc1_is_ccw, arc2_is_ccw = None, None

    if turn_is_ccw: # Force Left Turn (LL Tangent)
        tc1 = start_left_tc
        tc2 = end_left_tc
        arc1_is_ccw = True
        arc2_is_ccw = True # Turn perspective relative to its center
    else: # Force Right Turn (RR Tangent)
        tc1 = start_right_tc
        tc2 = end_right_tc
        arc1_is_ccw = False
        arc2_is_ccw = False

    # Calculate common external tangent points (t1 on circle 1, t2 on circle 2)
    vec_c1_c2 = np.array(tc2) - np.array(tc1)
    dist_c1_c2 = np.linalg.norm(vec_c1_c2)
    if dist_c1_c2 < 1e-6: # Centers coincide - lines are likely overlapping
        print("Warning: Turn centers coincide in inter-line turn. Using straight line.")
        return [p2], abs(((a2_deg - a1_deg + 180) % 360) - 180)

    angle_c1_c2_rad = np.arctan2(vec_c1_c2[1], vec_c1_c2[0])

    if turn_is_ccw: # LL tangent
        tangent_angle_offset = -np.pi / 2
    else: # RR tangent
        tangent_angle_offset = +np.pi / 2

    # Angle from center to tangent point (same for both circles for external tangent)
    tangent_point_angle_rad = angle_c1_c2_rad + tangent_angle_offset

    t1 = (tc1[0] + turn_radius * np.cos(tangent_point_angle_rad),
          tc1[1] + turn_radius * np.sin(tangent_point_angle_rad))
    t2 = (tc2[0] + turn_radius * np.cos(tangent_point_angle_rad),
          tc2[1] + turn_radius * np.sin(tangent_point_angle_rad))

    # --- Sanity Check: Tangent points should be further out ---
    # Midpoint between original p1 and p2
    mid_p1_p2 = (np.array(p1) + np.array(p2)) / 2.0
    # Check if t1 is further from mid_p1_p2 than p1 is (a proxy for being "outside")
    dist_mid_t1 = np.linalg.norm(np.array(t1) - mid_p1_p2)
    dist_mid_p1 = np.linalg.norm(np.array(p1) - mid_p1_p2)
    if dist_mid_t1 < dist_mid_p1 - turn_radius * 0.1 : # Allow some tolerance
        print(f"Warning: Inter-line turn tangent point t1 {t1} might be inside. Check geometry.")
        # Potential fallback: Use straight line? Or proceed cautiously.

    # --- Calculate Arcs ---
    arc1_start_deg, arc1_end_deg = _get_arc_angles(tc1, p1, t1, arc1_is_ccw)
    # For arc2, points are t2 -> p2. Need angles relative to tc2.
    arc2_start_deg, arc2_end_deg = _get_arc_angles(tc2, t2, p2, arc2_is_ccw)

    # --- Discretize and Combine ---
    arc1_pts = _discretize_arc(tc1, turn_radius, arc1_start_deg, arc1_end_deg, segment_length)
    arc2_pts = _discretize_arc(tc2, turn_radius, arc2_start_deg, arc2_end_deg, segment_length)

    turn_points = []
    turn_points.extend(arc1_pts.tolist()) # Add points from first arc

    # Add tangent point t1 if distinct from last arc1 point
    if not turn_points or np.linalg.norm(np.array(turn_points[-1]) - np.array(t1)) > 1e-3:
        turn_points.append(t1)

    # Add tangent point t2 if distinct from t1
    if np.linalg.norm(np.array(t1) - np.array(t2)) > 1e-3:
         turn_points.append(t2) # Add start of second tangent

    turn_points.extend(arc2_pts.tolist()) # Add points from second arc

    # Ensure final point is p2
    if not turn_points or np.linalg.norm(np.array(turn_points[-1]) - np.array(p2)) > 1e-3:
        turn_points.append(p2)

    # Calculate total turn angle for stats
    total_turn_angle = abs(arc1_end_deg - arc1_start_deg) + abs(arc2_end_deg - arc2_start_deg)

    return turn_points, total_turn_angle


def _calculate_tof_turn_points(start_point, start_angle_deg, end_point, end_angle_deg, is_to_tof, settings):
    """
    Generates turn points between a line end/start and TOF.
    Uses fixed turn diameter from settings.
    """
    turn_diameter = settings.get("turn_diameter", 50.0)
    segment_length = settings.get("turn_segment_length", 21.0)
    turn_radius = turn_diameter / 2.0

    if turn_radius < 1e-3: # No radius, straight line
        return [end_point], abs(((end_angle_deg - start_angle_deg + 180) % 360) - 180)

    # Reference point/angle is the one connected to the survey line
    if is_to_tof: # Turning FROM line end (start_point) TO TOF (end_point)
        tc_ref_point = start_point
        tc_ref_angle = start_angle_deg
        other_point = end_point # TOF point
    else: # Turning FROM TOF (start_point) TO line start (end_point)
        tc_ref_point = end_point
        tc_ref_angle = end_angle_deg # Angle arriving at line lead-in
        other_point = start_point # TOF point

    left_tc, right_tc = _get_turn_centres(tc_ref_point, tc_ref_angle, turn_radius)

    # Find tangent point from TOF (other_point) to the left/right circles
    tangent_left = _calculate_tangent_point(left_tc, other_point, turn_radius, turn_direction_ccw=True)
    tangent_right = _calculate_tangent_point(right_tc, other_point, turn_radius, turn_direction_ccw=False)

    # Choose best tangent based on shortest path from other_point (TOF) to tangent
    best_tangent, chosen_tc, is_ccw = None, None, None
    min_dist = float('inf')

    if tangent_left:
        dist = np.linalg.norm(np.array(other_point) - np.array(tangent_left))
        if dist < min_dist:
            min_dist = dist; best_tangent = tangent_left; chosen_tc = left_tc; is_ccw = True
    if tangent_right:
        dist = np.linalg.norm(np.array(other_point) - np.array(tangent_right))
        if dist < min_dist:
             min_dist = dist; best_tangent = tangent_right; chosen_tc = right_tc; is_ccw = False

    if not best_tangent: # Fallback if TOF is inside turn circles
        print("Warning: TOF inside turn radius? Using straight line for TOF turn.")
        return [end_point], abs(((end_angle_deg - start_angle_deg + 180) % 360) - 180)

    # --- Calculate Arc and Combine Path ---
    turn_points = []
    arc_angle = 0
    if is_to_tof:
        # Path: line_end(start_point) -> arc -> tangent(best_tangent) -> TOF(end_point)
        arc_start_deg, arc_end_deg = _get_arc_angles(chosen_tc, start_point, best_tangent, is_ccw)
        arc_pts = _discretize_arc(chosen_tc, turn_radius, arc_start_deg, arc_end_deg, segment_length)
        turn_points.extend(arc_pts.tolist())
        # Add tangent point if distinct
        if not turn_points or np.linalg.norm(np.array(turn_points[-1]) - np.array(best_tangent)) > 1e-3:
             turn_points.append(best_tangent)
        # Add TOF point if distinct
        if np.linalg.norm(np.array(best_tangent) - np.array(end_point)) > 1e-3:
             turn_points.append(end_point)
        arc_angle = abs(arc_end_deg - arc_start_deg)
    else: # From TOF to Line Start
        # Path: TOF(start_point) -> tangent(best_tangent) -> arc -> line_start(end_point)
        arc_start_deg, arc_end_deg = _get_arc_angles(chosen_tc, best_tangent, end_point, is_ccw)
        arc_pts = _discretize_arc(chosen_tc, turn_radius, arc_start_deg, arc_end_deg, segment_length)
        # Add tangent point (first point after TOF) if distinct from TOF
        if np.linalg.norm(np.array(start_point) - np.array(best_tangent)) > 1e-3:
            turn_points.append(best_tangent)
        turn_points.extend(arc_pts.tolist())
        # Ensure final point is end_point
        if not turn_points or np.linalg.norm(np.array(turn_points[-1]) - np.array(end_point)) > 1e-3:
            turn_points.append(end_point)
        arc_angle = abs(arc_end_deg - arc_start_deg)

    # Filter out consecutive duplicates that might arise from tangent points
    final_turn_points = []
    if turn_points:
        final_turn_points.append(turn_points[0])
        for i in range(1, len(turn_points)):
            if np.linalg.norm(np.array(turn_points[i]) - np.array(turn_points[i-1])) > 1e-4:
                final_turn_points.append(turn_points[i])

    return final_turn_points, arc_angle


def convert_argb_to_matplotlib_hex(argb_hex):
    # (Implementation remains the same)
    if not isinstance(argb_hex, str):
        try: mcolors.to_rgba(argb_hex); return argb_hex
        except ValueError: return '#0000FF'
    clean_hex = argb_hex.lstrip('#')
    if len(clean_hex) == 8: return f"#{clean_hex[2:8]}{clean_hex[0:2]}"
    elif len(clean_hex) == 6: return f"#{clean_hex}"
    else:
        try: mcolors.to_rgba(clean_hex); return clean_hex
        except ValueError: return '#0000FF'


# --- Flight Class ---

class Flight(Node):
    # __init__ remains the same, applying defaults
    def __init__(self, name, flight_settings):
        super().__init__(name)
        default_settings = {
            'lead_in': 50.0, 'lead_out': 50.0, 'add_smooth_turns': True,
            'turn_segment_length': 21.0, 'turn_diameter': 50.0
        }
        self.flight_settings = {**default_settings, **(flight_settings or {})}
        self.utm_fly_list, self.turns = [], []
        self.overall_dist, self.production, self.waste_dist = 0, 0, 0
        self._raw_color, self.color = None, '#0000FF'

    @property
    def line_list(self):
        # (Implementation remains the same)
        try:
             from .IIII_line import Line
             return [child for child in self.children if isinstance(child, Line)]
        except ImportError:
             return [child for child in self.children if child.__class__.__name__ == "Line"]

    @property
    def tof_assignment(self):
        # (Implementation remains the same)
        current = self.parent
        while current is not None:
            if isinstance(current, TOFAssignment): return current
            current = current.parent
        if hasattr(self.root, 'children'):
             for child in self.root.children:
                 if isinstance(child, TOFAssignment): return child
        print("Warning: Could not find TOFAssignment.")
        return None

    def _get_line_segment_endpoints(self, line):
        # (Implementation remains the same)
        lead_in = self.flight_settings.get("lead_in", 0)
        lead_out = self.flight_settings.get("lead_out", 0)
        start_xy, end_xy = line.start.xy, line.end.xy
        if hasattr(line, 'angle_deg'): angle_deg = line.angle_deg
        else: diff = np.array(end_xy) - np.array(start_xy); angle_deg = np.rad2deg(np.arctan2(diff[1], diff[0]))
        start_with_leadin = _calculate_offset_point(start_xy, angle_deg + 180, lead_in)
        end_with_leadout = _calculate_offset_point(end_xy, angle_deg, lead_out)
        return start_with_leadin, end_with_leadout, angle_deg

    def generate_drone_path(self, show_plot=False):
        """Generates the drone's flight path covering all lines."""
        add_smooth_turns = self.flight_settings.get("add_smooth_turns", True)
        segment_length = self.flight_settings.get("turn_segment_length", 21.0)

        # Color assignment (remains the same)
        self._raw_color = None
        try:
            if hasattr(self.root, 'color_cycle'):
                if not hasattr(self.root.color_cycle, '__next__'): self.root.color_cycle = iter(self.root.color_cycle)
                self._raw_color = next(self.root.color_cycle)
                self.color = convert_argb_to_matplotlib_hex(self._raw_color)
            else: self.color = '#0000FF'
        except StopIteration: self.color = '#0000FF'; print("Warning: Color cycle exhausted.")
        except Exception as e: self.color = '#0000FF'; print(f"Warning: Color assignment error - {e}.")

        lines = self.line_list
        if not lines: # Handle no lines case
             self.utm_fly_list, self.turns = [], []; self.overall_dist, self.production, self.waste_dist = 0, 0, 0; return 0

        tof_assignment = self.tof_assignment
        if not tof_assignment: raise ValueError("TOFAssignment not found.")
        tof_xy = tof_assignment.tof.xy

        # --- Path Initialization ---
        self.utm_fly_list = [tof_xy]
        current_pos = tof_xy
        current_angle_deg = None # Undefined until first move
        prod_length = sum(line.length for line in lines if hasattr(line, 'length'))
        self.production = prod_length
        self.turns = []

        # --- 1. Transition TOF -> Line 1 Lead-in ---
        first_line = lines[0]
        start_p1, end_p1, angle1_deg = self._get_line_segment_endpoints(first_line)
        angle_at_line_entry = (angle1_deg + 180) % 360
        vec_tof_p1 = np.array(start_p1) - np.array(tof_xy)
        dist_tof_p1 = np.linalg.norm(vec_tof_p1)
        if dist_tof_p1 < 1e-6: angle_from_tof = angle_at_line_entry
        else: angle_from_tof = np.rad2deg(np.arctan2(vec_tof_p1[1], vec_tof_p1[0]))
        current_angle_deg = angle_from_tof # Initial angle leaving TOF

        if add_smooth_turns and dist_tof_p1 > 1e-4: # Add tolerance for smoothing check
            turn_pts, turn_angle = _calculate_tof_turn_points(
                tof_xy, angle_from_tof, start_p1, angle_at_line_entry, False, self.flight_settings)
            # Add points excluding start point (TOF), which is already first point
            self.utm_fly_list.extend(turn_pts)
            self.turns.append(turn_angle)
        else:
             if dist_tof_p1 > 1e-4: self.utm_fly_list.append(start_p1) # Add if not coincident
             self.turns.append(abs(((angle_at_line_entry - angle_from_tof + 180)%360)-180))

        current_pos = self.utm_fly_list[-1] # Should be start_p1
        current_angle_deg = angle_at_line_entry # Now aligned with lead-in direction

        # --- 2. Fly Line 1 (Append Lead-out) ---
        # Add end_p1 only if it's different from current_pos (start_p1)
        if np.linalg.norm(np.array(end_p1) - np.array(current_pos)) > 1e-4:
            self.utm_fly_list.append(end_p1)
        current_pos = self.utm_fly_list[-1] # Should be end_p1
        current_angle_deg = angle1_deg # Angle leaving lead-out point

        # --- 3. Loop through Inter-Line Transitions and Flights ---
        for i in range(len(lines) - 1):
            line_j = lines[i+1]
            start_pj, end_pj, angle_j_deg = self._get_line_segment_endpoints(line_j)
            angle_leadin_j = (angle_j_deg + 180) % 360

            dist_turn = np.linalg.norm(np.array(start_pj) - np.array(current_pos))
            if add_smooth_turns and dist_turn > 1e-4:
                turn_pts, turn_angle = _calculate_inter_line_turn_points(
                    current_pos, current_angle_deg, start_pj, angle_leadin_j, segment_length)
                # Add points excluding start point (current_pos)
                self.utm_fly_list.extend(turn_pts)
                self.turns.append(turn_angle)
            else:
                 if dist_turn > 1e-4: self.utm_fly_list.append(start_pj)
                 self.turns.append(abs(((angle_leadin_j - current_angle_deg + 180)%360)-180))

            current_pos = self.utm_fly_list[-1] # Should be start_pj
            current_angle_deg = angle_leadin_j

            # --- Fly Line j (Append Lead-out) ---
            if np.linalg.norm(np.array(end_pj) - np.array(current_pos)) > 1e-4:
                self.utm_fly_list.append(end_pj)
            current_pos = self.utm_fly_list[-1] # Should be end_pj
            current_angle_deg = angle_j_deg

        # --- 4. Transition Last Line Lead-out -> TOF ---
        vec_plast_tof = np.array(tof_xy) - np.array(current_pos)
        dist_last_tof = np.linalg.norm(vec_plast_tof)
        if dist_last_tof < 1e-6: angle_to_tof = (current_angle_deg + 180) % 360
        else: angle_to_tof = np.rad2deg(np.arctan2(vec_plast_tof[1], vec_plast_tof[0]))

        if add_smooth_turns and dist_last_tof > 1e-4:
            turn_pts, turn_angle = _calculate_tof_turn_points(
                current_pos, current_angle_deg, tof_xy, angle_to_tof, True, self.flight_settings)
            # Add points excluding start point (current_pos)
            self.utm_fly_list.extend(turn_pts)
            self.turns.append(turn_angle)
        else:
             if dist_last_tof > 1e-4: self.utm_fly_list.append(tof_xy)
             self.turns.append(abs(((angle_to_tof - current_angle_deg + 180)%360)-180))

        # --- Final Cleanup & Calculations ---
        # Consolidate close points and remove exact duplicates
        unique_path = []
        if self.utm_fly_list:
            unique_path.append(self.utm_fly_list[0])
            for i in range(1, len(self.utm_fly_list)):
                # Use a slightly larger tolerance to merge very close points
                if np.linalg.norm(np.array(self.utm_fly_list[i]) - np.array(unique_path[-1])) > 0.1: # e.g., 0.1 meters
                    unique_path.append(self.utm_fly_list[i])
                # else: # Optional: print merge
                #     print(f"Merging point {i} {self.utm_fly_list[i]} with previous {unique_path[-1]}")
        self.utm_fly_list = unique_path


        coord_list = np.array(self.utm_fly_list)
        if len(coord_list) > 1:
            dist = np.linalg.norm(np.diff(coord_list, axis=0), axis=1).sum()
            self.overall_dist = dist
        else: self.overall_dist = 0
        self.waste_dist = max(0, self.overall_dist - self.production)

        if show_plot: self._plot_path(self.utm_fly_list, lines, tof_xy)
        return self.overall_dist

    def _plot_path(self, utm_fly_list, line_list, tof_xy):
        fig, ax = plt.subplots(figsize=(10, 8))
        path_color = self.color if self.color else '#0000FF'
        try:
            mcolors.to_rgba(path_color)
        except ValueError:
            path_color = '#0000FF'
            print(f"Error: Invalid plot color '{self.color}'.")

        if utm_fly_list:
            utm_path = np.array(utm_fly_list)
            # Plot a thicker black line as an outline for the drone path
            ax.plot(utm_path[:, 0], utm_path[:, 1], 'o-', color='k', markersize=4, linewidth=3, zorder=1)
            # Plot the drone path over the outline
            ax.plot(utm_path[:, 0], utm_path[:, 1], 'o-', color=path_color, markersize=4, linewidth=1.5,
                    label='Drone Path', zorder=2)
            for i, (x, y) in enumerate(utm_path):
                ax.text(
                    x, y + 0.5, f'{i}',
                    fontsize=8,
                    color=path_color,
                    ha='center',
                    va='bottom',
                    zorder=100,  # Ensure text and its bbox are drawn on top of everything
                    bbox=dict(facecolor='grey', alpha=0.5, edgecolor='none', pad=0.5)
                )
        else:
            ax.plot([], [], 'o-', color=path_color, label='Drone Path (empty)')

        for i, line in enumerate(line_list):
            try:
                start_xy, end_xy = line.start.xy, line.end.xy
                label = 'Survey Lines' if i == 0 else None
                ax.plot([start_xy[0], end_xy[0]], [start_xy[1], end_xy[1]], 'r--', linewidth=2, label=label)
                start_li, end_lo, _ = self._get_line_segment_endpoints(line)
                ax.plot(start_li[0], start_li[1], 'g^', markersize=5, label='Lead-in' if i == 0 else None, alpha=0.6)
                ax.plot(end_lo[0], end_lo[1], 'mv', markersize=5, label='Lead-out' if i == 0 else None, alpha=0.6)
            except Exception as e:
                print(f"Error plotting line {i}: {e}")

        ax.plot(tof_xy[0], tof_xy[1], 'k*', markersize=12, label='TOF')
        ax.set_xlabel("UTM X")
        ax.set_ylabel("UTM Y")
        ax.set_title(f"Flight Path: {self.name}")
        ax.legend()
        ax.set_aspect('equal', adjustable='box')
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.show()

# --- END OF REVISED FILE ---