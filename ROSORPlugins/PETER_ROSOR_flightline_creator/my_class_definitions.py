import math
import numpy as np
from shapely.geometry import Polygon

class EndPoint():
    def __init__(self, x, y):
        # Set the internal attributes directly to avoid reference before assignment
        self._x = x
        self._y = y
        # Now it's safe to set self._xy since both _x and _y have been set
        self._xy = (self._x, self._y)

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        self._x = value
        # Make sure to update _xy only if _y already exists
        if hasattr(self, '_y'):  # Check if _y has been set
            self._xy = (self._x, self._y)

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        self._y = value
        # Make sure to update _xy only if _x already exists
        if hasattr(self, '_x'):  # Check if _x has been set
            self._xy = (self._x, self._y)

    @property
    def xy(self):
        return self._xy

    def plot(self, ax, style='kx'):
        """Plot this point on the given matplotlib axis with the specified style."""
        ax.plot(self.x, self.y, style)

    def __repr__(self):
        return f"(x={self._x}, y={self._y})"

    def calculate_distance(self, other_point):
        """Calculate Euclidean distance from this point to another point."""
        if not isinstance(other_point, EndPoint):
            raise ValueError("other_point must be an instance of Point")
        return math.sqrt((self.x - other_point.x) ** 2 + (self.y - other_point.y) ** 2)

    def point_at_distance_and_angle(self, distance, angle_degrees):
        """Calculate a new point at a specified distance and angle from this point.

        Parameters:
        - distance: The distance to the new point.
        - angle_degrees: The angle in degrees from this point to the new point.

        Returns:
        A new Point instance at the calculated location.
        """
        angle_radians = math.radians(angle_degrees)
        x_new = self.x + distance * math.cos(angle_radians)
        y_new = self.y + distance * math.sin(angle_radians)
        return EndPoint(x_new, y_new)

def is_within_segments(point, seg1, seg2):
    # Inline function for checking if a point is within a segment's bounds
    within1 = np.all(np.logical_and(np.minimum(seg1[0], seg1[1]) <= point, point <= np.maximum(seg1[0], seg1[1])))
    within2 = np.all(np.logical_and(np.minimum(seg2[0], seg2[1]) <= point, point <= np.maximum(seg2[0], seg2[1])))
    return within1 and within2

class Line():
    def __init__(self, start_point, end_point):
        if not isinstance(start_point, EndPoint) or not isinstance(end_point, EndPoint):
            raise ValueError("start_point and end_point must be instances of EndPoint class")
        self.start_point = start_point
        self.end_point = end_point

    def length(self):
        # Calculate the length of the line using the distance formula
        return math.sqrt((self.end_point.x - self.start_point.x)**2 + (self.end_point.y - self.start_point.y)**2)


    def plot(self, ax, **kwargs):
        # Now use these plotting parameters along with any others that might be in kwargs
        ax.plot([self.start_point.x, self.end_point.x], [self.start_point.y, self.end_point.y], **kwargs)

    @property
    def point_list(self):
        return [self.start_point, self.end_point]

    @property
    def point_arr(self):
        return np.array([self.start_point.xy, self.end_point.xy])

    def __repr__(self):
        return f"Line(start={repr(self.start_point)}, end={repr(self.end_point)})"

    @property
    def angle(self):
        """Get the angle of the line in degrees."""
        dx = self.end_point.x - self.start_point.x
        dy = self.end_point.y - self.start_point.y
        # Calculate angle in radians
        angle_radians = math.atan2(dy, dx)
        # Convert to degrees
        angle_degrees = math.degrees(angle_radians)
        return angle_degrees

    def get_buffer_poly(self, buffer, extend_length=0.01):
        """Returns a Shapely Polygon that represents a buffered rectangle around the line."""
        dx = self.end_point.x - self.start_point.x
        dy = self.end_point.y - self.start_point.y

        # Calculate the length of the line
        line_length = math.sqrt(dx ** 2 + dy ** 2)

        # Normalize the direction vector
        dx_normalized = dx / line_length
        dy_normalized = dy / line_length

        # Extend start and end points
        extended_start_x = self.start_point.x - dx_normalized * extend_length
        extended_start_y = self.start_point.y - dy_normalized * extend_length
        extended_end_x = self.end_point.x + dx_normalized * extend_length
        extended_end_y = self.end_point.y + dy_normalized * extend_length

        # Calculate the angle of the line
        angle = math.atan2(dy, dx)

        # Calculate offsets for the perpendicular directions
        offset_x = math.cos(angle + math.pi / 2) * buffer
        offset_y = math.sin(angle + math.pi / 2) * buffer

        # Calculate the four corners of the rectangle
        corner1 = (extended_start_x - offset_x, extended_start_y - offset_y)
        corner2 = (extended_end_x - offset_x, extended_end_y - offset_y)
        corner3 = (extended_end_x + offset_x, extended_end_y + offset_y)
        corner4 = (extended_start_x + offset_x, extended_start_y + offset_y)

        # Create and return the Shapely Polygon
        return Polygon([corner1, corner2, corner3, corner4])

    def calculate_intersection(line1, line2):
        # Flatten point arrays and create variables for readability
        p1, p2 = line1.point_arr[0], line1.point_arr[1]
        p3, p4 = line2.point_arr[0], line2.point_arr[1]

        # Use NumPy arrays for vectorized operations
        p = np.array([p1, p2, p3, p4])

        # Calculate differences for use in equations
        d = p[1] - p[0], p[3] - p[2]
        d = np.array(d)

        # Construct matrices from point differences
        den = np.linalg.det(d)

        # Check for parallel lines (denominator = 0)
        if np.isclose(den, 0):
            return None  # Lines are parallel or coincident

        # Matrix for the numerator calculations
        num_matrix = np.array([p[2] - p[0], d[1]])

        # Calculate the intersection point using Cramer's Rule
        t = np.linalg.det(num_matrix) / den
        intersection = p[0] + t * d[0]

        # Check if the intersection is within the segments
        if is_within_segments(intersection, line1.point_arr, line2.point_arr):
            return intersection
        else:
            return None


class TieLine(Line):
    def __init__(self, start_point, end_point):
        super().__init__(start_point, end_point)
        self.is_flt_line = False
        self.is_tie_line = True

    def __repr__(self):
        return f"Tie Line (start={repr(self.start_point)}, end={repr(self.end_point)})"

class FltLine(Line):
    def __init__(self, start_point, end_point):
        super().__init__(start_point, end_point)
        self.is_flt_line = True
        self.is_tie_line = False

    def __repr__(self):
        return f"Flt Line (start={repr(self.start_point)}, end={repr(self.end_point)})"

# Example usage:
if __name__ == "__main__":
    start = EndPoint(0, 0)
    end = EndPoint(3, 4)
    line = Line(start, end)