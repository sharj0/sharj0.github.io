import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString #this might be obsolete

# Calculates the distance between points on each row and returns the total sum
def iterative_point_calcution(mag_points_geodf, flightline):
    # Variable to hold the travel distance between Flightlines
    points_traveled = 0

    # Isolates points by Flightline (should already be sorted by time, but done so just in case)
    line_points = mag_points_geodf[mag_points_geodf['Flightline'] == flightline].sort_values(
        by='Counter').copy().reset_index(drop=True)

    # Calculates the distance between a point and the one before it for each point in the flightline
    for i in range(len(line_points)):

        # Skips the first point as there is no point before it
        if i == 0:
            continue

        # Uses the distance function to calculate distance (an alternative is to use euclidean x^2 + y^2 = r^2 as the crs is in metres, should be the same/similar)
        points_traveled = points_traveled + line_points.geometry[i].distance(line_points.geometry[i - 1])

    return points_traveled


def calculation_setup(csv_file):
    # Variable to hold the travel distance between files
    cumulative_point_distance = 0

    # Create a dataframe from the rows and columns of the csv file and uses UTME as x and UTMN as y coords so that the .distance() function can reference the coords
    mag_points_csv = pd.read_csv(csv_file)
    mag_points_geodf = gpd.GeoDataFrame(mag_points_csv,
                                        geometry=gpd.points_from_xy(mag_points_csv.UTME, mag_points_csv.UTMN),
                                        )

    # Separates the file data into flightlines and runs it through the calculation function
    if 'Flightline' in mag_points_geodf.columns:

        flightlines = mag_points_geodf.Flightline.unique()

        for flightline in flightlines:
            cumulative_point_distance = cumulative_point_distance + iterative_point_calcution(mag_points_geodf,
                                                                                              flightline)

        # Returns value in km
        return cumulative_point_distance / 1000
    else:
        return -1

