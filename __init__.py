import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import Qgis, QgsApplication


def classFactory(iface):
    return FilletPlugin(iface)


class FilletPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None

    def initGui(self):
        # Use a default icon if custom icon doesn't exist
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            # Use built-in QGIS icon as fallback
            icon = QgsApplication.getThemeIcon("/mActionFileSave.svg")
        
        self.action = QAction(icon, "Fillet Tool", self.iface.mainWindow())
        self.action.setWhatsThis("Fillet polygon corners – ArcGIS Pro style")
        self.action.setObjectName("FilletToolAction")  # Important for persistence
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
