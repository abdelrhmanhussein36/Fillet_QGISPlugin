import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication


def classFactory(iface):
    return FilletPlugin(iface)


class FilletPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        # Load icon from the embedded resource (base64 in resources.py).
        # This is 100% path-independent and survives QGIS restarts on Windows.
        try:
            from .resources import get_icon
            icon = get_icon()
            if icon.isNull():
                raise ValueError("Embedded icon is null")
        except Exception:
            # Last-resort fallback to a built-in QGIS icon
            icon = QgsApplication.getThemeIcon("/mActionFileSave.svg")

        self.action = QAction(icon, "Fillet Tool", self.iface.mainWindow())
        self.action.setWhatsThis("Fillet polygon corners – ArcGIS Pro style")
        self.action.setObjectName("FilletToolAction")
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Fillet Tool", self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Fillet Tool", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        from .simple_dialog import ArcGISProFilletDialog
        dialog = ArcGISProFilletDialog(self.iface)
        dialog.show()
        dialog.exec()
