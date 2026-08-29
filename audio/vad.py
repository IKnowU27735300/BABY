"""
audio/vad.py — Silero VAD integration.
Provides:
  - capture_until_silence(): record speech, stop on silence
  - BargeInMonitor: detects speech during TTS playback
Uses sounddevice (pure Python) instead of pyaudio to avoid
Windows C-compiler build requirements.
"""

from __future__ import annotations
import asyncio
import queue
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from loguru import logger

RATE   = 16000
CHUNK  = 512           # 32 ms @ 16 kHz

# Hard ceiling on a single capture so the assistant can never hang recording.
DEFAULT_MAX_DURATION_S = 20.0
# Skip this many seconds of audio at the very start of a capture. Used to ignore
# the tail of Baby's own TTS playback bleeding into the mic ("echo").
DEFAULT_LEAD_IN_SKIP_S = 0.0




def _load_silero():
    """Load Silero VAD model once and cache it."""
    import torch
    res = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
    )
    model = res[0] if isinstance(res, (tuple, list)) else res
    return model


_silero_model = None
_silero_lock  = threading.Lock()


from typing import Any


def get_silero() -> Any:
    global _silero_model
    if _silero_model is None:
        with _silero_lock:
            if _silero_model is None:
                logger.info("[VAD] Loading Silero VAD model...")
                _silero_model = _load_silero()
                logger.success("[VAD] Silero VAD loaded ✓")
    return _silero_model


