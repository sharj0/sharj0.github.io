import math
from .Global_Singleton import Global_Singleton
from . import smooth_turn_functions
from .Line_End_Class import Line_End_Class
import numpy as np

class Line_Class():
    def __init__(self, start, end, grid_fltln, strip, id, use_name, layer_ind, parent_layer_path):
        self.start = start
        self.end = end
        self.start.parent_line = self
        self.end.parent_line = self
        self.grid_fltln = grid_fltln
        self.strip = strip
        self.id = id
        self.use_name = use_name
        self.layer_ind = layer_ind
        self.parent_layer_path = parent_layer_path
        self.angle_degrees_cwN = self.calculate_angle()
        self.centroid_xy = self.calculate_centroid()
        self.length = self.calculate_length()

    def __repr__(self):
        if self.use_name == 'grid_fltln':
            return self.grid_fltln
        elif self.use_name == 'id':
            return self.id
        else:
            return self.layer_ind

    def calculate_length(self):
        delta_x = self.end.x - self.start.x
        delta_y = self.end.y - self.start.y
        length = math.sqrt(delta_x ** 2 + delta_y ** 2)
        return length

    def calculate_angle(self):
        delta_x = self.end.x - self.start.x
        delta_y = self.end.y - self.start.y
        angle_radians = math.atan2(delta_y, delta_x)
        angle_degrees_ccwE = math.degrees(angle_radians)
        angle_degrees_cwN = 90 - angle_degrees_ccwE
        return angle_degrees_cwN

    def calculate_centroid(self):
        centroid_x = (self.start.x + self.end.x) / 2
        centroid_y = (self.start.y + self.end.y) / 2
        return centroid_x, centroid_y

def get_lead_in(next_line_start):
    plugin_global = Global_Singleton()
    lead_in = plugin_global.lead_in
    arr = np.array
    diff = (arr(next_line_start.parent_line.end.xy) - arr(next_line_start.parent_line.start.xy))
    next_line_start.parent_line.ang_deg = round(np.rad2deg(np.arctan2(diff[1], diff[0])), 4)
    next_line_start.parent_line.updated = True
    leadin_dir = next_line_start.parent_line.ang_deg + 180
    y = np.sin(np.deg2rad(leadin_dir)) * lead_in
    x = np.cos(np.deg2rad(leadin_dir)) * lead_in
    return (next_line_start.xy[0] + x, next_line_start.xy[1] + y)

def line_end_has_been_flown(next_line_start):
    next_line_start.parent_line.been_flown = True
    next_line_start.parent_line.parent_flight.points_need_to_be_flown.remove(next_line_start)

def fly_line(cur_line_end,
             next_line_start,
             utm_fly_list):

    plugin_global = Global_Singleton()
    add_smooth_turns = plugin_global.add_smooth_turns
    turn_segment_length = plugin_global.turn_segment_length
    turn_diameter = plugin_global.turn_diameter

    if isinstance(next_line_start, tuple) and not isinstance(cur_line_end, tuple):
        if not add_smooth_turns:
            utm_fly_list.append(next_line_start)
        else:
            smooth_turn_functions.flt_end(utm_fly_list=utm_fly_list,
                                          start_coord=cur_line_end.xy,
                                          start_ang=cur_line_end.parent_line.ang_deg,
                                          end_coord=next_line_start,
                                          turn_segment_length=turn_segment_length,
                                          og_turn_diameter=turn_diameter,
                                          turn_diameter=turn_diameter
                                          )
    if isinstance(next_line_start, Line_End_Class):
        next_line_start_wt_needed_leadin = get_lead_in(next_line_start)
    if isinstance(cur_line_end, tuple) and not isinstance(next_line_start, tuple):
        if not add_smooth_turns:
            utm_fly_list.append(cur_line_end)
    if isinstance(next_line_start, Line_End_Class):
        line_end_has_been_flown(next_line_start)
        next_line_end = next_line_start.parent_line.end
        if not add_smooth_turns:
            utm_fly_list.append(next_line_start_wt_needed_leadin)
        if add_smooth_turns:
            if isinstance(cur_line_end, tuple):
                utm_fly_list.append(cur_line_end)
                smooth_turn_functions.flt_beginning(utm_fly_list=utm_fly_list,
                                          start_coord=cur_line_end,
                                          end_coord=next_line_start_wt_needed_leadin,
                                          end_ang=next_line_start.parent_line.ang_deg,
                                          turn_segment_length=turn_segment_length,
                                          og_turn_diameter=turn_diameter,
                                          turn_diameter=turn_diameter
                                          )
            else:
                smooth_turn_functions.between_lines(utm_fly_list=utm_fly_list,
                                                    start_coord=cur_line_end.xy,
                                                    start_ang=cur_line_end.parent_line.ang_deg,
                                                    end_coord=next_line_start_wt_needed_leadin,
                                                    end_ang=next_line_start.parent_line.ang_deg,
                                                    turn_segment_length=turn_segment_length,
                                                    turn_diameter=turn_diameter
                                                    )
        utm_fly_list.append(next_line_end.xy)
        return next_line_end