import math
import os

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QHBoxLayout, QDoubleSpinBox, QMessageBox
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QCursor, QIcon
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes, Qgis
from qgis.gui import QgsRubberBand, QgsMapTool


class ArcGISProFilletDialog(QDialog):
    """Fillet tool – ArcGIS Pro style (edge click + graphic radius drag)"""

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface  = iface
        self.canvas = iface.mapCanvas()

        self.setWindowTitle("Fillet Tool")
        _icon = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(_icon):
            self.setWindowIcon(QIcon(_icon))

        try:
            self.setWindowFlags(Qt.Tool)
        except AttributeError:
            self.setWindowFlags(Qt.WindowType.Tool)

        self.setMinimumWidth(310)

        # ── state ─────────────────────────────────────────────────────────────
        self.selected_edges  = []
        self.edge_rubbers    = []
        self.preview_rubber  = None
        self.current_layer   = None
        self.current_fid     = None
        self.corner_pt       = None
        self.prev_pt         = None
        self.next_pt         = None
        self.corner_angle    = 0.0
        self.max_radius      = 0.0
        self.original_geom   = None  # Store original geometry for undo
        # ──────────────────────────────────────────────────────────────────────

        self._setup_ui()
        self._start_edge_selection()
        self.move(QCursor.pos())

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)

        self.status = QLabel("🔴 Click first edge")
        self.status.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.status)

        # Radius row
        row = QHBoxLayout()
        row.addWidget(QLabel("Radius:"))
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setDecimals(6)
        self.radius_spin.setRange(1e-9, 999999)
        self.radius_spin.setValue(1.0)
        self.radius_spin.setSingleStep(0.1)
        self.radius_spin.valueChanged.connect(self._on_radius_changed)
        row.addWidget(self.radius_spin)
        layout.addLayout(row)

        self.max_label = QLabel("")
        self.max_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.max_label)

        # Drag button
        self.drag_btn = QPushButton("🖱 Drag to set radius")
        self.drag_btn.setEnabled(False)
        self.drag_btn.setCheckable(True)
        self.drag_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; }"
            "QPushButton:checked { background-color: #e67e22; color: white; }"
        )
        self.drag_btn.clicked.connect(self._toggle_drag_mode)
        layout.addWidget(self.drag_btn)

        # Apply / Clear
        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold;")
        self.apply_btn.clicked.connect(self._apply_fillet)
        btn_row.addWidget(self.apply_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_selection)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    # ── drag-radius mode ──────────────────────────────────────────────────────

    def _toggle_drag_mode(self):
        if self.drag_btn.isChecked():
            self.drag_btn.setText("🖱 Dragging… (click to finish)")
            self.status.setText("🖱 Drag from corner to set radius")
            self.status.setStyleSheet("color: #e67e22; font-weight: bold;")
            self.drag_tool = RadiusDragTool(self.canvas, self)
            self.canvas.setMapTool(self.drag_tool)
        else:
            self._exit_drag_mode()

    def _exit_drag_mode(self):
        """Return to edge-selection tool, un-toggle the button."""
        self.drag_btn.setChecked(False)
        self.drag_btn.setText("🖱 Drag to set radius")
        self.status.setText("✅ Ready – adjust radius or Apply")
        self.status.setStyleSheet("color: #27ae60; font-weight: bold;")
        self.canvas.setMapTool(self.edge_tool)

    def update_radius_from_drag(self, map_point):
        """Called continuously by RadiusDragTool on mouse-move"""
        if not self.corner_pt:
            return

        p1, p2, p3 = self.prev_pt, self.corner_pt, self.next_pt
        v1x, v1y = p1.x()-p2.x(), p1.y()-p2.y()
        v2x, v2y = p3.x()-p2.x(), p3.y()-p2.y()
        l1 = math.hypot(v1x, v1y)
        l2 = math.hypot(v2x, v2y)
        if l1 < 1e-12 or l2 < 1e-12:
            return
        u1x, u1y = v1x/l1, v1y/l1
        u2x, u2y = v2x/l2, v2y/l2
        bx, by = u1x+u2x, u1y+u2y
        bl = math.hypot(bx, by)
        if bl < 1e-12:
            return
        bx, by = bx/bl, by/bl

        dx = map_point.x() - p2.x()
        dy = map_point.y() - p2.y()
        proj = dx*bx + dy*by
        if proj < 0:
            proj = -proj

        radius = proj * math.sin(self.corner_angle / 2)
        radius = max(1e-9, min(radius, self.max_radius))

        self.radius_spin.blockSignals(True)
        self.radius_spin.setValue(radius)
        self.radius_spin.blockSignals(False)
        self._show_preview()

    # ── edge selection ────────────────────────────────────────────────────────

    def _start_edge_selection(self):
        self.edge_tool = EdgeSelectTool(self.canvas, self)
        self.canvas.setMapTool(self.edge_tool)

    def add_edge(self, layer, feature_id, edge_idx, start, end):
        if len(self.selected_edges) == 0:
            self.current_layer = layer
            self.current_fid   = feature_id
            # Store original geometry for undo BEFORE any changes
            self.original_geom = layer.getFeature(feature_id).geometry()
            self.status.setText("🟠 Click the adjacent edge (sharing a vertex)")
            self.status.setStyleSheet("color: #e67e22; font-weight: bold;")
        elif len(self.selected_edges) == 1:
            self.status.setText("🟢 Processing…")
            self.status.setStyleSheet("color: #27ae60; font-weight: bold;")

        self.selected_edges.append({
            'feature_id': feature_id, 'edge_idx': edge_idx,
            'start': QgsPointXY(start.x(), start.y()),
            'end':   QgsPointXY(end.x(),   end.y()),
        })

        rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        rb.setColor(QColor(255, 0, 0, 180))
        rb.setWidth(3)
        rb.addPoint(start)
        rb.addPoint(end)
        self.edge_rubbers.append(rb)

        if len(self.selected_edges) == 2:
            self._calculate_corner()

    # ── corner geometry ───────────────────────────────────────────────────────

    def _calculate_corner(self):
        e1, e2 = self.selected_edges

        corner = prev = nxt = None
        if self._eq(e1['start'], e2['start']):
            corner, prev, nxt = e1['start'], e1['end'], e2['end']
        elif self._eq(e1['start'], e2['end']):
            corner, prev, nxt = e1['start'], e1['end'], e2['start']
        elif self._eq(e1['end'], e2['start']):
            corner, prev, nxt = e1['end'], e1['start'], e2['end']
        elif self._eq(e1['end'], e2['end']):
            corner, prev, nxt = e1['end'], e1['start'], e2['start']

        if corner is None:
            self._msg("Edges are not adjacent – no shared vertex", level=2)
            self._clear_selection()
            return

        self.corner_pt = corner
        self.prev_pt = prev
        self.next_pt = nxt
        self.corner_angle = self._angle(prev, corner, nxt)
        self.max_radius = min(self._dist(prev, corner),
                              self._dist(nxt, corner)) * math.tan(self.corner_angle / 2)

        default = round(self.max_radius * 0.5, 6)
        self.radius_spin.setValue(default if default > 0 else self.max_radius)

        mr_str = f"{self.max_radius:.6g}"
        self.max_label.setText(f"max: {mr_str}")
        self.status.setText(f"✅ Ready – max {mr_str}")
        self.status.setStyleSheet("color: #27ae60; font-weight: bold;")
        self.apply_btn.setEnabled(True)
        self.drag_btn.setEnabled(True)
        self._show_preview()

    def _on_radius_changed(self):
        if self.corner_pt:
            self._show_preview()

    # ── arc math ──────────────────────────────────────────────────────────────

    def _calc_arc(self, radius):
        if not self.corner_pt:
            return None
        try:
            p1, p2, p3 = self.prev_pt, self.corner_pt, self.next_pt
            angle = self.corner_angle

            v1x, v1y = p1.x()-p2.x(), p1.y()-p2.y()
            v2x, v2y = p3.x()-p2.x(), p3.y()-p2.y()
            l1 = math.hypot(v1x, v1y)
            u1x, u1y = v1x/l1, v1y/l1
            l2 = math.hypot(v2x, v2y)
            u2x, u2y = v2x/l2, v2y/l2

            t_dist = radius / math.tan(angle / 2)
            t1x = p2.x() + u1x * t_dist
            t1y = p2.y() + u1y * t_dist
            t2x = p2.x() + u2x * t_dist
            t2y = p2.y() + u2y * t_dist

            bx, by = u1x + u2x, u1y + u2y
            bl = math.hypot(bx, by)
            if bl < 1e-12:
                return None
            bx /= bl
            by /= bl

            cd = radius / math.sin(angle / 2)
            cx = p2.x() + bx * cd
            cy = p2.y() + by * cd

            a1 = math.atan2(t1y - cy, t1x - cx)
            a2 = math.atan2(t2y - cy, t2x - cx)
            diff = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi

            return [QgsPointXY(cx + radius * math.cos(a1 + diff * (i / 60)),
                               cy + radius * math.sin(a1 + diff * (i / 60)))
                    for i in range(61)]
        except Exception as e:
            print(f"[Fillet] arc error: {e}")
            return None

    # ── preview ───────────────────────────────────────────────────────────────

    def _show_preview(self):
        if self.preview_rubber:
            try:
                self.canvas.scene().removeItem(self.preview_rubber)
            except:
                pass
            self.preview_rubber = None

        if not self.corner_pt:
            return

        radius = self.radius_spin.value()
        if radius <= 0:
            return

        pts = self._calc_arc(radius)
        if pts and len(pts) > 1:
            self.preview_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.preview_rubber.setColor(QColor(52, 152, 219, 200))
            self.preview_rubber.setWidth(4)
            for pt in pts:
                self.preview_rubber.addPoint(pt)

    # ── apply fillet with undo support ────────────────────────────────────────

    def _apply_fillet(self):
        try:
            if not self.current_layer:
                self._msg("No layer selected", level=3)
                return

            if not self.current_layer.isEditable():
                reply = QMessageBox.question(
                    self, "Start Editing",
                    "Layer is not in edit mode. Start editing?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                self.current_layer.startEditing()

            radius = self.radius_spin.value()
            if radius > self.max_radius:
                self._msg(f"Radius clamped to max {self.max_radius:.6g}", level=2)
                radius = self.max_radius
            if radius <= 0:
                self._msg("Radius must be greater than 0", level=3)
                return

            arc_pts = self._calc_arc(radius)
            if not arc_pts or len(arc_pts) < 2:
                self._msg("Failed to calculate arc", level=3)
                return

            feature = self.current_layer.getFeature(self.current_fid)
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                self._msg("Empty geometry", level=3)
                return

            verts = [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]
            if len(verts) > 1 and self._eq(verts[0], verts[-1]):
                verts.pop()

            corner_idx = next((i for i, v in enumerate(verts)
                               if self._eq(v, self.corner_pt)), None)
            if corner_idx is None:
                self._msg("Corner vertex not found", level=3)
                return

            n = len(verts)
            prev_idx = (corner_idx - 1) % n
            ordered = arc_pts if self._eq(verts[prev_idx], self.prev_pt) else list(reversed(arc_pts))

            new_verts = []
            for i, v in enumerate(verts):
                if i == corner_idx:
                    new_verts.extend(ordered)
                else:
                    new_verts.append(v)

            if not self._eq(new_verts[0], new_verts[-1]):
                new_verts.append(new_verts[0])

            new_geom = QgsGeometry.fromPolygonXY([new_verts])

            if not new_geom.isGeosValid():
                fixed = new_geom.makeValid()
                if fixed and not fixed.isEmpty():
                    if fixed.wkbType() in (
                            QgsWkbTypes.MultiPolygon, QgsWkbTypes.MultiPolygonZ,
                            QgsWkbTypes.MultiPolygonM, QgsWkbTypes.MultiPolygonZM):
                        parts = sorted(fixed.asGeometryCollection(),
                                       key=lambda g: g.area(), reverse=True)
                        fixed = parts[0] if parts else fixed
                    if fixed.isGeosValid():
                        new_geom = fixed
                    else:
                        self._msg("Geometry invalid – try smaller radius", level=3)
                        return
                else:
                    self._msg("Invalid geometry – try smaller radius", level=3)
                    return

            # Apply the change WITHOUT committing
            # This keeps the layer in edit mode and allows Ctrl+Z
            if self.current_layer.changeGeometry(feature.id(), new_geom):
                self.iface.messageBar().pushMessage(
                    "Success", f"Fillet applied – radius {radius:.6g} (press Ctrl+Z to undo)",
                    level=Qgis.Success, duration=3
                )
                # Refresh canvas to show changes
                self.canvas.refresh()
                # Keep layer in edit mode - do NOT commit
                # User can manually save or undo with Ctrl+Z
                self._clear_selection()
                self.close()
            else:
                self._msg("Failed to update geometry", level=3)

        except Exception as e:
            self._msg(f"Error: {e}", level=3)
            import traceback
            traceback.print_exc()

    # ── clear selection ───────────────────────────────────────────────────────

    def _clear_selection(self):
        # Exit drag mode cleanly
        if hasattr(self, 'drag_btn') and self.drag_btn.isChecked():
            self._exit_drag_mode()

        for r in self.edge_rubbers:
            try:
                self.canvas.scene().removeItem(r)
            except:
                pass
        if self.preview_rubber:
            try:
                self.canvas.scene().removeItem(self.preview_rubber)
            except:
                pass

        self.selected_edges = []
        self.edge_rubbers = []
        self.preview_rubber = None
        self.current_layer = None
        self.current_fid = None
        self.corner_pt = None
        self.prev_pt = None
        self.next_pt = None
        self.corner_angle = 0.0
        self.max_radius = 0.0
        # Keep original_geom for potential undo reference

        if hasattr(self, 'apply_btn'):
            self.apply_btn.setEnabled(False)
        if hasattr(self, 'drag_btn'):
            self.drag_btn.setEnabled(False)
            self.drag_btn.setChecked(False)
            self.drag_btn.setText("🖱 Drag to set radius")
        if hasattr(self, 'max_label'):
            self.max_label.setText("")
        if hasattr(self, 'radius_spin'):
            self.radius_spin.setValue(1.0)
        if hasattr(self, 'status'):
            self.status.setText("🔴 Click first edge")
            self.status.setStyleSheet("font-weight: bold;")
        
        self.canvas.refresh()

    def closeEvent(self, event):
        self._clear_selection()
        event.accept()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _eq(self, a, b, tol=1e-9):
        return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol

    def _dist(self, a, b):
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    def _angle(self, p1, p2, p3):
        v1x, v1y = p1.x() - p2.x(), p1.y() - p2.y()
        v2x, v2y = p3.x() - p2.x(), p3.y() - p2.y()
        l1 = math.hypot(v1x, v1y)
        l2 = math.hypot(v2x, v2y)
        if l1 < 1e-12 or l2 < 1e-12:
            return math.pi / 2
        return math.acos(max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (l1 * l2))))

    def _msg(self, text, level=1, duration=3):
        lvl = {0: Qgis.Success, 1: Qgis.Info, 2: Qgis.Warning, 3: Qgis.Critical}
        ttl = {0: "Success", 1: "Info", 2: "Warning", 3: "Error"}
        self.iface.messageBar().pushMessage(ttl[level], text, lvl[level], duration)


