import numpy as np
from .Global_Singleton import Global_Singleton
from scipy.optimize import linear_sum_assignment
import matplotlib.pyplot as plt
from .plugin_tools import show_error

def rotate_point(origin, point, angle):
    """
    Rotate a point counterclockwise by a given angle around a given origin.
    The angle should be given in degrees.
    """
    ox, oy = origin
    px, py = point

    angle_rad = np.deg2rad(angle)
    qx = ox + np.cos(angle_rad) * (px - ox) - np.sin(angle_rad) * (py - oy)
    qy = oy + np.sin(angle_rad) * (px - ox) + np.cos(angle_rad) * (py - oy)
    return qx, qy


def find_in_line_groups(centroids, ave_ang, lateral_thresh, plot=False, return_rotated=False):
    """
    Group lines based on whether they are in-line with each other.
    Rotate centroids by (ave_ang + 90) degrees about the origin.
    Lines are grouped if their lateral (rotated y-coordinate) separation is
    within the specified lateral_thresh.

    If return_rotated is True, returns a tuple (in_line_groups, rotated_centroids).
    """
    origin = (0, 0)
    rotated_centroids = np.array([rotate_point(origin, centroid, ave_ang + 90) for centroid in centroids])
    in_line_groups = np.zeros(len(rotated_centroids), dtype=int)
    current_group = 1

    for i, centroid in enumerate(rotated_centroids):
        if in_line_groups[i] == 0:
            in_line_groups[i] = current_group

        for j, other_centroid in enumerate(rotated_centroids):
            if i != j and in_line_groups[j] == 0:
                distance = abs(centroid[1] - other_centroid[1])  # lateral (y-axis) distance
                if distance <= lateral_thresh:
                    in_line_groups[j] = in_line_groups[i]

        current_group += 1

    if plot:
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 6))
        plt.scatter(rotated_centroids[:, 0], rotated_centroids[:, 1], c=in_line_groups, cmap='rainbow')
        for centroid in rotated_centroids:
            plt.axhline(y=centroid[1] - lateral_thresh, color='k', linestyle='--')
            plt.axhline(y=centroid[1] + lateral_thresh, color='k', linestyle='--')
        plt.xlabel('X')
        plt.ylabel('Y')
        plt.title('Rotated Points and Lateral Threshold Lines')
        plt.grid(True)
        plt.show()

    if return_rotated:
        return in_line_groups, rotated_centroids
    else:
        return in_line_groups


class ParentLineGroup:
    """Represents a group of lines that are in-line with each other."""
    def __init__(self, group_id):
        self.group_id = group_id
        self.children = []  # list of Line instances in this group
        self.left_neighbour = None  # a ParentLineGroup instance or None
        self.right_neighbour = None  # a ParentLineGroup instance or None

    def add_child(self, line):
        """Adds a line to the group and updates the line's parent_line_group attribute."""
        self.children.append(line)
        line.parent_line_group = self

    def __repr__(self):
        return f"ParentLineGroup(id={self.group_id}, children_count={len(self.children)})"


