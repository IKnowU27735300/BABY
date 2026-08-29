"""
ui/island_controller.py — Python-side bridge between async core and QML UI.
Exposes signals and slots that QML binds to.
"""

from __future__ import annotations
import json
import io
import base64
import sys
import threading

from PySide6.QtCore import QObject, Signal, Slot, Property, QMetaObject, Qt, QThread, QProcess
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from loguru import logger
from core.config import BabyConfig
from tools.screen_tools import (
    set_screen_share_selection,
    set_screen_share_enabled,
    get_screen_share_selection,
)

from ui.camera_preview import CameraPreviewWorker


def _system_mic_denied() -> bool:
    """True when the OS-level 'Microphone access' privacy toggle is OFF.

    Reads the CapabilityAccessManager consent store (same place the Windows
    Settings → Privacy → Microphone switch writes). False on any error.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Value")
            return str(value).strip().lower() != "allow"
    except OSError:
        return False


def _system_volume_is_zero() -> bool | None:
    """True when the default audio render device is muted or at 0% volume.

    Uses the Windows Core Audio API via ctypes (no third-party deps).
    Returns None when the device state cannot be read (treated as 'unknown').
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import POINTER, c_float, c_int, c_void_p, byref, c_wchar_p

        def _guid(uid: str):
            buf = ctypes.create_string_buffer(16)
            hr = ctypes.windll.ole32.CLSIDFromString(c_wchar_p(uid), buf)
            if hr != 0:
                raise OSError(hr)
            return buf

        CLSID_MM_DEVICE_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
        IID_IMM_DEVICE_ENUMERATOR  = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
        IID_IAUDIO_ENDPOINT_VOLUME = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

        ole32 = ctypes.windll.ole32
        mmdevapi = ctypes.windll.mmdevapi
        ole32.CoInitializeEx(None, 0)
        try:
            dev_enum = c_void_p()
            hr = ole32.CoCreateInstance(
                _guid(CLSID_MM_DEVICE_ENUMERATOR), None, 1,
                _guid(IID_IMM_DEVICE_ENUMERATOR), byref(dev_enum),
            )
            if hr != 0 or not dev_enum.value:
                return None

            endpoint = c_void_p()
            # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender=0, eConsole=0)
            # — fetch the real function address from the COM vtable (slot 4).
            enum_vtbl = ctypes.cast(dev_enum.value, POINTER(POINTER(c_void_p)))
            GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, c_void_p, c_int, c_int, POINTER(c_void_p),
            )(enum_vtbl.contents[4])
            hr = GetDefaultAudioEndpoint(dev_enum.value, 0, 0, byref(endpoint))
            if hr != 0 or not endpoint.value:
                return None

            volume = c_void_p()
            # IMMDevice::Activate — vtable slot 3.
            dev_vtbl = ctypes.cast(endpoint.value, POINTER(POINTER(c_void_p)))
            Activate = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, c_void_p, c_void_p, c_int,
                POINTER(c_void_p), POINTER(c_void_p),
            )(dev_vtbl.contents[3])
            hr = Activate(endpoint.value, _guid(IID_IAUDIO_ENDPOINT_VOLUME), 23, None, byref(volume))
            if hr != 0 or not volume.value:
                return None

            scalar = c_float()
            is_muted = c_int()
            # IAudioEndpointVolume: GetMasterVolumeLevelScalar = vtable 9, GetMute = vtable 15.
            vol_vtbl = ctypes.cast(volume.value, POINTER(POINTER(c_void_p)))
            GetLevel = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, POINTER(c_float))(vol_vtbl.contents[9])
            GetMute  = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, POINTER(c_int))(vol_vtbl.contents[15])
            if GetLevel(volume.value, byref(scalar)) != 0:
                return None
            if GetMute(volume.value, byref(is_muted)) == 0 and is_muted.value:
                return True
            return scalar.value <= 0.0001
        finally:
            ole32.CoUninitialize()
    except Exception as e:
        logger.debug("[UI] System volume check failed: {}", e)
        return None


