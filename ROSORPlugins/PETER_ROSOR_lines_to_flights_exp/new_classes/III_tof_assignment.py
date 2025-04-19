# tof_assignment.py
from .base_node_class import Node

class TOFAssignment(Node):
    def __init__(self, name, tof, initial_lines=None):
        # Initialize the Node with the name.
        super().__init__(name)
        # Prevent auto-creation and auto-deletion for TOFAssignment nodes.
        self.dont_create_or_destory = True
        self.tof = tof
        if initial_lines is None:
            initial_lines = []
        self.initial_lines =  initial_lines

    @property
    def quadrant_list(self):
        return self.filter_descendants("Quadrant")

    @property
    def flight_list(self):
        return self.filter_descendants("Flight")

    @property
    def line_list(self):
        return self.filter_descendants("Line")

    @property
    def end_point_list(self):
        return self.filter_descendants("EndPoint")

class InitialTOFAssignment(TOFAssignment):
    pass
