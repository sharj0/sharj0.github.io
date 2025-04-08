# strip.py
from .base_node_class import Node

class Strip(Node):
    def __init__(self, name):
        super().__init__(name)
        # Strips cannot trade.
        self.can_trade = False
        self.can_be_renamed = False

    @property
    def TA_list(self):
        return self.filter_descendants("TOFAssignment")

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
