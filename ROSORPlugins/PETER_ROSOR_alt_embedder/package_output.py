from pathlib import Path
import shutil
import json
import numpy as np
import os

def lat_lon_UAValt_to_mp_wp(output_file_path,
                            lats, lons, UAValtAsls):
    if len(lats) > 600:
        raise ValueError("can't do more than 600 mission planner waypoints (650 with a safe buffer)")

    # 1) strip off .kmz / .kml
    if output_file_path.endswith('.kmz') or output_file_path.endswith('.kml'):
        output_file_path = output_file_path[:-4]

    # 2) split into dir + base
    dirpath, base = os.path.split(output_file_path)

    # 3) remove 'RTH' and anything after it
    if 'RTH' in base:
        base = base.split('RTH', 1)[0]

    # 4) append the waypoint count
    base = f"{base}len_{len(lats)}"

    # 5) rebuild full path with .waypoints
    output_file_path = os.path.join(dirpath, base + '.waypoints')

    # make sure directory exists
    os.makedirs(dirpath, exist_ok=True)

    with open(output_file_path, 'w') as file:
        file.write('QGC WPL 110\n')
        # alt_mode_num 0-abs 3-rel 10-terrain
        alt_mode_num = 0
        for i, (lat, lon, alt) in enumerate(zip(lats, lons, UAValtAsls)):
            if i == 0:
                line = (
                    f'{i}\t1\t0\t16\t0\t0\t0\t0\t{lat}\t{lon}\t410\t1\n'
                    f'{i+1}\t0\t{alt_mode_num}\t16\t0\t0\t0\t0\t{lat}\t{lon}\t{alt}\t1\n'
                )
            else:
                line = (
                    f'{i+1}\t0\t{alt_mode_num}\t16\t0\t0\t0\t0\t'
                    f'{lat}\t{lon}\t{alt}\t1\n'
                )
            file.write(line)

    print('output_to')
    print(output_file_path)


def lat_lon_UAValt_to_altaX_QGC_Plan(output_file_path,
                                     lats, lons, UAValtAsls, heading,
                                     cruiseSpeed=5,
                                     firmwareType=12,
                                     hoverSpeed=5,
                                     vehicleType=2):
    """
    Produce a .plan almost identical in structure to your sample.

    Parameters
    ----------
    output_file_path : str
        Path to write the .plan file (will be given .plan extension).
    lats, lons : sequence of float
    UAValtAsls : sequence of float
    heading : sequence of float
        Per-waypoint yaw, in degrees (clockwise from north).
    """
    # 1) Normalize extension & ensure dir exists
    if output_file_path.endswith(('.kmz', '.kml')):
        output_file_path = output_file_path[:-4]
    if not output_file_path.endswith('.plan'):
        output_file_path += '.plan'
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

    # 2) Build base plan dict with insertion order matching your sample
    plan = {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": cruiseSpeed,
            "firmwareType": firmwareType,
            "hoverSpeed": hoverSpeed,
            "items": [],
            "plannedHomePosition": [float(lats[0]), float(lons[0]), float(UAValtAsls[0])],
            "vehicleType": vehicleType,
            "version": 2
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1
    }

    heading_cw_of_Ns_off_by_one = (heading - 90) * -1

    # 3) Compute yaw list so first WP has yaw=0
    yaws = np.concatenate(([0.0], np.array(heading_cw_of_Ns_off_by_one, float)[:-1]))

    # 4) Populate each SimpleItem
    for idx, (lat, lon, alt, yaw_deg) in enumerate(zip(lats, lons, UAValtAsls, yaws), start=1):
        item = {
            "AMSLAltAboveTerrain": None,
            "Altitude": float(alt),
            "AltitudeMode": 2,
            "autoContinue": True,
            "command": 16,
            "doJumpId": idx,
            "frame": 0,
            "params": [
                0,  # hold time
                0,  # acceptance radius
                0,  # pass through
                float(yaw_deg),  # yaw at WP
                float(lat),
                float(lon),
                float(alt)
            ],
            "type": "SimpleItem"
        }
        plan["mission"]["items"].append(item)

    # 5) Write JSON
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(plan, f, indent=4)

    print(f"Wrote QGC .plan → {output_file_path}")

