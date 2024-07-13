from shapely.geometry import LineString


def flightline_lkm(flight_lines):

    flightline_lkm_list = []
    flightline_lkm_total = 0
    for flight_line in flight_lines:
        flightline_length = LineString(flight_line).length/1000
        flightline_lkm_list.append(f'{flightline_length:.3f}')
        flightline_lkm_total += flightline_length

    return flightline_lkm_list, f'{flightline_lkm_total:.3f}'
