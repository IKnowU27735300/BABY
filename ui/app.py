"""
ui/app.py — Bootstraps PySide6 app + QML engine + asyncio event loop.
Uses qasync to run asyncio alongside the Qt event loop on the same thread.
"""

from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl
from PySide6.QtQuickControls2 import QQuickStyle
from loguru import logger

from core.config import BabyConfig
from ui.island_controller import BabyIslandController
from ui.system_tray import SystemTrayManager
from ui.ai_pointer import AIPointerOverlay
from ui.settings_bridge import BabySettingsBridge
from ui.image_provider import CameraImageProvider
from tools.screen_tools import set_pointer_overlay


class BabyApp:
    def __init__(self, config: BabyConfig):
        self._config = config
        self._qt_app: QApplication | None = None
        # Single shared engine — all QML windows load into this one engine.
        # Using multiple QQmlApplicationEngine instances in a frozen (PyInstaller)
        # build causes an access violation (0xC0000005): each new engine triggers
        # global QML type re-registration, which corrupts the Qt heap after several
        # engines. Qt officially supports multiple root windows from one engine.
        self._engine: QQmlApplicationEngine | None = None
        self.controller: BabyIslandController | None = None
        self.tray: SystemTrayManager | None = None
        self.pointer: AIPointerOverlay | None = None
        self._settings_bridge = BabySettingsBridge(config)
        # Root object for the settings window (loaded once at startup, hidden)
        self._settings_root = None
        self._orchestrator = None

    def run(self):
        """Start the Qt application. Blocks until the app exits."""
        import qasync   # pip install qasync

        # On Windows, Qt's QML plugin loader (LoadLibraryEx with altered search
        # path) cannot resolve the Qt6*.dll dependencies that live in the PySide6
        # package directory, so every QtQuick.Controls plugin fails to load with
        # "The specified module could not be found." Pre-loading the Qt6 DLLs
        # into the process image lets the engine's loader reuse the already
        # mapped modules. See: qtquickcontrols2plugin.dll load failure.
        if sys.platform == "win32":
            self._preload_qt_dlls()

        from typing import cast
        # Use Basic style — supports full background & handle customization in QML controls.
        # Must be called BEFORE QApplication is created.
        QQuickStyle.setStyle("Basic")
        self._qt_app = cast(QApplication, QApplication.instance() or QApplication(sys.argv))
        self._qt_app.setApplicationName("BABY")
        self._qt_app.setQuitOnLastWindowClosed(False)   # Don't quit on island close

        # Window/taskbar icon: bundled copy in frozen builds, dist/ in dev.
        icon_path = None
        if getattr(sys, "frozen", False):
            candidate = Path(sys._MEIPASS) / "icons" / "BABY.ico"
            if candidate.exists():
                icon_path = str(candidate)
        else:
            candidate = Path(__file__).resolve().parent.parent / "dist" / "BABY.ico"
            if candidate.exists():
                icon_path = str(candidate)
        if icon_path:
            from PySide6.QtGui import QIcon
            self._qt_app.setWindowIcon(QIcon(icon_path))

        # ── Controller (Python ↔ QML bridge) ──────────────────────
        self._camera_image_provider = CameraImageProvider()
        self.controller = BabyIslandController(self._config, camera_image_provider=self._camera_image_provider)

        # ── Single shared QML Engine ────────────────────────────────
        # All windows (DynamicIsland, ResponseWindow, ConsentWindow,
        # CameraPreview, ScreenSharePreview, ScreenSharePicker, Settings)
        # share this one engine. Qt handles multiple top-level windows from
        # a single engine correctly on all platforms.

        self._engine = QQmlApplicationEngine()
        self._engine.addImageProvider("camera", self._camera_image_provider)

        # Register all context properties once, before any load() call.
        ctx = self._engine.rootContext()
        ctx.setContextProperty("babyController", self.controller)
        ctx.setContextProperty("babyController", self.controller)
        ctx.setContextProperty("BabyConfig", self._settings_bridge)
        ctx.setContextProperty("babyConfig", self._settings_bridge)

        # Register neural network backend for knowledge graph visualization
        from ui.neural_backend import NeuralNetworkBackend
        self._neural_backend = NeuralNetworkBackend()
        ctx.setContextProperty("neuralBackend", self._neural_backend)

        # Create bio_db early so settings is available before orchestrator starts
        from biometrics.biometric_db import BiometricDB
        self._early_bio_db = BiometricDB()
        self._settings_bridge._bio_db = self._early_bio_db

        # Log QML errors from the shared engine
        def _on_qml_warnings(warnings):
            for w in warnings:
                logger.warning("[QML] {}:{} {}", w.url().toString(), w.line(), w.description())
        self._engine.warnings.connect(_on_qml_warnings)

        # ── Load all QML windows into the shared engine ─────────────
        # Order matters: DynamicIsland must be first so rootObjects()[0] is
        # the main island (checked immediately below).
        self._engine.load(self._resolve_qml_url("ui/qml/DynamicIsland.qml"))
        if not self._engine.rootObjects():
            logger.critical("Failed to load QML. Check ui/qml/DynamicIsland.qml")
            sys.exit(1)

        self._engine.load(self._resolve_qml_url("ui/qml/ResponseWindow.qml"))
        self._engine.load(self._resolve_qml_url("ui/qml/ConsentWindow.qml"))
        self._engine.load(self._resolve_qml_url("ui/qml/CameraPreviewWindow.qml"))
        self._engine.load(self._resolve_qml_url("ui/qml/ScreenSharePreviewWindow.qml"))
        self._engine.load(self._resolve_qml_url("ui/qml/ScreenSharePickerWindow.qml"))

        # Settings panel — loaded once, starts hidden, shown on demand.
        # Capture count before loading so we can identify the new root
        # even if earlier windows had non-fatal QML errors.
        _roots_before = len(self._engine.rootObjects())
        self._engine.load(self._resolve_qml_url("ui/qml/SettingsPanel.qml"))
        all_roots = self._engine.rootObjects()
        if len(all_roots) > _roots_before:
            # New root object was added — it must be the SettingsPanel.
            self._settings_root = all_roots[-1]
            logger.debug("[App] Settings root object: {}", self._settings_root)
        elif all_roots:
            # Fallback: scan by window title in case of load-order oddity.
            for obj in reversed(all_roots):
                try:
                    if "BABY Settings" in (obj.property("title") or ""):
                        self._settings_root = obj
                        logger.debug("[App] Settings root found by title: {}", obj)
                        break
                except Exception:
                    pass
            if self._settings_root is None:
                logger.error("[App] SettingsPanel.qml loaded but root not identifiable")
        else:
            logger.error("[App] Failed to load SettingsPanel.qml — no root objects after load")

        # Neural Network Viewer — loaded once, starts hidden, shown from Settings.
        _roots_before_nn = len(self._engine.rootObjects())
        self._engine.load(self._resolve_qml_url("ui/qml/NeuralNetworkViewer.qml"))
        all_roots_nn = self._engine.rootObjects()
        if len(all_roots_nn) > _roots_before_nn:
            self._neural_root = all_roots_nn[-1]
            self._neural_backend.set_neural_root(self._neural_root)
            logger.debug("[App] Neural Network Viewer root object: {}", self._neural_root)
        else:
            self._neural_root = None
            logger.warning("[App] Failed to load NeuralNetworkViewer.qml")

        # ── System Tray ────────────────────────────────────────────
        self.tray = SystemTrayManager()
        self.tray.quit_requested.connect(self._qt_app.quit)
        self.tray.settings_requested.connect(self._show_settings)
        self.tray.reset_position_requested.connect(self.controller.resetPosition)

        # ── Exit / Settings button on the Dynamic Island ───────────
        self.controller.exitRequested.connect(self._qt_app.quit)
        self.controller.openSettingsRequested.connect(self._show_settings)
        self.controller.showNeuralNetworkRequested.connect(self._neural_backend.show_window)

        # ── OS privacy watchdog ─────────────────────────────────────
        # If the user switches the mic OFF (Windows privacy toggle) the
        # assistant's mic access is turned off; if the volume drops to 0
        # the speaker access is turned off. Polled every 3 s.
        from PySide6.QtCore import QTimer
        self._system_state_timer = QTimer()
        self._system_state_timer.timeout.connect(self.controller.refresh_system_audio_state)
        self._system_state_timer.start(3000)
        self.controller.refresh_system_audio_state()

        # Mirror controller state → tray icon
        self.controller.stateChanged.connect(self.tray.set_state)

        # ── AI Pointer Overlay ─────────────────────────────────────
        self.pointer = AIPointerOverlay()
        set_pointer_overlay(self.pointer)

        # ── Asyncio event loop alongside Qt ────────────────────────
        loop = qasync.QEventLoop(self._qt_app)
        asyncio.set_event_loop(loop)

        try:
            with loop:
                # Schedule async services as a background task (don't block)
                # so that when Qt quits the event loop, the future is cancelled
                # gracefully instead of raising RuntimeError.
                asyncio.ensure_future(self._start_async_services())
                loop.run_forever()
        except (RuntimeError, asyncio.CancelledError) as e:
            logger.info("[App] Event loop shutdown cleanly.")
        except Exception as e:
            logger.error("[App] Event loop error: {}", e)
        finally:
            # Stop audio worker threads before the process exits: a live
            # sounddevice capture races the Qt window teardown performed by
            # process exit (0xC0000005 in qwindows.dll). main.py then calls
            # TerminateProcess, which never runs destructors — so the QML
            # engine must NOT be deleted here (deleting it past the event
            # loop is what crashed in qwindows.dll).
            import time as _time
            _t0 = _time.monotonic()
            if self._orchestrator is not None:
                try:
                    self._orchestrator.shutdown()
                except Exception:
                    pass
            logger.info("[App] finally: orchestrator.shutdown() done in {:.3f}s", _time.monotonic() - _t0)
            try:
                if getattr(self, "_system_state_timer", None) is not None:
                    self._system_state_timer.stop()
            except Exception:
                pass
            logger.info("[App] finally: done")

    @staticmethod
    def _resolve_qml_url(rel_path: str) -> QUrl:
        """Robustly resolve QML file relative path to QUrl across dev and compiled executable environments."""
        from pathlib import Path
        if getattr(sys, "frozen", False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).parent.parent
        abs_path = (base_dir / rel_path).resolve()
        return QUrl.fromLocalFile(str(abs_path))

    @staticmethod
    def _preload_qt_dlls():
        """Load every Qt6*.dll from the PySide6 package before the QML engine starts.

        Required on Windows because the QML plugin loader does not search the
        PySide6 directory for the plugins' transitive DLL dependencies.
        """
        import glob
        import ctypes

        try:
            import PySide6
        except Exception:
            return

        pyside_dir = os.path.dirname(PySide6.__file__)
        for dll_path in glob.glob(os.path.join(pyside_dir, "Qt6*.dll")):
            try:
                ver = _dll_version(dll_path)
            except Exception:
                ver = None
            if ver is not None:
                pkg_ver = tuple(int(p) for p in str(PySide6.__version__).split(".")[:3])
                if ver[:3] != pkg_ver:
                    print(f"[Preload] SKIPPING stale Qt DLL (version {ver}) {os.path.basename(dll_path)}")
                    continue
            try:
                ctypes.CDLL(dll_path)
            except Exception:
                # Non-fatal: a missing optional DLL will surface as a QML error later.
                pass

    async def _start_async_services(self):
        try:
            from core.orchestrator import BabyOrchestrator
            from core.event_bus import get_bus
            from antigravity.agents.vision_agent import set_ui_controller

            # Register UI controller with vision agent for permission checks
            set_ui_controller(self.controller)

            logger.info("[App] _start_async_services: creating orchestrator...")
            orchestrator = BabyOrchestrator(
                config=self._config,
                ui=self.controller,
                pointer=self.pointer,
            )
            self._orchestrator = orchestrator
            logger.info("[App] _start_async_services: orchestrator created ✓")

            # Reuse the early bio_db so settings and orchestrator share the same instance
            self._early_bio_db = None
            self._settings_bridge._bio_db = orchestrator._bio_db
            self._settings_bridge._orchestrator = orchestrator

            # Wire knowledge graph to neural backend for social graph
            from core.knowledge_graph import knowledge_graph
            self._neural_backend.set_knowledge_graph(knowledge_graph)
            logger.info("[App] _start_async_services: knowledge graph wired ✓")

            # Wire training manager to settings bridge
            from core.training_manager import TrainingManager
            self._training_manager = TrainingManager()
            self._settings_bridge.set_training_manager(self._training_manager)
            logger.info("[App] _start_async_services: training manager created ✓")

            bus = get_bus()
            logger.info("[App] _start_async_services: bus obtained ✓")

            # Run orchestrator and event bus concurrently under the active loop
            logger.info("[App] _start_async_services: entering gather(orchestrator.start, bus.run)")
            await asyncio.gather(
                orchestrator.start(),
                bus.run(),
            )
            logger.info("[App] _start_async_services: done ✓")
        except Exception as _boot_err:
            logger.exception("[App] _start_async_services FAILED: {}", _boot_err)

    def _show_settings(self):
        """Show the Settings Panel (loaded once at startup, reused on every open)."""
        logger.info("[Settings] _show_settings called")

        if self._settings_root is None:
            logger.error("[Settings] Settings root object not available — QML did not load")
            return

        try:
            self._settings_bridge.beginEdit()
        except Exception as e:
            logger.exception("[Settings] beginEdit failed: {}", e)
            return

        try:
            # Refresh values from current config before showing
            self._settings_root.refreshValues()
        except Exception as e:
            logger.warning("[Settings] refreshValues() call failed (non-fatal): {}", e)

        try:
            self._settings_root.setProperty("visible", True)
            self._settings_root.show()
            self._settings_root.raise_()
            self._settings_root.requestActivate()
            logger.success("[App] SettingsPanel shown successfully")
        except Exception as e:
            logger.exception("[Settings] Failed to show settings window: {}", e)

    def _on_quit(self):
        from core.event_bus import get_bus, Event, EventType
        get_bus().publish_sync(Event(type=EventType.SHUTDOWN))



def _dll_version(path):
    """Read (major, minor, patch, build) from a DLL's version resource, or None."""
    import ctypes
    size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
        return None
    ptr = ctypes.POINTER(ctypes.c_uint32)()
    length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
        return None
    hi = ptr[2]
    lo = ptr[3]
    return (hi >> 16, hi & 0xFFFF, lo >> 16, lo & 0xFFFF)



















