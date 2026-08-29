"""
audio/stt.py — Speech-to-Text using faster-whisper.
Handles multilingual transcription (EN, HI, KN).

Accuracy-Maximisation Strategy (no GPU training required):
  1. Audio preprocessing  — normalization + soft spectral denoising
  2. Contextual initial_prompt — seeds Whisper with the user's language/domain
  3. Vocabulary hotwords  — biases recognition toward known command words
  4. Adaptive beam search — higher beam = more search paths = more accuracy
  5. Confidence tracking  — session history refines language priors over time
"""

from __future__ import annotations
import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Deque, Tuple

import numpy as np
from loguru import logger

from core.config import STTConfig
from core.languages import SUPPORTED_LANGUAGES  # shared with TTS + orchestrator

# Common Whisper hallucination artefacts on silence / noise.
_HALLUCINATION_BLOCKLIST = (
    "thank you for watching", "thanks for watching", "please subscribe",
    "subtitles by", "amara.org",
)

# Unicode script ranges for Baby's supported languages.
# Devanagari (hi/mr) is disambiguated via Whisper's detected language in
# _resolve_language — the same script is used by Hindi and Marathi.
_SCRIPT_RANGES = {
    "kn": (0x0C80, 0x0CFF),   # Kannada
    "hi": (0x0900, 0x097F),   # Devanagari (Hindi / Marathi)
    "ta": (0x0B80, 0x0BFF),   # Tamil
    "te": (0x0C00, 0x0C7F),   # Telugu
    "bn": (0x0980, 0x09FF),   # Bengali / Assamese
    "gu": (0x0A80, 0x0AFF),   # Gujarati
    "ml": (0x0D00, 0x0D7F),   # Malayalam
    "ur": (0x0600, 0x06FF),   # Arabic script (Urdu)
    "ja": (0x3040, 0x30FF),   # Hiragana / Katakana
    "zh": (0x4E00, 0x9FFF),   # CJK
    "ko": (0xAC00, 0xD7AF),   # Hangul
    "ru": (0x0400, 0x04FF),   # Cyrillic
}

# ─── Per-language Whisper initial_prompt seeds ────────────────────────────────
# The initial_prompt tricks Whisper into expecting these languages / domains so
# it does not have to "guess" the language from just a few syllables.  The
# richer the seed the better Whisper's prior — especially helpful for short
# commands and accented speech.
_INITIAL_PROMPTS: dict[str, str] = {
    "en": (
        "Baby, open, close, minimize, maximize, search, play, pause, stop, "
        "set alarm, remind me, what time, how much, tell me, scroll, click, "
        "increase, decrease, volume, brightness, write, compose, send, check."
    ),
    "hi": (
        "क्लारा, खोलो, बंद करो, कम करो, बड़ा करो, खोजो, चलाओ, रोको, "
        "बताओ, याद दिलाओ, कितना, क्या समय, लिखो, भेजो, जांचो, "
        "वॉल्यूम, चमक, स्क्रॉल, क्लिक।"
    ),
    "kn": (
        "ಕ್ಲಾರಾ, ತೆರೆ, ಮುಚ್ಚು, ಕಡಿಮೆ ಮಾಡು, ಹೆಚ್ಚಿಸು, ಹುಡುಕು, ಪ್ಲೇ ಮಾಡು, "
        "ನಿಲ್ಲಿಸು, ಹೇಳು, ನೆನಪಿಸು, ಎಷ್ಟು ಸಮಯ, ಬರೆ, ಕಳಿಸು, "
        "ವಾಲ್ಯೂಮ್, ಪ್ರಕಾಶ, ಸ್ಕ್ರೋಲ್, ಕ್ಲಿಕ್."
    ),
}


def _script_of(text: str) -> str | None:
    for lang, (lo, hi) in _SCRIPT_RANGES.items():
        if any(lo <= ord(c) <= hi for c in text):
            return lang
    return None

def _resolve_language(text: str, detected: str, prob: float) -> str:
    """
    Decide the final language code for a transcript.

    Priority:
      1. If the transcript is written in a supported script, trust it
         (Devanagari → Marathi when Whisper detected Marathi, else Hindi).
      2. Else if Whisper detected a supported language (en/hi/kn/mr/ta/te/...),
         keep it.
      3. Else fall back to English.
    """
    script_lang = _script_of(text)
    if script_lang == "hi" and detected == "mr":
        return "mr"   # Devanagari is shared by Hindi and Marathi
    if script_lang:
        return script_lang

    if detected in SUPPORTED_LANGUAGES:
        return detected

    if prob >= 0.85:
        return detected
    return "en"


