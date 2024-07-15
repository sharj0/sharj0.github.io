import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import os

def run(pdf_plot_data,mag_data_folder):
    version = 1
    file_basen_no_ex = os.path.basename(mag_data_folder) + 'Base_Mag_QaQc'
    output_pdf_path_no_ex = os.path.join(mag_data_folder, file_basen_no_ex)
    while os.path.exists(f"{output_pdf_path_no_ex}_v{version}.pdf"):
        version += 1
    output_pdf_path = f"{output_pdf_path_no_ex}_v{version}.pdf"

    pdf_base_data, pdf_air_data = pdf_plot_data
    with PdfPages(output_pdf_path) as pdf:
        for base_mag_data_page in pdf_base_data:
            fig, ax = plt.subplots(figsize=(10, 4))
            ave_y_list = []

            # Get the title from the first artist
            if base_mag_data_page:
                first_artist_title = base_mag_data_page[0].get('label', 'No Title')

            for artist in base_mag_data_page:
                x = artist.pop('x')
                y = artist.pop('y')
                ave_y_list.extend(y)
                fmt = artist.pop('fmt')
                ax.plot(x, y, fmt, **artist)
            for artist in pdf_air_data:
                x_air = artist.pop('x')
                y_air = artist.pop('y')
                fmt_air = artist.pop('fmt')
                y_air_ave = np.array(y_air) + np.mean(ave_y_list)
                ax.plot(x_air, y_air_ave, fmt_air, **artist)
                # Add the popped items back
                artist['x'] = x_air
                artist['y'] = y_air
                artist['fmt'] = fmt_air
            ax_rot = 10
            # Rotate x-ticks
            ax.tick_params(axis='x', rotation=ax_rot)
            # Set the figure title
            fig.suptitle(first_artist_title, fontsize=14)
            # Save the current figure to the PDF
            pdf.savefig(fig)
            plt.close(fig)