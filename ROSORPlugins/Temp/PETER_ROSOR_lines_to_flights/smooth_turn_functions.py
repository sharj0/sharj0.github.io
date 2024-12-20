import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Arc

arr = np.array

def less_360(inp):
    return np.mod(inp, 360)

def get_turn_centres(coord, ang, turn_diameter):
    c, s = np.cos(np.deg2rad(ang - 90)), np.sin(np.deg2rad(ang - 90))
    right_tc = (coord[0] + c * turn_diameter / 2, coord[1] + s * turn_diameter / 2)
    c, s = np.cos(np.deg2rad(ang + 90)), np.sin(np.deg2rad(ang + 90))
    left_tc = (coord[0] + c * turn_diameter / 2, coord[1] + s * turn_diameter / 2)
    return left_tc, right_tc


def get_tangent_point(turn_direction_ccw, turn_centre, origin_point, turn_diameter):
    dist_xy = arr(origin_point) - arr(turn_centre)
    b = np.hypot(dist_xy[0], dist_xy[1])
    if (turn_diameter / 2) / b > 1:
        return
    if (turn_diameter / 2) / b < -1:
        return
    theta = np.arccos((turn_diameter / 2) / b)
    d = np.arctan2(dist_xy[1], dist_xy[0])  # direction angle of origin_point from turn_centre
    if turn_direction_ccw:
        d_tc = d + theta  # direction angle of point T1 from C
    else:
        d_tc = d - theta  # direction angle of point T2 from C
    Tx = turn_centre[0] + turn_diameter / 2 * np.cos(d_tc)
    Ty = turn_centre[1] + turn_diameter / 2 * np.sin(d_tc)
    return (Tx, Ty)


def get_turn_ang(tp_closest, start_coord, fly_line_ang, is_ccw):
    diffz = arr(tp_closest) - arr(start_coord)
    line_ang = np.rad2deg(np.arctan2(diffz[1], diffz[0]))
    turn_ang = fly_line_ang - line_ang
    if is_ccw and turn_ang < 0:
        turn_ang = turn_ang + 360
    if not is_ccw and turn_ang > 0:
        turn_ang = turn_ang - 360
    turn_ang -= np.trunc(turn_ang / 360) * 360
    assert not turn_ang > 360 and not turn_ang < -360, 'ang must be between -360 and + 360'
    return turn_ang

def choose_best_tangent_point(left_tc, right_tc, start_coord, turn_diameter, fly_line_ang,
                              point_between_circs, flight_start):
    left_tp = get_tangent_point(turn_direction_ccw=True, turn_centre=left_tc,
                                origin_point=start_coord, turn_diameter=turn_diameter)
    right_tp = get_tangent_point(turn_direction_ccw=False, turn_centre=right_tc,
                                 origin_point=start_coord, turn_diameter=turn_diameter)
    if left_tp is None:
        turn_ang = get_turn_ang(right_tp, start_coord, fly_line_ang, is_ccw=False)
        return right_tp, right_tc, turn_ang
    if right_tp is None:
        turn_ang = get_turn_ang(left_tp, start_coord, fly_line_ang, is_ccw=True)
        return left_tp, left_tc, turn_ang
    dist_xy = arr(start_coord) - arr(left_tc)
    left_tc_hyp = np.hypot(dist_xy[0], dist_xy[1])
    if left_tc_hyp < turn_diameter / 2:
        turn_ang = get_turn_ang(right_tp, start_coord, fly_line_ang, is_ccw=False)
        return right_tp, right_tc, turn_ang
    dist_xy = arr(start_coord) - arr(right_tc)
    right_tc_hyp = np.hypot(dist_xy[0], dist_xy[1])
    if right_tc_hyp < turn_diameter / 2:
        turn_ang = get_turn_ang(left_tp, start_coord, fly_line_ang, is_ccw=True)
        return left_tp, left_tc, turn_ang
    dist_xy = arr(start_coord) - arr(left_tp)
    left_tp_hyp = np.hypot(dist_xy[0], dist_xy[1])
    dist_xy = arr(start_coord) - arr(right_tp)
    right_tp_hyp = np.hypot(dist_xy[0], dist_xy[1])
    closest_tp_ind = np.argmin([left_tp_hyp, right_tp_hyp])
    tp_closest = [left_tp, right_tp][closest_tp_ind]
    tc_closest = [left_tc, right_tc][closest_tp_ind]
    turn_is_ccw = not bool(closest_tp_ind)
    turn_ang = get_turn_ang(tp_closest, start_coord, fly_line_ang, turn_is_ccw)
    plot_here = False
    if plot_here:
        fig, ax = plt.subplots()
        plt.axis('equal')
        ax.title.set_text(f'Turn ang {turn_ang}')
        ax.add_patch(Arc(left_tc, turn_diameter, turn_diameter,
                         edgecolor='k'))
        ax.add_patch(Arc(right_tc, turn_diameter, turn_diameter,
                         edgecolor='k'))
        dx = np.cos(np.deg2rad(fly_line_ang)) * turn_diameter
        dy = np.sin(np.deg2rad(fly_line_ang)) * turn_diameter
        ax.plot([point_between_circs[0], point_between_circs[0] + dx],
                [point_between_circs[1], point_between_circs[1] + dy])
        ax.plot([start_coord[0], tp_closest[0]], [start_coord[1], tp_closest[1]])
        plt.show()
    return tp_closest, tc_closest, turn_ang

