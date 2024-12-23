class Take_off_Class():
    def __init__(self, x, y, tof_name, id, use_name, layer_ind, tof_points_path):
        self.x = x
        self.y = y
        self.xy = self.x, self.y
        self.tof_name = tof_name
        self.id = id
        self.use_name = use_name
        self.layer_ind = layer_ind
        self.tof_points_path = tof_points_path

    def __repr__(self):
        if self.use_name == 'tof_name':
            return self.tof_name
        elif self.use_name == 'id':
            return self.id
        else:
            return self.layer_ind