# ── RadiusDragTool ────────────────────────────────────────────────────────────

class RadiusDragTool(QgsMapTool):
    """Live-drag tool: move the mouse and the arc updates in real time."""

    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog

    def canvasMoveEvent(self, event):
        pt = self.toMapCoordinates(event.pos())
        self.dialog.update_radius_from_drag(pt)

    def canvasPressEvent(self, event):
        pt = self.toMapCoordinates(event.pos())
        self.dialog.update_radius_from_drag(pt)
        self.dialog._exit_drag_mode()


# ── EdgeSelectTool ────────────────────────────────────────────────────────────

class EdgeSelectTool(QgsMapTool):

    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog

    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        layer = self.canvas.currentLayer()

        if not layer:
            self.dialog._msg("Select a polygon layer first", level=2)
            return
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.dialog._msg("Active layer is not a polygon layer", level=2)
            return

        tol = 20 / self.canvas.mapUnitsPerPixel()
        best = None
        best_d = float('inf')

        for feat in layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            verts = [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]
            if len(verts) > 1 and verts[0] == verts[-1]:
                verts.pop()
            for i in range(len(verts)):
                s, e = verts[i], verts[(i + 1) % len(verts)]
                d = self._seg_dist(point, s, e)
                if d < tol and d < best_d:
                    best_d = d
                    best = (feat.id(), i, s, e, layer)

        if best:
            fid, idx, s, e, lyr = best
            self.dialog.add_edge(lyr, fid, idx, s, e)
        else:
            self.dialog._msg("No edge found – click closer to a polygon edge", level=1)

    def _seg_dist(self, p, a, b):
        ax, ay = b.x() - a.x(), b.y() - a.y()
        lsq = ax * ax + ay * ay
        if lsq < 1e-20:
            return math.hypot(p.x() - a.x(), p.y() - a.y())
        t = max(0.0, min(1.0, ((p.x() - a.x()) * ax + (p.y() - a.y()) * ay) / lsq))
        return math.hypot(p.x() - (a.x() + t * ax), p.y() - (a.y() + t * ay))