def lat_lon_UAValt_to_PX4_wp(output_file_path,
                            lats, lons, UAValtAsls, heading):

    heading_cw_of_Ns_off_by_one = (heading - 90) * -1

    heading_cw_of_Ns = np.concatenate(([0], heading_cw_of_Ns_off_by_one[:-1]))

    if len(lats) > 600:
        raise ValueError("can't do more than 600 mission planner waypoints (650 with a safe buffer)")

    # 1) strip off .kmz / .kml
    if output_file_path.endswith('.kmz') or output_file_path.endswith('.kml'):
        output_file_path = output_file_path[:-4]

    # 2) split into dir + base
    dirpath, base = os.path.split(output_file_path)

    # 3) DO NOT remove 'RTH' and anything after it
    #if 'RTH' in base:
    #    base = base.split('RTH', 1)[0]

    # add under_score:
    base+='_'

    # 4) append the waypoint count
    base = f"{base}len_{len(lats)}"

    # 5) rebuild full path with .waypoints
    output_file_path = os.path.join(dirpath, base + '.waypoints')

    # make sure directory exists
    os.makedirs(dirpath, exist_ok=True)

    with open(output_file_path, 'w') as file:
        file.write('QGC WPL 110\n')
        # alt_mode_num 0-abs 3-rel 10-terrain
        alt_mode_num = 0
        for i, (lat, lon, alt, heading_cw_of_N) in enumerate(zip(lats, lons, UAValtAsls, heading_cw_of_Ns)):
            if i == 0:
                line = (
                    f'{i}\t1\t0\t16\t0\t0\t0\t0\t{lat}\t{lon}\t410\t1\n'
                    f'{i+1}\t0\t{alt_mode_num}\t16\t0\t0\t0\t{heading_cw_of_N}\t{lat}\t{lon}\t{alt}\t1\n'
                )
            else:
                line = (
                    f'{i+1}\t0\t{alt_mode_num}\t16\t0\t0\t0\t{heading_cw_of_N}\t'
                    f'{lat}\t{lon}\t{alt}\t1\n'
                )
            file.write(line)

    print('output_to')
    print(output_file_path)


