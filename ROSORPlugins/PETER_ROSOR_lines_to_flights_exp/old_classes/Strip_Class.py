import numpy as np
from .Flight_area_Class import Flight_Area
from .Global_Singleton import Global_Singleton
import warnings

def get_same_sections(inds):
    diffs = np.diff(inds)
    # Find the indexes where the difference is greater than 1 (indicating a new section)
    starts = list(np.where(diffs > 0)[0] + 1)
    starts.insert(0, 0)
    ends = list(np.where(diffs > 0)[0])
    ends.append(len(inds)-1)
    ranges = list(zip(starts,ends))
    return ranges

class Strip_Class():
    def __init__(self, name, lines, tofs):
        self.name = name
        self.lines = lines
        for line in lines:
            line.parent_strip = self
        self.tofs = tofs
        # assign neighbours
        for line_idx, line in enumerate(lines):
            if line_idx == 0:
                line.left_neighbour = None
            else:
                line.left_neighbour = lines[line_idx - 1]
            if line_idx == len(lines) - 1:
                line.right_neighbour = None
            else:
                line.right_neighbour = lines[line_idx + 1]
        self.assign_lines_and_tofs_to_flight_areas()
        self.all_flt_mid_points = []
        self.children_flights = []

    def __repr__(self):
        return f'Strip {self.name}'

    def assign_lines_and_tofs_to_flight_areas(self):
        for line in self.lines:
            line.start.closest_tof, line.start.closest_tof_dist = self.find_closest_tof(line.start.xy)
            line.end.closest_tof, line.end.closest_tof_dist = self.find_closest_tof(line.end.xy)
        clost = []
        for line in self.lines:
            if line.start.closest_tof_dist <= line.end.closest_tof_dist:
                line.closest_tof = line.start.closest_tof
                line.closest_tof_at_end = line.start
            else:
                line.closest_tof = line.end.closest_tof
                line.closest_tof_at_end = line.end
            clost.append(line.closest_tof)

        unique_objects = {}
        index_list = []
        for item in clost:
            if item not in unique_objects:
                unique_objects[item] = len(unique_objects)
            index_list.append(unique_objects[item])


        rangez = get_same_sections(np.array(index_list))


        flight_areas = []
        for range in rangez:
            tof = clost[range[0]]
            fa_lines = self.lines[range[0]:range[1]]
            flight_areas.append(Flight_Area(tof, self, fa_lines))

        # need to get tofs that are before and after the closest ones.
        # deliberately ignoring ones that in the middle of the range but that are far.
        leading_tofs_need_fa = self.tofs[:self.tofs.index(flight_areas[0].tof)]
        leading_fas = [Flight_Area(tof, self, []) for tof in leading_tofs_need_fa]
        trailing_tofs_need_fa = self.tofs[self.tofs.index(flight_areas[-1].tof)+1:]
        trailing_fas = [Flight_Area(tof, self, []) for tof in trailing_tofs_need_fa]
        fa_list = leading_fas + flight_areas + trailing_fas
        self.flight_area_list = fa_list
        # assign neighbours
        for fa_idx, fa in enumerate(fa_list):
            if fa_idx == 0:
                fa.left_neighbour = None
            else:
                fa.left_neighbour = fa_list[fa_idx - 1]
            if fa_idx == len(fa_list) - 1:
                fa.right_neighbour = None
            else:
                fa.right_neighbour = fa_list[fa_idx + 1]

    def find_closest_tof(self, point_xy):
        min_dist = float('inf')
        closest_tof = None
        for tof in self.tofs:
            dist = np.linalg.norm(np.array(point_xy) - np.array(tof.xy))
            if dist < min_dist:
                min_dist = dist
                closest_tof = tof
        return closest_tof, min_dist

    def run_more_flight_calcs(self):
        plugin_global = Global_Singleton()
        arr = np.array
        for indx, flight in enumerate(plugin_global.flight_list):
            flight.ind_within_mission = indx
        plugin_global.all_flt_mid_points = []
        for indx, flight_area in enumerate(self.flight_area_list):
            flight_area.parent_strip = self
            flight_area.num = indx + 1
            flight_area.ind_within_mission = indx
            flight_area.overall_dist = arr([flight.overall_dist for flight in flight_area.children_flights]).sum()
            flight_area.mid_points = []
            flight_area.utm_fly_list = []
            flight_area.mid_points = []
            flight_area.line_list = []
            flight_area.turns = []
            for indx, flight in enumerate(flight_area.children_flights):
                flight.start_loc = flight.line_list[0].start.xy
                flight.mid_points = [line.centroid_xy for line in flight.line_list]
                flight.mid_point = arr(flight.mid_points).mean(axis=0)
                self.all_flt_mid_points.append(flight.mid_point)
                flight_area.utm_fly_list.extend(flight.utm_fly_list)
                flight_area.mid_points.extend(flight.mid_points)
                flight_area.line_list.extend(flight.line_list)
                flight_area.turns.extend(flight.turns)
                flight.ind_within_fa = indx
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    flight_area.mid_point = arr(flight_area.mid_points).mean(axis=0)
            except Exception as e:
                print(f"An error occurred: {e}")
            #flight_area.start_loc = flight_area.children_flights[0].start_point.utm_tup
            #flight_area.end_loc = flight_area.children_flights[-1].end_loc
            flight_area.waste_dist = np.sum(arr([flight.waste_dist for flight in flight_area.children_flights]))
            flight_area.production = arr([flight.production for flight in flight_area.children_flights]).sum()
            flight_area.turns = arr(flight_area.turns)

    def flip_every_other_line_starting_with(self, flip_bool):
        for line in self.lines:
            if flip_bool:
                line.flip()
            flip_bool = not flip_bool