def quantize_turn(srt_coord, srt_ang_deg,
                  end_coord, total_turn_ang, turn_segment_length, og_turn_diameter):
    default_coords = arr([srt_coord, end_coord])
    if abs(total_turn_ang) < 10:
        segs_coords = np.expand_dims(default_coords[0], 0)
        radius_big_enough = True
        return segs_coords, radius_big_enough
    expected_angle = np.ceil(np.degrees(np.arctan2(turn_segment_length / 2, og_turn_diameter / 2) * 2) * 10) / 10
    srt_ang_deg -= np.trunc(srt_ang_deg / 180) * 360
    if srt_ang_deg < 0:
        srt_ang_deg += 360
    end_ang_deg = srt_ang_deg + total_turn_ang
    num_segs = 1
    plot_here = False
    if plot_here:
        fig, ax = plt.subplots()
        plt.axis('equal')
        dx = np.cos(np.deg2rad(srt_ang_deg + 180)) * turn_segment_length * 4
        dy = np.sin(np.deg2rad(srt_ang_deg + 180)) * turn_segment_length * 4
        liner, = ax.plot([srt_coord[0], srt_coord[0] + dx], [srt_coord[1], srt_coord[1] + dy], alpha=0.5)
        ax.plot(srt_coord[0] + dx, srt_coord[1] + dy, 'X', color=liner.get_color(), ms=6, alpha=0.5)
        ax.plot(*srt_coord, '^', color=liner.get_color(), ms=6, alpha=0.5)
        dx = np.cos(np.deg2rad(end_ang_deg)) * turn_segment_length * 4
        dy = np.sin(np.deg2rad(end_ang_deg)) * turn_segment_length * 4
        liner, = ax.plot([end_coord[0], end_coord[0] + dx], [end_coord[1], end_coord[1] + dy], alpha=0.5)
        ax.plot(*end_coord, 'X', color=liner.get_color(), ms=6, alpha=0.5)
        ax.plot(end_coord[0] + dx, end_coord[1] + dy, '^', color=liner.get_color(), ms=6, alpha=0.5)
    while True:
        if num_segs > 10:
            pass
        ang_per_segment = total_turn_ang / (num_segs + 1)
        ang_arr = np.ones(num_segs + 1) * ang_per_segment
        ang_arr = np.insert(ang_arr, 0, 0)
        ang_arr = np.cumsum(ang_arr) + srt_ang_deg
        angle1 = np.mean(ang_arr[:2])
        angle2 = np.mean(ang_arr[-2:])
        if total_turn_ang > 0:
            angle1 += 90
            angle2 += 90
        else:
            angle1 -= 90
            angle2 -= 90
        # Convert angles to radians
        rad1 = np.radians(angle1)
        rad2 = np.radians(angle2)
        # Calculate the direction vectors of the lines
        dir1 = np.array([np.cos(rad1), np.sin(rad1)])
        dir2 = np.array([np.cos(rad2), np.sin(rad2)])
        # Calculate the difference vector between the two starting points
        diff = np.array(end_coord) - np.array(srt_coord)
        # Calculate the intersection point using matrix multiplication
        if np.cross(dir1, dir2) == 0:
            segs_coords = np.expand_dims(default_coords[0], 0)
            radius_big_enough = True
            return segs_coords, radius_big_enough
        t = np.cross(diff, dir2) / np.cross(dir1, dir2)
        intersection = np.array(srt_coord) + t * dir1
        new_radius = np.linalg.norm(intersection - np.array(srt_coord))
        new_turn_centre = tuple(intersection)
        angle1 += 180
        angle2 += 180
        ang_arr_centre_perspective = np.linspace(angle1, angle2, num_segs + 1, endpoint=True)
        x = np.cos(np.deg2rad(ang_arr_centre_perspective)) * new_radius + new_turn_centre[0]
        y = np.sin(np.deg2rad(ang_arr_centre_perspective)) * new_radius + new_turn_centre[1]
        segs_coords = arr([x, y]).T
        seg_len = np.linalg.norm(np.diff(segs_coords, axis=0), axis=1)[0]
        if plot_here:
            if angle1 > angle2:
                draw_ang_1, draw_ang_2 = angle2, angle1
            else:
                draw_ang_1, draw_ang_2 = angle1, angle2
            lineerz, = ax.plot(segs_coords.T[0], segs_coords.T[1])
            ax.plot(*new_turn_centre, 'o', color=lineerz.get_color())
            ax.add_patch(Arc(new_turn_centre, new_radius * 2, new_radius * 2,
                             theta1=draw_ang_1, theta2=draw_ang_2,
                             edgecolor=lineerz.get_color(), facecolor='none', lw=1.5))

            for inder, (xr, yr) in enumerate(zip(segs_coords.T[0], segs_coords.T[1])):
                text_box_props = dict(boxstyle='round', facecolor='white', alpha=0.7)
                ploted_text = ax.text(xr,
                                      yr,
                                      inder,
                                      fontsize=7,
                                      multialignment='center', bbox=text_box_props, zorder=6)
            plt.show()
        if expected_angle > abs(ang_per_segment):
            if seg_len < turn_segment_length:
                radius_big_enough = False
            else:
                radius_big_enough = True
            return segs_coords,  radius_big_enough
        num_segs += 1

