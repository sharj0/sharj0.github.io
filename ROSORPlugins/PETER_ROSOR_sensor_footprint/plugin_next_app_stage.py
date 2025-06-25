'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
This is where the substance of the plugin begins. In main()
'''

from . import plugin_load_settings
from . import plugin_tools

import time
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from osgeo import osr, gdal
from shapely.geometry import Polygon, Point
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.tri import Triangulation

# QGIS imports (make sure this script runs in QGIS’s Python console)
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
)

import sys
import os
# IMPORT 3rd PARTY libraries
plugin_dir = os.path.dirname(os.path.realpath(__file__))
# Path to the subdirectory containing the external libraries
lib_dir = os.path.join(plugin_dir, 'plugin_3rd_party_libs')
# Add this directory to sys.path so Python knows where to find the external libraries
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
import trimesh

def main(settings_file_path):
    # load settings and allow for the re-naming of settings with a conversion step between the .json name and the internal code
    settings_dict = plugin_load_settings.run(settings_file_path)

    imu_file_path = settings_dict['Headwall Hyperspectral imu_gps.txt file']
    dsm_file_path = settings_dict['DEM or DSM file']
    data_collection_polygon = settings_dict['Data collection area polygon file']
    sub_sample_rate = settings_dict['Imu Data sub-sample rate']

    dsm_clip_buffer = settings_dict['DSM clip buffer']
    sensor_fov = settings_dict['Sensor Field of View']
    ''' ^ Swir 21.7 degs ^ '''
    ''' ^ Vnir 28 deegs ^ '''
    show_plot = settings_dict['Show plot']
    show_sensor_fov = settings_dict["Show the sensor's fov"]
    plot_arrow_len = settings_dict['Plotted arrow length']

    save_to_file = True

    settings_dict = None # don't use settings_dict from here on
    plot_3d_with_dsm(
        imu_path=imu_file_path,
        data_collection_polygon=data_collection_polygon,
        show_plot=show_plot,
        dsm_path=dsm_file_path,
        sub_sample_rate=sub_sample_rate,
        arrow_len=plot_arrow_len,
        fov=sensor_fov,
        dsm_clip_buffer=dsm_clip_buffer,
        show_sensor_fov=show_sensor_fov,
        save_to_file=save_to_file,
    )



def get_name_of_non_existing_output_file(base_filepath, additional_suffix='', new_extension=''):
    base, ext = os.path.splitext(base_filepath)
    if new_extension:
        ext = new_extension
    candidate = f"{base}{additional_suffix}{ext}"
    if not os.path.exists(candidate):
        return candidate
    version = 2
    while os.path.exists(f"{base}{additional_suffix}_v{version}{ext}"):
        version += 1
    return f"{base}{additional_suffix}_v{version}{ext}"

def is_qgis_desktop_running():
    return QgsApplication.instance().platform() == 'desktop'

def start_time():
    global _start_time
    _start_time = time.perf_counter()

def end_time():
    elapsed = time.perf_counter() - _start_time
    print(f"Took {elapsed:.2f} seconds")

def dir_ned_to_enu(v_ned):
    n, e, d = v_ned
    return np.array([e, n, -d])

def body_to_ned(v_b, roll, pitch, yaw):
    cx, sx = np.cos(roll), np.sin(roll)
    cy, sy = np.cos(pitch), np.sin(pitch)
    cz, sz = np.cos(yaw),   np.sin(yaw)
    Rx = np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    Ry = np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    Rz = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    return Rz @ (Ry @ (Rx @ v_b))

def raster_to_mesh(dsm_path, x_min, x_max, y_min, y_max):
    ds   = gdal.Open(dsm_path)
    band = ds.GetRasterBand(1)
    arr  = band.ReadAsArray()
    x0, pw, _, y0, _, ph = ds.GetGeoTransform()
    rows, cols = arr.shape
    xs_all = x0 + (np.arange(cols)+0.5)*pw
    ys_all = y0 + (np.arange(rows)+0.5)*ph
    ci = np.where((xs_all>=x_min)&(xs_all<=x_max))[0]
    ri = np.where((ys_all>=y_min)&(ys_all<=y_max))[0]
    if not len(ci) or not len(ri):
        return None, None, None
    c0, c1 = ci.min(), ci.max()+1
    r0, r1 = ri.min(), ri.max()+1
    Xc, Yc = np.meshgrid(xs_all[c0:c1], ys_all[r0:r1])
    return Xc, Yc, arr[r0:r1, c0:c1]

def plot_3d_with_dsm(
    imu_path,
    data_collection_polygon,
    show_plot=False,
    dsm_path=None,
    sub_sample_rate=100,
    arrow_len=5,
    fov=21.7,
    dsm_clip_buffer=120,
    show_sensor_fov=False,
    save_to_file=True
):
    start_time()

    # --- load and subsample IMU/GPS (lat,lon,Alt,Roll,Pitch,Yaw) ---
    df     = pd.read_csv(imu_path, sep='\t').iloc[::sub_sample_rate].reset_index(drop=True)
    alts   = df['Alt'].values - df['Geoid_Separation'].values
    lons   = df['Lon'].values
    lats   = df['Lat'].values
    rolls  = np.deg2rad(df['Roll'].values)
    pitches= np.deg2rad(df['Pitch'].values)
    yaws   = np.deg2rad(df['Yaw'].values)

    # --- segment the IMU track into flight_lines using the polygon ---
    poly_layer = QgsVectorLayer(data_collection_polygon, "data_poly", "ogr")
    if not poly_layer.isValid():
        print(f"ERROR: could not load polygon '{data_collection_polygon}'")
        return
    feats = list(poly_layer.getFeatures())
    if not feats:
        print("ERROR: no features in data collection polygon.")
        return
    poly_geom = feats[0].geometry()
    if poly_geom.isMultipart():
        rings = poly_geom.asMultiPolygon()[0][0]
    else:
        rings = poly_geom.asPolygon()[0]
    data_poly = Polygon([(pt.x(), pt.y()) for pt in rings])

    inside = [data_poly.contains(Point(lon, lat)) for lon, lat in zip(lons, lats)]
    segments = []
    start_idx = None
    for i, inc in enumerate(inside):
        if inc and start_idx is None:
            start_idx = i
        elif not inc and start_idx is not None:
            segments.append((start_idx, i - 1))
            start_idx = None
    if start_idx is not None:
        segments.append((start_idx, len(inside) - 1))
    if not segments:
        print("No flight segments found inside the polygon.")
        return
    print(f"Found {len(segments)} flight line segment(s).")

    # --- open DSM to get its CRS and validate EPSG code ---
    ds = gdal.Open(dsm_path)
    if ds is None:
        plugin_tools.show_error(f"Could not open DSM '{dsm_path}'")
        raise RuntimeError(f"Cannot open DSM '{dsm_path}'")

    wkt = ds.GetProjection()
    if not wkt:
        plugin_tools.show_error("Input DEM/DSM has no projection information")
        raise RuntimeError("DEM/DSM projection missing")

    tgt = osr.SpatialReference()
    tgt.ImportFromWkt(wkt)
    try:
        tgt.AutoIdentifyEPSG()
        code = int(tgt.GetAuthorityCode(None))
    except:
        plugin_tools.show_error("Could not determine EPSG code of DEM/DSM")
        raise RuntimeError("DEM/DSM EPSG code unknown")

    if not ((32600 < code < 32700) or (32700 < code < 32800)):
        plugin_tools.show_error(
            f"Input DEM/DSM is EPSG:{code}, must be either EPSG:326xx or EPSG:327xx"
        )
        raise ValueError(f"Invalid DEM/DSM EPSG:{code}")

    # --- set up transformations ---
    src = osr.SpatialReference(); src.ImportFromEPSG(4326)  # WGS84 lat/lon
    tfm = osr.CoordinateTransformation(src, tgt)
    inv_tfm = osr.CoordinateTransformation(tgt, src)

    # --- reproject IMU (lat,lon,alt) → DEM CRS ---
    east  = np.empty_like(lons, dtype=float)
    north = np.empty_like(lats, dtype=float)
    for i, (lon, lat, alt) in enumerate(zip(lons, lats, alts)):
        x, y, _ = tfm.TransformPoint(lat, lon, alt)
        east[i], north[i] = x, y

    # --- DEM ⇔ IMU EXTENT OVERLAP CHECK ---
    gt = ds.GetGeoTransform()
    dem_xmin = gt[0]
    dem_xmax = gt[0] + gt[1] * ds.RasterXSize
    dem_ymax = gt[3]
    dem_ymin = gt[3] + gt[5] * ds.RasterYSize

    imu_xmin, imu_xmax = east.min(), east.max()
    imu_ymin, imu_ymax = north.min(), north.max()

    if imu_xmax < dem_xmin or imu_xmin > dem_xmax or imu_ymax < dem_ymin or imu_ymin > dem_ymax:
        plugin_tools.show_error("IMU track extent does not overlap DEM/DSM extent")
        raise ValueError("No spatial overlap between IMU track and DEM/DSM")

    # --- prepare 3D figure ---
    de, dn, dz = east.max()-east.min(), north.max()-north.min(), alts.max()-alts.min()
    m = max(de, dn, dz) / 2.0
    me, mn, mz = (east.max()+east.min())/2.0, (north.max()+north.min())/2.0, (alts.max()+alts.min())/2.0
    buf = dsm_clip_buffer
    x_min, x_max = me - m - buf, me + m + buf
    y_min, y_max = mn - m - buf, mn + m + buf
    z_min, z_max = mz - m, mz + m
    plane_z = math.floor(alts.min()/10.0) * 10.0 - 20.0

    fig = plt.figure(figsize=(12,10))
    ax  = fig.add_subplot(111, projection='3d')

    # --- DEM/DSM clipping & mesh build ---
    Xc, Yc, Zc = raster_to_mesh(dsm_path, x_min, x_max, y_min, y_max)
    if Xc is None:
        plugin_tools.show_error("No overlap between flight-path bounds and DEM/DSM")
        raise ValueError("DEM/DSM and flight-path bounds do not intersect")

    Xf, Yf = Xc.ravel(), Yc.ravel()
    Zf     = Zc.ravel()
    tri    = Triangulation(Xf, Yf).triangles.copy()
    ax.plot_trisurf(Xf, Yf, Zf, triangles=tri, alpha=0.5, color='green', linewidth=0.2)
    mesh = trimesh.Trimesh(
        vertices=np.column_stack((Xf, Yf, Zf)),
        faces=tri,
        process=False
    )

    # --- compute FOV ray directions for all samples ---
    v_down = np.array([0,0,1])
    th     = np.deg2rad(fov/2.0)
    R_p    = np.array([[1,0,0],[0,math.cos(th),-math.sin(th)],[0,math.sin(th),math.cos(th)]])
    R_m    = np.array([[1,0,0],[0,math.cos(-th),-math.sin(-th)],[0,math.sin(-th),math.cos(-th)]])
    dirs_p = np.stack([dir_ned_to_enu(body_to_ned(R_p @ v_down, r, p, y))
                       for r, p, y in zip(rolls, pitches, yaws)])
    dirs_m = np.stack([dir_ned_to_enu(body_to_ned(R_m @ v_down, r, p, y))
                       for r, p, y in zip(rolls, pitches, yaws)])
    origins = np.column_stack((east, north, alts))

    # --- plot full flight path and sample points ---
    ax.scatter(east, north, alts, s=15, color='black')
    ax.plot(east, north, alts, color='gray', lw=1.5)
    if show_sensor_fov:
        ax.quiver(east, north, alts,
                  dirs_p[:,0], dirs_p[:,1], dirs_p[:,2],
                  length=arrow_len, normalize=True, color='red',   arrow_length_ratio=0)
        ax.quiver(east, north, alts,
                  dirs_m[:,0], dirs_m[:,1], dirs_m[:,2],
                  length=arrow_len, normalize=True, color='blue',  arrow_length_ratio=0)

    # --- trace rays & build footprints ---
    any_hit = False
    kml_placemarks = []
    for idx, (s, e) in enumerate(segments, start=1):
        seg_orig = origins[s:e+1]
        loc_r, rid_r, _ = mesh.ray.intersects_location(seg_orig, dirs_p[s:e+1], multiple_hits=False)
        loc_l, rid_l, _ = mesh.ray.intersects_location(seg_orig, dirs_m[s:e+1], multiple_hits=False)
        if len(rid_r) or len(rid_l):
            any_hit = True

        ord_r = loc_r[np.argsort(rid_r)] if len(rid_r) else np.empty((0,3))
        ord_l = loc_l[np.argsort(rid_l)] if len(rid_l) else np.empty((0,3))

        # build 2D ring
        pts3d = np.vstack((ord_r, ord_l[::-1]))
        xs2d, ys2d = pts3d[:,0], pts3d[:,1]

        lonlat = []
        for x_, y_ in zip(xs2d, ys2d):
            lat_, lon_, _ = inv_tfm.TransformPoint(x_, y_, 0)
            lonlat.append(f"{lon_:.9f},{lat_:.9f}")
        if lonlat:
            lonlat.append(lonlat[0])

        coords_str = " ".join(lonlat)
        kml_placemarks.append(f"""
      <Placemark>
        <name>flight_line_{idx}</name>
        <Style>
          <LineStyle><color>ff000000</color><width>1</width></LineStyle>
          <PolyStyle><color>50000000</color><fill>1</fill><outline>1</outline></PolyStyle>
        </Style>
        <Polygon>
          <outerBoundaryIs><LinearRing><coordinates>
            {coords_str}
          </coordinates></LinearRing></outerBoundaryIs>
        </Polygon>
      </Placemark>""")

        # two matching surfaces: mesh & reference plane
        ring_mesh  = np.vstack((ord_r, ord_l[::-1]))
        ring_plane = np.column_stack((xs2d, ys2d, np.full_like(xs2d, plane_z)))
        surf_color = 'blue' if idx % 2 else 'red'
        ax.add_collection3d(Poly3DCollection([ring_plane], facecolor='grey', alpha=0.4))
        ax.add_collection3d(Poly3DCollection([ring_mesh], facecolor=surf_color, edgecolor=surf_color, alpha=0.4))

    # --- no intersections? popup + raise ---
    if not any_hit:
        plugin_tools.show_error("No intersections found between sensor rays and DEM mesh")
        raise RuntimeError("Trimesh ray-mesh intersection returned zero hits")

    # --- reference plane & axes styling ---
    xx, yy = np.linspace(x_min, x_max, 2), np.linspace(y_min, y_max, 2)
    Xp, Yp = np.meshgrid(xx, yy)
    Zp      = np.full_like(Xp, plane_z)
    ax.plot_surface(Xp, Yp, Zp, alpha=0.1, color='grey', linewidth=0)

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_zlim(z_min, z_max)
    ax.set_xlabel('Easting (m)')
    ax.set_ylabel('Northing (m)')
    ax.set_zlabel('Altitude (m)')
    ax.set_title('3D DSM + Flight Path + Footprints')

    end_time()
    plt.tight_layout()
    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    # --- write KML if requested ---
    if save_to_file and kml_placemarks:
        out_kml = get_name_of_non_existing_output_file(
            imu_path,
            additional_suffix="_footprint",
            new_extension=".kml"
        )
        os.makedirs(os.path.dirname(out_kml), exist_ok=True)
        name = os.path.splitext(os.path.basename(out_kml))[0]
        kml = f"""<?xml version='1.0' encoding='utf-8'?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document id="root_doc">
    <Folder>
      <name>{name}</name>
      {''.join(kml_placemarks)}
    </Folder>
  </Document>
</kml>"""
        with open(out_kml, "w", encoding="utf-8") as f:
            f.write(kml)
        print(f"KML with {len(kml_placemarks)} flight line(s) written to {out_kml}")

        if is_qgis_desktop_running():
            layer = QgsVectorLayer(out_kml, name, "ogr")
            if layer.isValid():
                root = QgsProject.instance().layerTreeRoot()
                QgsProject.instance().addMapLayer(layer, False)
                root.insertLayer(0, layer)
                print("Flight lines KML loaded into QGIS.")
            else:
                print("Failed to load flight lines KML into QGIS.")
