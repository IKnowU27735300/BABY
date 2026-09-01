"""
ui/system_tray.py — System tray icon with status menu.
Shows whether Baby is active, and provides quick settings access.
"""

from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QBrush
from PySide6.QtCore import Qt, Signal, QObject
from loguru import logger


def _app_icon_path() -> str | None:
    """Resolve the BABY icon in dev and frozen builds.

    The icon ships inside the frozen app via Baby.spec datas ("icons").
    """
    if getattr(sys, "frozen", False):
        candidate = Path(sys._MEIPASS) / "icons" / "BABY.ico"
        return str(candidate) if candidate.exists() else None
    else:
        for candidate in [
            Path(__file__).resolve().parent.parent / "assets" / "BABY.ico",
            Path(__file__).resolve().parent.parent / "dist" / "BABY.ico",
        ]:
            if candidate.exists():
                return str(candidate)
        return None


def _make_icon(color: str, size: int = 32) -> QIcon:
    """BABY icon tinted with a small status-dot in the bottom-right corner."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    icon_path = _app_icon_path()
    if icon_path:
        painter.drawPixmap(0, 0, size, size, QPixmap(icon_path))
    dot = max(7, size // 4)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(size - dot - 1, size - dot - 1, dot, dot)
    painter.end()
    return QIcon(pix)


_ICONS: dict[str, QIcon] | None = None

def get_icon(state: str) -> QIcon:
    global _ICONS
    if _ICONS is None:
        _ICONS = {
            "idle":      _make_icon("#555555"),
            "listening": _make_icon("#7C7CFF"),
            "thinking":  _make_icon("#FF9F0A"),
            "speaking":  _make_icon("#30D158"),
            "consent":   _make_icon("#FFB347"),
            "error":     _make_icon("#FF453A"),
        }
    return _ICONS.get(state, _ICONS["idle"])


class SystemTrayManager(QObject):
    quit_requested = Signal()
    settings_requested = Signal()
    reset_position_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(parent)
        self._tray.setToolTip("BABY — Local AI Assistant")
        self._tray.setIcon(get_icon("idle"))
        self._build_menu()
        self._tray.show()
        logger.info("[Tray] System tray icon shown")

    def _build_menu(self):
        menu = QMenu()

        menu.addAction("✦ BABY v1.0").setEnabled(False)
        menu.addSeparator()

        status_action = menu.addAction("● Idle")
        status_action.setEnabled(False)
        self._status_action = status_action

        menu.addSeparator()
        menu.addAction("⚙  Settings", self._open_settings)
        menu.addAction("🎯  Reset Island Position", self.reset_position_requested.emit)
        menu.addAction("📋  View Logs", self._open_logs)
        menu.addSeparator()
        menu.addAction("✕  Quit BABY", self.quit_requested.emit)

        self._tray.setContextMenu(menu)

    def set_state(self, state: str):
        icon   = get_icon(state)
        labels = {
            "idle":      "● Idle",
            "listening": "🎙 Listening...",
            "thinking":  "⟳ Thinking...",
            "speaking":  "🔊 Speaking",
            "consent":   "⚡ Waiting for approval",
            "error":     "⚠ Error",
        }
        self._tray.setIcon(icon)
        self._status_action.setText(labels.get(state, "● Idle"))
        self._tray.setToolTip(f"BABY — {labels.get(state, 'Idle')}")

    def show_notification(self, title: str, message: str, duration_ms: int = 3000):
        self._tray.showMessage(title, message, QSystemTrayIcon.Information, duration_ms)

    def _open_settings(self):
        logger.info("[Tray] Settings requested")
        self.settings_requested.emit()

    def _open_logs(self):
        log_dir = Path("data/logs")
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(["explorer", str(log_dir)], shell=True)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", str(log_dir)])



















