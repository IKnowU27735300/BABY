"""
audio/admin_phrase.py — Admin phrase detector ("Baby I'm back").

Two inference backends (selected automatically):

  1. JOBLIB backend (preferred when models/admin_phrase.joblib exists):
     - Runs OWW's AudioFeatures to extract speech embeddings.
     - Scores the clip with the trained GradientBoostingClassifier.
     - No dependency on OWW's Model class (which only loads OWW-format nets).

  2. OWW backend (fallback, when a real OWW-format .tflite/.onnx exists):
     - Original OpenWakeWord Model class path.

On detection, publishes ADMIN_PHRASE_DETECTED to the event bus for voice
verification.
"""

from __future__ import annotations
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from loguru import logger

from core.event_bus import get_bus, Event, EventType


RATE     = 16000
CHANNELS = 1
CHUNK    = 1280   # 80 ms @ 16 kHz — OWW expected chunk size

# How many CHUNK-sized frames we accumulate before scoring the joblib model.
# 12 frames = ~960 ms, enough to contain a 1.5 s phrase with a small buffer.
JOBLIB_WINDOW_FRAMES = 12


class AdminPhraseDetector:
    """
    Runs admin phrase detection in a background thread.
    On detection, publishes ADMIN_PHRASE_DETECTED to the event bus.
    """

    def __init__(self, model_path: str, threshold: float = 0.75, device_index: int = -1):
        self._model_path   = model_path
        self._threshold    = threshold
        self._device_index = device_index
        self._running      = False
        self._thread: threading.Thread | None = None
        self._fallback     = False
        self._muted        = False
        self._stop_evt     = threading.Event()
        # Resolved at start()
        self._backend: str | None = None  # "joblib" | "oww"
        self._joblib_clf   = None
        self._oww_model    = None
        self._oww_key: str | None = None
        self._af           = None  # AudioFeatures (shared by joblib backend)

    def set_muted(self, muted: bool):
        self._muted = muted

    def update_device(self, device_index: int):
        self._device_index = device_index
        if self._running and not self._fallback:
            logger.info("[AdminPhrase] Restarting on new microphone device...")
            self.stop()
            if self._thread:
                self._thread.join(timeout=2.0)
            self.start()

    # ─── Backend selection ────────────────────────────────────────────────────

    def _resolve_backend(self) -> bool:
        """
        Determine which backend to use.  Returns True if a backend was found.

        Priority:
          1. .joblib  (GBM trained by train_admin_phrase.py)
          2. .onnx    (real OWW-format model)
          3. .tflite  (real OWW-format model)
        """
        model_dir  = Path(self._model_path).parent
        stem       = Path(self._model_path).stem
        joblib_path = model_dir / f"{stem}.joblib"

        # --- Joblib backend ---
        if joblib_path.exists():
            try:
                import joblib
                self._joblib_clf = joblib.load(joblib_path)
                from openwakeword.utils import AudioFeatures
                resources = Path(self._model_path).parent / "oww_resources"
                if (resources / "embedding_model.onnx").exists():
                    self._af = AudioFeatures(
                        melspec_model_path=str(resources / "melspectrogram.onnx"),
                        embedding_model_path=str(resources / "embedding_model.onnx"),
                        inference_framework="onnx",
                    )
                else:
                    self._af = AudioFeatures(inference_framework="onnx")
                self._backend = "joblib"
                logger.success("[AdminPhrase] Joblib backend loaded ✓ ({})", joblib_path.name)
                return True
            except Exception as e:
                logger.warning("[AdminPhrase] Joblib backend failed: {} — trying OWW.", e)

        # --- OWW backend ---
        onnx_path = Path(self._model_path).with_suffix(".onnx")
        if onnx_path.exists() and onnx_path.read_bytes()[:4] not in (b"ONNX", b"JOBL"):
            model_file, framework = str(onnx_path), "onnx"
        elif Path(self._model_path).exists() and Path(self._model_path).read_bytes()[:4] not in (b"JOBL", b"ONNX"):
            model_file, framework = self._model_path, "tflite"
        else:
            return False  # only sentinels exist, no real OWW model

        try:
            from openwakeword.model import Model
            self._oww_model = Model(
                wakeword_models=[model_file],
                inference_framework=framework,
            )
            self._oww_key   = Path(self._model_path).stem
            self._backend   = "oww"
            logger.success("[AdminPhrase] OWW backend loaded ✓ (framework={})", framework)
            return True
        except Exception as e:
            logger.error("[AdminPhrase] OWW backend failed: {!r}", e)
            return False

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        model_path = Path(self._model_path)
        joblib_path = model_path.parent / f"{model_path.stem}.joblib"

        # A model exists if the joblib OR the tflite/onnx exists
        if not model_path.exists() and not joblib_path.exists():
            logger.warning(
                "[AdminPhrase] No model found at '{}' or '{}'. "
                "Admin phrase detection disabled.",
                self._model_path, joblib_path,
            )
            self._fallback = True
            return

        if not self._resolve_backend():
            logger.warning("[AdminPhrase] No usable backend found — admin phrase detection disabled.")
            self._fallback = True
            return

        self._running  = True
        self._stop_evt = threading.Event()
        self._thread   = threading.Thread(
            target=self._run_loop, daemon=True, name="AdminPhraseThread",
            args=(self._stop_evt,),
        )
        self._thread.start()
        logger.info("[AdminPhrase] Listening for admin phrase (backend={})...", self._backend)

    def stop(self):
        self._running = False
        self._stop_evt.set()

    # ─── Audio loop ───────────────────────────────────────────────────────────

    def _run_loop(self, stop_evt: threading.Event):
        audio_q: queue.Queue[bytes] = queue.Queue()
        dev = None if self._device_index == -1 else self._device_index

        def _callback(indata, frames, time, status):
            audio_q.put(bytes(indata))

        def _create_stream(target_dev):
            return sd.RawInputStream(
                samplerate=RATE, channels=CHANNELS, dtype="int16",
                blocksize=CHUNK, callback=_callback, device=target_dev,
            )

        # Sliding window buffer for joblib backend
        frame_buffer: list[bytes] = []

        while self._running and not stop_evt.is_set():
            if self._muted:
                import time as _time
                _time.sleep(0.1)
                continue

            stream = None
            try:
                stream = _create_stream(dev)
            except Exception:
                if dev is not None:
                    dev = None
                    try:
                        stream = _create_stream(None)
                    except Exception:
                        pass

            if stream is None:
                import time as _time
                _time.sleep(0.5)
                continue

            with stream:
                while self._running and not self._muted and not stop_evt.is_set():
                    try:
                        raw = audio_q.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if self._backend == "joblib":
                        score = self._score_joblib(raw, frame_buffer)
                    else:
                        pcm   = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                        score = float(self._oww_model.predict(pcm).get(self._oww_key, 0.0)) if self._oww_model and self._oww_key else 0.0

                    if score >= self._threshold:
                        logger.info("[AdminPhrase] Admin phrase detected (score={:.3f})", score)
                        self._fire_event(score)
                        # Clear buffer to avoid repeated triggers
                        frame_buffer.clear()

    # ─── Joblib scoring ───────────────────────────────────────────────────────

    def _score_joblib(self, raw: bytes, frame_buffer: list) -> float:
        """
        Accumulate CHUNK-sized frames; once we have JOBLIB_WINDOW_FRAMES,
        embed the window and score the GBM pipeline.  Returns the probability
        of the positive class.
        """
        frame_buffer.append(raw)
        if len(frame_buffer) < JOBLIB_WINDOW_FRAMES:
            return 0.0

        # Build a 2.5 s int16 window from the last N frames
        window = b"".join(frame_buffer[-JOBLIB_WINDOW_FRAMES:])
        pcm    = np.frombuffer(window, dtype=np.int16)

        try:
            # Pad/trim to the fixed clip length the model was trained on
            target = int(2.5 * RATE)
            if len(pcm) < target:
                pcm = np.pad(pcm, (0, target - len(pcm)))
            else:
                pcm = pcm[:target]

            if self._af is None or self._joblib_clf is None:
                return 0.0
            clips = pcm.reshape(1, -1)               # (1, samples) int16
            embs  = self._af.embed_clips(clips, batch_size=1)   # (1, frames, dim)
            feat  = embs.reshape(1, -1).astype(np.float32)      # (1, features)

            prob = float(self._joblib_clf.predict_proba(feat)[0][1])

            # Slide by half the window (50 % overlap)
            del frame_buffer[:JOBLIB_WINDOW_FRAMES // 2]

            return prob
        except Exception as e:
            logger.debug("[AdminPhrase] Joblib score error: {}", e)
            frame_buffer.clear()
            return 0.0

    # ─── Event ────────────────────────────────────────────────────────────────

    def _fire_event(self, confidence: float):
        if self._muted:
            return
        get_bus().publish_sync(Event(
            type=EventType.ADMIN_PHRASE_DETECTED,
            data={"confidence": confidence},
            source="admin_phrase",
        ))
