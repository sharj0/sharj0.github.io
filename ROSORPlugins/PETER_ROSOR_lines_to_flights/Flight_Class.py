import numpy as np
from .Line_Class import fly_line
from scipy import spatial
import os
import sys
# IMPORT 3rd PARTY libraries
parent_dir = os.path.dirname(os.path.realpath(__file__))
# Add this directory to sys.path so Python knows where to find the external libraries
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from rdp import rdp


class Flight():
    def __init__(self):
        self.is_flight_area = False
        self.is_flight = True

    def __repr__(self):
        return f'Flight: {self.sorted_line_list}'

def generate_flight(lines_to_fly, parent_flight_area, **kwargs):
    if len(lines_to_fly) == 0:
        print('was given no lines to generate flight with, please increase allowable flight size')
    if kwargs:
        if 'mod_flight' in kwargs.keys():
            flight = kwargs['mod_flight']
        else:
            flight = Flight()
    else:
        flight = Flight()
    flight.sorted_line_list = lines_to_fly
    flight.line_list = lines_to_fly
    flight.utm_fly_list = []
    flight.start_points = []
    prod_length = 0
    for ind, line in enumerate(lines_to_fly):
        prod_length += line.length
        line.parent_flight = flight
        flight.start_points.append(line.start)
    flight.points_need_to_be_flown = flight.start_points.copy()
    #coord_lst = [point.xy for point in flight.points_need_to_be_flown]
    try:
        flight.start_point = flight.points_need_to_be_flown[0]
    except IndexError:
        error_str = '''Cannot Generate Flights With The Current Settings!
        Try changing these settings:
        max_flt_size
        line_direction_reverse
        line_flight_order_reverse
        home_point_sort_reverse'''
        assert False, error_str
    current_point = fly_line(parent_flight_area.tof.xy,
                             flight.start_point,
                             flight.utm_fly_list)
    current_point_location = current_point.xy
    while len(flight.points_need_to_be_flown) > 0:
        coord_lst = [point.xy for point in flight.points_need_to_be_flown]
        distance, index = spatial.KDTree(coord_lst).query(current_point_location)
        current_point = fly_line(current_point,
                                 flight.points_need_to_be_flown[index],
                                 flight.utm_fly_list)
        current_point_location = current_point.xy
        # print(len(flight.points_need_to_be_flown))
        # print(current_point.xy)
    flight.end_loc = flight.utm_fly_list[-1]
    fly_line(current_point,
             parent_flight_area.tof.xy,
             flight.utm_fly_list)
    flight.utm_fly_list = rdp(flight.utm_fly_list, 0.01)
    coord_list = np.array(flight.utm_fly_list)
    dist_xy = np.diff(coord_list, axis=0)
    dist = np.linalg.norm(dist_xy, axis=1)
    dx = dist_xy.T[0]
    dy = dist_xy.T[1]
    angles = np.degrees(np.arctan2(dy, dx))
    angles %= 360
    turns = np.abs(np.diff(angles))
    turns[turns > 180] = 360 - turns[turns > 180]
    flight.turns = turns
    flight.overall_dist = dist.sum()
    flight.production = prod_length
    flight.waste_dist = flight.overall_dist - prod_length
    #flight.num = mission.current_flight
    return flight