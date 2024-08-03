class Line_End_Class():
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.xy = self.x, self.y

    def __repr__(self):
        return f'Line end {self.xy}'