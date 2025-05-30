# survey_area.py
from .base_node_class import Node
from collections import deque

class SurveyArea(Node):
    def __init__(self, name):
        super().__init__(name)
        self.can_trade = False
        self.can_be_renamed = False
        self.dont_create_or_destory = True
        self.initial_creation_stage = True
        self.everything_needs_renaming = False

    def _all_nodes(self):
        """Breadth‐first traverse the entire tree, yielding every node."""
        q = deque([self])
        while q:
            n = q.popleft()
            yield n
            q.extend(n.children)

    def backup_colors(self):
        """Save each node’s current .color into ._base_color."""
        for n in self._all_nodes():
            n._base_color = getattr(n, "color", None)

    def restore_colors(self):
        """Restore from ._base_color back into .color."""
        for n in self._all_nodes():
            if hasattr(n, "_base_color"):
                n.color = n._base_color

    def rename_everything(self):
        """
        Renames every node in the tree based on a global counter per type.
        Nodes with can_be_renamed == False or that are deleted are skipped.
        """
        #print("Renaming everything")
        self.assign_per_TOF_flight_counts()
        counters = {}
        def rename_node(node):
            # If the node is deleted, skip renaming/counting
            if node.deleted:
                return

            if getattr(node, "can_be_renamed", True):
                classname = node.__class__.__name__
                cnt = counters.get(classname, 0) + 1
                counters[classname] = cnt
                node.name = f"{classname}-{cnt}"
                node.global_count = cnt

            for child in node.children:
                rename_node(child)

        rename_node(self)
        self.everything_needs_renaming = False

    def recolor_everything(self):
        """
        Recolors every node in the tree level by level (Breadth-First).
        Uses self.root.color_cycle to assign colors sequentially across each level.
        Assumes self.root (which is self for SurveyArea) has a 'color_cycle' attribute
        that is an iterator (e.g., from itertools.cycle).
        """
        # Ensure the color_cycle attribute exists and is usable
        if not hasattr(self.root, 'color_cycle'):
            print("Error: Root node must have a 'color_cycle' attribute.")
            # Or raise AttributeError("Root node must have a 'color_cycle' attribute.")
            return

        try:
            # Get the iterator. This also helps catch if color_cycle is None or not iterable.
            color_iterator = iter(self.root.color_cycle)
        except TypeError:
            print("Error: Root node's 'color_cycle' is not an iterable.")
            # Or raise TypeError("Root node's 'color_cycle' must be an iterable.")
            return

        # Initialize the queue with the root node (self)
        queue = deque([self])

        while queue:
            # Dequeue the next node to process
            current_node = queue.popleft()

            # Assign the next color from the cycle
            try:
                current_node.color = next(color_iterator)
                # print(f"Colored {current_node.name} with {current_node.color}") # Optional: for debugging
            except StopIteration:
                # This shouldn't happen with itertools.cycle, but good practice for general iterators
                print("Warning: Color iterator exhausted.")
                # Decide how to handle: stop, reset, raise error? Stopping for now.
                break
            except Exception as e:
                print(f"An error occurred while getting next color: {e}")
                break

            # Enqueue all children of the current node for the next level
            for child in current_node.children:
                # Ensure child hasn't been deleted (though BFS on tree usually doesn't revisit)
                if not child.deleted:
                    queue.append(child)

    def color_by_tof(self):
        """
        Assign a unique color to each TOF and propagate it to all associated flights/lines.
        """
        if not hasattr(self.root, 'color_cycle'):
            print("Error: Root node must have a 'color_cycle' attribute.")
            return

        color_iterator = iter(self.root.color_cycle)
        tof_color_map = {}

        # Assign a unique color to each TOF
        for tof in self.TOF_list:
            color = next(color_iterator)
            tof.color = color
            tof_color_map[tof] = color

        # Color all TOFAssignment nodes and their descendants by their TOF's color
        for ta in self.TA_list:
            if ta.tof in tof_color_map:
                ta.color = tof_color_map[ta.tof]
                # Color all descendants (quadrants, flights, lines, etc.)
                for quadrant in ta.quadrant_list:
                    quadrant.color = ta.color
                for flight in ta.flight_list:
                    flight.color = ta.color
                    for line in flight.line_list:
                        line.color = ta.color

    def assign_per_TOF_flight_counts(self):
        for tof in self.TOF_list:
            counter = 1
            for flight in tof.flight_list:
                flight.per_tof_count = counter
                counter += 1

    @property
    def TOF_list(self):
        tof_list = [TA.tof for TA in self.TA_list]
        seen = set()
        unique_tof_list = []
        for tof in tof_list:
            if id(tof) not in seen:
                seen.add(id(tof))
                unique_tof_list.append(tof)
        return unique_tof_list

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

    @property
    def end_point_list(self):
        return self.filter_descendants("EndPoint")