def lat_lon_UAValt_turnRad_to_DJI_wp_kmz(lat, lon,
                                         settings_description,
                                         UAValtAsl, UAValtEll,
                                         turnRad,
                                         output_file_path,
                                         speed,
                                         keep_temp_kml=False):
    kml_text = f'''
                <kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.0">
               <Document>
                  <description>{settings_description}</description>
                  <wpml:createTime>1690230952508</wpml:createTime>
                  <wpml:updateTime>1690230952508</wpml:updateTime>
                  <wpml:missionConfig>
                     <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>
                     <wpml:finishAction>noAction</wpml:finishAction>
                     <wpml:exitOnRCLost>goContinue</wpml:exitOnRCLost>
                     <wpml:takeOffSecurityHeight>100</wpml:takeOffSecurityHeight>
                     <wpml:globalTransitionalSpeed>10</wpml:globalTransitionalSpeed>
                     <wpml:droneInfo>
                        <wpml:droneEnumValue>89</wpml:droneEnumValue>
                        <wpml:droneSubEnumValue>0</wpml:droneSubEnumValue>
                     </wpml:droneInfo>
                  </wpml:missionConfig>
                  <Folder>
                     <wpml:templateType>waypoint</wpml:templateType>
                     <wpml:templateId>0</wpml:templateId>
                     <wpml:waylineCoordinateSysParam>
                        <wpml:coordinateMode>WGS84</wpml:coordinateMode>
                        <wpml:heightMode>EGM96</wpml:heightMode>
                     </wpml:waylineCoordinateSysParam>
                     <wpml:autoFlightSpeed>{speed}</wpml:autoFlightSpeed>
                     <wpml:globalHeight>0.0</wpml:globalHeight>
                     <wpml:caliFlightEnable>0</wpml:caliFlightEnable>
                     <wpml:gimbalPitchMode>manual</wpml:gimbalPitchMode>
                     <wpml:globalWaypointHeadingParam>
                        <wpml:waypointHeadingMode>followWayline</wpml:waypointHeadingMode>
                        <wpml:waypointHeadingAngle>0.0</wpml:waypointHeadingAngle>
                     </wpml:globalWaypointHeadingParam>
                     <wpml:globalWaypointTurnMode>coordinateTurn</wpml:globalWaypointTurnMode>
                     <wpml:globalUseStraightLine>1</wpml:globalUseStraightLine>'''
    for wp_index, (_lat, _lon, _UAValtAsl, _UAValtEll, _turnRad) in enumerate(zip(lat, lon, UAValtAsl, UAValtEll, turnRad)):
        kml_text +=f''' 
                            <Placemark>
                            <Point>
                               <coordinates>{round(_lon, 8)},{round(_lat, 8)}</coordinates>
                            </Point>
                            <wpml:index>{wp_index+1}</wpml:index>
                            <wpml:ellipsoidHeight>{round(_UAValtEll, 8)}</wpml:ellipsoidHeight>
                            <wpml:height>{round(_UAValtAsl, 8)}</wpml:height>
                            <wpml:useGlobalSpeed>1</wpml:useGlobalSpeed>
                            <wpml:waypointHeadingParam>
                               <wpml:waypointHeadingMode>followWayline</wpml:waypointHeadingMode>
                               <wpml:waypointHeadingAngle>0.0</wpml:waypointHeadingAngle>
                               <wpml:waypointHeadingPathMode>followBadArc</wpml:waypointHeadingPathMode>
                            </wpml:waypointHeadingParam>
                            <wpml:waypointTurnParam>
                               <wpml:waypointTurnMode>coordinateTurn</wpml:waypointTurnMode>
                               <wpml:waypointTurnDampingDist>{_turnRad}</wpml:waypointTurnDampingDist>
                            </wpml:waypointTurnParam>
                            <wpml:useGlobalHeight>0</wpml:useGlobalHeight>
                            <wpml:useStraightLine>1</wpml:useStraightLine>
                            <wpml:actionGroup>
                               <wpml:actionGroupId>0</wpml:actionGroupId>
                               <wpml:actionGroupStartIndex>0</wpml:actionGroupStartIndex>
                               <wpml:actionGroupEndIndex>0</wpml:actionGroupEndIndex>
                               <wpml:actionGroupMode>sequence</wpml:actionGroupMode>
                               <wpml:actionTrigger>
                                  <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>
                               </wpml:actionTrigger>
                               <wpml:action>
                                  <wpml:actionId>0</wpml:actionId>
                                  <wpml:actionActuatorFunc>recordPointCloud</wpml:actionActuatorFunc>
                                  <wpml:actionActuatorFuncParam>
                                     <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
                                     <wpml:recordPointCloudOperate>startRecord</wpml:recordPointCloudOperate>
                                  </wpml:actionActuatorFuncParam>
                               </wpml:action>
                            </wpml:actionGroup>
                         </Placemark>'''
    kml_text +='''
                 </Folder>
               </Document>
            </kml>
            '''


    base_file_path = Path(output_file_path).parent
    new_temp_dir_path_1 = os.path.join(base_file_path, 'pyotyrs_temp_will_be_deleted')
    if os.path.exists(new_temp_dir_path_1):
        shutil.rmtree(new_temp_dir_path_1)
    os.makedirs(new_temp_dir_path_1, exist_ok=True)
    new_temp_dir_path_2 = os.path.join(new_temp_dir_path_1, 'wpmz')
    os.mkdir(new_temp_dir_path_2)
    out_file_path = os.path.join(new_temp_dir_path_2, 'template.kml')
    # out_file
    f = open(out_file_path, "w")
    f.write(kml_text)
    f.close()
    temp_zip_path = os.path.join(base_file_path, 'pyotyrs_temp_zip_will_be_deleted')
    shutil.make_archive(temp_zip_path, 'zip', new_temp_dir_path_1)
    if not keep_temp_kml:
        shutil.rmtree(new_temp_dir_path_1)
    try:
        os.rename(temp_zip_path + '.zip', output_file_path)
    except FileExistsError:
        os.remove(output_file_path)
        os.rename(temp_zip_path + '.zip', output_file_path)
    #print('out_text')
    #print(kml_text)
    print('output_to')
    print(output_file_path)


