
from .Flight_Class import generate_flight

class Flight_Area():
    def __init__(self, tof, strip, lines):
        self.tof = tof
        self.strip = strip
        self.line_list = lines
        self.children_flights = []

    def __repr__(self):
        return f'<Flight area lines: {self.line_list}, tof:{self.tof}, {self.strip}>'

    #mission.flt_heap = []
    def generate_flights_within_fa(self, max_number_of_lines_per_flight, max_flt_size, perfer_even_number_of_lines):
        dividing_start_inds = [0]
        dividing_end_inds = [len(self.line_list)]
        current_flight = 0
        while True:
            if dividing_end_inds[0] == 0:
                return []
            print('generating flight...')

            # limit number of lines tested
            if dividing_end_inds[current_flight] - dividing_start_inds[current_flight] > max_number_of_lines_per_flight:
                dividing_end_inds[current_flight] = int(dividing_start_inds[current_flight] + max_number_of_lines_per_flight)

            line_list = \
                self.line_list[dividing_start_inds[current_flight]:dividing_end_inds[current_flight]]


            print(f'srt {dividing_start_inds[current_flight]}, end {dividing_end_inds[current_flight]}, len {len(line_list)}')
            if len(line_list) == 0:
                print('no lines given')
            test_flight = generate_flight(line_list, self)
            if test_flight.overall_dist < max_flt_size:
                test_flight.ind_within_fa = current_flight
                test_flight.parent_flight_area = self
                self.children_flights.append(test_flight)
                print(self.children_flights)
                #mission.flt_heap.append(test_flight)
                if dividing_end_inds[current_flight] == len(self.line_list):
                    break # THIS BREAKS OUT OF GENERATING FLIGHTS WITHIN THE FA BECAUSE WHEN DONE
                else:
                    dividing_start_inds.append(dividing_end_inds[current_flight])
                    dividing_end_inds.append(len(self.line_list))
                    current_flight += 1
                    print('accepted')
            else:
                if not perfer_even_number_of_lines:
                    # old way just subtract one
                    dividing_end_inds[current_flight] -= 1
                else:
                    # new way when subtracting ensure # of lines is even
                    dividing_end_inds[current_flight] -= 1
                    len_of_lines = dividing_end_inds[current_flight] - dividing_start_inds[current_flight]
                    if len_of_lines % 2 == 1 and len_of_lines > 1:
                        dividing_end_inds[current_flight] -= 1

        self.dividing_start_inds = dividing_start_inds
        self.dividing_end_inds = dividing_end_inds
        return self.children_flights




