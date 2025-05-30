from qgis.utils import plugins
from ..plugin_tools import show_information

class Node:
    # Class-level dictionary to hold counters for auto-created nodes (from previous feature).
    new_instance_counters = {}

    def __init__(self, name):
        self.name = name
        self.parent = None
        self.children = []  # maintained left-to-right
        self.deleted = False  # flag if node has been removed
        self.can_trade = True  # by default nodes can trade
        self.dont_create_or_destory = False  # NEW: flag to disable auto-creation/destruction
        self.can_be_renamed = True
        self.color = None
        self.newest_baby = None
        self.highest_parent = None

    def process_deletions(self):
        """
        Recursively remove children marked as deleted.
        After removal, re-check self and parent nodes for deletion eligibility.
        """
        # First recursively process deletions on all children
        for child in list(self.children):
            child.process_deletions()

        # Now remove any children that are marked deleted
        deleted_any = False
        for child in list(self.children):
            if child.deleted:
                print(f"Removing {child.name} from {self.name}")
                self.children.remove(child)
                child.parent = None
                # Clear the graphic if it exists
                if hasattr(child, 'graphic') and child.graphic:
                    print(f"Clearing graphic for {child.name}")
                    child.graphic.clear()
                    child.graphic = None
                deleted_any = True

        # If any deletions occurred, check if this node is now empty and deletable
        if deleted_any:
            current = self
            while current is not None:
                before = current.deleted
                current.check_empty()
                if current.deleted and not before:
                    print(f"{current.name} now marked deleted from cleanup")
                    # Clear the graphic for this node too
                    if hasattr(current, 'graphic') and current.graphic:
                        print(f"Clearing graphic for {current.name}")
                        current.graphic.clear()
                        current.graphic = None
                if not current.deleted:
                    break
                current = current.parent

    # --- Immediate neighbour helper methods ---
    def _immediate_left_neighbour(self):
        if self.parent:
            try:
                idx = self.parent.children.index(self)
            except ValueError:
                raise ValueError(f"{self.name} has been deleted")
            if idx > 0:
                return self.parent.children[idx - 1]
        return None

    def _immediate_right_neighbour(self):
        if self.parent:
            try:
                idx = self.parent.children.index(self)
            except ValueError:
                raise ValueError(f"{self.name} has been deleted")
            if idx < len(self.parent.children) - 1:
                return self.parent.children[idx + 1]
        return None

    def _get_effective_left_neighbour(self):
        # First check the immediate left neighbour
        ln = self._immediate_left_neighbour()
        if ln is not None and ln.__class__ == self.__class__:
            return ln, None

        recursion_count = 0
        parent = self.parent
        while parent is not None:
            if not parent.can_trade:
                print(f"{parent.name} cannot trade {parent.children[0].__class__.__name__}s")
                return None, None

            # find the next immediate left sibling, but skip any that are empty and non-deletable
            parent_ln = parent._immediate_left_neighbour()
            while parent_ln is not None and parent_ln.dont_create_or_destory and not parent_ln.children:
                parent_ln = parent_ln._immediate_left_neighbour()

            if parent_ln is not None:
                candidate = parent_ln
                # Descend recursively (for left, always take the right-most child)
                for _ in range(recursion_count + 1):
                    if candidate.children:
                        candidate = candidate.children[-1]
                    else:
                        candidate = None
                        break
                if candidate is not None and candidate.__class__ == self.__class__:
                    return candidate, parent

            recursion_count += 1
            parent = parent.parent

        return None, None

    def _get_effective_right_neighbour(self):
        # First check the immediate right neighbour
        rn = self._immediate_right_neighbour()
        if rn is not None and rn.__class__ == self.__class__:
            return rn, None

        recursion_count = 0
        parent = self.parent
        while parent is not None:
            if not parent.can_trade:
                print(f"{parent.name} cannot trade {parent.children[0].__class__.__name__}s")
                return None, None

            # find the next immediate right sibling, but skip any that are empty and non-deletable
            parent_rn = parent._immediate_right_neighbour()
            while parent_rn is not None and parent_rn.dont_create_or_destory and not parent_rn.children:
                parent_rn = parent_rn._immediate_right_neighbour()

            if parent_rn is not None:
                candidate = parent_rn
                # Descend recursively (for right, always take the left-most child)
                for _ in range(recursion_count + 1):
                    if candidate.children:
                        candidate = candidate.children[0]
                    else:
                        candidate = None
                        break
                if candidate is not None and candidate.__class__ == self.__class__:
                    return candidate, parent

            recursion_count += 1
            parent = parent.parent

        return None, None

    # --- New Neighbour Properties ---
    @property
    def left_neighbour(self):
        immediate = self._immediate_left_neighbour()
        if immediate is not None and immediate.__class__ == self.__class__:
            self.highest_parent = None
            return immediate
        # Otherwise, use effective lookup
        effective, highest = self._get_effective_left_neighbour()
        print("effective LN",effective)
        self.highest_parent = highest if effective is not None else None
        return effective

    @property
    def right_neighbour(self):
        immediate = self._immediate_right_neighbour()
        if immediate is not None and immediate.__class__ == self.__class__:
            self.highest_parent = None
            return immediate
        # Otherwise, use effective lookup
        effective, highest = self._get_effective_right_neighbour()
        self.highest_parent = highest if effective is not None else None
        return effective

    def _take_right_node_specific(self):
        # default is “no‑op”
        pass

    def _take_left_node_specific(self):
        # default is “no‑op”
        pass

    def _give_right_node_specific(self):
        # default is “no‑op”
        pass

    def _give_left_node_specific(self):
        # default is “no‑op”
        pass

    def display_and_select(self):
        old_level = self.root.plugin_canvas_gui.level
        self.root.plugin_canvas_gui.display_level(old_level)
        if hasattr(self, 'graphic') and self.graphic:
            self.graphic.select()

    def take_right(self): # takes a child away from its own right neighbour
        if not self.can_trade: # Block trades if dis-allowed
            print(f"{self.__class__.__name__} cannot trade")
            return
        rn = self.right_neighbour
        if rn is None:
            print(f"{self.name} has no right neighbour")
            return
        if not rn.children:
            print(f"{rn.name} has no children to take")
            return
        child = rn.remove_left_child()  # take left-most child from right neighbour
        if child:
            self.add_child_to_right(child)
            if self.highest_parent:
                print(f"{self.name} took {child.name} from {rn.name} through its parent {self.highest_parent.name}")
            else:
                print(f"{self.name} took {child.name} from {rn.name}")
        self._take_right_node_specific()

        if self.root.everything_needs_renaming:
            self.root.rename_everything()

        self.root.process_deletions()

    def give_right(self):
        if not self.can_trade:
            print(f"{self.__class__.__name__} cannot trade")
            return
        if len(self.children) == 1:
            # Can't give away last child, must be taken. Prevents needing self-delete logic
            msg = f"Cannot give away last child. It must be taken away."
            print(msg)
            show_information(msg)
            return
        rn = self.right_neighbour  # property will attempt effective lookup
        if rn is None:
            rn = self.create_a_new_right_neighbour()
            if rn is None: #if could not create_a_new_right_neighbour
                return

        child = self.remove_right_child()
        if child:
            rn.add_child_to_left(child)
            if self.highest_parent:
                print(f"{self.name} gave {child.name} to {rn.name} through its parent {self.highest_parent.name}")
            else:
                print(f"{self.name} gave {child.name} to {rn.name}")
        self._give_right_node_specific()

        if self.root.everything_needs_renaming:
            self.root.rename_everything()

        self.root.process_deletions()

    def take_left(self):
        if not self.can_trade:  # Block trades if dis‐allowed
            print(f"{self.__class__.__name__} cannot trade")
            return

        ln = self.left_neighbour
        if ln is None:
            print(f"{self.name} has no left neighbour")
            return
        if not ln.children:
            print(f"{ln.name} has no children to take")
            return

        child = ln.remove_right_child()  # take right‐most child from left neighbour
        if child:
            self.add_child_to_left(child)
            if self.highest_parent:
                print(f"{self.name} took {child.name} from {ln.name} through its parent {self.highest_parent.name}")
            else:
                print(f"{self.name} took {child.name} from {ln.name}")

        self._take_left_node_specific()

        if self.root.everything_needs_renaming:
            self.root.rename_everything()

        self.root.process_deletions()


    def give_left(self):
        if not self.can_trade:
            print(f"{self.__class__.__name__} cannot trade")
            return
        if len(self.children) == 1:
            # Can't give away last child, must be taken. Prevents needing self-delete logic
            msg = f"Cannot give away last child. It must be taken away."
            print(msg)
            show_information(msg)
            return
        ln = self.left_neighbour
        if ln is None:
            ln = self.create_a_new_left_neighbour()
            if ln is None:  # failed to create
                return

        child = self.remove_left_child()
        if child:
            ln.add_child_to_right(child)
            if self.highest_parent:
                print(f"{self.name} gave {child.name} to {ln.name} through its parent {self.highest_parent.name}")
            else:
                print(f"{self.name} gave {child.name} to {ln.name}")

        self._give_left_node_specific()

        if self.root.everything_needs_renaming:
            self.root.rename_everything()

        self.root.process_deletions()


    def create_a_new_right_neighbour(self):
        if self.parent is None:
            print(f"{self.name} has no parent to create a right neighbour.")
            return
        if self.dont_create_or_destory:
            print(f"{self.name} has dont_create_or_destory enabled, not creating a right neighbour.")
            return
        new_counter = Node.new_instance_counters.get(self.__class__.__name__, 1)
        new_name = f"new_{self.__class__.__name__}_{new_counter}"
        Node.new_instance_counters[self.__class__.__name__] = new_counter + 1
        new_node = self.__class__(new_name)
        idx = self.parent.children.index(self)
        self.parent.children.insert(idx + 1, new_node)
        new_node.parent = self.parent
        self.newest_baby = new_node
        print(f"Created new {self.__class__.__name__}: {new_node.name}")
        self.root.everything_needs_renaming = True
        return new_node

    def create_a_new_left_neighbour(self):
        if self.parent is None:
            print(f"{self.name} has no parent to create a left neighbour.")
            return
        if self.dont_create_or_destory:
            print(f"{self.name} has dont_create_or_destory enabled, not creating a left neighbour.")
            return

        # generate a unique name for the new instance
        new_counter = Node.new_instance_counters.get(self.__class__.__name__, 1)
        new_name = f"new_{self.__class__.__name__}_{new_counter}"
        Node.new_instance_counters[self.__class__.__name__] = new_counter + 1

        # instantiate and insert to the left of self
        new_node = self.__class__(new_name)
        idx = self.parent.children.index(self)
        self.parent.children.insert(idx, new_node)
        new_node.parent = self.parent
        self.newest_baby = new_node
        self.root.everything_needs_renaming = True

        print(f"Created new {self.__class__.__name__}: {new_node.name}")
        return new_node

    # Standard insertion methods.
    def add_child_to_left(self, child):
        child.parent = self
        self.children.insert(0, child)

    def add_child_to_right(self, child):
        child.parent = self
        self.children.append(child)

    def remove_left_child(self):
        if self.children:
            child = self.children.pop(0)
            child.parent = None
            self.check_empty()
            return child
        return None

    def remove_right_child(self):
        if self.children:
            child = self.children.pop(-1)
            child.parent = None
            self.check_empty()
            return child
        return None

    def get_descendants(self):
        result = []
        for child in self.children:
            result.append(child)
            result.extend(child.get_descendants())
        return result

    def __repr__(self):
        status = " (deleted)" if self.deleted else ""
        return f"{self.name}{status}"

    @property
    def root(self):
        current = self
        while current.parent is not None:
            current = current.parent
        return current

    @property
    def utm_fly_list(self):
        nodes_utm_fly_list = []
        for child in self.children:
            nodes_utm_fly_list.extend(child.utm_fly_list)
        return nodes_utm_fly_list

    @property
    def efficiency_percent(self):
        if self.total_length == 0:
            return 0.0
        return (self.production_length/self.total_length)*100

    @property
    def production_length(self):
        return sum([child.production_length for child in self.children])

    @property
    def total_length(self):
        return sum([child.total_length for child in self.children])

    # --- Global tree name property ---
    @property
    def tree_name(self):
        # If there's no parent, we're at the top of the tree.
        if self.parent is None:
            return f"{self.__class__.__name__[0]}1"
        else:
            idx = self.parent.children.index(self) + 1
            return f"{self.parent.tree_name}-{self.__class__.__name__[0]}{idx}"

    @property
    def end_point_centroid(self):
        if self.end_point_list:
            points = [pt.xy for pt in self.end_point_list]
            total_x = 0.0
            total_y = 0.0
            count = 0
            for x, y in points:
                total_x += x
                total_y += y
                count += 1
            return (total_x / count, total_y / count)
        else:
            return None

    # When a node loses all children, mark it for deletion.
    def check_empty(self):
        if not self.children:
            if self.dont_create_or_destory:
                return
            print(f"Marking {self.name} for deletion because it has no children")
            self.deleted = True
            self.root.everything_needs_renaming = True


    def _flip_lines_node_specific(self):
        # default is “no‑op”
        pass

    def flip_lines(self):
        self._flip_lines_node_specific()


    def filter_descendants(self, cls_or_name):
        """
        Recursively collects descendant nodes matching the specified class or class name,
        skipping nodes that have been marked as deleted.
        If cls_or_name is a string, compares the descendant's class name;
        otherwise, uses isinstance.
        """
        # If this node is deleted, return an empty list.
        if self.deleted:
            return []

        result = []
        for child in self.children:
            # Skip the child if it has been deleted.
            if child.deleted:
                continue
            if isinstance(cls_or_name, str):
                if child.__class__.__name__ == cls_or_name:
                    result.append(child)
            else:
                if isinstance(child, cls_or_name):
                    result.append(child)
            result.extend(child.filter_descendants(cls_or_name))
        return result

    @property
    def short_name(self):
        letter = self.__class__.__name__[0].upper()
        count = getattr(self, 'global_count', 1)
        return f'{letter}{count}'

    def get_list_of_all_children_at_level(self, class_string):
        """
        Returns all children (descendants) matching the specified class name.
        If the current node itself matches the class_string, return [self].
        Otherwise, recursively search children.
        """
        # Match the current node
        if self.__class__.__name__ == class_string:
            return [self]

        matching_children = []
        for child in self.children:
            matching_children.extend(child.get_list_of_all_children_at_level(class_string))
        return matching_children


    def get_parent_at_level(self, class_string):
        """
        Traverses upward through the parent hierarchy until a node is found
        whose class name matches the provided class_string.
        Raises a ValueError if no matching parent is found.
        """
        if self.parent is None:
            raise ValueError(f"No parent exists for {self.name} matching '{class_string}'")
        current = self.parent
        while True:
            if current.__class__.__name__ == class_string:
                return current
            if current.parent is None:
                raise ValueError(f"No parent found for {self.name} with class matching '{class_string}'")
            current = current.parent

    def get_right_most_child_at_level(self, class_string):
        """
        Traverses downward by always taking the right-most child until a node is found
        whose class name matches the provided class_string.
        Raises a ValueError if no matching child is found.
        """
        if not self.children:
            raise ValueError(f"No children available for {self.name} to search for class '{class_string}'")
        current = self.children[-1]
        while True:
            if current.__class__.__name__ == class_string:
                return current
            if not current.children:
                raise ValueError(f"No right-most child found for {self.name} with class matching '{class_string}'")
            current = current.children[-1]

    def get_left_most_child_at_level(self, class_string):
        """
        Traverses downward by always taking the left-most child until a node is found
        whose class name matches the provided class_string.
        Raises a ValueError if no matching child is found.
        """
        if not self.children:
            raise ValueError(f"No children available for {self.name} to search for class '{class_string}'")
        current = self.children[0]
        while True:
            if current.__class__.__name__ == class_string:
                return current
            if not current.children:
                raise ValueError(f"No left-most child found for {self.name} with class matching '{class_string}'")
            current = current.children[0]