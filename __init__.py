from qgis.PyQt.QtWidgets import QAction, QMessageBox

def classFactory(iface):
    """Required entry point - this MUST exist"""
    return FilletPlugin(iface)


class FilletPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.name = "Fillet Tool"

    def initGui(self):
        """Create the menu entry and toolbar icon"""
        # Create action without icon to avoid missing file errors
        self.action = QAction("Fillet Tool", self.iface.mainWindow())
        self.action.setWhatsThis("Fillet polygon corners")
        self.action.triggered.connect(self.run)
        
        # Add to toolbar and menu
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Fillet Tool", self.action)

    def unload(self):
        """Remove plugin from interface"""
        self.iface.removePluginMenu("&Fillet Tool", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        """Show a simple message to test if plugin loads"""
        from .simple_dialog import SimpleFilletDialog
        dialog = SimpleFilletDialog(self.iface)
        dialog.show()
        dialog.exec_()