def assign_strips_to_lines(groups_sorted, group_lines, show_plot=False, debug=False):
    """
    Automatically assign strip identifiers (strip_letter) to each line based on their
    post-rotation x-axis positions and the sorted order of the groups, where groups are
    sorted by the rotated centroid's y coordinate. This function:

      1. Computes rotated endpoints and centroids for each group.
         - For each child line of a group, the centroid is rotated using (ave_ang + 90°).
         - The endpoints for each line are also rotated (using line.start.xy and line.end.xy).
         - The group centroid is computed as the mean of the rotated centroids.

      2. Sorts the groups by the rotated centroid y coordinate in ascending order.

      3. Assigns strip IDs using the following logic:
         - For the first (sorted) group, its lines (sorted by rotated x coordinate) are
           each assigned a new strip ID.
         - For every subsequent adjacent pair of groups, the lines in each group are sorted
           by their rotated x coordinate. Then a cost matrix (absolute differences in x) is built
           and solved using the Hungarian algorithm. Matched lines inherit the strip id from the
           previous group; any unmatched line gets a new strip id.
         - Debug printouts show the matching details for each pair.

      4. Converts numeric strip IDs to letters (0 -> "A", 1 -> "B", ..., 26 -> "AA", etc.)
         and updates each line's attribute 'strip_letter'.

      5. Optionally plots the final assignment with post-rotation coordinates:
         - For each (sorted) group the rotated line segments are drawn.
         - A text label (the sorted group index) is placed at the group's rotated centroid.

    Parameters:
        groups_sorted: List of ParentLineGroup instances.
        group_lines: Dict mapping group_id to a list of (line, rotated_x) tuples.
        show_plot: If True, show a plot of post-rotation lines and group labels.
        debug: If True, print debug statements at each matching step.

    The actual strip-to-line assignment logic uses the rotated x positions (from group_lines)
    to match lines in adjacent groups and propagate or create new strip ids.
    """

    # --- 1. Compute rotated centroids & endpoints for each group ---
    global_sing = Global_Singleton()
    ave_ang = global_sing.ave_line_ang_cwN
    rotation_angle = ave_ang + 90  # this rotation makes lines horizontal

    # Build a list of tuples: (group, group_centroid, list_of_rotated_line_endpoints)
    group_info = []
    for group in groups_sorted:
        rotated_centroids = []  # rotated centroids for each child line in the group
        rotated_lines = []      # rotated endpoints for each child line in the group
        for line in group.children:
            # Rotate the line's centroid.
            r_centroid = rotate_point((0, 0), line.centroid_xy, rotation_angle)
            rotated_centroids.append(r_centroid)
            # Get the endpoints from line.start.xy and line.end.xy.
            endpoints = [line.start.xy, line.end.xy]  # expected format: ((x1, y1), (x2, y2))
            # Rotate both endpoints.
            r_endpoints = np.array([rotate_point((0, 0), pt, rotation_angle) for pt in endpoints])
            rotated_lines.append(r_endpoints)
        # Compute the group centroid (mean of rotated centroids).
        if rotated_centroids:
            group_centroid = np.mean(np.array(rotated_centroids), axis=0)
        else:
            group_centroid = (0, 0)
        group_info.append((group, group_centroid, rotated_lines))

    # --- 2. Re-sort groups by the y coordinate of the rotated centroid (ascending order) ---
    group_info_sorted = sorted(group_info, key=lambda item: item[1][1])
    # Extract sorted groups in the new order.
    sorted_groups = [entry[0] for entry in group_info_sorted]

    if debug:
        print("Sorted groups by rotated centroid y coordinate:")
        for idx, (group, centroid, _) in enumerate(group_info_sorted):
            print(f"Index {idx}: Group {group.group_id}, Rotated Centroid: {centroid}")

    # --- 3. Assign strip IDs using rotated x coordinates ---
    next_strip_id = 0  # new strip IDs counter
    line_to_strip = {}

    # Process the first group in the sorted order.
    first_group = sorted_groups[0]
    first_sorted = sorted(group_lines[first_group.group_id], key=lambda tup: tup[1])
    # Update group's children order based on sorted rotated x coordinate.
    first_group.children = [tup[0] for tup in first_sorted]

    if debug:
        print("===== Assigning strips to first group =====")
    for (line, rx) in first_sorted:
        line_to_strip[line] = next_strip_id
        if debug:
            print(f"   Group {first_group.group_id}: line={line}, rotated x={rx:.4f}, assigned strip_id={next_strip_id}")
        next_strip_id += 1

    # Process each adjacent pair of groups.
    for i in range(1, len(sorted_groups)):
        left_group = sorted_groups[i - 1]
        right_group = sorted_groups[i]

        # Sort lines in each group by the rotated x coordinate.
        left_sorted = sorted(group_lines[left_group.group_id], key=lambda tup: tup[1])
        right_sorted = sorted(group_lines[right_group.group_id], key=lambda tup: tup[1])
        left_group.children = [tup[0] for tup in left_sorted]
        right_group.children = [tup[0] for tup in right_sorted]

        left_x = np.array([tup[1] for tup in left_sorted])
        right_x = np.array([tup[1] for tup in right_sorted])

        # Build cost matrix based on absolute x differences.
        cost_matrix = np.abs(left_x[:, None] - right_x[None, :])
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        if debug:
            print(f"\n===== Matching Group {left_group.group_id} -> Group {right_group.group_id} =====")
            print("Left group sorted lines (rotated x with current strip IDs):")
            for idx, (ln, rx) in enumerate(left_sorted):
                s_val = line_to_strip.get(ln, "??")
                print(f"   L-idx={idx}, line={ln}, rotated x={rx:.4f}, strip_id={s_val}")
            print("Right group sorted lines (rotated x):")
            for idx, (ln, rx) in enumerate(right_sorted):
                print(f"   R-idx={idx}, line={ln}, rotated x={rx:.4f}")
            print("Cost matrix:\n", cost_matrix)
            print("Hungarian matching results:")
            print("   row indices =", row_ind)
            print("   col indices =", col_ind)

        current_assignments = [None] * len(right_sorted)
        # Propagate strip IDs based on matching.
        for r, c in zip(row_ind, col_ind):
            left_line = left_sorted[r][0]
            current_assignments[c] = line_to_strip[left_line]
            if debug:
                print(f"   MATCH: L-idx={r} (strip_id={line_to_strip[left_line]}) -> R-idx={c} (line={right_sorted[c][0]})")
        # Any unmatched lines get new strip IDs.
        for idx, (line, rx) in enumerate(right_sorted):
            if current_assignments[idx] is None:
                current_assignments[idx] = next_strip_id
                if debug:
                    print(f"   NEW STRIP: R-idx={idx}, line={line}, rotated x={rx:.4f}, assigned new strip_id={next_strip_id}")
                next_strip_id += 1
            line_to_strip[line] = current_assignments[idx]

    # --- 4. Convert numeric strip IDs to letter identifiers ---
    unique_ids = sorted(set(line_to_strip.values()))
    id_to_letter = {}

    def num_to_letters(n):
        # Convert numbers: 0 -> "A", 1 -> "B", ... 25 -> "Z", 26 -> "AA", etc.
        result = ""
        while True:
            result = chr(65 + (n % 26)) + result
            n = n // 26 - 1
            if n < 0:
                break
        return result

    for sid in unique_ids:
        id_to_letter[sid] = num_to_letters(sid)

    # Update each line's strip_letter attribute.
    for line, sid in line_to_strip.items():
        line.strip_letter = id_to_letter[sid]

    # --- 5. (Optional) Plot final assignment using post-rotation coordinates ---
    if show_plot:
        from matplotlib.lines import Line2D

        # Build a list of all lines from the sorted groups.
        all_lines = []
        for group in sorted_groups:
            all_lines.extend(group.children)
        unique_letters = sorted({line.strip_letter for line in all_lines})
        num_letters = len(unique_letters)
        cmap = plt.get_cmap('tab10', num_letters)
        letter_to_color = {letter: cmap(i) for i, letter in enumerate(unique_letters)}

        plt.figure(figsize=(10, 6))
        # Use the group_info_sorted list (which is already sorted by centroid y)
        for idx, (group, centroid, _) in enumerate(group_info_sorted):
            for line in group.children:
                # Rotate the endpoints using the same rotation.
                endpoints = [line.start.xy, line.end.xy]
                r_endpoints = np.array([rotate_point((0, 0), pt, rotation_angle) for pt in endpoints])
                color = letter_to_color.get(line.strip_letter, "black")
                plt.plot(r_endpoints[:, 0], r_endpoints[:, 1], color=color, linewidth=2)
            # Place the group label (its sorted index) at the group's centroid.
            #plt.text(centroid[0], centroid[1], str(idx), fontsize=12, ha='center', va='center')
        plt.xlabel('Rotated X')
        plt.ylabel('Rotated Y')
        plt.title("Post-Rotation Lines and Group Labels (Sorted by Centroid Y)")
        plt.grid(True)
        plt.show()

    return



