import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QWidget, QLineEdit, QLabel, QHBoxLayout, QApplication
from PyQt5.QtCore import Qt
import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.patches import Arc
import subprocess
import os




class LineSpaceCalc(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FOV and Swath Width Calculator")

        self.fov_deg = 84
        self.alt_m = 120
        self.side_lap_percent = 75
        self.line_spacing = 54.02

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        self.canvas = FigureCanvas(plt.Figure())
        self.ax = self.canvas.figure.subplots()

        self.fov_input = QLineEdit(str(self.fov_deg))
        self.alt_input = QLineEdit(str(self.alt_m))
        self.side_lap_input = QLineEdit(str(self.side_lap_percent))
        self.line_spacing_input = QLineEdit(str(self.line_spacing))

        self.side_lap_button = QPushButton("Calculate Side Lap %")
        self.line_spacing_button = QPushButton("Calculate Line Spacing")
        self.show_typical_overlap_button = QPushButton("See required overlap percentages")

        self.side_lap_button.clicked.connect(self.calculate_side_lap)
        self.line_spacing_button.clicked.connect(self.calculate_line_spacing)
        self.show_typical_overlap_button.clicked.connect(self.show_overlap_excel)

        layout.addWidget(self.canvas)

        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("FOV (deg):"))
        input_layout.addWidget(self.fov_input)
        input_layout.addWidget(QLabel("Altitude (m):"))
        input_layout.addWidget(self.alt_input)
        layout.addLayout(input_layout)

        input_layout2 = QHBoxLayout()
        input_layout2.addWidget(QLabel("Side Lap %:"))
        input_layout2.addWidget(self.side_lap_input)
        input_layout2.addWidget(self.side_lap_button)
        input_layout2.addWidget(QLabel("Line Spacing (m):"))
        input_layout2.addWidget(self.line_spacing_input)
        input_layout2.addWidget(self.line_spacing_button)
        layout.addLayout(input_layout2)

        input_layout3 = QHBoxLayout()
        input_layout3.addWidget(self.show_typical_overlap_button)
        layout.addLayout(input_layout3)



        self.setLayout(layout)
        self.plot_triangles()  # Initial plot call at the end of initialization

    def show_overlap_excel(self):
        # open excel with overlaps
        file_name = 'Typical-Required-overlap-line-spacing.xlsx'
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        if os.name == 'nt':  # For Windows
            os.startfile(file_path)
        elif os.name == 'posix':  # For MacOS and Linux
            subprocess.call(('open', file_path))  # MacOS
            # subprocess.call(('xdg-open', file_path))  # Linux (uncomment if needed)
        else:
            print(f"Unsupported OS: {os.name}")
        pass

    def calculate_side_lap(self):
        fov_deg = float(self.fov_input.text())
        alt_m = float(self.alt_input.text())
        swath_width = get_swath_width(alt_m, fov_deg)
        line_spacing = float(self.line_spacing_input.text())
        side_lap_percent = get_side_lap_percent(line_spacing, swath_width)
        self.side_lap_input.setText(f"{side_lap_percent:.2f}")
        self.plot_triangles()

    def calculate_line_spacing(self):
        fov_deg = float(self.fov_input.text())
        alt_m = float(self.alt_input.text())
        swath_width = get_swath_width(alt_m, fov_deg)
        side_lap_percent = float(self.side_lap_input.text())
        line_spacing = get_line_spacing(swath_width, side_lap_percent)
        self.line_spacing_input.setText(f"{line_spacing:.2f}")
        self.plot_triangles()

    def plot_triangles(self):
        self.canvas.figure.clear()
        ax = self.canvas.figure.add_subplot(111)

        fov_deg = float(self.fov_input.text())
        alt_m = float(self.alt_input.text())
        side_lap_percent = float(self.side_lap_input.text())
        line_spacing = float(self.line_spacing_input.text())

        swath_width = get_swath_width(alt_m, fov_deg)

        l1_l = -swath_width / 2
        l1_r = swath_width / 2
        l2_l = line_spacing + l1_l
        l2_r = line_spacing + l1_r

        ax.plot([l1_l, 0, l1_r], [0, alt_m, 0], 'k-')
        ax.plot([l2_l, line_spacing, l2_r], [0, alt_m, 0], 'r-')

        # Plot line spacing
        ax.annotate('', xy=(0, alt_m), xytext=(line_spacing, alt_m),
                    arrowprops=dict(arrowstyle='<->', color='blue'))
        ax.text(line_spacing / 2, alt_m * 1.1, f"Line Spacing = {line_spacing:.2f}", color='blue', ha='center',
                bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.2'))

        # Plot swath width
        ax.annotate('', xy=(l1_l, alt_m * -0.04), xytext=(l1_r, alt_m * -0.04),
                    arrowprops=dict(arrowstyle='<->', color='blue'))
        ax.text(0, alt_m * -0.125, f"Swath Width = {swath_width:.2f}", color='blue', ha='center',
                bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.2'))
        ax.plot([l1_l, l1_l], [alt_m * 0.03, alt_m * -0.07], 'b-')
        ax.plot([l1_r, l1_r], [alt_m * 0.03, alt_m * -0.07], 'b-')

        # Plot FOV arc
        start_angle = (-fov_deg / 2) - 90
        end_angle = (fov_deg / 2) - 90
        center = (0, alt_m)
        radius = alt_m * 0.2
        arc = Arc(center, 2 * radius * np.tan(np.radians(fov_deg / 2)), 2 * radius, angle=0, theta1=start_angle,
                  theta2=end_angle, color='blue', linestyle='--')
        ax.add_patch(arc)

        # Calculate the position for the FOV label
        label_x = center[0] + radius * np.cos(np.radians(start_angle))
        label_y = center[1] + radius * np.sin(np.radians(start_angle))
        ax.text(label_x, label_y, f"FOV = {fov_deg}°", color='blue', ha='right',
                bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.2'))

        # Set plot limits and labels
        ax.set_xlim(l1_l * 1.2, l2_r + (l1_r * .2))
        ax.set_ylim(0 - (alt_m * 0.2), alt_m * 1.2)
        ax.set_aspect('equal')
        ax.set_xlabel('Side Distance (m)')
        ax.set_ylabel('Altitude (m)')
        ax.grid(True, alpha=0.5)
        self.canvas.draw()


def get_swath_width(alt_m, fov_deg):
    fov_rad = np.radians(fov_deg)
    swath_width = abs(2 * alt_m * (np.tan(fov_rad / 2)))
    return swath_width


def get_line_spacing(swath_width, side_lap_percent):
    overlap_area_width = swath_width * (side_lap_percent / 100)
    line_spacing = swath_width - overlap_area_width
    return line_spacing


def get_side_lap_percent(line_spacing, swath_width):
    overlap_area_width = swath_width - line_spacing
    side_lap_percent = (overlap_area_width / swath_width) * 100
    return side_lap_percent


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = LineSpaceCalc()
    main_window.show()
    sys.exit(app.exec_())
