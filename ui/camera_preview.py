from __future__ import annotations
import base64
import threading
import time

from PySide6.QtCore import QObject, Signal

from loguru import logger


class CameraPreviewWorker(QObject):
    """
    Captures frames from the webcam in a background thread and emits them as
    JPEG data-URL strings ready for QML Image.source.

    Emitting a data-URL string (instead of a QImage) avoids the broken
    QBuffer/base64 round-trip that produced blank frames in QML.
    """

    frame_ready = Signal(str)   # "data:image/jpeg;base64,<b64>"
    error = Signal(str)
    camera_switched = Signal(int)  # Emits new camera index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap = None
        self._last_frame = None  # numpy BGR frame for enrollment
        self._current_camera_index = 0
        self._max_cameras = 4

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="CameraCapture"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._release_cap()

    def get_frame(self):
        """Return the most recent raw BGR numpy frame, or None."""
        return self._last_frame.copy() if self._last_frame is not None else None

    def switch_camera(self):
        """Switch to the next available camera."""
        if not self._running:
            return
        self._release_cap()
        self._current_camera_index = (self._current_camera_index + 1) % self._max_cameras
        logger.info("[CameraPreview] Switching to camera index {}", self._current_camera_index)
        self.camera_switched.emit(self._current_camera_index)
        # Restart capture with new camera
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="CameraCapture"
        )
        self._thread.start()

    @property
    def current_camera_index(self):
        return self._current_camera_index

    # ── Internal ──────────────────────────────────────────────────────────────

    def _release_cap(self):
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _probe_and_open_camera(self, cv2):
        """
        Try camera indices 0-3 on all available backends.
        On Windows try DirectShow first (CAP_DSHOW) for faster init.
        Returns an opened VideoCapture or None.
        """
        import sys

        backends = []
        if sys.platform == "win32":
            try:
                backends.append(cv2.CAP_DSHOW)
            except AttributeError:
                pass
        backends.append(cv2.CAP_ANY)

        for idx in range(4):
            for backend in backends:
                logger.debug("[CameraPreview] Probing index {} backend {}…", idx, backend)
                try:
                    cap = cv2.VideoCapture(idx, backend)
                except Exception:
                    cap = cv2.VideoCapture(idx)

                if not cap.isOpened():
                    cap.release()
                    continue

                # Set resolution / fps
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 25)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # Warm-up read (up to 1.5 s)
                deadline = time.time() + 1.5
                while time.time() < deadline:
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        logger.info(
                            "[CameraPreview] Camera ready at index {} backend {}",
                            idx, backend,
                        )
                        return cap
                    time.sleep(0.05)
                cap.release()

        return None

    def _open_camera(self, cv2, index: int):
        """Open a specific camera index on available backends."""
        import sys

        backends = []
        if sys.platform == "win32":
            try:
                backends.append(cv2.CAP_DSHOW)
            except AttributeError:
                pass
        backends.append(cv2.CAP_ANY)

        for backend in backends:
            logger.debug("[CameraPreview] Opening index {} backend {}…", index, backend)
            try:
                cap = cv2.VideoCapture(index, backend)
            except Exception:
                cap = cv2.VideoCapture(index)

            if not cap.isOpened():
                cap.release()
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 25)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            deadline = time.time() + 1.5
            while time.time() < deadline:
                ret, frame = cap.read()
                if ret and frame is not None:
                    logger.info("[CameraPreview] Camera ready at index {} backend {}", index, backend)
                    return cap
                time.sleep(0.05)
            cap.release()

        return None

    def _capture_loop(self):
        try:
            import cv2
        except ImportError:
            msg = "OpenCV (cv2) not installed — camera preview unavailable."
            logger.error("[CameraPreview] {}", msg)
            self.error.emit(msg)
            self._running = False
            return

        logger.info("[CameraPreview] Opening camera at index {}…", self._current_camera_index)
        cap = self._open_camera(cv2, self._current_camera_index)
        if cap is None:
            msg = f"Camera {self._current_camera_index} not found or device in use by another application."
            logger.error("[CameraPreview] {}", msg)
            self.error.emit(msg)
            self._running = False
            return

        self._cap = cap
        consecutive_failures = 0
        logger.info("[CameraPreview] Frame capture started ✓")

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 80]

        while self._running:
            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures > 30:
                        self.error.emit("Camera lost connection.")
                        break
                    time.sleep(0.04)
                    continue

                consecutive_failures = 0
                self._last_frame = frame.copy()  # Store raw frame for enrollment

                # Encode directly to JPEG bytes in the worker thread
                ok, buf = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue

                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                data_url = f"data:image/jpeg;base64,{b64}"
                self.frame_ready.emit(data_url)

                time.sleep(0.04)   # ~25 fps

            except Exception as exc:
                logger.warning("[CameraPreview] Frame error: {}", exc)
                consecutive_failures += 1
                if consecutive_failures > 10:
                    self.error.emit(f"Frame capture error: {exc}")
                    break
                time.sleep(0.1)

        self._release_cap()
        self._running = False
        logger.info("[CameraPreview] Capture loop ended.")



















