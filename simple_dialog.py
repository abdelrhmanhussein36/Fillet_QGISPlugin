from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, 
    QMessageBox, QHBoxLayout, QDoubleSpinBox
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsGeometry, QgsPointXY, QgsProject, QgsFeatureRequest,
    QgsRectangle, QgsWkbTypes
)
from qgis.gui import QgsRubberBand, QgsMapTool
import math


class SimpleFilletDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.setWindowTitle("Fillet Tool")
        self.setMinimumWidth(450)
        
        # Store data
        self.selected_layer = None
        self.selected_feature = None
        self.selected_vertex_index = None
        self.vertices = []
        self.rubber_band = None
        self.preview_band = None
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("POLYGON CORNER FILLET TOOL")
        title.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #2c3e50; color: white; padding: 10px; border-radius: 5px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Instructions
        instructions = QLabel(
            "HOW TO USE:\n\n"
            "1️⃣ Select a polygon layer in the Layers panel\n"
            "2️⃣ Click 'Pick Polygon' then click INSIDE a polygon\n"
            "3️⃣ Click 'Pick Corner' then click ON a corner vertex\n"
            "4️⃣ Adjust radius and click 'Apply Fillet'\n\n"
            "⚠️ Make sure the layer is in EDITING MODE (yellow pencil icon)"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("background-color: #ecf0f1; padding: 10px; border-radius: 5px;")
        layout.addWidget(instructions)
        
        # Status
        self.status_label = QLabel("⚡ Ready - Select a polygon layer first")
        self.status_label.setStyleSheet("color: #2980b9; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)
        
        # Info labels
        self.layer_label = QLabel("📁 Layer: None")
        layout.addWidget(self.layer_label)
        
        self.polygon_label = QLabel("🔷 Polygon: None")
        layout.addWidget(self.polygon_label)
        
        self.corner_label = QLabel("📍 Corner: None")
        layout.addWidget(self.corner_label)
        
        self.max_radius_label = QLabel("📏 Max radius: --")
        layout.addWidget(self.max_radius_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.pick_polygon_btn = QPushButton("1. Pick Polygon")
        self.pick_polygon_btn.clicked.connect(self.pick_polygon)
        self.pick_polygon_btn.setStyleSheet("background-color: #3498db; color: white; padding: 8px; font-weight: bold;")
        btn_layout.addWidget(self.pick_polygon_btn)
        
        self.pick_corner_btn = QPushButton("2. Pick Corner")
        self.pick_corner_btn.clicked.connect(self.pick_corner)
        self.pick_corner_btn.setEnabled(False)
        self.pick_corner_btn.setStyleSheet("background-color: #95a5a6; color: white; padding: 8px; font-weight: bold;")
        btn_layout.addWidget(self.pick_corner_btn)
        
        layout.addLayout(btn_layout)
        
        # Radius input
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(QLabel("Radius (map units):"))
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.1, 100000)
        self.radius_spin.setValue(10.0)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setEnabled(False)
        self.radius_spin.valueChanged.connect(self.on_radius_changed)
        radius_layout.addWidget(self.radius_spin)
        layout.addLayout(radius_layout)
        
        # Apply button
        self.apply_btn = QPushButton("3. Apply Fillet")
        self.apply_btn.clicked.connect(self.apply_fillet)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet("background-color: #27ae60; color: white; font-size: 14px; padding: 10px; font-weight: bold; border-radius: 5px;")
        layout.addWidget(self.apply_btn)
        
        self.setLayout(layout)
        
        # Create map tools
        self.polygon_picker = PolygonPickerTool(self.canvas, self)
        self.corner_picker = CornerPickerTool(self.canvas, self)
    
    def pick_polygon(self):
        """Activate polygon picking mode"""
        self.canvas.setMapTool(self.polygon_picker)
        self.status_label.setText("⚡ Click INSIDE a polygon to select it")
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
    
    def pick_corner(self):
        """Activate corner picking mode"""
        self.canvas.setMapTool(self.corner_picker)
        self.status_label.setText("⚡ Click ON a corner vertex")
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
    
    def polygon_picked(self, layer, feature):
        """Called when a polygon is picked"""
        self.selected_layer = layer
        self.selected_feature = feature
        
        # Get vertices from polygon
        self.vertices = []
        geom = feature.geometry()
        
        # Extract vertices based on geometry type
        if geom.isMultipart():
            # For multipart polygons, take first part
            parts = geom.parts()
            if parts:
                first_part = next(parts)
                for v in first_part.vertices():
                    self.vertices.append(QgsPointXY(v.x(), v.y()))
        else:
            for v in geom.vertices():
                self.vertices.append(QgsPointXY(v.x(), v.y()))
        
        # Remove duplicate last point if it exists (closed polygon)
        if len(self.vertices) > 1 and self.vertices[0] == self.vertices[-1]:
            self.vertices.pop()
        
        # Update UI
        layer_name = layer.name() if layer.name() else "Unknown"
        self.layer_label.setText(f"📁 Layer: {layer_name}")
        self.polygon_label.setText(f"🔷 Polygon: ID {feature.id()} ({len(self.vertices)} vertices)")
        self.pick_corner_btn.setEnabled(True)
        self.pick_corner_btn.setStyleSheet("background-color: #e67e22; color: white; padding: 8px; font-weight: bold;")
        self.status_label.setText("✓ Polygon selected! Now click 'Pick Corner'")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        
        # Highlight polygon
        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(0, 255, 0, 80))
        self.rubber_band.setWidth(2)
        self.rubber_band.setToGeometry(geom)
    
    def corner_picked(self, vertex_index):
        """Called when a corner is picked"""
        self.selected_vertex_index = vertex_index
        
        # Get the three points (before, at, after corner)
        prev_idx = (vertex_index - 1) % len(self.vertices)
        next_idx = (vertex_index + 1) % len(self.vertices)
        
        p1 = self.vertices[prev_idx]
        p2 = self.vertices[vertex_index]
        p3 = self.vertices[next_idx]
        
        # Calculate edge lengths from corner
        len1 = math.sqrt((p1.x() - p2.x())**2 + (p1.y() - p2.y())**2)
        len2 = math.sqrt((p3.x() - p2.x())**2 + (p3.y() - p2.y())**2)
        
        # Calculate angle at corner
        v1 = (p1.x() - p2.x(), p1.y() - p2.y())
        v2 = (p3.x() - p2.x(), p3.y() - p2.y())
        
        u1 = (v1[0]/len1, v1[1]/len1)
        u2 = (v2[0]/len2, v2[1]/len2)
        
        dot = u1[0]*u2[0] + u1[1]*u2[1]
        dot = max(-0.9999, min(0.9999, dot))
        angle = math.acos(dot)
        
        # Calculate max possible radius (ArcGIS Pro style)
        max_radius = min(len1, len2) * math.tan(angle / 2)
        
        # Store corner data
        self.corner_data = {
            'p1': p1, 'p2': p2, 'p3': p3,
            'max_radius': max_radius,
            'angle': angle,
            'len1': len1, 'len2': len2
        }
        
        # Update UI
        self.corner_label.setText(f"📍 Corner: Vertex {vertex_index}")
        self.max_radius_label.setText(f"📏 Max radius: {max_radius:.2f}")
        self.radius_spin.setRange(0.1, max_radius)
        self.radius_spin.setValue(min(10.0, max_radius * 0.8))
        self.radius_spin.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.status_label.setText("✓ Corner selected! Adjust radius and click Apply")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        
        # Show preview
        self.update_preview()
    
    def on_radius_changed(self):
        """Update preview when radius changes"""
        if hasattr(self, 'corner_data'):
            self.update_preview()
    
    def update_preview(self):
        """Show preview of the fillet"""
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
        
        radius = min(self.radius_spin.value(), self.corner_data['max_radius'])
        arc_points = self.calculate_arc(radius)
        
        if arc_points and len(arc_points) > 1:
            self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.preview_band.setColor(QColor(52, 152, 219, 200))
            self.preview_band.setWidth(3)
            for pt in arc_points:
                self.preview_band.addPoint(pt)
    
    def calculate_arc(self, radius):
        """Calculate arc points for fillet"""
        try:
            p1 = self.corner_data['p1']
            p2 = self.corner_data['p2']
            p3 = self.corner_data['p3']
            angle = self.corner_data['angle']
            
            # Vectors from corner
            v1 = (p1.x() - p2.x(), p1.y() - p2.y())
            v2 = (p3.x() - p2.x(), p3.y() - p2.y())
            
            len1 = math.sqrt(v1[0]**2 + v1[1]**2)
            len2 = math.sqrt(v2[0]**2 + v2[1]**2)
            
            # Unit vectors
            u1 = (v1[0]/len1, v1[1]/len1)
            u2 = (v2[0]/len2, v2[1]/len2)
            
            # Distance from corner to tangent points
            tan_dist = radius / math.tan(angle / 2)
            
            # Tangent points
            t1 = QgsPointXY(p2.x() + u1[0] * tan_dist, p2.y() + u1[1] * tan_dist)
            t2 = QgsPointXY(p2.x() + u2[0] * tan_dist, p2.y() + u2[1] * tan_dist)
            
            # Center point (along angle bisector)
            bisector = (u1[0] + u2[0], u1[1] + u2[1])
            bisector_len = math.sqrt(bisector[0]**2 + bisector[1]**2)
            
            if bisector_len < 0.0001:
                return None
                
            bisector = (bisector[0]/bisector_len, bisector[1]/bisector_len)
            center_dist = radius / math.sin(angle / 2)
            center = QgsPointXY(p2.x() + bisector[0] * center_dist, p2.y() + bisector[1] * center_dist)
            
            # Angles from center to tangent points
            start_angle = math.atan2(t1.y() - center.y(), t1.x() - center.x())
            end_angle = math.atan2(t2.y() - center.y(), t2.x() - center.x())
            
            # Ensure we go the shorter way
            angle_diff = end_angle - start_angle
            if angle_diff < 0:
                angle_diff += 2 * math.pi
            
            # Generate arc points
            points = []
            segments = 30
            for i in range(segments + 1):
                t = i / segments
                a = start_angle + angle_diff * t
                x = center.x() + radius * math.cos(a)
                y = center.y() + radius * math.sin(a)
                points.append(QgsPointXY(x, y))
            
            return points
            
        except Exception as e:
            print(f"Arc calculation error: {e}")
            return None
    
    def apply_fillet(self):
        """Apply the fillet to the polygon"""
        try:
            # Check if layer is editable
            if not self.selected_layer.isEditable():
                reply = QMessageBox.question(self, "Start Editing", 
                    "Layer is not in edit mode.\n\nStart editing now?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.selected_layer.startEditing()
                else:
                    return
            
            radius = min(self.radius_spin.value(), self.corner_data['max_radius'])
            arc_points = self.calculate_arc(radius)
            
            if not arc_points or len(arc_points) < 2:
                QMessageBox.warning(self, "Error", "Failed to calculate arc. Try a smaller radius.")
                return
            
            # Create new vertex list with arc replacing the corner
            new_vertices = []
            for i, v in enumerate(self.vertices):
                if i == self.selected_vertex_index:
                    new_vertices.extend(arc_points)
                else:
                    new_vertices.append(v)
            
            # Close the polygon ring
            if len(new_vertices) > 1 and new_vertices[0] != new_vertices[-1]:
                new_vertices.append(new_vertices[0])
            
            # Create new geometry
            new_geom = QgsGeometry.fromPolygonXY([new_vertices])
            
            # Check if geometry is valid (QGIS 3.x method)
            if new_geom.isGeosValid() is False:
                QMessageBox.warning(self, "Warning", 
                    "Geometry may be invalid, but attempting to apply...")
            
            # Apply the change
            success = self.selected_layer.changeGeometry(self.selected_feature.id(), new_geom)
            
            if success:
                self.selected_layer.commitChanges()
                self.iface.messageBar().pushMessage(
                    "✅ Success", f"Fillet applied! Radius: {radius:.2f}", 
                    level=0, duration=3
                )
                self.close()
            else:
                QMessageBox.warning(self, "Error", "Failed to update geometry. Check if layer is editable.")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error applying fillet:\n{str(e)}")
    
    def closeEvent(self, event):
        """Clean up when dialog closes"""
        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
        event.accept()


class PolygonPickerTool(QgsMapTool):
    """Tool to pick a polygon by clicking inside it"""
    
    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
    
    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        
        layer = self.canvas.currentLayer()
        if not layer:
            self.dialog.iface.messageBar().pushMessage("Error", "Select a polygon layer first", level=2)
            return
        
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.dialog.iface.messageBar().pushMessage("Error", "Layer must be a polygon layer", level=2)
            return
        
        # Search for polygon containing the click point
        rect = QgsRectangle(point.x() - 0.1, point.y() - 0.1, point.x() + 0.1, point.y() + 0.1)
        request = QgsFeatureRequest().setFilterRect(rect)
        
        found = False
        for feature in layer.getFeatures(request):
            geom = feature.geometry()
            if geom and geom.contains(point):
                self.dialog.polygon_picked(layer, feature)
                found = True
                break
        
        if not found:
            self.dialog.iface.messageBar().pushMessage("Info", "Click INSIDE a polygon", level=1)


class CornerPickerTool(QgsMapTool):
    """Tool to pick a corner vertex"""
    
    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
    
    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        
        if not self.dialog.vertices:
            self.dialog.iface.messageBar().pushMessage("Error", "Select a polygon first", level=2)
            return
        
        # Calculate tolerance in map units (15 pixels)
        tolerance = 20 / self.canvas.mapUnitsPerPixel()
        
        # Find closest vertex
        best_idx = -1
        best_dist = float('inf')
        
        for i, v in enumerate(self.dialog.vertices):
            dist = math.sqrt((v.x() - point.x())**2 + (v.y() - point.y())**2)
            if dist < tolerance and dist < best_dist:
                best_dist = dist
                best_idx = i
        
        if best_idx >= 0:
            self.dialog.corner_picked(best_idx)
        else:
            self.dialog.iface.messageBar().pushMessage("Info", "Click ON a corner vertex", level=1)