def get_tangents_for_2_circs(start_tc, start_direction_is_cw, start_direction, start_coord,
                             end_tc, end_direction_is_cw, end_direction, end_coord,
                             turn_radius, turn_option):
    debug_turns = [-1, -2]
    norming_coord = start_tc
    start_tc = tuple(arr(start_tc) - arr(norming_coord))
    start_coord = tuple(arr(start_coord) - arr(norming_coord))
    end_tc = tuple(arr(end_tc) - arr(norming_coord))
    end_coord = tuple(arr(end_coord) - arr(norming_coord))
    rot_ang = -np.rad2deg(np.arctan2(end_tc[0], end_tc[1])) + 90
    all_coords_arr = arr([start_tc, start_coord, end_tc, end_coord])
    c, s = np.cos(np.deg2rad(rot_ang)), np.sin(np.deg2rad(rot_ang))
    rot_x = c * all_coords_arr.T[0] + s * all_coords_arr.T[1]
    rot_y = -s * all_coords_arr.T[0] + c * all_coords_arr.T[1]
    all_coords_rot_arr = arr([rot_x, rot_y]).T
    start_tc = tuple(all_coords_rot_arr[0])
    start_coord = tuple(all_coords_rot_arr[1])
    end_tc = tuple(all_coords_rot_arr[2])
    end_coord = tuple(all_coords_rot_arr[3])
    start_direction -= rot_ang
    end_direction -= rot_ang

    def diagonal(end_tc, turn_radius):
        mid_point = end_tc[0] / 2
        if turn_radius / mid_point > 1 or turn_radius / mid_point < -1:
            return (0, 0), (0, 0), 0, 0
        tc2tl_ang = np.rad2deg(np.arccos(turn_radius / mid_point))
        tl_srt = (np.cos(np.deg2rad(tc2tl_ang)) * turn_radius, np.sin(np.deg2rad(tc2tl_ang)) * turn_radius)
        tl_end = tuple(arr(end_tc) - arr(tl_srt))
        line_len = np.hypot(tl_end[0] - tl_srt[0], tl_end[1] - tl_srt[1])
        return tl_srt, tl_end, tc2tl_ang - 90, line_len

    def parralell(end_tc, turn_radius):
        tl_srt = (0, turn_radius)
        tl_end = (end_tc[0], turn_radius)
        return tl_srt, tl_end, 0, end_tc[0]

    if start_direction_is_cw and end_direction_is_cw:
        tl_srt, tl_end, line_ang, line_len = parralell(end_tc, turn_radius)

    elif start_direction_is_cw and not end_direction_is_cw:
        tl_srt, tl_end, line_ang, line_len = diagonal(end_tc, turn_radius)

    elif not start_direction_is_cw and end_direction_is_cw:
        tl_srt, tl_end, line_ang, line_len = diagonal(end_tc, turn_radius)
        tl_srt = (tl_srt[0], tl_srt[1] * -1)
        tl_end = (tl_end[0], tl_end[1] * -1)
        line_ang *= -1

    elif not start_direction_is_cw and not end_direction_is_cw:
        tl_srt, tl_end, line_ang, line_len = parralell(end_tc, turn_radius)
        tl_srt = (tl_srt[0], tl_srt[1] * -1)
        tl_end = (tl_end[0], tl_end[1] * -1)

    if start_direction_is_cw:
        start_direction_angle_from_turn_centre_to_tangent_point = less_360(start_direction + 90)
        line_ang_srt_angle_from_turn_centre_to_tangent_point = less_360(line_ang + 90)
    else:
        start_direction_angle_from_turn_centre_to_tangent_point = less_360(start_direction - 90)
        line_ang_srt_angle_from_turn_centre_to_tangent_point = less_360(line_ang - 90)
    if end_direction_is_cw:
        line_ang_end_angle_from_turn_centre_to_tangent_point = less_360(line_ang + 90)
        end_direction_angle_from_turn_centre_to_tangent_point = less_360(end_direction + 90)
    else:
        line_ang_end_angle_from_turn_centre_to_tangent_point = less_360(line_ang - 90)
        end_direction_angle_from_turn_centre_to_tangent_point = less_360(end_direction - 90)

    if not start_direction_is_cw:
        srt_turn = line_ang_srt_angle_from_turn_centre_to_tangent_point - \
                   start_direction_angle_from_turn_centre_to_tangent_point
    else:
        srt_turn = start_direction_angle_from_turn_centre_to_tangent_point - \
                   line_ang_srt_angle_from_turn_centre_to_tangent_point
    if not end_direction_is_cw:
        end_turn = end_direction_angle_from_turn_centre_to_tangent_point - \
                   line_ang_end_angle_from_turn_centre_to_tangent_point
    else:
        end_turn = line_ang_end_angle_from_turn_centre_to_tangent_point - \
                   end_direction_angle_from_turn_centre_to_tangent_point

    srt_turn = round(srt_turn, 3)
    end_turn = round(end_turn, 3)
    srt_turn -= np.trunc(srt_turn / 180) * 360
    end_turn -= np.trunc(end_turn / 180) * 360
    if srt_turn < 0: srt_turn += 360
    if end_turn < 0: end_turn += 360
    if start_direction_is_cw:
        srt_turn *= -1
    if end_direction_is_cw:
        end_turn *= -1

    srt_turn_len = abs(np.deg2rad(srt_turn) * turn_radius)
    end_turn_len = abs(np.deg2rad(end_turn) * turn_radius)
    length = srt_turn_len + line_len + end_turn_len
    plot_here = False
    if plot_here:
        from matplotlib.patches import Circle, Arc
        fig, ax = plt.subplots()
        plt.axis('equal')
        turn_name = str(turn_counter) + '.' + str(turn_option)
        ax.title.set_text(turn_name)
        dx = np.cos(np.deg2rad(start_direction + 180)) * turn_diameter
        dy = np.sin(np.deg2rad(start_direction + 180)) * turn_diameter
        liner, = ax.plot([start_coord[0], start_coord[0] + dx], [start_coord[1], start_coord[1] + dy], alpha=0.5)
        ax.plot(start_coord[0] + dx, start_coord[1] + dy, 'X', color=liner.get_color(), ms=6, alpha=0.5)
        ax.plot(*start_coord, '^', color=liner.get_color(), ms=6, alpha=0.5)
        dx = np.cos(np.deg2rad(end_direction)) * turn_diameter
        dy = np.sin(np.deg2rad(end_direction)) * turn_diameter
        liner, = ax.plot([end_coord[0], end_coord[0] + dx], [end_coord[1], end_coord[1] + dy], alpha=0.5)
        ax.plot(end_coord[0] + dx, end_coord[1] + dy, '^', color=liner.get_color(), ms=6, alpha=0.5)
        ax.plot(*end_coord, 'X', color=liner.get_color(), ms=6, alpha=0.5)
        liner, = ax.plot([tl_srt[0], tl_end[0]], [tl_srt[1], tl_end[1]], alpha=0.5)
        ax.plot(*tl_srt, 'X', color=liner.get_color(), ms=6, alpha=0.5)
        ax.plot(*tl_end, '^', color=liner.get_color(), ms=6, alpha=0.5)
        # ax.add_patch(Circle(start_tc, turn_radius, edgecolor='k', facecolor='none'))
        # ax.add_patch(Circle(end_tc, turn_radius, edgecolor='k', facecolor='none'))
        if start_direction_is_cw:
            plot_arc_ang_1 = line_ang_srt_angle_from_turn_centre_to_tangent_point
            plot_arc_ang_2 = start_direction_angle_from_turn_centre_to_tangent_point
        else:
            plot_arc_ang_1 = start_direction_angle_from_turn_centre_to_tangent_point
            plot_arc_ang_2 = line_ang_srt_angle_from_turn_centre_to_tangent_point
        if end_direction_is_cw:
            plot_arc_ang_3 = end_direction_angle_from_turn_centre_to_tangent_point
            plot_arc_ang_4 = line_ang_end_angle_from_turn_centre_to_tangent_point
        else:
            plot_arc_ang_3 = line_ang_end_angle_from_turn_centre_to_tangent_point
            plot_arc_ang_4 = end_direction_angle_from_turn_centre_to_tangent_point

        ax.add_patch(Arc(start_tc, turn_radius * 2, turn_radius * 2,
                         theta1=plot_arc_ang_1, theta2=plot_arc_ang_2,
                         edgecolor='k', facecolor='none'))
        ax.add_patch(Arc(end_tc, turn_radius * 2, turn_radius * 2,
                         theta1=plot_arc_ang_3, theta2=plot_arc_ang_4,
                         edgecolor='k', facecolor='none'))
        plt.show()
    all_coords_arr = arr([tl_srt, tl_end])
    c, s = np.cos(np.deg2rad(-rot_ang)), np.sin(np.deg2rad(-rot_ang))
    rot_x = c * all_coords_arr.T[0] + s * all_coords_arr.T[1]
    rot_y = -s * all_coords_arr.T[0] + c * all_coords_arr.T[1]
    all_coords_rot_arr = arr([rot_x, rot_y]).T
    tl_srt_unrot = tuple(all_coords_rot_arr[0])
    tl_end_unrot = tuple(all_coords_rot_arr[1])
    tl_srt_unnormed = tuple(arr(norming_coord) + arr(tl_srt_unrot))
    tl_end_unnormed = tuple(arr(norming_coord) + arr(tl_end_unrot))
    return length, tl_srt_unnormed, tl_end_unnormed, srt_turn, end_turn, line_len