class ScreenSharePreviewWorker(QThread):
    frame_ready = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def start_preview(self):
        self._running = True
        if not self.isRunning():
            self.start()

    def stop_preview(self):
        self._running = False
        if self.isRunning():
            self.quit()
            self.wait(2000)

    def run(self):
        import time
        from io import BytesIO
        try:
            from tools.screen_tools import _capture_monitors, is_screen_share_enabled
        except ImportError as e:
            logger.error("[ScreenSharePreviewWorker] Import failed: {}", e)
            self.error.emit(f"Import error: {e}")
            return

        logger.info("[ScreenSharePreviewWorker] Capture loop started (pid={})", __import__("os").getpid())
        fail_count = 0
        while self._running:
            try:
                enabled = is_screen_share_enabled()
                if enabled:
                    img, _ = _capture_monitors()
                    if img and hasattr(img, "width"):
                        fail_count = 0
                        if img.width > 640:
                            ratio = 640.0 / img.width
                            new_h = max(1, int(img.height * ratio))
                            img = img.resize((640, new_h))
                        buf = BytesIO()
                        img.save(buf, format="JPEG", quality=70)
                        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                        self.frame_ready.emit(f"data:image/jpeg;base64,{b64}")
                    else:
                        fail_count += 1
                        if fail_count <= 3:
                            logger.warning("[ScreenSharePreviewWorker] No image from _capture_monitors")
                else:
                    fail_count += 1
                    if fail_count <= 3:
                        logger.debug("[ScreenSharePreviewWorker] Screen share not enabled (tick {})", fail_count)
                    self.frame_ready.emit("")
            except PermissionError as e:
                fail_count += 1
                if fail_count <= 3:
                    logger.warning("[ScreenSharePreviewWorker] Permission error: {}", e)
            except Exception as e:
                fail_count += 1
                if fail_count <= 3:
                    logger.warning("[ScreenSharePreviewWorker] Capture error: {}", e)
            time.sleep(0.5)


VALID_STATES = {"loading", "activating", "idle", "listening", "thinking", "speaking", "consent", "error", "network_active"}


