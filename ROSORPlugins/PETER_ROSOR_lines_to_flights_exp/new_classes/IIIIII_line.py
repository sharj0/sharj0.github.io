# line.py
import math

from .base_node_class import Node

class Line(Node):
    def __init__(self, name, start, end, grid_fltln, strip_letter, ids, layer_ind, input_lines_file_path):
        super().__init__(name)
        self.can_trade = False # Lines do not trade.
        self.dont_create_or_destory = True
        self.flipped = False
        self.start = start
        self.end = end
        self.add_child_to_right(start)
        self.add_child_to_right(end)
        self.grid_fltln = grid_fltln
        self.strip_letter = strip_letter
        self.ids = ids
        self.layer_ind = layer_ind
        self.input_lines_file_path = input_lines_file_path
        # New attributes:
        self.continued_line_front = None    # either None or another Line instance
        self.continued_line_back = None     # either None or another Line instance
        self.parent_line_group = None       # will be assigned an instance of ParentLineGroup

    def flip(self):
        self.flipped = True
        self.start, self.end = self.end, self.start

    def un_flip(self):
        if self.flipped:
            self.start, self.end = self.end, self.start
            self.flipped = False

    @property
    def end_point_list(self):
        return self.filter_descendants("EndPoint")

    @property
    def angle_degrees_cwN(self):
        delta_x = self.end.x - self.start.x
        delta_y = self.end.y - self.start.y
        angle_radians = math.atan2(delta_y, delta_x)
        angle_degrees_ccwE = math.degrees(angle_radians)
        angle_degrees_cwN = 90 - angle_degrees_ccwE
        return angle_degrees_cwN

    @property
    def centroid_xy(self):
        centroid_x = (self.start.x + self.end.x) / 2
        centroid_y = (self.start.y + self.end.y) / 2
        return centroid_x, centroid_y

    @property
    def production_length(self):
        return self.length

    @property
    def length(self):
        delta_x = self.end.x - self.start.x
        delta_y = self.end.y - self.start.y
        length = math.sqrt(delta_x ** 2 + delta_y ** 2)
        return length

    @property
    def close_end(self):
        """
        Returns the endpoint (either start or end) that is closest to the
        associated TOF (obtained from the parent TOFAssignment node).
        """
        # Get the parent TOFAssignment node.
        try:
            tof_assignment = self.get_parent_at_level('TOFAssignment')
        except:
            tof_assignment = self.get_parent_at_level('InitialTOFAssignment')
        tof_xy = tof_assignment.tof.xy

        # Compute distances from the start and end to the TOF.
        d_start = math.dist(self.start.xy, tof_xy)
        d_end = math.dist(self.end.xy, tof_xy)

        # Return the endpoint that is closest.
        return self.start if d_start <= d_end else self.end

    @property
    def far_end(self):
        """
        Returns the endpoint (either start or end) that is farthest from the
        associated TOF (obtained from the parent TOFAssignment node).
        """
        # Get the parent TOFAssignment node.
        try:
            tof_assignment = self.get_parent_at_level('TOFAssignment')
        except:
            tof_assignment = self.get_parent_at_level('InitialTOFAssignment')
        tof_xy = tof_assignment.tof.xy

        d_start = math.dist(self.start.xy, tof_xy)
        d_end = math.dist(self.end.xy, tof_xy)

        # Return the endpoint that is farthest.
        return self.start if d_start > d_end else self.end
