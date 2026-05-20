from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, 
    QMessageBox, QHBoxLayout, QDoubleSpinBox, QRadioButton,
    QButtonGroup, QGroupBox, QComboBox
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsGeometry, QgsPointXY, QgsProject, QgsFeatureRequest,
    QgsRectangle, QgsWkbTypes, QgsDistanceArea
)
from qgis.gui import QgsRubberBand, QgsMapTool, QgsMapMouseEvent
import math


class SimpleFilletDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.setWindowTitle("Fillet Tool - ArcGIS Pro Style")
        self.setMinimumWidth(480)
        
        # Store data
        self.selected_layer = None
        self.selected_feature = None
        self.selected_vertex_index = None
        self.vertices = []
        self.rubber_band = None
        self.preview_band = None
        self.radius_rubber_band = None
        
        # Arc direction (normal or reversed)
        self.arc_reversed = False
        
        # Radius selection mode
        self.radius_selection_mode = False
        self.radius_start_point = None
        self.radius_current_point = None
        
        # Distance calculator
        self.distance_calc = QgsDistanceArea()
        self.distance_calc.setEllipsoid('WGS84')
        
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
            "4️⃣ Choose arc direction (Normal or Reverse)\n"
            "5️⃣ Set radius (type value OR pick two points on map)\n"
            "6️⃣ Click 'Apply Fillet'"
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
        
        # Arc Direction (Reverse option - like ArcGIS Pro)
        direction_group = QGroupBox("Arc Direction")
        direction_layout = QHBoxLayout()
        
        self.normal_radio = QRadioButton("↗ Normal (Convex)")
        self.normal_radio.setChecked(True)
        self.reverse_radio = QRadioButton("↙ Reverse (Concave)")
        
        self.normal_radio.toggled.connect(self.on_direction_changed)
        self.reverse_radio.toggled.connect(self.on_direction_changed)
        
        direction_layout.addWidget(self.normal_radio)
        direction_layout.addWidget(self.reverse_radio)
        direction_group.setLayout(direction_layout)
        layout.addWidget(direction_group)
        
        # Radius input method
        radius_method_group = QGroupBox("Radius Input Method")
        radius_method_layout = QVBoxLayout()
        
        self.radio_type = QRadioButton("✏️ Type value manually")
        self.radio_type.setChecked(True)
        self.radio_pick = QRadioButton("🎯 Pick distance from map (click two points)")
        
        self.radio_type.toggled.connect(self.on_radius_method_changed)
        self.radio_pick.toggled.connect(self.on_radius_method_changed)
        
        radius_method_layout.addWidget(self.radio_type)
        radius_method_layout.addWidget(self.radio_pick)
        radius_method_group.setLayout(radius_method_layout)
        layout.addWidget(radius_method_group)
        
        # Buttons for picking radius
        pick_layout = QHBoxLayout()
        self.pick_radius_btn = QPushButton("📏 Pick Radius from Map")
        self.pick_radius_btn.clicked.connect(self.activate_radius_picker)
        self.pick_radius_btn.setEnabled(False)
        self.pick_radius_btn.setStyleSheet("background-color: #9b59b6; color: white; padding: 5px;")
        pick_layout.addWidget(self.pick_radius_btn)
        
        self.clear_radius_btn = QPushButton("Clear")
        self.clear_radius_btn.clicked.connect(self.clear_radius_selection)
        self.clear_radius_btn.setEnabled(False)
        pick_layout.addWidget(self.clear_radius_btn)
        layout.addLayout(pick_layout)
        
        # Number input
        number_layout = QHBoxLayout()
        number_layout.addWidget(QLabel("Radius (map units):"))
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.1, 100000)
        self.radius_spin.setValue(10.0)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setEnabled(True)
        self.radius_spin.valueChanged.connect(self.on_radius_changed)
        number_layout.addWidget(self.radius_spin)
        layout.addLayout(number_layout)
        
        # Measured radius display
        self.measured_radius_label = QLabel("📐 Measured radius: --")
        self.measured_radius_label.setStyleSheet("color: #8e44ad; font-style: italic;")
        layout.addWidget(self.measured_radius_label)
        
        # Buttons for polygon/corner selection
        btn_layout = QHBoxLayout()
        
        self.pick_polygon_btn = QPushButton("1. Pick Polygon")
        self.pick_polygon_btn.clicked.connect(self.pick_polygon)
        self.pick_polygon_btn.setStyleSheet("background-color: #3498db; color: white; padding: 8px; font-weight: bold; border-radius: 3px;")
        btn_layout.addWidget(self.pick_polygon_btn)
        
        self.pick_corner_btn = QPushButton("2. Pick Corner")
        self.pick_corner_btn.clicked.connect(self.pick_corner)
        self.pick_corner_btn.setEnabled(False)
        self.pick_corner_btn.setStyleSheet("background-color: #95a5a6; color: white; padding: 8px; font-weight: bold; border-radius: 3px;")
        btn_layout.addWidget(self.pick_corner_btn)
        
        layout.addLayout(btn_layout)
        
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
        self.radius_picker = RadiusPickerTool(self.canvas, self)
    
    def on_direction_changed(self):
        """Handle arc direction change (normal vs reverse)"""
        self.arc_reversed = self.reverse_radio.isChecked()
        if hasattr(self, 'corner_data'):
            self.update_preview()
            # Update status message
            if self.arc_reversed:
                self.status_label.setText("✓ Arc direction: Reverse (Concave) - Preview updated")
            else:
                self.status_label.setText("✓ Arc direction: Normal (Convex) - Preview updated")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
    
    def on_radius_method_changed(self):
        """Handle radius input method change"""
        if self.radio_type.isChecked():
            self.radius_spin.setEnabled(True)
            self.pick_radius_btn.setEnabled(False)
            self.clear_radius_btn.setEnabled(False)
            self.measured_radius_label.setText("📐 Measured radius: --")
            if hasattr(self, 'corner_data'):
                self.radius_spin.setValue(min(10.0, self.corner_data['max_radius']))
        else:
            self.radius_spin.setEnabled(False)
            self.pick_radius_btn.setEnabled(True)
            self.clear_radius_btn.setEnabled(False)
    
    def activate_radius_picker(self):
        """Activate map tool for picking radius distance"""
        self.radius_selection_mode = True
        self.radius_start_point = None
        self.radius_current_point = None
        self.canvas.setMapTool(self.radius_picker)
        self.status_label.setText("📏 Click two points to define radius distance")
        self.status_label.setStyleSheet("color: #9b59b6; font-weight: bold;")
    
    def add_radius_point(self, point):
        """Add a point for radius measurement"""
        if self.radius_start_point is None:
            # First click
            self.radius_start_point = point
            
            # Show start point
            if self.radius_rubber_band:
                self.canvas.scene().removeItem(self.radius_rubber_band)
            self.radius_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.radius_rubber_band.setColor(QColor(155, 89, 182, 200))
            self.radius_rubber_band.setWidth(3)
            self.radius_rubber_band.addPoint(point)
            self.radius_rubber_band.addPoint(point)
            
            self.status_label.setText("📏 First point set. Click second point to measure radius")
        else:
            # Second click - calculate distance
            distance = self.distance_calc.measureLine([self.radius_start_point, point])
            
            # Convert to map units
            if hasattr(self, 'corner_data'):
                max_radius = self.corner_data['max_radius']
                if distance > max_radius:
                    self.iface.messageBar().pushMessage(
                        "Warning", f"Radius {distance:.2f} exceeds maximum {max_radius:.2f}. Clamping to max.",
                        level=1, duration=2
                    )
                    distance = max_radius
            
            # Update radius
            self.radius_spin.setValue(distance)
            self.measured_radius_label.setText(f"📐 Measured radius: {distance:.2f}")
            self.clear_radius_btn.setEnabled(True)
            
            # Clear rubber band
            if self.radius_rubber_band:
                self.canvas.scene().removeItem(self.radius_rubber_band)
                self.radius_rubber_band = None
            
            self.radius_selection_mode = False
            self.radius_start_point = None
            self.status_label.setText("✓ Radius measured! Click Apply to fillet")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            
            # Update preview
            self.update_preview()
    
    def clear_radius_selection(self):
        """Clear the radius measurement"""
        self.radius_start_point = None
        if self.radius_rubber_band:
            self.canvas.scene().removeItem(self.radius_rubber_band)
            self.radius_rubber_band = None
        self.measured_radius_label.setText("📐 Measured radius: --")
        self.radius_spin.setValue(self.radius_spin.value())
        self.clear_radius_btn.setEnabled(False)
        if self.radio_pick.isChecked():
            self.status_label.setText("📏 Click two points to define radius distance")
    
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
        
        if geom.isMultipart():
            parts = geom.parts()
            if parts:
                first_part = next(parts)
                for v in first_part.vertices():
                    self.vertices.append(QgsPointXY(v.x(), v.y()))
        else:
            for v in geom.vertices():
                self.vertices.append(QgsPointXY(v.x(), v.y()))
        
        # Remove duplicate last point
        if len(self.vertices) > 1 and self.vertices[0] == self.vertices[-1]:
            self.vertices.pop()
        
        # Update UI
        layer_name = layer.name() if layer.name() else "Unknown"
        self.layer_label.setText(f"📁 Layer: {layer_name}")
        self.polygon_label.setText(f"🔷 Polygon: ID {feature.id()} ({len(self.vertices)} vertices)")
        self.pick_corner_btn.setEnabled(True)
        self.pick_corner_btn.setStyleSheet("background-color: #e67e22; color: white; padding: 8px; font-weight: bold; border-radius: 3px;")
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
        
        # Get the three points
        prev_idx = (vertex_index - 1) % len(self.vertices)
        next_idx = (vertex_index + 1) % len(self.vertices)
        
        p1 = self.vertices[prev_idx]
        p2 = self.vertices[vertex_index]
        p3 = self.vertices[next_idx]
        
        # Calculate edge lengths
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
        
        # Calculate max possible radius
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
        
        # Set default radius
        current_val = self.radius_spin.value()
        if current_val > max_radius:
            self.radius_spin.setValue(max_radius * 0.8)
        
        self.radius_spin.setEnabled(self.radio_type.isChecked())
        self.apply_btn.setEnabled(True)
        self.status_label.setText("✓ Corner selected! Choose arc direction, set radius, click Apply")
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
            # Different colors for normal vs reverse
            if self.arc_reversed:
                color = QColor(231, 76, 60, 200)  # Red for reverse
            else:
                color = QColor(52, 152, 219, 200)  # Blue for normal
            
            self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.preview_band.setColor(color)
            self.preview_band.setWidth(3)
            for pt in arc_points:
                self.preview_band.addPoint(pt)
    
    def calculate_arc(self, radius):
        """Calculate arc points for fillet - supports normal and reverse direction"""
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
            
            # Distance to tangent points
            tan_dist = radius / math.tan(angle / 2)
            
            # Tangent points
            t1 = QgsPointXY(p2.x() + u1[0] * tan_dist, p2.y() + u1[1] * tan_dist)
            t2 = QgsPointXY(p2.x() + u2[0] * tan_dist, p2.y() + u2[1] * tan_dist)
            
            # Center along bisector
            bisector = (u1[0] + u2[0], u1[1] + u2[1])
            bisector_len = math.sqrt(bisector[0]**2 + bisector[1]**2)
            
            if bisector_len < 0.0001:
                return None
                
            bisector = (bisector[0]/bisector_len, bisector[1]/bisector_len)
            center_dist = radius / math.sin(angle / 2)
            
            # For reverse arc, the center is on the opposite side of the bisector
            if self.arc_reversed:
                center_dist = -center_dist
            
            center = QgsPointXY(p2.x() + bisector[0] * center_dist, p2.y() + bisector[1] * center_dist)
            
            # Angles from center to tangent points
            start_angle = math.atan2(t1.y() - center.y(), t1.x() - center.x())
            end_angle = math.atan2(t2.y() - center.y(), t2.x() - center.x())
            
            # For reverse arc, swap start and end or adjust direction
            if self.arc_reversed:
                # Reverse direction arc goes the other way around
                angle_diff = start_angle - end_angle
                if angle_diff < 0:
                    angle_diff += 2 * math.pi
                # Use reverse order
                points = []
                segments = 30
                for i in range(segments + 1):
                    t = i / segments
                    a = end_angle + angle_diff * t
                    x = center.x() + abs(radius) * math.cos(a)
                    y = center.y() + abs(radius) * math.sin(a)
                    points.append(QgsPointXY(x, y))
                return points
            else:
                # Normal arc
                angle_diff = end_angle - start_angle
                if angle_diff < 0:
                    angle_diff += 2 * math.pi
                
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
            
            # Create new vertex list
            new_vertices = []
            for i, v in enumerate(self.vertices):
                if i == self.selected_vertex_index:
                    new_vertices.extend(arc_points)
                else:
                    new_vertices.append(v)
            
            # Close polygon
            if len(new_vertices) > 1 and new_vertices[0] != new_vertices[-1]:
                new_vertices.append(new_vertices[0])
            
            # Create geometry
            new_geom = QgsGeometry.fromPolygonXY([new_vertices])
            
            if not new_geom.isGeosValid():
                QMessageBox.warning(self, "Warning", "Geometry may be invalid, attempting to apply...")
            
            # Apply
            success = self.selected_layer.changeGeometry(self.selected_feature.id(), new_geom)
            
            if success:
                self.selected_layer.commitChanges()
                arc_type = "Reverse" if self.arc_reversed else "Normal"
                self.iface.messageBar().pushMessage(
                    "✅ Success", f"Fillet applied! Radius: {radius:.2f} ({arc_type} arc)", 
                    level=0, duration=3
                )
                self.close()
            else:
                QMessageBox.warning(self, "Error", "Failed to update geometry")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")
    
    def closeEvent(self, event):
        """Clean up"""
        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
        if self.radius_rubber_band:
            self.canvas.scene().removeItem(self.radius_rubber_band)
        event.accept()


class PolygonPickerTool(QgsMapTool):
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
        
        rect = QgsRectangle(point.x() - 0.1, point.y() - 0.1, point.x() + 0.1, point.y() + 0.1)
        request = QgsFeatureRequest().setFilterRect(rect)
        
        for feature in layer.getFeatures(request):
            if feature.geometry() and feature.geometry().contains(point):
                self.dialog.polygon_picked(layer, feature)
                return
        
        self.dialog.iface.messageBar().pushMessage("Info", "Click INSIDE a polygon", level=1)


class CornerPickerTool(QgsMapTool):
    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
    
    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        
        if not self.dialog.vertices:
            return
        
        tolerance = 20 / self.canvas.mapUnitsPerPixel()
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


class RadiusPickerTool(QgsMapTool):
    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
    
    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        self.dialog.add_radius_point(point)
