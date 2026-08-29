"""
audio/wake_word.py — OpenWakeWord "Hey Baby" detector.
Runs in a dedicated background thread. Zero asyncio blocking.
Falls back to Ctrl+F12 hotkey if model file is missing.
"""

from __future__ import annotations
import asyncio
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from loguru import logger

from core.event_bus import get_bus, Event, EventType

RATE     = 16000
CHANNELS = 1
CHUNK    = 1280          # 80 ms @ 16 kHz — OWW expected chunk size



class WakeWordDetector:
    """
    Runs OpenWakeWord in a background thread.
    On detection, publishes WAKE_WORD_DETECTED to the event bus.
    """

    def __init__(self, model_path: str, threshold: float = 0.70, device_index: int = -1):
        self._model_path = model_path
        self._threshold  = threshold
        self._device_index = device_index
        self._running    = False
        self._thread: threading.Thread | None = None
        self._model      = None
        self._fallback   = False        # True if using keyboard hotkey
        self._muted      = False
        # Per-generation stop flag. stop() sets it; start() creates a fresh one
        # so a restarted session never revives the previous thread.
        self._stop_evt   = threading.Event()

    def set_muted(self, muted: bool):
        self._muted = muted

    # ─── Public API ──────────────────────────────────────────────────────────

    def update_device(self, device_index: int):
        """Update active microphone device and restart listener if active."""
        self._device_index = device_index
        if self._running and not self._fallback:
            logger.info("[WakeWord] Restarting wake-word engine on new microphone device...")
            self.stop()
            if self._thread:
                self._thread.join(timeout=2.0)
            self.start()

    def start(self):
        if not Path(self._model_path).exists():
            logger.warning(
                "[WakeWord] Model not found at '{}'. "
                "Using Ctrl+F12 as fallback wake trigger.", self._model_path
            )
            self._fallback = True
            self._start_keyboard_fallback()
            return

        try:
            from openwakeword.model import Model
            # Prefer the bundled .onnx variant — it runs on onnxruntime (already
            # shipped), while the .tflite variant needs tflite-runtime.
            model_file = self._model_path
            inference_framework = "tflite"
            onnx_path = Path(self._model_path).with_suffix(".onnx")
            if onnx_path.exists():
                model_file = str(onnx_path)
                inference_framework = "onnx"
            self._model = Model(
                wakeword_models=[model_file],
                inference_framework=inference_framework,
            )
            logger.success("[WakeWord] OpenWakeWord model loaded ✓ (framework={})", inference_framework)
        except ImportError as e:
            logger.error("[WakeWord] openwakeword import failed: {} — falling back to Ctrl+F12.", e)
            self._fallback = True
            self._start_keyboard_fallback()
            return
        except Exception as e:
            logger.error("[WakeWord] WakeWord init failed: {!r} — falling back to Ctrl+F12.", e)
            self._fallback = True
            self._start_keyboard_fallback()
            return

        self._running = True
        self._stop_evt = threading.Event()   # new generation
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="WakeWordThread",
            args=(self._stop_evt,),
        )
        self._thread.start()
        logger.info("[WakeWord] Listening for 'Hey Baby'...")

    def stop(self):
        self._running = False
        self._stop_evt.set()

    # ─── Main audio loop ─────────────────────────────────────────────────────

    def _run_loop(self, stop_evt: threading.Event):
        audio_q: queue.Queue[bytes] = queue.Queue()
        model_key = Path(self._model_path).stem   # "hey_baby"

        dev = None if self._device_index == -1 else self._device_index

        def _callback(indata, frames, time, status):
            audio_q.put(bytes(indata))

        def _create_stream(target_dev):
            return sd.RawInputStream(
                samplerate=RATE, channels=CHANNELS, dtype="int16",
                blocksize=CHUNK, callback=_callback, device=target_dev,
            )

        while self._running and not stop_evt.is_set():
            if self._muted:
                import time
                time.sleep(0.1)
                continue

            stream = None
            try:
                stream = _create_stream(dev)
            except Exception as err:
                if dev is not None:
                    dev = None
                    try:
                        stream = _create_stream(None)
                    except Exception:
                        pass

            if stream is None:
                import time
                time.sleep(0.5)
                continue

            with stream:
                while self._running and not self._muted and not stop_evt.is_set():
                    try:
                        raw = audio_q.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if self._model is None:
                        continue
                    pcm    = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    scores = self._model.predict(pcm)
                    score  = float(scores.get(model_key, 0.0))

                    if score >= self._threshold:
                        logger.info("[WakeWord] 'Hey Baby' detected (score={:.2f})", score)
                        self._fire_event(score)


    def _fire_event(self, confidence: float):
        if self._muted:
            return
        bus = get_bus()
        bus.publish_sync(Event(
            type=EventType.WAKE_WORD_DETECTED,
            data={"confidence": confidence},
            source="wake_word",
        ))

    # ─── Keyboard fallback ───────────────────────────────────────────────────

    def _start_keyboard_fallback(self):
        """Use pynput to listen for Ctrl+F12 as a wake/toggle trigger."""
        def _listen():
            try:
                from pynput import keyboard
                ctrl_held = False

                def on_press(key):
                    nonlocal ctrl_held
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                        ctrl_held = True
                    if ctrl_held and key == keyboard.Key.f12:
                        # Never fire while muted (e.g. during active conversation
                        # or the brief window right after activation) — otherwise a
                        # stray Ctrl+F12 would toggle the assistant off mid-turn.
                        if self._muted:
                            return
                        logger.info("[WakeWord] Ctrl+F12 triggered (fallback)")
                        self._fire_event(1.0)

                def on_release(key):
                    nonlocal ctrl_held
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                        ctrl_held = False

                with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                    listener.join()
            except ImportError:
                logger.error("[WakeWord] pynput not installed. Cannot create keyboard fallback.")

        t = threading.Thread(target=_listen, daemon=True, name="WakeHotkeyThread")
        t.start()



















