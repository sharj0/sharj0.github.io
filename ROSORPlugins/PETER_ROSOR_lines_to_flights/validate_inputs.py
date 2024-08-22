import numpy as np
from .Global_Singleton import Global_Singleton
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

def find_in_line_groups(centroids, ave_ang, lateral_thresh, plot=True):
    """
    Group lines based on whether they are in-line with each other.
    Rotate centroids by ave_ang around the origin, then determine if they are in-line
    based on a lateral distance threshold.
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
                distance = abs(centroid[1] - other_centroid[1])  # lateral distance in rotated coordinates
                if distance <= lateral_thresh:
                    in_line_groups[j] = in_line_groups[i]

        current_group += 1

    if plot:
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

    return in_line_groups


def validate_and_process_lines(lines, max_allowable_ang_spread_degs = 5,  lateral_line_thresh = 5):
    angs = np.array([line.angle_degrees_cwN for line in lines])
    angs_spread = angs.max() - angs.min()
    ave1 = angs.mean()

    angs_plus_180 = (angs + 180) % 360
    angs_plus_180_spread = angs_plus_180.max() - angs_plus_180.min()
    ave_plus_180 = angs_plus_180.mean()
    ave2 = (ave_plus_180 - 180) % 360
    ave2 = ave2 + 360 if ave2 < 0 else ave2

    arr = np.array([angs_spread, angs_plus_180_spread])
    indx = np.argmin(arr)
    spread = arr[indx]

    '''
    MAYBE IN THE FUTURE ADD A FUNCTION THAT SWAPS THE LINE START AND WHERE NEEDED END 
    AND RE-CALCS ANG SO THAT ALL LINES ARE ROUGHLY IN THE SAME DIRECTION
    '''

    if spread > max_allowable_ang_spread_degs:
        txt = f"Spread of line angles is {spread} " \
              f"which is greater than the allowable threshold of " \
              f"{max_allowable_ang_spread_degs}"
        show_error(txt)
        raise ValueError(txt)

    ave_ang = np.array([ave1, ave2])[indx]
    global_sing =  Global_Singleton()


    global_sing.ave_line_ang_cwN = ave_ang
    line_centroids = np.array([line.centroid_xy for line in lines])

    mask = find_in_line_groups(line_centroids, ave_ang, lateral_thresh=lateral_line_thresh, plot=False)

    class In_Line_Group:
        def __init__(self, num):
            self.num = num
            self.lines = {}

        def __repr__(self):
            return f'{self.indx}:{self.lines}'

    # Create a list of In_Line_Group objects
    unique_vals = np.unique(mask)
    in_line_groups = {val: In_Line_Group(val) for val in unique_vals}

    # Populate the In_Line_Group objects with line objects
    for i, val in enumerate(mask):
        in_line_groups[val].lines[i] = lines[i]

    max_group_size = 0
    in_line_groups_list = []
    for indx, group in enumerate(list(in_line_groups.values())):
        group.indx = indx
        in_line_groups_list.append(group)
        if len(group.lines) > max_group_size:
            max_group_size = len(group.lines)

    global_sing.line_groups_max_size = max_group_size
    global_sing.in_line_groups = in_line_groups_list

    strips = [line.strip for line in lines if not line.strip is None]
    if len(np.unique(strips)) < max_group_size:
        txt = f"Different strips detected but are not named, cannot continue"
        show_error(txt)
        raise ValueError(txt)



if __name__ == '__main__':
    class Line:
        def __init__(self, angle_degrees_cwN):
            self.angle_degrees_cwN = angle_degrees_cwN
    lines = [Line(358), Line(357), Line(0), Line(2), Line(1), Line(1.5), Line(1.5), Line(1.5)]