def lat_lon_to_DJI_with_P1_corridor_kmz(lat, lon,
                                        output_file_path,
                                        speed,
                                        keep_temp_kml=False):
    kml_text = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.4">
  <Document>
    <wpml:createTime>1713022536988</wpml:createTime>
    <wpml:updateTime>1713022750934</wpml:updateTime>
    <wpml:missionConfig>
      <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>
      <wpml:finishAction>noAction</wpml:finishAction>
      <wpml:exitOnRCLost>goContinue</wpml:exitOnRCLost>
      <wpml:takeOffSecurityHeight>20</wpml:takeOffSecurityHeight>
      <wpml:globalTransitionalSpeed>15</wpml:globalTransitionalSpeed>
      <wpml:droneInfo>
        <wpml:droneEnumValue>60</wpml:droneEnumValue>
        <wpml:droneSubEnumValue>0</wpml:droneSubEnumValue>
      </wpml:droneInfo>
      <wpml:payloadInfo>
        <wpml:payloadEnumValue>50</wpml:payloadEnumValue>
        <wpml:payloadSubEnumValue>0</wpml:payloadSubEnumValue>
        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
      </wpml:payloadInfo>
    </wpml:missionConfig>
    <Folder>
      <wpml:templateType>mappingStrip</wpml:templateType>
      <wpml:templateId>0</wpml:templateId>
      <wpml:waylineCoordinateSysParam>
        <wpml:coordinateMode>WGS84</wpml:coordinateMode>
        <wpml:heightMode>relativeToStartPoint</wpml:heightMode>
        <wpml:globalShootHeight>500</wpml:globalShootHeight>
      </wpml:waylineCoordinateSysParam>
      <wpml:autoFlightSpeed>{speed}</wpml:autoFlightSpeed>
      <Placemark>
        <wpml:caliFlightEnable>0</wpml:caliFlightEnable>
        <wpml:shootType>time</wpml:shootType>
        <wpml:direction>0</wpml:direction>
        <wpml:singleLineEnable>1</wpml:singleLineEnable>
        <wpml:cuttingDistance>630</wpml:cuttingDistance>
        <wpml:boundaryOptimEnable>0</wpml:boundaryOptimEnable>
        <wpml:leftExtend>20</wpml:leftExtend>
        <wpml:rightExtend>20</wpml:rightExtend>
        <wpml:includeCenterEnable>0</wpml:includeCenterEnable>
        <wpml:overlap>
          <wpml:orthoLidarOverlapH>80</wpml:orthoLidarOverlapH>
          <wpml:orthoLidarOverlapW>70</wpml:orthoLidarOverlapW>
          <wpml:orthoCameraOverlapH>80</wpml:orthoCameraOverlapH>
          <wpml:orthoCameraOverlapW>70</wpml:orthoCameraOverlapW>
        </wpml:overlap>
        <LineString>
          <coordinates>'''
    for wp_index, (_lat, _lon) in enumerate(zip(lat, lon)):
        kml_text +=f'\n            {round(_lon,8)},{round(_lat,8)},0'

    kml_text += f'''
          </coordinates>
        </LineString>
        <wpml:ellipsoidHeight>500</wpml:ellipsoidHeight>
        <wpml:height>500</wpml:height>
      </Placemark>
      <wpml:payloadParam>
        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
        <wpml:focusMode>firstPoint</wpml:focusMode>
        <wpml:dewarpingEnable>0</wpml:dewarpingEnable>
        <wpml:returnMode>singleReturnStrongest</wpml:returnMode>
        <wpml:samplingRate>240000</wpml:samplingRate>
        <wpml:scanningMode>repetitive</wpml:scanningMode>
        <wpml:modelColoringEnable>1</wpml:modelColoringEnable>
      </wpml:payloadParam>
    </Folder>
  </Document>
