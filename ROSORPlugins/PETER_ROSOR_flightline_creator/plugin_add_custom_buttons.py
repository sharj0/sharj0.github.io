'''
THIS .PY FILE IS NOT THE SAME FOR ALL PLUGINS.
'''

import os
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt

from . import swath_linespacing_fov_calc

def add_custom_buttons(guiz, plugin_dir):
    # Swath FOV Line-Spacing solver START
    LineSpace_icon_path = os.path.join(plugin_dir, 'LineSpace_calc.png')
    button_font = QFont()
    button_font.setPointSize(12)
    run_button = QPushButton("Swath FOV Line-Spacing solver")
    run_button.setFont(button_font)
    run_button.setIcon(QIcon(LineSpace_icon_path))
    guiz.mainLayout.addWidget(run_button, 0, Qt.AlignLeft)
    guiz.line_space_calc = swath_linespacing_fov_calc.LineSpaceCalc()
    run_button.clicked.connect(guiz.line_space_calc.show)
    # Swath FOV Line-Spacing solver END