class VADEngine:
    def __init__(self, threshold: float = 0.20, silence_ms: int = 600, device_index: int = -1):
        self._threshold  = threshold
        self._silence_ms = silence_ms
        self._device_index = device_index
        self._muted = False
        self._cancel = threading.Event()
        self._capture_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="VAD-Capture"
        )

    def set_muted(self, muted: bool):
        self._muted = muted

    def stop(self):
        """Cancel any in-flight capture and stop accepting new ones (exit path).

        Called by BabyOrchestrator.shutdown() before process exit. Waits for
        the worker to finish so no sounddevice/torch thread outlives the Qt
        event loop (racing it caused 0xC0000005 in qwindows.dll / fail-fast
        in ucrtbase.dll at exit).
        """
        self._cancel.set()
        self._muted = True
        self._capture_executor.shutdown(wait=True, cancel_futures=True)

    async def capture_until_silence(
        self,
        silence_ms: int | None = None,
        cancel_token: asyncio.Event | threading.Event | None = None,
        max_duration_s: float = DEFAULT_MAX_DURATION_S,
        lead_in_skip_s: float = DEFAULT_LEAD_IN_SKIP_S,
    ) -> np.ndarray:
        """
        Record from mic until sustained silence is detected.

        IMPORTANT: the blocking sounddevice stream + Silero inference run in a
        dedicated worker thread (never on the asyncio event loop), so TTS
        playback, the event bus, and the orchestrator stay responsive.

        Returns a float32 numpy array at 16 kHz (possibly empty).
        """
        # Block if muted at the start (cheap await, no stream opened).
        while getattr(self, "_muted", False):
            if cancel_token and cancel_token.is_set():
                return np.zeros(0, dtype=np.float32)
            await asyncio.sleep(0.1)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._capture_executor,
            lambda: self._capture_sync(
                silence_ms=silence_ms,
                cancel_token=cancel_token,
                max_duration_s=max_duration_s,
                lead_in_skip_s=lead_in_skip_s,
            ),
        )

    def _capture_sync(
        self,
        silence_ms: int | None,
        cancel_token: asyncio.Event | threading.Event | None,
        max_duration_s: float,
        lead_in_skip_s: float,
    ) -> np.ndarray:
        """Blocking recorder. Runs in a worker thread (see capture_until_silence)."""
        import torch
        model   = get_silero()
        chunk_duration_s = CHUNK / RATE  # 0.032s (32ms per chunk)
        chunk_duration_ms = chunk_duration_s * 1000.0  # 32.0ms

        silence = silence_ms or self._silence_ms
        limit   = int(silence / chunk_duration_ms)   # chunks of silence to end

        audio_q: queue.Queue[bytes] = queue.Queue()

        dev = None if self._device_index == -1 else self._device_index

        def _callback(indata, frames, time, status):
            audio_q.put(bytes(indata))

        logger.info("[VAD] Starting capture on device {} (threshold={})...", dev, self._threshold)
        frames_list: list[bytes] = []
        preroll_buf: deque[bytes] = deque(maxlen=4)
        silent_chunks  = 0
        initial_silent_chunks = 0
        initial_silent_limit = int(5000.0 / chunk_duration_ms)  # 5 seconds limit to start speaking
        speech_started = False
        lead_in_chunks = int(lead_in_skip_s / chunk_duration_s) if lead_in_skip_s else 0
        lead_in_done   = lead_in_chunks <= 0
        recorded_chunks = 0
        max_chunks = int(max_duration_s / chunk_duration_s)

        def _create_stream(target_dev):
            return sd.RawInputStream(
                samplerate=RATE, channels=1, dtype="int16",
                blocksize=CHUNK, callback=_callback, device=target_dev,
            )

        # Small delay before opening the mic — gives the audio hardware time
        # to be released from a previous capture or TTS playback (avoiding
        # "Device unavailable" errors on rapid re-enters).
        time.sleep(0.05)

        stream = None
        last_err: Exception | None = None
        devices_to_try = [dev, None] if dev is not None else [None]
        for attempt_dev in devices_to_try:
            for retry in range(3):
                try:
                    stream = _create_stream(attempt_dev)
                    break
                except Exception as err:
                    last_err = err
                    if retry < 2:
                        logger.warning(
                            "[VAD] Stream open failed on device {} (attempt {}/3): {}. Retrying...",
                            attempt_dev, retry + 1, err,
                        )
                        time.sleep(0.3)
                    else:
                        logger.warning(
                            "[VAD] Stream open failed on device {} after 3 attempts: {}",
                            attempt_dev, err,
                        )
            if stream is not None:
                break
            if attempt_dev is None:
                # Tried default mic, exhausted all retries.
                logger.error("[VAD] Failed to open mic stream after retries: {}. "
                             "Check mic connection, Windows permissions, or "
                             "try setting audio.device_index in config.yaml.", last_err)
                return np.zeros(0, dtype=np.float32)
            # Configured device failed — fall through to try default.
            logger.warning("[VAD] Falling back to default mic.")

        if stream is None:
            return np.zeros(0, dtype=np.float32)

        with stream:
            while True:
                if (cancel_token and cancel_token.is_set()) or getattr(self, "_muted", False) or self._cancel.is_set():
                    break

                # Hard ceiling — never record forever (prevents hangs).
                if recorded_chunks >= max_chunks:
                    logger.debug("[VAD] Reached max capture duration {:.1f}s.", max_duration_s)
                    break

                try:
                    raw = audio_q.get(timeout=0.1)
                except queue.Empty:
                    continue

                recorded_chunks += 1

                # Skip the lead-in window (e.g. Baby's own TTS echo) entirely.
                if not lead_in_done:
                    lead_in_chunks -= 1
                    if lead_in_chunks <= 0:
                        lead_in_done = True
                    continue

                pcm_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                pcm  = torch.from_numpy(pcm_np)
                prob = float(model(pcm, RATE).item())
                rms  = float(np.sqrt(np.mean(pcm_np**2)))

                # Dual Detector: Silero VAD threshold OR Audio Energy RMS + speech likelihood
                is_speech_frame = (prob > self._threshold) or (rms > 0.002 and prob > 0.03)

                if is_speech_frame:
                    if not speech_started:
                        speech_started = True
                        frames_list.extend(preroll_buf)
                        preroll_buf.clear()
                    silent_chunks  = 0
                    frames_list.append(raw)
                elif speech_started:
                    frames_list.append(raw)
                    silent_chunks += 1
                    if silent_chunks >= limit:
                        break
                else:
                    preroll_buf.append(raw)
                    initial_silent_chunks += 1
                    if initial_silent_chunks >= initial_silent_limit:
                        logger.debug("[VAD] No speech detected within 5s, timing out.")
                        break

        audio = np.frombuffer(b"".join(frames_list), dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) == 0:
            logger.info("[VAD] Capture ended — no speech detected (timed out after 5s).")
        else:
            logger.info("[VAD] Captured {:.2f}s of speech ({} chunks).", len(audio) / RATE, len(frames_list))
        return audio


    def is_speech(self, pcm_float32: np.ndarray) -> bool:
        """Quick single-chunk speech probability check."""
        import torch
        model = get_silero()
        t     = torch.from_numpy(pcm_float32)
        return float(model(t, RATE).item()) > self._threshold