def flt_end(utm_fly_list, start_coord, start_ang, end_coord,
                        turn_segment_length, og_turn_diameter, turn_diameter):
    left_tc, right_tc = get_turn_centres(start_coord, start_ang + 180, turn_diameter)
    tangent_point, turn_ang, turn_ang = choose_best_tangent_point(left_tc, right_tc, end_coord, turn_diameter,
                                                                  start_ang + 180, start_coord, flight_start=False)
    coord_arr, radius_big_enough = quantize_turn(start_coord, start_ang,
                                                 tangent_point, -turn_ang,
                                                 turn_segment_length, og_turn_diameter)
    if radius_big_enough:
        coord_list = coord_arr.tolist()
        utm_fly_list.extend(coord_list)
        utm_fly_list.append(end_coord)
    else:
        turn_diameter *= 1.2
        flt_end(utm_fly_list, start_coord, start_ang, end_coord, turn_segment_length,
                            og_turn_diameter, turn_diameter)

def flt_beginning(utm_fly_list, start_coord, end_coord, end_ang,
                              turn_segment_length, og_turn_diameter, turn_diameter):
    left_tc, right_tc = get_turn_centres(end_coord,end_ang,turn_diameter)
    tangent_point, tc, turn_ang = choose_best_tangent_point(left_tc, right_tc,
                                                            start_coord, turn_diameter,
                                                            end_ang, end_coord, flight_start=True)
    coord_arr, radius_big_enough = quantize_turn(end_coord, end_ang + 180,
                              tangent_point,
                              -turn_ang, turn_segment_length, og_turn_diameter)
    if radius_big_enough:
        coord_list = coord_arr.tolist()
        coord_list.reverse()
        utm_fly_list.extend(coord_list)
        utm_fly_list.append(end_coord)
    else:
        turn_diameter *= 1.2
        flt_beginning(utm_fly_list, start_coord, end_coord, end_ang, turn_segment_length,
                                  og_turn_diameter, turn_diameter)

