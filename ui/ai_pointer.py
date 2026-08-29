"""
ui/ai_pointer.py — Transparent, click-through AI pointer overlay.
Baby's virtual cursor that can point to things on screen independently of the real mouse.

- Covers the ENTIRE virtual desktop (all monitors).
- Accepts PHYSICAL pixel coordinates (the convention used by mss / PyAutoGUI /
  the vision agent) and converts them to Qt logical coordinates per-screen,
  so pointing stays accurate on DPI-scaled (125%/150%/200%) and multi-monitor
  setups.
- Smooth animated movement (OutCubic) plus a soft pulsing ring.
- Region highlight mode: draws a glowing circle/rounded-rect mark around a
  screen area (e.g. an app icon, a dialog, a button) so Baby can point at
  things that aren't a single pixel.
"""

from __future__ import annotations

from PySide6.QtCore import (QPointF, QRectF, QAbstractAnimation,
                            QPropertyAnimation, QEasingCurve, Qt, Property,
                            Signal, Slot)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QBrush, QRadialGradient, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget


class AIPointerOverlay(QWidget):
    _move_trigger   = Signal(float, float, str)
    _region_trigger = Signal(float, float, float, float, str)
    _hide_trigger   = Signal()

    _MOVE_MS  = 450   # pointer glide duration
    _PULSE_MS = 900   # one full ring pulse

    def __init__(self):
        super().__init__()

        self._cx     = 0.0    # current position (logical, widget space)
        self._cy     = 0.0
        self._vis    = False
        self._label  = "AI"
        self._pulse  = 0.0    # 0..1 ring pulse phase
        self._ever_moved = False

        self._region: QRectF | None = None  # region-highlight box (logical)
        self._region_label = ""

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput,   # KEY: click-through
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_NoSystemBackground)

        # Cover the entire virtual desktop — every monitor, including secondary
        # displays with negative origins or different DPI scaling.
        self._virtual = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(self._virtual)
        # Don't show on startup — only show when pointer is needed

        # Animated glide between positions
        from PySide6.QtCore import QByteArray
        self._pos_anim = QPropertyAnimation(self, QByteArray(b"pointer_pos"), self)
        self._pos_anim.setDuration(self._MOVE_MS)
        self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Pulsing ring around the pointer
        self._pulse_anim = QPropertyAnimation(self, QByteArray(b"pulse"), self)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setDuration(self._PULSE_MS)
        self._pulse_anim.setLoopCount(-1)

        self._move_trigger.connect(self._move_to_slot, Qt.QueuedConnection)
        self._region_trigger.connect(self._highlight_region_slot, Qt.QueuedConnection)
        self._hide_trigger.connect(self._hide_slot, Qt.QueuedConnection)

    # ─── Animated properties ──────────────────────────────────────────────────

    def _get_pointer_pos(self) -> QPointF:
        return QPointF(self._cx, self._cy)

    def _set_pointer_pos(self, pos: QPointF):
        self._cx = pos.x()
        self._cy = pos.y()
        self.update()

    pointer_pos = Property(QPointF, _get_pointer_pos, _set_pointer_pos)  # type: ignore[call-overload]

    def _get_pulse(self) -> float:
        return self._pulse

    def _set_pulse(self, v: float):
        self._pulse = v
        self.update()

    pulse = Property(float, _get_pulse, _set_pulse)  # type: ignore[call-overload]

    # ─── Physical → logical coordinate conversion ─────────────────────────────

    @staticmethod
    def _screen_for_physical(x: float, y: float):
        """Return the QScreen whose physical pixel rect contains (x, y)."""
        for screen in QGuiApplication.screens():
            dpr = screen.devicePixelRatio()
            geo = screen.geometry()
            pr = QRectF(geo.x() * dpr, geo.y() * dpr,
                        geo.width() * dpr, geo.height() * dpr)
            if pr.contains(QPointF(x, y)):
                return screen
        return QGuiApplication.primaryScreen()

    def _to_logical(self, x: float, y: float) -> QPointF:
        """Convert a physical-pixel coordinate into this widget's logical space."""
        screen = self._screen_for_physical(x, y)
        dpr = screen.devicePixelRatio()
        geo = screen.geometry()
        phys_left = geo.x() * dpr
        phys_top  = geo.y() * dpr
        logical_x = geo.x() + (x - phys_left) / dpr
        logical_y = geo.y() + (y - phys_top)  / dpr
        return QPointF(logical_x, logical_y)

    # ─── Public API ──────────────────────────────────────────────────────────

    def move_to(self, x: float, y: float, label: str = "AI"):
        """Move the AI pointer to a PHYSICAL pixel position. Thread-safe."""
        self._move_trigger.emit(float(x), float(y), label)

    def highlight_region(self, x: float, y: float, w: float, h: float,
                         label: str = "Look Here"):
        """Draw a glowing circle mark around a PHYSICAL-pixel region box.

        Center of the region becomes the pointer anchor; the mark pulses
        around the whole area. Thread-safe.
        """
        self._region_trigger.emit(float(x), float(y), float(w), float(h), label)

    def hide_pointer(self):
        """Hide the AI pointer. Thread-safe."""
        self._hide_trigger.emit()

    @Slot(float, float, str)
    def _move_to_slot(self, x: float, y: float, label: str):
        target = self._to_logical(x, y)
        self._label = label
        self._vis   = True
        self.show()

        self._pos_anim.stop()
        if not self._ever_moved:
            # First move — appear instantly, no cross-screen glide.
            self._ever_moved = True
            self._cx, self._cy = target.x(), target.y()
            self._pos_anim.setStartValue(target)
            self._pos_anim.setEndValue(target)
        else:
            self._pos_anim.setStartValue(QPointF(self._cx, self._cy))
            self._pos_anim.setEndValue(target)
        self._pos_anim.start()

        if self._pulse_anim.state() != QAbstractAnimation.State.Running:
            self._pulse_anim.start()

    @Slot()
    def _hide_slot(self):
        self._vis = False
        self._region = None
        self._pos_anim.stop()
        self._pulse_anim.stop()
        self.hide()
        self.update()

    @Slot(float, float, float, float, str)
    def _highlight_region_slot(self, x: float, y: float, w: float, h: float, label: str):
        """Convert a physical pixel region into logical space and show the mark."""
        tl = self._to_logical(x, y)
        br = self._to_logical(x + w, y + h)
        rect = QRectF(tl, br).normalized()
        # Center of the region is where the ring anchor sits
        self._cx, self._cy = rect.center().x(), rect.center().y()
        self._region = rect
        self._region_label = label
        self._vis = True
        self._ever_moved = True
        self.show()

        self._pos_anim.stop()
        self._pos_anim.setStartValue(self.pointer_pos)
        self._pos_anim.setEndValue(self.pointer_pos)

        if self._pulse_anim.state() != QAbstractAnimation.State.Running:
            self._pulse_anim.start()
        self.update()

    async def async_move_to(self, x: int, y: int, label: str = "AI"):
        """Async-friendly wrapper — safe to call from asyncio tasks."""
        self.move_to(x, y, label)

    # ─── Painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._vis:
            return

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

        if self._region is not None:
            self._paint_region_mark(painter)
            return

        x, y = int(self._cx), int(self._cy)
        pulse = self._pulse  # 0..1 phase

        # Outer soft glow
        glow_r = 26 + int(6 * pulse)
        grad = QRadialGradient(x, y, glow_r)
        grad.setColorAt(0.0, QColor(124, 124, 255, 60))
        grad.setColorAt(1.0, QColor(124, 124, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(x - glow_r, y - glow_r, glow_r * 2, glow_r * 2)

        # Pulsing ring — expands and fades as the pulse phase advances
        ring_r = 11 + int(9 * pulse)
        ring_a = int(160 - 120 * pulse)
        painter.setPen(QPen(QColor(124, 124, 255, ring_a), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(x - ring_r, y - ring_r, ring_r * 2, ring_r * 2)

        # Filled circle
        painter.setBrush(QBrush(QColor(124, 124, 255, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(x - 8, y - 8, 16, 16)

        # White center dot
        painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
        painter.drawEllipse(x - 3, y - 3, 6, 6)

        # Label pill
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        lw = max(30, painter.fontMetrics().horizontalAdvance(self._label) + 12)
        painter.setBrush(QBrush(QColor(13, 13, 15, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(x + 12, y - 10, lw, 18), 6, 6)
        painter.setPen(QPen(QColor(180, 180, 255, 230)))
        painter.drawText(QRectF(x + 12, y - 10, lw, 18), Qt.AlignCenter, self._label)

    def _paint_region_mark(self, painter: QPainter):
        """Draw a pulsing circle/rounded-rect mark around a screen region."""
        if self._region is None:
            return
        rect = self._region.normalized()
        pulse = self._pulse

        # Minimum mark size so tiny elements still get a visible circle
        w = max(rect.width(), 56.0)
        h = max(rect.height(), 42.0)
        cx, cy = rect.center().x(), rect.center().y()
        grow = 8 + int(5 * pulse)

        mark = QRectF(cx - w / 2 - grow, cy - h / 2 - grow,
                      w + 2 * grow, h + 2 * grow)

        # Soft glow fill
        fill = QColor(124, 124, 255, int(28 + 18 * pulse))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(mark, 16, 16)

        # Pulsing outline
        ring_a = int(150 - 90 * pulse)
        painter.setPen(QPen(QColor(124, 124, 255, ring_a), 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(mark, 16, 16)

        # Inner accent border
        inner = mark.adjusted(5, 5, -5, -5)
        painter.setPen(QPen(QColor(190, 190, 255, 120), 1.2))
        painter.drawRoundedRect(inner, 12, 12)

        # Corner dots (like a crop/highlight marker)
        dot_r = 4
        painter.setBrush(QBrush(QColor(124, 124, 255, 230)))
        painter.setPen(Qt.NoPen)
        for (dx, dy) in ((mark.left(), mark.top()), (mark.right(), mark.top()),
                         (mark.left(), mark.bottom()), (mark.right(), mark.bottom())):
            painter.drawEllipse(int(dx) - dot_r, int(dy) - dot_r,
                                dot_r * 2, dot_r * 2)

        # Label pill above the mark with a small arrow pointing down at it
        label = self._region_label
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        lw = max(30, painter.fontMetrics().horizontalAdvance(label) + 14)
        lx = cx - lw / 2
        ly = mark.top() - 30
        if ly < 4:  # keep the pill on-screen
            ly = mark.bottom() + 8
            arrow_tip_y = mark.bottom() + 2
        else:
            arrow_tip_y = mark.top() - 2
        painter.setBrush(QBrush(QColor(13, 13, 15, 210)))
        painter.drawRoundedRect(QRectF(lx, ly, lw, 20), 6, 6)
        painter.setPen(QPen(QColor(180, 180, 255, 235)))
        painter.drawText(QRectF(lx, ly, lw, 20), Qt.AlignCenter, label)

        # Arrow from the label pill toward the mark
        painter.setPen(QPen(QColor(180, 180, 255, 200), 2.0))
        painter.setBrush(Qt.NoBrush)
        ax = int(cx)
        if arrow_tip_y < mark.top():  # label above → arrow points down
            y0 = int(ly + 20)
            y1 = int(arrow_tip_y)
            painter.drawLine(ax, y0, ax, y1)
            painter.setBrush(QBrush(QColor(180, 180, 255, 200)))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygonF([
                QPointF(ax - 5, y1 + 2), QPointF(ax + 5, y1 + 2), QPointF(ax, y1 - 4),
            ]))
        else:  # label below → arrow points up
            y0 = int(ly)
            y1 = int(arrow_tip_y)
            painter.drawLine(ax, y0, ax, y1)
            painter.setBrush(QBrush(QColor(180, 180, 255, 200)))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygonF([
                QPointF(ax - 5, y1 - 2), QPointF(ax + 5, y1 - 2), QPointF(ax, y1 + 4),
            ]))



