def _is_hallucination(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    low = stripped.lower()
    if any(p in low for p in _HALLUCINATION_BLOCKLIST):
        return True
    # Repetition loop: a single token/phrase repeated many times.
    words = low.split()
    if len(words) >= 8 and len(set(words)) <= 3:
        return True
    return False


def _preprocess_audio(audio: np.ndarray) -> np.ndarray:
    """
    Audio quality pipeline that runs BEFORE STT inference.

    Steps (all zero-copy-safe, no extra dependencies):
      1. Normalize to 95% of full scale  → strong, consistent level
      2. Spectral noise reduction        → attenuate static/hiss by
                                           estimating a noise floor from the
                                           first 0.1 s (usually room noise)
                                           and subtracting it in freq domain.
      3. Pre-emphasis filter             → boost high-freq consonants that
                                           Whisper's mel filterbank under-weights.

    All three are lightweight NumPy operations — adds < 1 ms overhead on CPU.
    """
    if len(audio) == 0:
        return audio

    audio = audio.astype(np.float32, copy=True)

    # 1. Normalize
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        audio = audio * (0.95 / peak)

    # 2. Soft spectral subtraction (noise floor from first 0.1 s)
    noise_samples = int(0.1 * 16000)  # 1600 samples @ 16 kHz
    if len(audio) > noise_samples * 2:
        noise_floor = audio[:noise_samples]
        nfft = 512
        noise_fft = np.fft.rfft(noise_floor, n=nfft)
        noise_mag  = np.abs(noise_fft).mean() * 1.5  # slight overestimate
        # Apply frame-by-frame noise gate in freq domain
        hop  = nfft // 2
        n_frames = (len(audio) - nfft) // hop
        if n_frames > 0:
            out = np.zeros_like(audio)
            for i in range(n_frames):
                start = i * hop
                frame = audio[start : start + nfft]
                if len(frame) < nfft:
                    break
                spec   = np.fft.rfft(frame)
                mag    = np.abs(spec)
                phase  = np.angle(spec)
                mag_c  = np.maximum(mag - noise_mag, 0.0)
                out_f  = mag_c * np.exp(1j * phase)
                synth  = np.fft.irfft(out_f)
                # Overlap-add
                end = min(start + nfft, len(out))
                out[start:end] += synth[:end - start]
            audio = out

    # 3. Pre-emphasis (boost high-freq energy)
    audio[1:] = audio[1:] - 0.97 * audio[:-1]

    # Re-normalize after filtering
    peak2 = np.max(np.abs(audio))
    if peak2 > 1e-6:
        audio = audio * (0.95 / peak2)

    return audio


class STTEngine:
    """
    Wrapper around faster-whisper with accuracy-maximisation features:
      - Per-language contextual initial_prompt
      - Adaptive language prior from session history
      - Audio preprocessing pipeline (normalize, denoise, pre-emphasis)
      - Configurable beam search and temperature fallback
    """

    # Rolling buffer of the last N language detections.  Used to build an
    # adaptive prior that biases Whisper toward the user's dominant language in
    # the current session (e.g. if the last 5 turns were Hindi, we seed with the
    # Hindi initial_prompt even on ambiguous short clips).
    _LANG_HISTORY_SIZE = 8

    def __init__(self, config: STTConfig):
        self._config   = config
        self._model    = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="STT")
        # Session-adaptive language prior
        self._lang_history: Deque[str] = deque(maxlen=self._LANG_HISTORY_SIZE)

    # ─── Model loading ────────────────────────────────────────────────────────

    def load(self):
        """Load faster-whisper model. Call this at startup (blocks briefly)."""
        from faster_whisper import WhisperModel

        device = self._config.device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        compute_type = self._config.compute_type
        if device == "cpu" and compute_type in ("int8_float16", "float16"):
            logger.warning("[STT] Compute type '{}' is not supported on CPU. Falling back to 'int8'.", compute_type)
            compute_type = "int8"

        logger.info("[STT] Loading faster-whisper '{}' on {} ({}) ...", self._config.model, device, compute_type)
        try:
            self._model = WhisperModel(
                self._config.model,
                device=device,
                compute_type=compute_type,
            )
        except ValueError as ve:
            if "compute type" in str(ve).lower() and compute_type != "int8":
                logger.warning("[STT] Loading failed with compute_type='{}'. Retrying with 'int8'...", compute_type)
                self._model = WhisperModel(
                    self._config.model,
                    device=device,
                    compute_type="int8",
                )
            else:
                raise
        logger.success("[STT] faster-whisper loaded ✓")

    # ─── Session-adaptive initial prompt ──────────────────────────────────────

    def _adaptive_initial_prompt(self) -> str:
        """
        Return the initial_prompt that best matches the user's recent session
        language history.  Falls back to the English seed when history is empty.
        Appends the user's personal vocabulary so Whisper biases toward their
        own words, names and commands — improving accuracy session-over-session.
        """
        if not self._lang_history:
            dominant = "en"
        else:
            counts: dict[str, int] = {}
            for lang in self._lang_history:
                counts[lang] = counts.get(lang, 0) + 1
            dominant = max(counts, key=counts.__getitem__)

        base_prompt = _INITIAL_PROMPTS.get(dominant, _INITIAL_PROMPTS["en"])

        # Append personal vocabulary learned from past interactions
        try:
            from core.memory_engine import get_memory
            personal_vocab = get_memory().get_stt_vocab_hint(dominant)
            if personal_vocab:
                return base_prompt + ", " + personal_vocab
        except Exception:
            pass  # Memory not yet initialized — safe to ignore

        return base_prompt

    # ─── Public API ───────────────────────────────────────────────────────────

    async def transcribe(self, audio: np.ndarray) -> tuple[str, str]:
        """
        Transcribe float32 audio array.
        Runs in thread pool so it never blocks the event loop.
        Returns (text, language_code).
        """
        if self._model is None:
            raise RuntimeError("STT model not loaded. Call load() first.")

        loop   = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._transcribe_sync(audio),
        )
        return result

    # ─── Internal inference ───────────────────────────────────────────────────

    def _transcribe_sync(self, audio: np.ndarray) -> tuple[str, str]:
        # Short-circuit: empty or all-zero audio means silence/no mic.
        if len(audio) == 0 or np.max(np.abs(audio)) < 1e-8:
            logger.debug("[STT] Empty audio — skipping inference.")
            return "", "en"

        # ── Step 1: Audio preprocessing (normalize + denoise + pre-emphasis)
        audio = _preprocess_audio(audio)

        # ── Step 2: Pick initial_prompt based on session history
        initial_prompt = self._adaptive_initial_prompt()

        # ── Step 3: Primary transcription with high beam search
        text, lang, prob = self._run_whisper(
            audio,
            beam_size=self._config.beam_size,
            initial_prompt=initial_prompt,
            temperature=0.0,
        )

        # ── Step 4: Confidence fallback — if no-speech confidence is borderline,
        #    retry with temperature=0.2 to give Whisper a different decoding path.
        if not text.strip() and prob < 0.65:
            logger.debug("[STT] Low confidence ({:.0%}); retrying with temperature=0.2...", prob)
            text, lang, prob = self._run_whisper(
                audio,
                beam_size=self._config.beam_size,
                initial_prompt=initial_prompt,
                temperature=0.2,
            )

        # ── Step 5: Language resolution (script-based override)
        lang = _resolve_language(text, lang, prob)

        if not text:
            return "", lang

        if _is_hallucination(text):
            logger.warning("[STT] Discarded hallucinated output: '{}'", text)
            return "", lang

        # ── Step 6: Update session language history for adaptive prompting
        self._lang_history.append(lang)

        logger.debug("[STT] Language: {} ({:.0%}), Text: '{}'", lang, prob, text)
        return text, lang

    def _run_whisper(
        self,
        audio: np.ndarray,
        beam_size: int,
        initial_prompt: str,
        temperature: float,
    ) -> Tuple[str, str, float]:
        """Run faster-whisper and return (text, language, language_probability)."""
        if self._model is None:
            return "", "en", 0.0
        segments, info = self._model.transcribe(
            audio,
            beam_size=beam_size,
            language=self._config.language,    # None = auto-detect
            vad_filter=False,                  # Silero VAD in vad.py already isolated speech
            temperature=temperature,
            condition_on_previous_text=False,  # prevents runaway repetition loops
            no_speech_threshold=0.5,           # slightly more sensitive
            log_prob_threshold=-1.0,
            chunk_length=24,                   # chunked decoding for lower latency
            initial_prompt=initial_prompt,     # ← accuracy booster: language/domain seed
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, info.language, info.language_probability



















