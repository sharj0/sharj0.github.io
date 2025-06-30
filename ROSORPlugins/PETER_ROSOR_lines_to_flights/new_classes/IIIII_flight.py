# flight.py
import numpy as np
from scipy import spatial
import matplotlib.pyplot as plt


from .base_node_class import Node
from .III_tof_assignment import TOFAssignment
from .IIIIIII_end_point import EndPoint
from .. import smooth_turn_functions
from .. import rdp
from ..Node_Graphic_Class import NodeGraphic

class Flight(Node):
    def __init__(self, name):
        super().__init__(name)
        self.flight_settings = None
        self._total_length = None  # use a private variable
        self._utm_fly_list = None  # use a private variable
        self.per_tof_count = None

    @property
    def short_output_name(self):
        if not self.per_tof_count:
            return None
        tof = self.get_parent_at_level('TOFAssignment').tof
        return f'T{tof.clean_tof_name} F{self.per_tof_count}'

    @property
    def long_output_name(self):
        if not self.per_tof_count:
            return None
        tof = self.get_parent_at_level('TOFAssignment').tof
        rounded_length_km = round(self.total_length/1000,2)
        if self.root.flight_settings['name_tie_not_flt']:
            long_name = f'tof_{tof.clean_tof_name}_tie_{self.per_tof_count}_{rounded_length_km}km.kml'
        else:
            long_name = f'tof_{tof.clean_tof_name}_flt_{self.per_tof_count}_{rounded_length_km}km.kml'
        return long_name
        #return f'T{tof.clean_tof_name} F{self.per_tof_count}'

    @property
    def short_name(self):
        '''
        return self.short_output_name
        OR
        return f'F{self.global_count}'
        '''
        return self.short_output_name


    @property
    def utm_fly_list(self):
        # if _utm_fly_list is set, return it; otherwise, fall back to Node's behavior
        if self._utm_fly_list is not None:
            return self._utm_fly_list
        return super().utm_fly_list

    @utm_fly_list.setter
    def utm_fly_list(self, value):
        self._utm_fly_list = value

    @property
    def total_length(self):
        # if _total_length is set, return it; otherwise, fall back to Node's behavior
        if self._total_length is not None:
            return self._total_length
        return super().total_length

    @total_length.setter
    def total_length(self, value):
        self._total_length = value

    @property
    def line_list(self):
        # Only include children that are Lines.
        return [child for child in self.children if child.__class__.__name__ == "Line"]

    @property
    def end_point_list(self):
        return self.filter_descendants("EndPoint")

    @property
    def tof_assignment(self):
        """
        Recursively traverses the parent chain to find a parent instance whose type name is 'TOFAssignment'.
        Returns the found parent or None if no such parent exists.
        """
        current = self.parent
        while current is not None:
            if isinstance(current, TOFAssignment):
                return current
            current = current.parent
        return None

    def re_gen_right(self):
        if self.root.initial_creation_stage:
            return

        self.generate_drone_path()

        if self.right_neighbour and not self.right_neighbour.deleted:
            self.right_neighbour.generate_drone_path()

    def re_gen_left(self):
        if self.root.initial_creation_stage:
            return

        self.generate_drone_path()

        if self.left_neighbour and not self.left_neighbour.deleted:
            self.left_neighbour.generate_drone_path()

    def _take_right_node_specific(self):
        self.re_gen_right()

    def _give_right_node_specific(self):
        self.re_gen_right()

    def _take_left_node_specific(self):
        self.re_gen_left()

    def _give_left_node_specific(self):
        self.re_gen_left()

    def flip_every_other_line_starting_with(self, flip_bool, line_list):
        for line in line_list:
            if flip_bool:
                line.flip()
            flip_bool = not flip_bool

    def check_close_ends_close_to_og_starts(self, og_starts):
        line_list = self.line_list
        """
        Given a list of lines, each having attributes:
          - close_end.xy: tuple (x, y)
          - far_end.xy: tuple (x, y)
          - start.xy: tuple (x, y)
        and a method un_flip(),

        This function:
          1. Retrieves the list of close_end coordinates, far_end coordinates,
             and original start coordinates (og_starts). It calls un_flip() on each line.
          2. Computes the centroid (average point) for each set.
          3. Compares the distance from the close_ends centroid to the far_ends centroid 
             with the distance from the og_starts centroid to the far_ends centroid.
          4. Returns True if the two distances are nearly equal, indicating that the 
             close ends are close to the original starts.
        """
        # Gather coordinates from the lines
        close_ends = [line.close_end.xy for line in line_list]
        far_ends = [line.far_end.xy for line in line_list]

        # Compute centroids (average coordinates)
        centroid_close = np.mean(np.array(close_ends), axis=0)
        centroid_far = np.mean(np.array(far_ends), axis=0)
        centroid_og = np.mean(np.array(og_starts), axis=0)

        # Compute distances from centroids to the far_ends centroid
        d_close_far = np.linalg.norm(centroid_close - centroid_far)
        d_og_far = np.linalg.norm(centroid_og - centroid_far)

        # Define tolerance (e.g., 1e-6) for considering the distances as equal
        return np.isclose(d_close_far, d_og_far, atol=1e-6)

    def deal_with_line_flips(self):
        line_direction_reverse = self.flight_settings["line_direction_reverse"]
        # Unflip each line before getting the original start points
        for line in self.line_list:
            line.un_flip()
        og_starts = [line.start.xy for line in self.line_list]
        ends_close_to_TOF_are_close_to_og_starts = self.check_close_ends_close_to_og_starts(og_starts)
        if ends_close_to_TOF_are_close_to_og_starts:
            line_direction_reverse_local = line_direction_reverse
        else:
            line_direction_reverse_local = not line_direction_reverse

        self.flip_every_other_line_starting_with(line_direction_reverse_local, self.line_list)

    def _flip_lines_node_specific(self):
        print("FLIPPING LINES", self)
        self.flight_settings["line_direction_reverse"] = not self.flight_settings["line_direction_reverse"]
        for line in self.line_list:
            if line.flipped:
                line.un_flip()
            else:
                line.flip()
        self.generate_drone_path(suppress_flipping=True)

    def generate_drone_path(self, suppress_flipping=False, show_plot=False):
        if self.deleted:
            return
        #self.color = next(self.root.color_cycle)
        self.flight_settings = self.root.flight_settings
        add_smooth_turns = self.flight_settings["add_smooth_turns"]
        turn_segment_length = self.flight_settings["turn_segment_length"]
        turn_diameter = self.flight_settings["turn_diameter"]

        if len(self.line_list) == 0:
            print('was given no lines to generate flight with, please increase allowable flight size')

        if not suppress_flipping:
            self.deal_with_line_flips()


        tof_xy = self.tof_assignment.tof.xy
        self.utm_fly_list = []
        self.start_points = []
        prod_length = 0
        for ind, line in enumerate(self.line_list):
            prod_length += line.length
            self.start_points.append(line.start)
        self.points_need_to_be_flown = self.start_points.copy()
        #coord_lst = [point.xy for point in self.points_need_to_be_flown]

        try:
            self.start_point = self.points_need_to_be_flown[0]
        except IndexError:
            error_str = f'''Cannot Generate Flights With The Current Settings!
            Try changing these settings:
            max_flt_size
            line_direction_reverse
            line_self_order_reverse
            home_point_sort_reverse
            {self.line_list = }
            {self.points_need_to_be_flown}'''
            assert False, error_str
        current_point = self.fly_line(tof_xy,
                                 self.start_point,
                                 self.utm_fly_list,
                                 add_smooth_turns,
                                 turn_segment_length,
                                 turn_diameter)

        current_point_location = current_point.xy

        while len(self.points_need_to_be_flown) > 0:
            coord_lst = [point.xy for point in self.points_need_to_be_flown]
            distance, index = spatial.KDTree(coord_lst).query(current_point_location)
            current_point = self.fly_line(current_point,
                                     self.points_need_to_be_flown[index],
                                     self.utm_fly_list,
                                     add_smooth_turns,
                                     turn_segment_length,
                                     turn_diameter)
            current_point_location = current_point.xy
            # print(len(self.points_need_to_be_flown))
            # print(current_point.xy)
        self.end_loc = self.utm_fly_list[-1]
        self.fly_line(current_point,
                 tof_xy,
                 self.utm_fly_list,
                 add_smooth_turns,
                 turn_segment_length,
                 turn_diameter)

        self.utm_fly_list = rdp.rdp(self.utm_fly_list, 1)
        coord_list = np.array(self.utm_fly_list)
        dist_xy = np.diff(coord_list, axis=0)
        dist = np.linalg.norm(dist_xy, axis=1)
        dx = dist_xy.T[0]
        dy = dist_xy.T[1]
        angles = np.degrees(np.arctan2(dy, dx))
        angles %= 360
        turns = np.abs(np.diff(angles))
        turns[turns > 180] = 360 - turns[turns > 180]
        self.turns = turns
        self.total_length = dist.sum()

        # Plot the drone path and the lines if requested.
        if show_plot:
            fig, ax = plt.subplots()
            # Plot the drone path (flight path).
            utm_path = np.array(self.utm_fly_list)
            ax.plot(utm_path[:, 0], utm_path[:, 1], '-o', label='Drone Path')

            # --- Added: Label each point with its sequential number ---
            for i, (x, y) in enumerate(utm_path):
                ax.text(x, y, f'{i + 1}', fontsize=9, color='blue')
            # -----------------------------------------------------------

            # Plot each line from the line_list on top.
            for i, line in enumerate(self.line_list):
                # Assume line.start and line.end have an attribute 'xy' that returns (x, y) tuple.
                start = line.start.xy if hasattr(line.start, 'xy') else line.start
                end = line.end.xy if hasattr(line.end, 'xy') else line.end
                if i == 0:
                    ax.plot([start[0], end[0]], [start[1], end[1]], 'r-', linewidth=2, label='Line')
                else:
                    ax.plot([start[0], end[0]], [start[1], end[1]], 'r-', linewidth=2)
            ax.legend()
            ax.set_aspect('equal')
            ax.set_title("Drone Flight Path with Lines")
            plt.xlabel("X Coordinate")
            plt.ylabel("Y Coordinate")
            plt.show()

        return self.total_length


    def line_end_has_been_flown(self, next_line_start):
        next_line_start.parent.been_flown = True
        next_line_start.parent.parent.points_need_to_be_flown.remove(next_line_start)

    def get_lead_in(self,next_line_start):
        lead_in = self.flight_settings["lead_in"]
        diff = (np.array(next_line_start.parent.end.xy) - np.array(next_line_start.parent.start.xy))
        next_line_start.parent.ang_deg = round(np.rad2deg(np.arctan2(diff[1], diff[0])), 4)
        next_line_start.parent.updated = True
        leadin_dir = next_line_start.parent.ang_deg + 180
        y = np.sin(np.deg2rad(leadin_dir)) * lead_in
        x = np.cos(np.deg2rad(leadin_dir)) * lead_in
        return (next_line_start.xy[0] + x, next_line_start.xy[1] + y)


    def get_lead_out(self,cur_line_end):
        lead_out = self.flight_settings["lead_out"]
        diff = (np.array(cur_line_end.parent.end.xy) - np.array(cur_line_end.parent.start.xy))
        cur_line_end.parent.ang_deg = round(np.rad2deg(np.arctan2(diff[1], diff[0])), 4)
        cur_line_end.parent.updated = True
        leadout_dir = cur_line_end.parent.ang_deg
        y = np.sin(np.deg2rad(leadout_dir)) * lead_out
        x = np.cos(np.deg2rad(leadout_dir)) * lead_out
        return (cur_line_end.xy[0] + x, cur_line_end.xy[1] + y)

    def get_lead_out_alternatively(self, next_line_end):
        lead_out = self.flight_settings["lead_out"]
        diff = (np.array(next_line_end.parent.end.xy) - np.array(next_line_end.parent.start.xy))
        next_line_end.parent.ang_deg = round(np.rad2deg(np.arctan2(diff[1], diff[0])), 4)
        next_line_end.parent.updated = True
        leadout_dir = next_line_end.parent.ang_deg
        y = np.sin(np.deg2rad(leadout_dir)) * lead_out
        x = np.cos(np.deg2rad(leadout_dir)) * lead_out
        return (next_line_end.xy[0] + x, next_line_end.xy[1] + y)

    def fly_line(self,
                 cur_line_end,
                 next_line_start,
                 utm_fly_list,
                 add_smooth_turns,
                 turn_segment_length,
                 turn_diameter,
                 show_plot=False):
        # cur_line_end and next_line_start are tuples when they are the starts and ends of flights.

        # cuz cur_line_end is Line_End_Class its the end of a line
        if isinstance(cur_line_end, EndPoint):
            cur_line_end_with_leadout = self.get_lead_out(cur_line_end)

        # end of flight
        if isinstance(next_line_start, tuple) and not isinstance(cur_line_end, tuple):
            if not add_smooth_turns:
                utm_fly_list.append(next_line_start)
                #print('NOT_smooth_turns: end_of_flight')
            else:
                #print('smooth_turns: end_of_flight')
                smooth_turn_functions.flt_end(utm_fly_list=utm_fly_list,
                                              start_coord=cur_line_end_with_leadout,
                                              start_ang=cur_line_end.parent.ang_deg,
                                              end_coord=next_line_start,
                                              turn_segment_length=turn_segment_length,
                                              og_turn_diameter=turn_diameter,
                                              turn_diameter=turn_diameter
                                              )

        # upcoming line needs lead-in
        if isinstance(next_line_start, EndPoint):
            next_line_start_wt_needed_leadin = self.get_lead_in(next_line_start)

        # start of flight
        if isinstance(cur_line_end, tuple) and not isinstance(next_line_start, tuple):
            if not add_smooth_turns:
                #print('NOT_smooth_turns: start_of_flight')
                utm_fly_list.append(cur_line_end)

        if isinstance(next_line_start, EndPoint):
            self.line_end_has_been_flown(next_line_start)
            next_line_end = next_line_start.parent.end
            if not add_smooth_turns:
                #print('NOT_smooth_turns: between_lines?')
                utm_fly_list.append(next_line_start_wt_needed_leadin)
                # new
                utm_fly_list.append(self.get_lead_out_alternatively(next_line_end))
                # no lead out, kinda like the old way
                #utm_fly_list.append(next_line_end.xy)
            if add_smooth_turns:
                if isinstance(cur_line_end, tuple):  # start of flight
                    #print('smooth_turns: start of flight')
                    utm_fly_list.append(cur_line_end)
                    smooth_turn_functions.flt_beginning(utm_fly_list=utm_fly_list,
                                                        start_coord=cur_line_end,
                                                        end_coord=next_line_start_wt_needed_leadin,
                                                        end_ang=next_line_start.parent.ang_deg,
                                                        turn_segment_length=turn_segment_length,
                                                        og_turn_diameter=turn_diameter,
                                                        turn_diameter=turn_diameter
                                                        )
                else:  # between_lines
                    #print('smooth_turns: between_lines')
                    smooth_turn_functions.between_lines(utm_fly_list=utm_fly_list,
                                                        start_coord=cur_line_end_with_leadout,
                                                        start_ang=cur_line_end.parent.ang_deg,
                                                        end_coord=next_line_start_wt_needed_leadin,
                                                        end_ang=next_line_start.parent.ang_deg,
                                                        turn_segment_length=turn_segment_length,
                                                        turn_diameter=turn_diameter
                                                        )
                # no lead out, kinda like the old way
                #utm_fly_list.append(next_line_end.xy)

            # old way
            #utm_fly_list.append(next_line_end.xy)


            # Plot the flight path, line endpoints, and label the flight endpoints.
            if show_plot:
                line_endpoints_for_plotting = [(line.start.xy, line.end.xy) for line in self.line_list]
                # Determine coordinates to label:
                # For cur_line_end: if it's an EndPoint, we use its lead-out coordinate; otherwise, use it directly.
                if isinstance(cur_line_end, EndPoint):
                    cur_line_end_coord = cur_line_end_with_leadout
                else:
                    cur_line_end_coord = cur_line_end

                # For next_line_end: if next_line_start is an EndPoint, use the computed next_line_end.xy;
                # otherwise, assume next_line_start itself is the endpoint.
                if isinstance(next_line_start, EndPoint):
                    next_line_end_coord = next_line_end.xy
                else:
                    next_line_end_coord = next_line_start

                # NEW: Determine coordinates for next_line_start.
                if isinstance(next_line_start, EndPoint):
                    next_line_start_coord = next_line_start_wt_needed_leadin
                else:
                    next_line_start_coord = next_line_start

                plt.figure(figsize=(10, 8))

                # Plot the flight path from utm_fly_list.
                utm_fly_arr = np.array(utm_fly_list)
                plt.plot(utm_fly_arr[:, 0], utm_fly_arr[:, 1], 'bo-', label='Flight Path')

                # Plot each line segment from line_endpoints_for_plotting.
                for i, (start, end) in enumerate(line_endpoints_for_plotting):
                    if i == 0:
                        plt.plot([start[0], end[0]], [start[1], end[1]], 'r--', label='Line Endpoints')
                    else:
                        plt.plot([start[0], end[0]], [start[1], end[1]], 'r--')

                # Plot and label cur_line_end.
                plt.scatter(cur_line_end_coord[0], cur_line_end_coord[1], color='green', s=100, marker='o',
                            label='cur_line_end')
                plt.text(cur_line_end_coord[0], cur_line_end_coord[1], ' cur_line_end', color='green', fontsize=12)

                # Plot and label next_line_end.
                plt.scatter(next_line_end_coord[0], next_line_end_coord[1], color='purple', s=100, marker='x',
                            label='next_line_end')
                plt.text(next_line_end_coord[0], next_line_end_coord[1], ' next_line_end', color='purple', fontsize=12)

                # NEW: Plot and label next_line_start.
                plt.scatter(next_line_start_coord[0], next_line_start_coord[1], color='orange', s=100, marker='^',
                            label='next_line_start')
                plt.text(next_line_start_coord[0], next_line_start_coord[1], ' next_line_start', color='orange',
                         fontsize=12)
                # --- Added: Label each point with its sequential number ---
                for i, (x, y) in enumerate(utm_fly_arr):
                    plt.gca().text(x, y, f'{i + 1}', fontsize=9, color='black')
                # -----------------------------------------------------------
                plt.xlabel("UTM X")
                plt.ylabel("UTM Y")
                plt.title("Flight Path, Line Endpoints, and Flight Endpoints")
                plt.legend()
                plt.gca().set_aspect('equal')
                plt.show()

            return next_line_end

