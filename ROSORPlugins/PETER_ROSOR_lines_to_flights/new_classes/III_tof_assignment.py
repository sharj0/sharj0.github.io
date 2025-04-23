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

    def take_right(self): # TOFAssignment has only one child as of the current development of the script.
        if self.root.initial_creation_stage:
            super().take_right()
        else:
            self.children[0].take_right()

    def give_right(self): # TOFAssignment has only one child as of the current development of the script.
        if self.root.initial_creation_stage:
            super().give_right()
        else:
            self.children[0].give_right()

    def take_left(self): # TOFAssignment has only one child as of the current development of the script.
        if self.root.initial_creation_stage:
            super().take_left()
        else:
            self.children[0].take_left()

    def give_left(self): # TOFAssignment has only one child as of the current development of the script.
        if self.root.initial_creation_stage:
            super().give_left()
        else:
            self.children[0].give_left()


class InitialTOFAssignment(TOFAssignment):
    pass