def validate_and_process_lines(lines, user_assigned_unique_strip_letters, max_allowable_ang_spread_degs=5, lateral_line_thresh=5):

    # Calculate angles from each line.
    angs = np.array([line.angle_degrees_cwN for line in lines])
    angs_spread = angs.max() - angs.min()
    ave1 = angs.mean()

    # Compute alternate angles (rotated by 180°) to account for potential directional ambiguity.
    angs_plus_180 = (angs + 180) % 360
    angs_plus_180_spread = angs_plus_180.max() - angs_plus_180.min()
    ave_plus_180 = angs_plus_180.mean()
    ave2 = (ave_plus_180 - 180) % 360
    ave2 = ave2 + 360 if ave2 < 0 else ave2

    # Compare original and shifted spreads.
    arr = np.array([angs_spread, angs_plus_180_spread])
    indx = np.argmin(arr)
    spread = arr[indx]

    if spread > max_allowable_ang_spread_degs:
        txt = (f"Spread of line angles is {spread} which is greater than the allowable threshold "
               f"of {max_allowable_ang_spread_degs}")
        show_error(txt)
        raise ValueError(txt)

    # Choose the average angle corresponding to the smaller spread.
    ave_ang = np.array([ave1, ave2])[indx]
    global_sing = Global_Singleton()
    global_sing.ave_line_ang_cwN = ave_ang

    # Get centroids from the lines.
    line_centroids = np.array([line.centroid_xy for line in lines])

    # Get the group mask along with the rotated centroids.
    mask, rotated_centroids = find_in_line_groups(line_centroids, ave_ang, lateral_thresh=lateral_line_thresh,
                                                  plot=False, return_rotated=True)

    # --- GROUPING AND ASSIGNING THE NEW ATTRIBUTES ---

    # Create ParentLineGroup instances for each unique group.
    unique_groups = np.unique(mask)
    groups = {grp: ParentLineGroup(grp) for grp in unique_groups}

    # For each group, record (line, rotated_x) pairs.
    group_lines = {grp: [] for grp in unique_groups}

    for idx, line in enumerate(lines):
        grp = mask[idx]
        groups[grp].add_child(line)  # sets line.parent_line_group automatically.
        # rotated_centroids[idx][0] is the coordinate along the line direction.
        rotated_x = rotated_centroids[idx, 0]
        group_lines[grp].append((line, rotated_x))

    # For each group, sort lines by the rotated x-coordinate.
    for grp, line_list in group_lines.items():
        # Sort based on rotated x coordinate.
        line_list_sorted = sorted(line_list, key=lambda item: item[1])
        sorted_lines = [entry[0] for entry in line_list_sorted]
        # Update the group's children list with the sorted order.
        groups[grp].children = sorted_lines

        # Set continued_line_front and continued_line_back for each line.
        for i, line in enumerate(sorted_lines):
            line.continued_line_back = sorted_lines[i - 1] if i > 0 else None
            line.continued_line_front = sorted_lines[i + 1] if i < len(sorted_lines) - 1 else None

    # --- SORTING GROUPS & ASSIGNING NEIGHBOURING GROUPS ---

    # Create a sorted list of ParentLineGroup instances.
    # Here we sort by the minimum rotated x value from each group's lines.
    groups_sorted = sorted(
        groups.values(),
        key=lambda grp: min(x for (_, x) in group_lines[grp.group_id])
    )

    # Now assign left_neighbour and right_neighbour for each group.
    for i, group in enumerate(groups_sorted):
        if i > 0:
            group.left_neighbour = groups_sorted[i - 1]
        if i < len(groups_sorted) - 1:
            group.right_neighbour = groups_sorted[i + 1]

    # Determine maximum group size and assign grouping info to the global singleton.
    max_group_size = max(len(g.children) for g in groups.values())
    global_sing.line_groups_max_size = max_group_size
    global_sing.in_line_groups = groups_sorted  # now using the sorted list

    if not user_assigned_unique_strip_letters:
        # --- ASSIGN STRIPS AUTOMATICALLY IF NOT ALREADY NAMED ---
        assign_strips_to_lines(groups_sorted, group_lines, show_plot=False, debug=False)
        all_strip_letters = [line.strip_letter for line in lines]
        unique_strip_letters = np.unique(all_strip_letters)
    else:
        unique_strip_letters = user_assigned_unique_strip_letters

    if len(np.unique(all_strip_letters)) < max_group_size:
        txt = "Strip assignment failed: not enough unique strips detected."
        show_error(txt)
        raise ValueError(txt)
    return unique_strip_letters



if __name__ == '__main__':
    class Line:
        def __init__(self, angle_degrees_cwN):
            self.angle_degrees_cwN = angle_degrees_cwN
    lines = [Line(358), Line(357), Line(0), Line(2), Line(1), Line(1.5), Line(1.5), Line(1.5)]

