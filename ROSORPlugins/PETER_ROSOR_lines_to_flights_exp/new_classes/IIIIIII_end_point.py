#end_point.py
from .base_node_class import Node

class EndPoint(Node):
    def __init__(self, name, x, y):
        super().__init__(name)
        self.can_trade = False  # EndPoints are leafs do not trade.
        self.x = x
        self.y = y

    @property
    def xy(self):
        return self.x, self.y

