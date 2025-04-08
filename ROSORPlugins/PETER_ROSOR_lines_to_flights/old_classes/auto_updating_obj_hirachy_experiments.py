# survey_area.py
from base_node_class import Node

class SurveyArea(Node):
    def __init__(self, name):
        super().__init__(name)
        # SurveyArea remains tradable.

    def rename_everything(self):
        """
        Renames every node in the tree based on a global counter per type.
        SurveyArea itself is not renamed.
        """
        counters = {}

        def rename_node(node):
            # Skip renaming SurveyArea.
            if node.__class__.__name__ != "SurveyArea":
                classname = node.__class__.__name__
                cnt = counters.get(classname, 0) + 1
                counters[classname] = cnt
                node.name = f"{classname}-{cnt}"
            for child in node.children:
                rename_node(child)
        rename_node(self)

    @property
    def strip_list(self):
        return [child for child in self.children if child.__class__.__name__ == "Strip"]

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



# strip.py
from base_node_class import Node

class Strip(Node):
    def __init__(self, name):
        super().__init__(name)
        # Strips cannot trade.
        self.can_trade = False

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



# tof_assignment.py
from base_node_class import Node

class TOFAssignment(Node):
    def __init__(self, name):
        super().__init__(name)
        # Prevent auto-creation and auto-deletion for TOFAssignment nodes.
        self.dont_create_or_destory = True

    @property
    def quadrant_list(self):
        return self.filter_descendants("Quadrant")

    @property
    def flight_list(self):
        return self.filter_descendants("Flight")

    @property
    def line_list(self):
        return self.filter_descendants("Line")

# quadrant.py
from base_node_class import Node

class Quadrant(Node):
    @property
    def flight_list(self):
        return self.filter_descendants("Flight")

    @property
    def line_list(self):
        return self.filter_descendants("Line")



# flight.py
from base_node_class import Node

class Flight(Node):
    @property
    def line_list(self):
        # Only include children that are Lines.
        return [child for child in self.children if child.__class__.__name__ == "Line"]


# line.py
from base_node_class import Node

class Line(Node):
    # Lines are leaves; they do not trade.
    def __init__(self, name):
        super().__init__(name)
        self.can_trade = False



survey = SurveyArea("SurveyArea")

# Create 2 strips.
for i in range(1, 3):
    strip = Strip(f"Strip-{i}")
    survey.add_child_to_right(strip)

    # Each strip gets 5 TOF assignments.
    for j in range(1, 6):
        tof = TOFAssignment(f"TOF-asmt-{i}-{j}")
        strip.add_child_to_right(tof)

        # Only add children for the middle 3 TOFAssignments.
        if j in (2, 3, 4):
            quad = Quadrant(f"Quadrant-{i}-{j}")
            tof.add_child_to_right(quad)

            # Each quadrant gets 3 flights.
            for k in range(1, 4):
                flight = Flight(f"Flight-{i}-{j}-{k}")
                quad.add_child_to_right(flight)

                # Each flight gets 4 lines.
                for l in range(1, 5):
                    line = Line(f"Line-{i}-{j}-{k}-{l}")
                    flight.add_child_to_right(line)



survey.rename_everything()

# --- Demonstration of renaming and tree_name ---
def find_node_by_name(node, target_name):
    if node.name == target_name:
        return node
    for child in node.children:
        found = find_node_by_name(child, target_name)
        if found:
            return found
    return None


# For example, examine Flight-1, Flight-2, and Flight-3.
flight1 = find_node_by_name(survey, "Flight-1")
flight2 = find_node_by_name(survey, "Flight-2")
flight3 = find_node_by_name(survey, "Flight-3")

last_flight = survey.flight_list[-1]

if flight1 and flight2 and flight3:
    print("\nInitial state (after renaming):")
    print(f"{flight1.name} with global tree name: {flight1.tree_name}")
    print(f"{flight2.name} with global tree name: {flight2.tree_name}")
    print(f"{flight3.name} with global tree name: {flight3.tree_name}")
    print(f"{last_flight.name} with global tree name: {last_flight.tree_name}")
    # For demonstration, invoke give_left() on Flight-1.
    flight1.give_left()