# quadrant.py
from .base_node_class import Node
from ..Node_Graphic_Class import NodeGraphic

class Quadrant(Node):
    def __init__(self, name):
        super().__init__(name)
        self.initial_lines = None

    @property
    def flight_list(self):
        return self.filter_descendants("Flight")

    @property
    def line_list(self):
        return self.filter_descendants("Line")

    @property
    def end_point_list(self):
        return self.filter_descendants("EndPoint")

    @property
    def short_name(self):
        tof = self.get_parent_at_level('TOFAssignment').tof
        return f'T{tof.clean_tof_name} Q{self.global_count}'


    def _take_right_node_specific(self):
        if self.root.initial_creation_stage:
            return
        flight_being_traded = self.get_right_most_child_at_level('Flight')
        flight_being_traded.generate_drone_path()

    def _give_right_node_specific(self):
        if self.root.initial_creation_stage:
            return

        if self.right_neighbour and not self.right_neighbour.deleted:
            flight_being_traded = self.right_neighbour.get_left_most_child_at_level('Flight')
            flight_being_traded.generate_drone_path()

    def _take_left_node_specific(self):
        if self.root.initial_creation_stage:
            return
        flight_being_traded = self.get_left_most_child_at_level('Flight')
        flight_being_traded.generate_drone_path()

    def _give_left_node_specific(self):
        if self.root.initial_creation_stage:
            return
        if self.left_neighbour and not self.left_neighbour.deleted:
            flight_being_traded = self.left_neighbour.get_right_most_child_at_level('Flight')
            flight_being_traded.generate_drone_path()

