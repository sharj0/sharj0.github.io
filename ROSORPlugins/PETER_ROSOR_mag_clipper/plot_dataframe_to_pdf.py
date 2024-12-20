import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import datetime
from matplotlib.backends.backend_pdf import PdfPages
import tempfile

def determine_direction(minutes_elapsed_series):
    # Check if the 'minutes_elapsed' value increases or decreases from start to end
    start_minutes = minutes_elapsed_series.iloc[0]
    end_minutes = minutes_elapsed_series.iloc[-1]
    return '→' if start_minutes < end_minutes else '←'

def wrap_values(values, y_min, y_max):
    range_size = y_max - y_min
    wrapped_values = (values - y_min) % range_size + y_min
    mask = np.abs((values - y_min) // range_size)  # This will give the number of wraps
    return wrapped_values, mask


def run(df, local_grid_line_names, flight_line_sort_direction, export_file_path, whole_flight_fig, Y_axis_display_range_override):
    mag_col = 'Mag_TMI_nT'
    split_plots_by = 'Flightline'

    if Y_axis_display_range_override == 0:
        max_height_override = None # Set to None to use the calculated value
    else:
        max_height_override = Y_axis_display_range_override
    max_width_override = None # Set to None to use the calculated value

    # Calculate the maximum width needed across all flight lines
    flightlines = {}
    width = []
    height = []
    for flightline_key, flightline_data in df.groupby(split_plots_by):
        if flightline_key > 0:
            flightlines[flightline_key] = flightline_data
            x = flightline_data[flight_line_sort_direction[flightline_key]]
            y = flightline_data[mag_col]
            width.append(x.max() - x.min())
            height.append(y.max() - y.min())
    max_width_needed = int(np.ceil(max(width)))
    max_height_needed = int(np.ceil(max(height)))

    if max_height_override:
        max_height_needed = max_height_override
    if max_width_override:
        max_width_needed = max_width_override

    version = 1
    file_basen_no_ex = os.path.basename(export_file_path).split('.')[0]
    temp_dir = tempfile.gettempdir()
    output_pdf_path_no_ex = os.path.join(temp_dir,file_basen_no_ex)
    while os.path.exists(f"{output_pdf_path_no_ex}_v{version}.pdf"):
        version += 1
    output_pdf_path = f"{output_pdf_path_no_ex}_v{version}.pdf"
    #print(f"Output pdf: {output_pdf_path}")

    flightline_list = list(flightlines.values())
    with PdfPages(output_pdf_path) as pdf:
        for df_plot in flightline_list:
            i = df_plot['Flightline'].unique()[0]
            # Create a new figure for each flightline
            fig, ax = plt.subplots(1, 1, figsize=(12, 4))
            #fig, ax = plt.subplots(1, 1, figsize=(12, 8))
            x_col = flight_line_sort_direction[i]
            df_plot = df_plot.sort_values(by=[x_col])  # Sort by x_col before plotting

            mag_mid = (df_plot[mag_col].max() - df_plot[mag_col].min()) / 2 + df_plot[mag_col].min()
            if max_height_override is None:
                y_axis_min = mag_mid - 0.5 * max_height_needed * 1.1
                y_axis_max = mag_mid + 0.5 * max_height_needed * 1.1
            else:
                y_axis_min = mag_mid - 0.5 * max_height_override
                y_axis_max = mag_mid + 0.5 * max_height_override

            # Wrap the magnetic data values into a new column
            df_plot['wrapped_mag_col'], df_plot['wrap_mask'] = wrap_values(df_plot[mag_col], y_axis_min, y_axis_max)


            # Create a second y-axis for the accelerometer data
            ax2 = ax.twinx()
            alpha_accel = 0.6
            # Calculate means and center the data around zero
            accel_x_mean = df_plot['AccelerometerX'].mean()
            accel_y_mean = df_plot['AccelerometerY'].mean()
            accel_z_mean = df_plot['AccelerometerZ'].mean()

            accel_x_centered = df_plot['AccelerometerX'] - accel_x_mean
            accel_y_centered = df_plot['AccelerometerY'] - accel_y_mean
            accel_z_centered = df_plot['AccelerometerZ'] - accel_z_mean

            ax.plot(df_plot[x_col].values, accel_x_centered.values, 'c-', linewidth=0.5, label=f'AcelX -{round(accel_x_mean,2)}', alpha=alpha_accel)
            ax.plot(df_plot[x_col].values, accel_y_centered.values, 'm--', linewidth=0.5, label=f'AcelY -{round(accel_y_mean,2)}', alpha=alpha_accel)
            ax.plot(df_plot[x_col].values, accel_z_centered.values, 'b-.', linewidth=0.5, label=f'AcelZ -{round(accel_z_mean,2)}', alpha=alpha_accel)
            ax.set_ylabel('Accelerometer Data')
            ax.set_ylim(-0.4, 0.4)


            #background
            ax2.plot(np.array(df_plot[df_plot['wrap_mask'] == 0][x_col]),
                    np.array(df_plot[df_plot['wrap_mask'] == 0]['wrapped_mag_col']),
                    'w.', markersize=6)
            ax2.plot(np.array(df_plot[df_plot['wrap_mask'] != 0][x_col]),
                    np.array(df_plot[df_plot['wrap_mask'] != 0]['wrapped_mag_col']),
                    'k.', markersize=4.7)
            # Plot where noise is considered good (False) in green
            ax2.plot(np.array(df_plot[df_plot['noise_bad'] == False][x_col]),
                    np.array(df_plot[df_plot['noise_bad'] == False]['wrapped_mag_col']),
                    'g.', markersize=3, label='Noise Okay')
            # Plot where noise is considered bad (True) in red 'x'
            ax2.plot(np.array(df_plot[df_plot['noise_bad'] == True][x_col]),
                    np.array(df_plot[df_plot['noise_bad'] == True]['wrapped_mag_col']),
                    'rx', markersize=5, label='Noise Bad')
            # Set limits, labels, title, and grid
            ax2.set_xlim(df_plot[x_col].min() - (0.03 * max_width_needed),
                        df_plot[x_col].min() + max_width_needed + (0.03 * max_width_needed))

            # Predefined axis ranges
            x_axis_min = df_plot[x_col].min() - (0.03 * max_width_needed)
            x_axis_max = df_plot[x_col].min() + max_width_needed + (0.03 * max_width_needed)

            ax2.set_xlim(x_axis_min, x_axis_max)
            ax2.set_ylim(y_axis_min, y_axis_max)

            local_grid_line_name = local_grid_line_names[i - 1]
            if local_grid_line_name:
                local_grid_line_name = f': "{local_grid_line_name}"'
            else:
                local_grid_line_name = ''
            # Include axis ranges in the subplot title
            ax.set_title(f'{file_basen_no_ex}  Flightline {i}{local_grid_line_name}  Y Range [{(y_axis_max-y_axis_min):.1f}] X Range [{(x_axis_max-x_axis_min):.1f}]', loc='left')
            ax.grid(True)  # Add grid lines for better data readability

            direction = determine_direction(df_plot['elapsed_time_minutes'])
            ax.set_xlabel(f'{x_col} [meters] flight direction {direction}')
            ax2.set_ylabel('Total Magnetic Intensity [nT]')

            # Combine legends from both y-axes
            lines_1, labels_1 = ax.get_legend_handles_labels()
            lines_2, labels_2 = ax2.get_legend_handles_labels()
            ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right')

            # Adjust layout, save the figure to the PDF, and close the figure to free memory
            plt.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
        pdf.savefig(whole_flight_fig)
        plt.close(whole_flight_fig)
    os.startfile(output_pdf_path)

    return output_pdf_path