</kml>'''

    base_file_path = Path(output_file_path).parent
    out_file = Path(output_file_path).name
    new_temp_dir_path_1 = os.path.join(base_file_path, 'pyotyrs_temp_will_be_deleted')
    if os.path.exists(new_temp_dir_path_1):
        shutil.rmtree(new_temp_dir_path_1)
    os.mkdir(new_temp_dir_path_1)
    new_temp_dir_path_2 = os.path.join(new_temp_dir_path_1, 'wpmz')
    os.mkdir(new_temp_dir_path_2)
    out_file_path = os.path.join(new_temp_dir_path_2, 'template.kml')
    # out_file
    f = open(out_file_path, "w")
    f.write(kml_text)
    f.close()
    temp_zip_path = os.path.join(base_file_path, 'pyotyrs_temp_zip_will_be_deleted')
    shutil.make_archive(temp_zip_path, 'zip', new_temp_dir_path_1)
    if not keep_temp_kml:
        shutil.rmtree(new_temp_dir_path_1)
    try:
        os.rename(temp_zip_path + '.zip', output_file_path)
    except FileExistsError:
        os.remove(output_file_path)
        os.rename(temp_zip_path + '.zip', output_file_path)
    #print('out_text')
    #print(kml_text)
    print('output_to')
    print(output_file_path)



def lat_lon_UAValt_turnRad_heading_to_DJI_with_P1_wp_kmz(lat, lon,
                                                         UAValtAsl, UAValtEll,
                                                         turnRad,
                                                         output_file_path,
                                                         heading,
                                                         speed,
                                                         is_midline,
                                                         keep_temp_kml=False):
    heading_ccw_of_N = (heading-90)*-1
    end_index = len(lat) - 1
    kml_text = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.4">
  <Document>
    <wpml:createTime>1712685674624</wpml:createTime>
    <wpml:updateTime>1712694376165</wpml:updateTime>
    <wpml:missionConfig>
      <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>
      <wpml:finishAction>noAction</wpml:finishAction>
      <wpml:exitOnRCLost>goContinue</wpml:exitOnRCLost>
      <wpml:takeOffSecurityHeight>100</wpml:takeOffSecurityHeight>
      <wpml:globalTransitionalSpeed>15</wpml:globalTransitionalSpeed>
      <wpml:droneInfo>
        <wpml:droneEnumValue>89</wpml:droneEnumValue>
        <wpml:droneSubEnumValue>0</wpml:droneSubEnumValue>
      </wpml:droneInfo>
      <wpml:payloadInfo>
        <wpml:payloadEnumValue>50</wpml:payloadEnumValue>
        <wpml:payloadSubEnumValue>0</wpml:payloadSubEnumValue>
        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
      </wpml:payloadInfo>
    </wpml:missionConfig>
    <Folder>
      <wpml:templateType>waypoint</wpml:templateType>
      <wpml:templateId>0</wpml:templateId>
      <wpml:waylineCoordinateSysParam>
        <wpml:coordinateMode>WGS84</wpml:coordinateMode>
        <wpml:heightMode>EGM96</wpml:heightMode>
        <wpml:positioningType>GPS</wpml:positioningType>
      </wpml:waylineCoordinateSysParam>
      <wpml:autoFlightSpeed>{speed}</wpml:autoFlightSpeed>
      <wpml:globalHeight>0</wpml:globalHeight>
      <wpml:caliFlightEnable>0</wpml:caliFlightEnable>
      <wpml:gimbalPitchMode>usePointSetting</wpml:gimbalPitchMode>
      <wpml:globalWaypointHeadingParam>
        <wpml:waypointHeadingMode>followWayline</wpml:waypointHeadingMode>
        <wpml:waypointHeadingAngle>0</wpml:waypointHeadingAngle>
        <wpml:waypointPoiPoint>0.000000,0.000000,0.000000</wpml:waypointPoiPoint>
        <wpml:waypointHeadingPoiIndex>0</wpml:waypointHeadingPoiIndex>
      </wpml:globalWaypointHeadingParam>
      <wpml:globalWaypointTurnMode>coordinateTurn</wpml:globalWaypointTurnMode>
      <wpml:globalUseStraightLine>1</wpml:globalUseStraightLine>'''
    for wp_index, (_lat, _lon, _UAValtAsl, _UAValtEll, _turnRad, _heading_ccw_of_N, _is_midline) in \
            enumerate(zip(lat, lon, UAValtAsl, UAValtEll, turnRad, heading_ccw_of_N, is_midline)):
        is_first_waypoint, is_last_waypoint = (wp_index == 0), (wp_index == end_index)
        kml_text +=f''' 
      <Placemark>
        <Point>
          <coordinates>
            {round(_lon, 8)},{round(_lat, 8)}
          </coordinates>
        </Point>
        <wpml:index>{wp_index}</wpml:index>
        <wpml:ellipsoidHeight>{round(_UAValtEll, 8)}</wpml:ellipsoidHeight>
        <wpml:height>{round(_UAValtAsl, 8)}</wpml:height>
        <wpml:waypointHeadingParam>
          <wpml:waypointHeadingMode>followWayline</wpml:waypointHeadingMode>
          <wpml:waypointHeadingAngle>0</wpml:waypointHeadingAngle>
          <wpml:waypointPoiPoint>0.000000,0.000000,0.000000</wpml:waypointPoiPoint>
          <wpml:waypointHeadingPathMode>followBadArc</wpml:waypointHeadingPathMode>
          <wpml:waypointHeadingPoiIndex>0</wpml:waypointHeadingPoiIndex>
        </wpml:waypointHeadingParam>
        <wpml:waypointTurnParam>
          <wpml:waypointTurnMode>coordinateTurn</wpml:waypointTurnMode>
          <wpml:waypointTurnDampingDist>{_turnRad}</wpml:waypointTurnDampingDist>
        </wpml:waypointTurnParam>
        <wpml:useGlobalSpeed>1</wpml:useGlobalSpeed>'''
        if is_last_waypoint:
            kml_text += f'''
        <wpml:gimbalPitchAngle>0</wpml:gimbalPitchAngle>'''
        else:
            kml_text += f'''
        <wpml:gimbalPitchAngle>-90</wpml:gimbalPitchAngle>'''
        kml_text += f'''
        <wpml:useStraightLine>1</wpml:useStraightLine>'''
        if is_first_waypoint:
            kml_text += f'''
        <wpml:actionGroup>
          <wpml:actionGroupId>{wp_index}</wpml:actionGroupId>
          <wpml:actionGroupStartIndex>{wp_index}</wpml:actionGroupStartIndex>
          <wpml:actionGroupEndIndex>{wp_index}</wpml:actionGroupEndIndex>
          <wpml:actionGroupMode>sequence</wpml:actionGroupMode>
          <wpml:actionTrigger>
            <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>
          </wpml:actionTrigger>
          <wpml:action>
            <wpml:actionId>0</wpml:actionId>
            <wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>
            <wpml:actionActuatorFuncParam>
              <wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode>
              <wpml:gimbalPitchRotateEnable>0</wpml:gimbalPitchRotateEnable>
              <wpml:gimbalPitchRotateAngle>0</wpml:gimbalPitchRotateAngle>
              <wpml:gimbalRollRotateEnable>0</wpml:gimbalRollRotateEnable>
              <wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>
              <wpml:gimbalYawRotateEnable>1</wpml:gimbalYawRotateEnable>
              <wpml:gimbalYawRotateAngle>{round(_heading_ccw_of_N)}</wpml:gimbalYawRotateAngle>
              <wpml:gimbalRotateTimeEnable>0</wpml:gimbalRotateTimeEnable>
              <wpml:gimbalRotateTime>0</wpml:gimbalRotateTime>
              <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
            </wpml:actionActuatorFuncParam>
          </wpml:action>
        </wpml:actionGroup>
        <wpml:actionGroup>
          <wpml:actionGroupId>{wp_index}</wpml:actionGroupId>
          <wpml:actionGroupStartIndex>{wp_index}</wpml:actionGroupStartIndex>
          <wpml:actionGroupEndIndex>{end_index}</wpml:actionGroupEndIndex>
          <wpml:actionGroupMode>sequence</wpml:actionGroupMode>
          <wpml:actionTrigger>
            <wpml:actionTriggerType>multipleTiming</wpml:actionTriggerType>
            <wpml:actionTriggerParam>1</wpml:actionTriggerParam>
          </wpml:actionTrigger>
          <wpml:action>
            <wpml:actionId>0</wpml:actionId>
            <wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc>
            <wpml:actionActuatorFuncParam>
              <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
              <wpml:useGlobalPayloadLensIndex>0</wpml:useGlobalPayloadLensIndex>
            </wpml:actionActuatorFuncParam>
          </wpml:action>
        </wpml:actionGroup>'''
        elif _is_midline:
            kml_text += f'''
        <wpml:actionGroup>
          <wpml:actionGroupId>{wp_index}</wpml:actionGroupId>
          <wpml:actionGroupStartIndex>{wp_index}</wpml:actionGroupStartIndex>
          <wpml:actionGroupEndIndex>{wp_index}</wpml:actionGroupEndIndex>
          <wpml:actionGroupMode>sequence</wpml:actionGroupMode>
          <wpml:actionTrigger>
            <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>
          </wpml:actionTrigger>
          <wpml:action>
            <wpml:actionId>0</wpml:actionId>
            <wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>
            <wpml:actionActuatorFuncParam>
              <wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode>
              <wpml:gimbalPitchRotateEnable>0</wpml:gimbalPitchRotateEnable>
              <wpml:gimbalPitchRotateAngle>0</wpml:gimbalPitchRotateAngle>
              <wpml:gimbalRollRotateEnable>0</wpml:gimbalRollRotateEnable>
              <wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>
              <wpml:gimbalYawRotateEnable>1</wpml:gimbalYawRotateEnable>
              <wpml:gimbalYawRotateAngle>{round(_heading_ccw_of_N)}</wpml:gimbalYawRotateAngle>
              <wpml:gimbalRotateTimeEnable>0</wpml:gimbalRotateTimeEnable>
              <wpml:gimbalRotateTime>0</wpml:gimbalRotateTime>
              <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
            </wpml:actionActuatorFuncParam>
          </wpml:action>
        </wpml:actionGroup>'''

        kml_text += f'''
        <wpml:isRisky>0</wpml:isRisky>
      </Placemark>'''
    kml_text +='''
      <wpml:payloadParam>
        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
        <wpml:meteringMode>average</wpml:meteringMode>
        <wpml:dewarpingEnable>0</wpml:dewarpingEnable>
        <wpml:returnMode>singleReturnFirst</wpml:returnMode>
        <wpml:samplingRate>240000</wpml:samplingRate>
        <wpml:scanningMode>repetitive</wpml:scanningMode>
        <wpml:modelColoringEnable>0</wpml:modelColoringEnable>
      </wpml:payloadParam>
    </Folder>
  </Document>
</kml>'''

    base_file_path = Path(output_file_path).parent
    new_temp_dir_path_1 = os.path.join(base_file_path, 'pyotyrs_temp_will_be_deleted')
    if os.path.exists(new_temp_dir_path_1):
        shutil.rmtree(new_temp_dir_path_1)
    os.makedirs(new_temp_dir_path_1, exist_ok=True)
    new_temp_dir_path_2 = os.path.join(new_temp_dir_path_1, 'wpmz')
    os.mkdir(new_temp_dir_path_2)
    out_file_path = os.path.join(new_temp_dir_path_2, 'template.kml')
    # out_file
    f = open(out_file_path, "w")
    f.write(kml_text)
    f.close()
    temp_zip_path = os.path.join(base_file_path, 'pyotyrs_temp_zip_will_be_deleted')
    shutil.make_archive(temp_zip_path, 'zip', new_temp_dir_path_1)
    if not keep_temp_kml:
        shutil.rmtree(new_temp_dir_path_1)
    try:
        os.rename(temp_zip_path + '.zip', output_file_path)
    except FileExistsError:
        os.remove(output_file_path)
        os.rename(temp_zip_path + '.zip', output_file_path)
    #print('out_text')
    #print(kml_text)
    print('output_to')
    print(output_file_path)