class BabyIslandController(QObject):
    """
    Exposed to QML as `babyController`.
    All methods are thread-safe — use set_state_threadsafe from async code.
    """

    # ─── Signals ─────────────────────────────────────────────────────────────
    stateChanged      = Signal(str)
    transcriptChanged = Signal(str)
    planTextChanged   = Signal(str)
    riskLevelChanged  = Signal(str)
    speakerChanged    = Signal(str)
    consentGiven      = Signal(bool)    # True=approve, False=deny
    micActiveChanged  = Signal(bool)
    camActiveChanged  = Signal(bool)
    screenShareGrantedChanged = Signal(bool)
    screenShareSelectionChanged = Signal()
    cameraAccessGrantedChanged = Signal(bool)
    islandXChanged    = Signal(int)
    islandYChanged    = Signal(int)
    isActivatedChanged = Signal(bool)
    toggleActivation  = Signal()
    micMutedChanged   = Signal(bool)
    speakerMutedChanged = Signal(bool)
    networkActiveChanged = Signal(bool)   # True while Baby is doing web research
    _state_change_trigger = Signal(str)
    assistantResponseChanged = Signal(str)
    responseWindowVisibleChanged = Signal(bool)
    cameraPreviewVisibleChanged = Signal(bool)
    screenSharePreviewVisibleChanged = Signal(bool)
    screenSharePickerVisibleChanged = Signal(bool)
    cameraFrameChanged = Signal(str)
    screenShareFrameChanged = Signal(str)
    screenShareFramesChanged = Signal(list)
    cameraPreviewError = Signal(str)
    exitRequested      = Signal()    # User tapped the Exit button on the island
    openSettingsRequested = Signal()  # User requested Settings panel
    showNeuralNetworkRequested = Signal()  # Show neural network viewer
    themeChanged = Signal()  # Theme/mode/color/animation speed changed
    consentWindowVisibleChanged = Signal(bool)
    cameraAvailableChanged = Signal(bool)
    _camera_probe_trigger = Signal(bool)
    relationshipsReady = Signal(list)
    relationshipError = Signal(str)
    purityAlert = Signal(str)

    def __init__(self, config: BabyConfig, camera_image_provider=None, parent=None):
        super().__init__(parent)
        self._config     = config
        self._state     = "loading"
        self._transcript = ""
        self._plan_text  = ""
        self._risk_level = "low"
        self._speaker    = ""
        self._mic_active = False
        self._cam_active = False
        self._is_activated = False
        self._mic_user_muted = False
        self._speaker_user_muted = False
        self._mic_system_denied = False
        self._speaker_system_muted = False
        self._mic_muted  = False
        self._speaker_muted = False
        self._network_active = False
        self._screen_share_granted = False
        self._screen_share_selection: list[int] = []
        self._camera_access_granted = False
        self._camera_available = True   # flipped by the startup probe
        self._assistant_response = ""
        self._response_window_visible = False
        self._consent_window_visible = False
        self._camera_preview_visible = False
        self._screen_share_preview_visible = False
        self._screen_share_picker_visible = False
        self._camera_frame = ""
        self._screen_share_frame = ""
        self._screen_share_frames = []
        self._camera_image_provider = camera_image_provider
        self._camera_worker = CameraPreviewWorker()
        self._camera_worker.frame_ready.connect(self._on_camera_frame, Qt.QueuedConnection)
        self._camera_worker.error.connect(self._on_camera_error, Qt.QueuedConnection)
        self._camera_minimized = False
        self._screen_share_worker = ScreenSharePreviewWorker()
        self._screen_share_worker.frame_ready.connect(self._on_screen_share_frame, Qt.QueuedConnection)
        self._state_change_trigger.connect(self.set_state, Qt.QueuedConnection)
        self._camera_probe_trigger.connect(self.set_camera_available, Qt.QueuedConnection)

        # Probe camera availability without blocking startup.
        threading.Thread(target=self._probe_camera_availability, daemon=True, name="CameraProbe").start()

    # ─── Properties ──────────────────────────────────────────────────────────

    @Property(str, notify=stateChanged)  # type: ignore
    def state(self):
        return self._state

    @Property(str, notify=transcriptChanged)  # type: ignore
    def transcript(self):
        return self._transcript

    @Property(str, notify=planTextChanged)  # type: ignore
    def planText(self):
        return self._plan_text

    @Property(str, notify=riskLevelChanged)  # type: ignore
    def riskLevel(self):
        return self._risk_level

    @Property(str, notify=speakerChanged)  # type: ignore
    def speaker(self):
        return self._speaker

    @Property(bool, notify=micActiveChanged)  # type: ignore
    def micActive(self):
        return self._mic_active

    @Property(bool, notify=camActiveChanged)  # type: ignore
    def camActive(self):
        return self._cam_active

    def _is_position_on_screen(self, x: int, y: int) -> bool:
        screens = QApplication.screens()
        if not screens:
            return True
        for screen in screens:
            geo = screen.geometry()
            if (geo.x() - 50 <= x <= geo.x() + geo.width() - 50) and \
               (geo.y() <= y <= geo.y() + geo.height() - 20):
                return True
        return False

    @Property(int, notify=islandXChanged)  # type: ignore
    def islandX(self):
        x = self._config.ui.island_x
        y = self._config.ui.island_y
        if x == -1 or not self._is_position_on_screen(x, y):
            screen = QApplication.primaryScreen()
            if screen:
                return screen.geometry().x() + (screen.availableGeometry().width() - 320) // 2
            return 600  # fallback
        return x

    @Property(int, notify=islandYChanged)  # type: ignore
    def islandY(self):
        x = self._config.ui.island_x
        y = self._config.ui.island_y
        if x == -1 or not self._is_position_on_screen(x, y):
            screen = QApplication.primaryScreen()
            if screen:
                return screen.geometry().y() + getattr(self._config.ui, "island_y_offset", 12)
            return 12
        return y

    @Property(bool, notify=isActivatedChanged)  # type: ignore
    def isActivated(self):
        return self._is_activated

    @Property(bool, notify=micMutedChanged)  # type: ignore
    def micMuted(self):
        return self._mic_muted

    @Property(bool, notify=speakerMutedChanged)  # type: ignore
    def speakerMuted(self):
        return self._speaker_muted

    @Property(bool, notify=networkActiveChanged)  # type: ignore
    def networkActive(self):
        return self._network_active

    @Property(bool, notify=screenShareGrantedChanged)  # type: ignore
    def screenShareGranted(self):
        return self._screen_share_granted

    @Property(list, notify=screenShareSelectionChanged)  # type: ignore
    def screenShareSelection(self):
        return list(self._screen_share_selection)

    @Property(str, notify=screenShareSelectionChanged)  # type: ignore
    def screenShareSummary(self):
        if not self._screen_share_selection:
            return "No screens selected"
        if len(self._screen_share_selection) == 1:
            return f"Screen {self._screen_share_selection[0]}"
        return f"{len(self._screen_share_selection)} screens selected"

    @Property(bool, notify=cameraAccessGrantedChanged)  # type: ignore
    def cameraAccessGranted(self):
        return self._camera_access_granted

    @Property(bool, notify=cameraPreviewVisibleChanged)  # type: ignore
    def cameraPreviewVisible(self):
        return self._camera_preview_visible

    @Property(bool, notify=cameraPreviewVisibleChanged)  # type: ignore
    def cameraMinimized(self):
        return self._camera_minimized

    @Property(str, notify=assistantResponseChanged)  # type: ignore
    def assistantResponse(self):
        return self._assistant_response

    @Property(bool, notify=responseWindowVisibleChanged)  # type: ignore
    def responseWindowVisible(self):
        return self._response_window_visible

    @Property(bool, notify=consentWindowVisibleChanged)  # type: ignore
    def consentWindowVisible(self):
        return self._consent_window_visible

    @Property(bool, notify=cameraAvailableChanged)  # type: ignore
    def cameraAvailable(self):
        return self._camera_available

    @Property(bool, notify=screenSharePreviewVisibleChanged)  # type: ignore
    def screenSharePreviewVisible(self):
        return self._screen_share_preview_visible

    @Property(str, notify=screenShareFrameChanged)  # type: ignore
    def screenShareFrame(self):
        return getattr(self, "_screen_share_frame", "")

    @Property(list, notify=screenShareFramesChanged)  # type: ignore
    def screenShareFrames(self):
        return list(getattr(self, "_screen_share_frames", []))

    @Property(bool, notify=screenSharePickerVisibleChanged)  # type: ignore
    def screenSharePickerVisible(self):
        return self._screen_share_picker_visible

    @Property(str, notify=cameraFrameChanged)  # type: ignore
    def cameraFrame(self):
        return self._camera_frame

    # Theme properties
    @Property(str, notify=themeChanged)  # type: ignore
    def themeMode(self):
        return getattr(self._config.ui, "theme_mode", "dark")

    @Property(str, notify=themeChanged)  # type: ignore
    def themeColor(self):
        return getattr(self._config.ui, "theme_color", "#7C7CFF")

    @Property(float, notify=themeChanged)  # type: ignore
    def animationSpeed(self):
        return getattr(self._config.ui, "animation_speed", 1.0)

    # Admin theme properties (black + gold)
    @Property(str, notify=themeChanged)  # type: ignore
    def adminThemeActive(self):
        return getattr(self, "_admin_theme_active", False)

    @Property(str, notify=themeChanged)  # type: ignore
    def adminPrimaryColor(self):
        return getattr(self, "_admin_primary_color", "#000000")

    @Property(str, notify=themeChanged)  # type: ignore
    def adminSecondaryColor(self):
        return getattr(self, "_admin_secondary_color", "#FFD700")

    # ─── Setters (called from async orchestrator) ─────────────────────────────

    def set_state(self, state: str):
        if state not in VALID_STATES:
            logger.warning("[UI] Invalid state: {}", state)
            return
        # Drive the network_active property from the state machine
        is_network = state == "network_active"
        if is_network != self._network_active:
            self._network_active = is_network
            self.networkActiveChanged.emit(is_network)
            logger.info("[UI] Network indicator: {}", "ON" if is_network else "OFF")
        if self._state != state:
            self._state = state
            self.stateChanged.emit(state)
            # Permission requests live in a dedicated window (like the
            # response window), not inside the island.
            self.set_consent_window_visible(state == "consent")

    def set_state_threadsafe(self, state: str):
        """Call from a non-Qt thread (e.g. asyncio tasks)."""
        self._state_change_trigger.emit(state)

    def set_transcript(self, text: str):
        if self._transcript != text:
            self._transcript = text
            self.transcriptChanged.emit(text)

    def set_plan_text(self, text: str):
        if self._plan_text != text:
            self._plan_text = text
            self.planTextChanged.emit(text)

    def set_risk_level(self, level: str):
        if self._risk_level != level:
            self._risk_level = level
            self.riskLevelChanged.emit(level)

    def set_speaker(self, name: str):
        if self._speaker != name:
            self._speaker = name
            self.speakerChanged.emit(name)

    def set_assistant_response(self, text: str):
        if self._assistant_response != text:
            self._assistant_response = text
            self.assistantResponseChanged.emit(text)
        # The generated answer is shown in the Dynamic Island itself; the
        # user can expand it into the response window via the ⛶ button.

    @Slot()
    def dismissResponse(self):
        """Hide the response panel/window and clear the shown answer."""
        self.set_assistant_response("")
        self.set_response_window_visible(False)

    @Slot(bool)
    def set_response_window_visible(self, visible: bool):
        if self._response_window_visible != visible:
            self._response_window_visible = visible
            self.responseWindowVisibleChanged.emit(visible)

    @Slot(bool)
    def set_consent_window_visible(self, visible: bool):
        if self._consent_window_visible != visible:
            self._consent_window_visible = visible
            self.consentWindowVisibleChanged.emit(visible)

    @Slot()
    def openConsentWindow(self):
        self.set_consent_window_visible(True)

    def set_camera_available(self, available: bool):
        if self._camera_available != available:
            self._camera_available = available
            logger.info("[UI] Camera availability: {}", "available" if available else "NOT available")
            self.cameraAvailableChanged.emit(available)

    def _probe_camera_availability(self):
        """Background probe: a real capture attempt is the only reliable check."""
        try:
            import cv2
            logger.info("[CameraProbe] cv2 loaded, scanning indices 0-3...")
            for idx in range(4):
                cap = None
                for backend in (getattr(cv2, "CAP_DSHOW", None), cv2.CAP_ANY):
                    if backend is None:
                        continue
                    try:
                        cap = cv2.VideoCapture(idx, backend)
                    except Exception as exc:
                        logger.debug("[CameraProbe] idx={} backend={}: {}", idx, backend, exc)
                        cap = None
                    if cap is not None and cap.isOpened():
                        logger.info("[CameraProbe] Camera found at index {} backend {}", idx, backend)
                        cap.release()
                        self._camera_probe_trigger.emit(True)
                        return
                    if cap is not None:
                        cap.release()
            logger.info("[CameraProbe] No camera found in indices 0-3")
            self._camera_probe_trigger.emit(False)
        except Exception as exc:
            logger.error("[CameraProbe] Probe failed: {}", exc)
            self._camera_probe_trigger.emit(False)

    @Slot(bool)
    def setCameraPreviewVisible(self, visible: bool):
        if visible and not self._camera_available:
            logger.info("[UI] Camera preview blocked — no camera available.")
            self.cameraPreviewError.emit("No camera detected. Please connect a camera.")
            return
        if self._camera_preview_visible != visible:
            self._camera_preview_visible = visible
            self.cameraPreviewVisibleChanged.emit(visible)
            if visible:
                self._camera_minimized = False
                # Use queued connection to start camera worker in event loop
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._camera_worker.start)
            else:
                self._camera_minimized = False
                self._camera_worker.stop()
                # Sync camera access state when preview is closed
                if self._camera_access_granted:
                    self._camera_access_granted = False
                    self.cameraAccessGrantedChanged.emit(False)

    @Slot()
    def minimizeCameraPreview(self):
        """Hide the camera preview window without stopping the camera worker.
        The camera keeps running in the background so reopening is instant.
        """
        if self._camera_preview_visible:
            self._camera_preview_visible = False
            self.cameraPreviewVisibleChanged.emit(False)
            self._camera_minimized = True
            logger.info("[UI] Camera preview minimized (worker still running)")

    @Slot(str)
    def _on_camera_frame(self, data_url: str):
        """Receive a JPEG data-URL string from the worker thread and push it to QML."""
        if not data_url:
            return
        self._camera_frame = data_url
        # Also update the image provider so image://camera/frame works
        if self._camera_image_provider:
            try:
                from PySide6.QtGui import QImage
                # Strip the header and decode to update the provider
                header = "data:image/jpeg;base64,"
                if data_url.startswith(header):
                    import base64
                    raw = base64.b64decode(data_url[len(header):])
                    img = QImage()
                    img.loadFromData(raw, b"JPEG")
                    self._camera_image_provider.set_image(img)
            except Exception:
                pass
        self.cameraFrameChanged.emit(data_url)

    @Slot(str)
    def _on_camera_error(self, error_msg: str):
        logger.warning("[CameraPreview] Error: {}", error_msg)
        self.cameraPreviewError.emit(error_msg)
        self.setCameraPreviewVisible(False)
        # Keep camera available so user can retry — don't permanently lock out.

    def get_camera_frame(self):
        """Return the most recent raw BGR numpy frame from the camera worker, or None."""
        if self._camera_worker:
            return self._camera_worker.get_frame()
        return None

    @Slot()
    def switchCamera(self):
        """Switch to the next available camera."""
        if self._camera_worker and self._camera_preview_visible:
            logger.info("[UI] Switching camera")
            self._camera_worker.switch_camera()

    @Slot(int, result=int)
    def getCameraIndex(self):
        """Get the current camera index."""
        if self._camera_worker:
            return self._camera_worker.current_camera_index
        return 0

    @Slot(bool)
    def setScreenSharePreviewVisible(self, visible: bool):
        if self._screen_share_preview_visible != visible:
            self._screen_share_preview_visible = visible
            self.screenSharePreviewVisibleChanged.emit(visible)
            if visible:
                # Create a fresh worker each time — QThread cannot be
                # restarted after run() returns.
                old = self._screen_share_worker
                if old is not None:
                    old.stop_preview()
                    old.deleteLater()
                self._screen_share_worker = ScreenSharePreviewWorker()
                self._screen_share_worker.frame_ready.connect(
                    self._on_screen_share_frame, Qt.QueuedConnection
                )
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._screen_share_worker.start_preview)
            else:
                if self._screen_share_worker is not None:
                    self._screen_share_worker.stop_preview()
        elif visible and (self._screen_share_worker is None or not self._screen_share_worker.isRunning()):
            old = self._screen_share_worker
            if old is not None:
                old.stop_preview()
                old.deleteLater()
            self._screen_share_worker = ScreenSharePreviewWorker()
            self._screen_share_worker.frame_ready.connect(
                self._on_screen_share_frame, Qt.QueuedConnection
            )
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._screen_share_worker.start_preview)

    @Slot(str)
    def _on_screen_share_frame(self, data_url: str):
        self._screen_share_frame = data_url
        self.screenShareFrameChanged.emit(data_url)

    @Slot(list)
    def _on_screen_share_frames(self, frames: list):
        self._screen_share_frames = frames
        self.screenShareFramesChanged.emit(frames)

    @Slot(bool)
    def setScreenSharePickerVisible(self, visible: bool):
        if self._screen_share_picker_visible != visible:
            self._screen_share_picker_visible = visible
            self.screenSharePickerVisibleChanged.emit(visible)
            if visible:
                self.setScreenSharePreviewVisible(False)

    def set_mic_active(self, active: bool):
        if self._mic_active != active:
            self._mic_active = active
            self.micActiveChanged.emit(active)

    def set_cam_active(self, active: bool):
        if self._cam_active != active:
            self._cam_active = active
            self.camActiveChanged.emit(active)

    @Slot(result=list)
    def getAvailableScreens(self) -> list[dict]:
        """Return the available displays so QML can present a multi-select picker."""
        screens = []
        for idx, screen in enumerate(QApplication.screens(), start=1):
            geometry = screen.geometry()
            screens.append(
                {
                    "index": idx,
                    "name": screen.name() or f"Display {idx}",
                    "label": f"Display {idx} - {geometry.width()}x{geometry.height()}",
                    "x": geometry.x(),
                    "y": geometry.y(),
                    "width": geometry.width(),
                    "height": geometry.height(),
                    "primary": screen == QApplication.primaryScreen(),
                }
            )
        return screens

    @Slot(str)
    def applyScreenShareSelection(self, selection_json: str):
        """Store the user-chosen screen selection and enable live observation."""
        try:
            selection = json.loads(selection_json) if selection_json else []
            if not isinstance(selection, list):
                selection = []
        except Exception as e:
            logger.error("[UI] Failed to parse screen selection: {}", e)
            selection = []

        clean: list[int] = []
        for value in selection:
            try:
                idx = int(value)
            except (TypeError, ValueError):
                continue
            if idx >= 1 and idx not in clean:
                clean.append(idx)

        self._screen_share_selection = clean
        self._screen_share_granted = bool(clean)
        set_screen_share_selection(clean)
        set_screen_share_enabled(self._screen_share_granted)
        logger.info("[UI] Screen share selection applied: {}", clean)
        self.screenShareSelectionChanged.emit()
        self.screenShareGrantedChanged.emit(self._screen_share_granted)
        if self._screen_share_granted:
            logger.info("[UI] Showing screen share preview!")
            self.setScreenSharePreviewVisible(True)

    @Slot()
    def toggleCameraAccess(self):
        if not self._camera_available:
            logger.info("[UI] Camera blocked — no camera available.")
            self.cameraPreviewError.emit("No camera detected. Please connect a camera and restart.")
            return
        self._camera_access_granted = not self._camera_access_granted
        logger.info("[UI] Camera access permission changed to: {}", self._camera_access_granted)
        self.cameraAccessGrantedChanged.emit(self._camera_access_granted)
        if self._camera_access_granted:
            if self._camera_worker and self._camera_worker._running:
                # Camera worker already running (minimized) — just show the window
                self._camera_preview_visible = True
                self.cameraPreviewVisibleChanged.emit(True)
            else:
                self.setCameraPreviewVisible(True)
        else:
            self.setCameraPreviewVisible(False)

    @Slot()
    def clearScreenShareSelection(self):
        self._screen_share_selection = []
        self._screen_share_granted = False
        self._screen_share_picker_visible = False
        set_screen_share_selection([])
        set_screen_share_enabled(False)
        logger.info("[UI] Screen share permission cleared")
        self.screenShareSelectionChanged.emit()
        self.screenShareGrantedChanged.emit(False)
        self.screenSharePickerVisibleChanged.emit(False)
        self.setScreenSharePreviewVisible(False)

    @Slot()
    def closeScreenSharePicker(self):
        """Sync Python state when QML closes the picker window."""
        if self._screen_share_picker_visible:
            self._screen_share_picker_visible = False
            self.screenSharePickerVisibleChanged.emit(False)

    @Slot()
    def toggleScreenShare(self):
        """Toggle screen sharing: if active, turn it off; if inactive, open picker."""
        logger.info("[UI] toggleScreenShare called, granted: {}, picker: {}", 
                    self._screen_share_granted, self._screen_share_picker_visible)
        
        # If screen sharing is currently active, turn it off completely
        if self._screen_share_granted:
            self.clearScreenShareSelection()
        # If picker is open, close it
        elif self._screen_share_picker_visible:
            self._screen_share_picker_visible = False
            self.screenSharePickerVisibleChanged.emit(False)
        # Otherwise, open the picker
        else:
            self._screen_share_picker_visible = True
            self.screenSharePickerVisibleChanged.emit(True)
            self.setScreenSharePreviewVisible(False)

    def set_activated(self, active: bool):
        if self._is_activated != active:
            self._is_activated = active
            self.isActivatedChanged.emit(active)

    # ─── QML-callable slots ──────────────────────────────────────────────────

    @Slot()
    def triggerToggle(self):
        logger.info("[UI] User clicked Toggle Activation")
        self.toggleActivation.emit()

    @Slot()
    def approve_action(self):
        logger.info("[UI] User clicked Approve")
        self.set_consent_window_visible(False)
        self.consentGiven.emit(True)

    @Slot()
    def deny_action(self):
        logger.info("[UI] User clicked Deny")
        self.set_consent_window_visible(False)
        self.consentGiven.emit(False)

    @Slot()
    def requestExit(self):
        logger.info("[UI] User clicked Exit — terminating Baby")
        self.exitRequested.emit()

    @Slot()
    def openSettings(self):
        logger.info("[UI] User clicked Settings — opening settings panel")
        self.openSettingsRequested.emit()

    @Slot()
    def requestRestart(self):
        logger.info("[UI] User clicked Restart — restarting Baby")
        self._config.save("config.yaml")
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()

    @Slot()
    def toggleTestMode(self):
        cfg = self._config
        cfg.llm.test_mode = not cfg.llm.test_mode
        cfg.save("config.yaml")
        mode = "ON" if cfg.llm.test_mode else "OFF"
        logger.info("[UI] Test mode toggled {} (live)", mode)
        from core.event_bus import get_bus, Event, EventType
        get_bus().publish_sync(Event(
            type=EventType.CONFIG_CHANGED,
            data={"category": "llm", "key": "test_mode", "value": cfg.llm.test_mode},
            source="ui",
        ))

    @Slot(str, str)
    def setTheme(self, mode: str, color: str):
        """Change theme mode and accent color. mode: 'dark' | 'light' | 'system'"""
        if mode in ("dark", "light", "system"):
            self._config.ui.theme_mode = mode
        if color and color.startswith("#"):
            self._config.ui.theme_color = color
        self._config.save("config.yaml")
        self.themeChanged.emit()
        logger.info("[UI] Theme updated: mode={}, color={}", mode, color)

    @Slot(bool)
    def setAdminTheme(self, active: bool):
        """Activate/deactivate admin theme (black + gold)."""
        if getattr(self, "_admin_theme_active", False) != active:
            self._admin_theme_active = active
            if active:
                self._admin_primary_color = "#000000"    # Black
                self._admin_secondary_color = "#FFD700"  # Gold
            self.themeChanged.emit()
            logger.info("[UI] Admin theme: {}", "ACTIVATED" if active else "DEACTIVATED")

    @Slot()
    def toggleAdminTheme(self):
        """Toggle admin theme on/off."""
        self.setAdminTheme(not getattr(self, "_admin_theme_active", False))

    @Slot()
    def toggleMicMute(self):
        self._mic_user_muted = not self._mic_user_muted
        self._recompute_mutes()
        logger.info("[UI] Microphone user-mute toggled to: {} (system denied: {})",
                    self._mic_user_muted, self._mic_system_denied)

    @Slot()
    def toggleSpeakerMute(self):
        self._speaker_user_muted = not self._speaker_user_muted
        self._recompute_mutes()
        logger.info("[UI] Speaker user-mute toggled to: {} (system volume zero: {})",
                    self._speaker_user_muted, self._speaker_system_muted)

    def _recompute_mutes(self):
        """Effective mute = user toggle OR system privacy state. Emits only on change."""
        mic = self._mic_user_muted or self._mic_system_denied
        spk = self._speaker_user_muted or self._speaker_system_muted
        if mic != self._mic_muted:
            self._mic_muted = mic
            self.micMutedChanged.emit(mic)
        if spk != self._speaker_muted:
            self._speaker_muted = spk
            self.speakerMutedChanged.emit(spk)

    def refresh_system_audio_state(self):
        """Poll OS privacy controls:
        - Windows mic-access toggle OFF  → assistant mic access is turned off.
        - Master volume at 0 (or muted)  → speaker access is turned off.
        Called periodically by the app's QTimer.
        """
        mic_denied = _system_mic_denied()
        vol_zero = _system_volume_is_zero()
        changed = False
        if mic_denied != self._mic_system_denied:
            self._mic_system_denied = mic_denied
            changed = True
            logger.info("[UI] System mic access: {}", "DENIED" if mic_denied else "allowed")
        if vol_zero is not None and vol_zero != self._speaker_system_muted:
            self._speaker_system_muted = vol_zero
            changed = True
            logger.info("[UI] System volume: {}", "ZERO (speaker off)" if vol_zero else "audible")
        if changed:
            self._recompute_mutes()

    @Slot(int, int)
    def savePosition(self, x: int, y: int):
        if self._is_position_on_screen(x, y):
            self._config.ui.island_x = x
            self._config.ui.island_y = y
        else:
            logger.warning("[UI] Off-screen position (x={}, y={}). Resetting to default center.", x, y)
            screen = QApplication.primaryScreen()
            if screen:
                self._config.ui.island_x = screen.geometry().x() + (screen.availableGeometry().width() - 120) // 2
                self._config.ui.island_y = screen.geometry().y() + getattr(self._config.ui, "island_y_offset", 12)
            else:
                self._config.ui.island_x = -1
                self._config.ui.island_y = 12
        self._config.save("config.yaml")
        logger.info("[UI] Saved island position: x={}, y={}", self._config.ui.island_x, self._config.ui.island_y)
        self.islandXChanged.emit(self._config.ui.island_x)
        self.islandYChanged.emit(self._config.ui.island_y)

    @Slot()
    def resetPosition(self):
        screen = QApplication.primaryScreen()
        if screen:
            x = screen.geometry().x() + (screen.availableGeometry().width() - 120) // 2
            y = screen.geometry().y() + getattr(self._config.ui, "island_y_offset", 12)
        else:
            x = -1
            y = 12
        self.savePosition(x, y)

    @Slot()
    def showNeuralNetwork(self):
        """Show the neural network viewer (knowledge graph)."""
        self.showNeuralNetworkRequested.emit()

    # ─── Relationship Engine Slots ────────────────────────────────────────────

    @Slot(list)
    def on_relationships_ready(self, results: list):
        """Slot called when relationship analysis completes."""
        self.relationshipsReady.emit(results)

    @Slot(str)
    def on_purity_alert(self, message: str):
        """Slot called when purity monitor detects contamination."""
        self.purityAlert.emit(message)
        logger.warning("[UI] Purity alert: {}", message)

    @Slot(str)
    def on_relationship_error(self, error: str):
        """Slot called on relationship engine error."""
        self.relationshipError.emit(error)
        logger.warning("[UI] Relationship error: {}", error)

    def subscribe_relationship_events(self, bus):
        """Subscribe to relationship engine events on the event bus."""
        from core.event_bus import EventType

        async def _on_relationship_detected(event):
            if event.data:
                self._qt_invoke(self.on_relationships_ready, [event.data])

        async def _on_contamination(event):
            if event.data:
                self._qt_invoke(self.on_purity_alert, str(event.data))

        bus.subscribe(EventType.RELATIONSHIP_DETECTED, _on_relationship_detected)
        bus.subscribe(EventType.RELATIONSHIP_CONTAMINATION, _on_contamination)

    def _qt_invoke(self, slot, args=None):
        """Invoke a slot from async thread via Qt signal."""
        if args is None:
            args = []
        QMetaObject.invokeMethod(
            self, slot.__name__, Qt.QueuedConnection,
            *[type(a).__name__ == 'list' and a or a for a in args]
        )



















