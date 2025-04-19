import re

class Take_off_Class():
    def __init__(self, x, y, tof_name, id, use_name, layer_ind, tof_points_path):
        self.x = x
        self.y = y
        self.tof_name = tof_name
        self.id = id
        self.use_name = use_name
        self.layer_ind = layer_ind
        self.tof_points_path = tof_points_path
        self.children = []

    def __repr__(self):
        if self.use_name == 'tof_name':
            return self.tof_name
        elif self.use_name == 'id':
            return self.id
        else:
            return self.layer_ind

    @property
    def clean_tof_name(self) -> str:
        """
        Returns the substring starting from the first numerical character in self.tof_name.
        If no numerical character is found, returns an empty string.
        """
        match = re.search(r'\d', self.tof_name)
        if match:
            return self.tof_name[match.start():]
        return ""

    @property
    def xy(self):
        return self.x, self.y

    @property
    def flight_list(self):
        flights_list = []
        for ta in self.children:
            for flight in ta.flight_list:
                flights_list.append(flight)
        return flights_list
