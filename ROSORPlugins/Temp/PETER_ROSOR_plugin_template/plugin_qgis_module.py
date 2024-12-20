'''
THIS .PY FILE SHOULD BE THE SAME FOR ALL PLUGINS.
A CHANGE TO THIS .PY IN ONE OF THE PLUGINS SHOULD BE COPPY-PASTED TO ALL THE OTHER ONES
'''

from qgis.PyQt.QtWidgets import QAction
from PyQt5.QtGui import QIcon
import os

from . import plugin_common_module
from . import plugin_tools

#USE IN C:\Users\pyoty\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins

class plugin_class:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        # Get the directory containing the current Python file.
        current_directory = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(current_directory, 'plugin_icon.png')
        self.action = QAction(QIcon(icon_path),
                              plugin_tools.get_plugin_name(),
                              self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.window = plugin_common_module.run(skip=False)