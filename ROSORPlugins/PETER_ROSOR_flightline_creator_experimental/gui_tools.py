from PyQt5.QtGui import QScreen
from PyQt5.QtCore import QCoreApplication

def convert_app_cm_to_px(width_cm, height_cm):
    # Assuming this is within your QWidget or QMainWindow subclass
    app = QCoreApplication.instance()
    screen: QScreen = app.primaryScreen()
    dpi = screen.physicalDotsPerInch()
    def cm_to_pixels(cm, dpi):
        inches = cm * 0.393701  # Convert cm to inches
        pixels = inches * dpi   # Convert inches to pixels based on DPI
        return int(pixels)
    # Desired dimensions in centimeters
    width_px = cm_to_pixels(width_cm, dpi)
    height_px = cm_to_pixels(height_cm, dpi)
    return width_px, height_px