def between_lines(utm_fly_list, start_coord, start_ang, end_coord, end_ang,
                              turn_segment_length, turn_diameter):
    #turn_diameter *= 8
    end_left_tc, end_right_tc = get_turn_centres(end_coord, end_ang, turn_diameter)
    start_left_tc, start_right_tc = get_turn_centres(start_coord, start_ang+180, turn_diameter)
    tc_list = [[start_left_tc, 1, end_left_tc, 0],
               [start_left_tc, 1, end_right_tc, 1],
               [start_right_tc, 0, end_left_tc, 0],
               [start_right_tc, 0, end_right_tc, 1]]
    tl_list = []
    for ind, pair in enumerate(tc_list):
        stuff = get_tangents_for_2_circs(start_tc=pair[0],
                                      start_direction_is_cw=pair[1],
                                      start_direction = start_ang,
                                      start_coord = start_coord,
                                      end_tc=pair[2],
                                      end_direction_is_cw=pair[3],
                                      end_direction = end_ang,
                                      end_coord = end_coord,
                                      turn_radius=turn_diameter / 2,
                                      turn_option=ind)
        tl_list.append(stuff)
    tl_arr = arr(tl_list,dtype=object)
    #print(tl_arr.T[0])
    ind_shortest = np.argmin(tl_arr.T[0])
    shortest_turn = tl_arr[ind_shortest]
    tangent_line_start = shortest_turn[1]
    tangent_line_end = shortest_turn[2]
    start_turn_ang = shortest_turn[3]
    end_turn_ang = shortest_turn[4]
    tangent_line_len = shortest_turn[5]
    #print('start_turn_ang', tl_arr[:, 3],
    #      'end_turn_ang', tl_arr[:, 4],
    #      'tangent_line_len', tl_arr[:, 5])
    coord_arr, radius_big_enough  = quantize_turn(start_coord, start_ang,
                              tangent_line_start,
                              start_turn_ang, turn_segment_length, turn_diameter)
    coord_list_start = coord_arr.tolist()
    coord_arr, radius_big_enough  = quantize_turn(end_coord, end_ang+180,
                              tangent_line_end,
                              -end_turn_ang, turn_segment_length, turn_diameter)
    coord_list_end = coord_arr.tolist()
    coord_list_end.reverse()
    plot_here = False
    if plot_here:
        fig, ax = plt.subplots()
        plt.axis('equal')
        ax.plot(*start_coord, 'o')
        ax.plot(*end_coord, 'o')
        ax.plot(*arr(coord_list_end).T, '-x')
        plt.show()
    utm_fly_list.extend(coord_list_start)
    utm_fly_list.extend(coord_list_end)
    utm_fly_list.append(end_coord)