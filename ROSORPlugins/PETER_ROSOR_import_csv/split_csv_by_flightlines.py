import pandas as pd
import os
import sys
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit, \
    QMessageBox
from PyQt5.QtGui import QIcon


def split_csv_by_flightlines(csv_path, flightline_pairs, match_data_to_flt, gui):
    # Load the CSV file into a DataFrame
    df = pd.read_csv(csv_path)

    # Check if the 'Flightline' column exists
    if 'Flightline' not in df.columns:
        print(f"Error: 'Flightline' column not found in {csv_path}")
        return

    # Iterate over the list of flight line pairs
    for pair in flightline_pairs:
        # Filter the DataFrame for the current pair of flight lines
        pair_df = df[df['Flightline'].isin(pair)]

        # Check if the resulting DataFrame is not empty
        if not pair_df.empty:

            Csv_Mag_Data, flights_list, get_best_kml_for_csv, match_thresh_percent = match_data_to_flt
            # Construct the output filename based on the pair of flight lines
            output_filename = f"{os.path.splitext(csv_path)[0]}_fl_{'-'.join(map(str, pair))}.csv"
            # Save the filtered DataFrame to a new CSV file
            pair_df.to_csv(output_filename, index=False)
            print(f"Created {output_filename}")
            best_kml = get_best_kml_for_csv(Csv_Mag_Data(output_filename),
                                            flights_list, match_thresh_percent)
            clean_basename = clean_name(os.path.splitext(os.path.basename(output_filename))[0])

            if best_kml:
                new_basename = best_kml.basic_name + '_' + clean_basename + '.csv'
                new_export_file_path = os.path.join(os.path.dirname(output_filename), new_basename)
                os.rename(output_filename, new_export_file_path)
                gui.show_message(f'For mag data: {clean_basename}\n\n'
                                 f'found matching flight: {best_kml.basic_name}\n\n'
                                 f'Renamed to: {new_basename}\n\n'
                                 f'Full path:  {new_export_file_path}')
                #[1],[2,3],[4,5],[7,8],[9,10],[11,12]
            else:
                gui.show_error(f'Did not find matching flight for {clean_basename}\n\n'
                               f'Full path:  {output_filename}\n\n'
                               f'Try assigning a different set of flight-lines')
        else:
            print(f"Warning: No data found for flight lines {pair}")

def clean_name(name):
    # Remove specific substrings
    substrings_to_remove = ['SRVY0-', '_10Hz', 'SRVY0', '10Hz']
    for substring in substrings_to_remove:
        name = name.replace(substring, '')
    return name

class FlightlineSplitterGUI(QDialog):
    def __init__(self, default_csv_path, match_data_to_flt, how_done):
        super().__init__()
        self.how_done = how_done
        self.match_data_to_flt = match_data_to_flt
        self.default_csv_path = default_csv_path
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout()

        icon_path = os.path.join(os.path.dirname(__file__), 'split.png')
        self.setWindowIcon(QIcon(icon_path))

        self.csv_label = QLabel('Select Input CSV:')
        self.layout.addWidget(self.csv_label)

        self.csv_input = QLineEdit(self)
        if self.default_csv_path:
            self.csv_input.setText(self.default_csv_path)
        self.layout.addWidget(self.csv_input)

        self.csv_button = QPushButton('Browse', self)
        self.csv_button.clicked.connect(self.browse_csv)
        self.layout.addWidget(self.csv_button)

        self.pairs_label = QLabel('No matching flight were detected for the mag data. \n'
                                  'In case the data spans multiple flights, here you can split the data by flight-lines. \n'
                                  'Enter the flight-lines to assign to each new file. \n'
                                  'The following will assign flight-line 1,2 to a flight. Then 3,4 to a different flight etc..')

        self.layout.addWidget(self.pairs_label)

        self.pairs_input = QTextEdit(self)
        self.pairs_input.setText('[1,2],[3,4],[5,6],[7,8],[9,10],[11,12]')
        self.layout.addWidget(self.pairs_input)

        self.run_button = QPushButton('Run', self)
        self.run_button.clicked.connect(self.run_splitter)
        self.layout.addWidget(self.run_button)

        self.setLayout(self.layout)
        self.setWindowTitle(f'Split flight by flightline {self.how_done}')

        # Set window size
        self.resize(600, 300)

    def browse_csv(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Input CSV", "", "CSV Files (*.csv);;All Files (*)",
                                                   options=options)
        if file_path:
            self.csv_input.setText(file_path)

    def run_splitter(self):
        csv_path = self.csv_input.text()
        pairs_text = self.pairs_input.toPlainText()

        try:
            # Convert text input to a list of lists
            flightline_pairs = eval(pairs_text)
        except SyntaxError:
            self.show_error("Invalid flightline pairs format.")
            return
        self.close()
        split_csv_by_flightlines(csv_path, flightline_pairs, self.match_data_to_flt, self)



    def show_error(self, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText(message)
        msg.setWindowTitle("Error")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    def show_message(self, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(message)
        msg.setWindowTitle("Information")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()


# Keep a reference to the GUI instance to prevent it from being garbage collected
gui_instance = None


def run_flightline_splitter_gui(no_match_csv_path, match_data_to_flt, how_done):
    app = QApplication.instance()  # Check if QApplication already exists
    if app is None:
        app = QApplication(sys.argv)
    gui_instance = FlightlineSplitterGUI(no_match_csv_path, match_data_to_flt, how_done)
    gui_instance.show()
    gui_instance.exec_()  # Start a nested event loop to make it blocking
    return gui_instance