from I_survey_area import SurveyArea
from II_strip import Strip
from III_tof_assignment import TOFAssignment
from IIII_quadrant import Quadrant
from IIIII_flight import Flight
from IIIIII_line import Line
from IIIIIII_end_point import EndPoint

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

                    # Each line gets 2 end point.
                    for m in range(1, 3):
                        end = EndPoint(f"EndPoint-{i}-{j}-{k}-{l}-{m}", 0,0)
                        line.add_child_to_right(end)


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
    last_flight.give_left()