class BargeInMonitor:
    """
    Monitors the microphone during TTS playback.
    Sets `barge_in_event` when speech is detected.

    The blocking sounddevice stream runs in a worker thread so it never stalls
    the asyncio event loop (which runs TTS playback + the orchestrator).
    """

    def __init__(self, threshold: float = 0.5, device_index: int = -1):
        self._threshold  = threshold
        self._device_index = device_index
        self._task: asyncio.Task | None = None
        self.barge_in_event = asyncio.Event()
        self._muted = False
        # Per-session stop flag. stop() sets the CURRENT session's flag so an
        # old worker thread terminates on its next loop iteration instead of
        # lingering for up to 2 minutes (and re-firing barge-ins).
        self._stop_evt: threading.Event | None = None
        self._monitor_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="BargeIn"
        )

    def set_muted(self, muted: bool):
        self._muted = muted

    def start(self):
        # Fresh session: a new stop flag means a previous, still-exiting worker
        # keeps watching its OWN flag and cannot be re-awakened by this start.
        self._stop_evt = threading.Event()
        self.barge_in_event.clear()
        self._task = asyncio.create_task(self._monitor(), name="BargeInMonitor")

    def stop(self):
        stop_evt = self._stop_evt
        if stop_evt is not None:
            stop_evt.set()
        if self._task and not self._task.done():
            self._task.cancel()
        self.barge_in_event.clear()

    def shutdown(self):
        """Exit path: stop the worker and release the executor for good."""
        self.stop()
        self._monitor_executor.shutdown(wait=True, cancel_futures=True)

    async def _monitor(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._monitor_executor, self._monitor_sync)

    def _monitor_sync(self):
        import torch
        model   = get_silero()
        audio_q: queue.Queue[bytes] = queue.Queue()

        dev = None if self._device_index == -1 else self._device_index

        def _callback(indata, frames, time, status):
            audio_q.put(bytes(indata))

        # Skip the first ~0.6s of playback (Baby's own voice) so it does not
        # count as the user barging in.
        chunk_duration_s = CHUNK / RATE
        lead_in_chunks = int(0.6 / chunk_duration_s)
        max_chunks = int(120.0 / chunk_duration_s)  # safety cap: 2 minutes
        recorded = 0

        def _create_stream(target_dev):
            return sd.RawInputStream(
                samplerate=RATE, channels=1, dtype="int16",
                blocksize=CHUNK, callback=_callback, device=target_dev,
            )

        try:
            stream = _create_stream(dev)
        except Exception as err:
            if dev is not None:
                logger.warning("[BargeIn] Failed to open mic index {} ({}). Falling back to default mic.", dev, err)
                dev = None
                try:
                    stream = _create_stream(None)
                except Exception as fatal_err:
                    logger.error("[BargeIn] Failed to open default mic stream: {}", fatal_err)
                    return
            else:
                logger.error("[BargeIn] Failed to open mic stream: {}", err)
                return

        try:
            with stream:
                while True:
                    stop_evt = self._stop_evt
                    if self._muted or stop_evt is None or stop_evt.is_set():
                        return
                    if self.barge_in_event.is_set():
                        return
                    if recorded >= max_chunks:
                        return

                    try:
                        raw = audio_q.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    recorded += 1
                    if lead_in_chunks > 0:
                        lead_in_chunks -= 1
                        continue

                    pcm = torch.from_numpy(
                        np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    )
                    if float(model(pcm, RATE).item()) > self._threshold:
                        if stop_evt.is_set():
                            return
                        logger.info("[BargeIn] Speech detected during TTS — interrupting!")
                        self.barge_in_event.set()
                        return
        except asyncio.CancelledError:
            pass




















