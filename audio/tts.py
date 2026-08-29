"""
audio/tts.py — Text-to-Speech engine.
Primary: edge-tts (native Microsoft neural voices — fluent Kannada, Hindi,
         Marathi, Tamil, Telugu + 12 more languages, zero local model cost).
Fallback: Kokoro-ONNX (fast, zero-cost, local, en/hi/es/fr/it/pt/ja/zh only).
Cloud option: Gemini TTS for scripts Kokoro cannot render when a key is set.
"""

from __future__ import annotations
import asyncio
import base64
import re
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import numpy as np
from loguru import logger

from core.config import TTSConfig
from core.languages import SPOKEN_LANGUAGES


KOKORO_LANG_CODES: dict[str, str] = {
    "en": "en-us",
    "hi": "hi",
    "kn": "hi",  # Kokoro has no Kannada model; kn script routes to Gemini instead.
}

KOKORO_LANG_VOICES: dict[str, str] = {
    "en": "af_kore",
    "hi": "hf_alpha",
    "kn": "hf_alpha",
}

# Unicode script ranges → language, in priority order. Devanagari is shared by
# Hindi and Marathi — it always maps to Hindi (Marathi is never spoken).
_SCRIPT_LANG_RANGES: tuple[tuple[str, int, int], ...] = (
    ("hi", 0x0900, 0x097F),  # Devanagari → Hindi (Marathi excluded from speech)
    ("kn", 0x0C80, 0x0CFF),  # Kannada
    ("ta", 0x0B80, 0x0BFF),  # Tamil
    ("te", 0x0C00, 0x0C7F),  # Telugu
    ("bn", 0x0980, 0x09FF),  # Bengali / Assamese
    ("gu", 0x0A80, 0x0AFF),  # Gujarati
    ("ml", 0x0D00, 0x0D7F),  # Malayalam
    ("ur", 0x0600, 0x06FF),  # Arabic script (Urdu)
    ("ja", 0x3040, 0x30FF),  # Hiragana / Katakana
    ("zh", 0x4E00, 0x9FFF),  # CJK
    ("ko", 0xAC00, 0xD7AF),  # Hangul
    ("ru", 0x0400, 0x04FF),  # Cyrillic
)


class TTSEngine:
    def __init__(self, config: TTSConfig):
        self._config      = config
        self._pipeline    = None
        self._engine_type = "kokoro"
        self._last_lang   = "en"
        self._synthesis_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="TTS-Synth")
        self._playback_executor  = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TTS-Play")
        self._lock        = asyncio.Lock()
        self._stop_evt    = asyncio.Event()
        self._muted       = False

    def set_muted(self, muted: bool):
        self._muted = muted
        if muted:
            self.stop()

    # ─── Language Tracking ───────────────────────────────────────────────────

    def set_last_language(self, lang: str):
        """Update last active user input language code (e.g. 'en', 'hi', 'kn')."""
        self._last_lang = lang
        logger.debug("[TTS] Updated active language reference to: {}", lang)

    def _has_unsupported_script(self, text: str) -> bool:
        """True if `text` is in a script Kokoro cannot render locally."""
        for lang, lo, hi in _SCRIPT_LANG_RANGES:
            if lang in ("en", "hi", "mr", "es", "fr", "it", "pt", "ja", "zh"):
                continue
            if any(lo <= ord(c) <= hi for c in text):
                return True
        return False

    def _detect_lang(self, text: str) -> str:
        """Detect language code from script ranges, falling back to _last_lang.

        Result is ALWAYS clamped to SPOKEN_LANGUAGES (en/hi/kn) — Baby never
        speaks any other language. Text in an unallowed script or last-language
        falls back to English.
        """
        has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in text)
        has_cjk = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
        if has_kana or (has_cjk and self._last_lang == "ja"):
            lang = "ja"
        else:
            lang = ""
            for c in text:
                o = ord(c)
                for lng, lo, hi in _SCRIPT_LANG_RANGES:
                    if lo <= o <= hi:
                        lang = lng
                        break
                if lang:
                    break
        if not lang:
            lang = (self._last_lang or "en").lower().strip()
        if lang not in SPOKEN_LANGUAGES:
            logger.debug("[TTS] '{}' not in spoken set (en/hi/kn); clamping to 'en'", lang)
            lang = "en"
        return lang

    def _resolve_kokoro(self, text: str, requested_voice: str) -> tuple[str, str]:
        """Return (voice_id, lang_code) for Kokoro based on detected language.

        Uses two pre-trained zero-shot voice models (no training required):
          1. English Voice Model (default: af_kore / English voice) for English
          2. Indic Voice Model (default: hf_alpha) for Hindi and Kannada
        """
        lang = self._detect_lang(text)
        lang_code = KOKORO_LANG_CODES.get(lang, "en-us")

        _KOKORO_ALIAS: dict[str, str] = {
            "mahiru": "af_kore",
            "kore": "af_kore",
            "puck": "am_puck",
        }
        clean_voice = (requested_voice or "").split(" ")[0].strip().lower()
        clean_voice = _KOKORO_ALIAS.get(clean_voice, clean_voice)

        # Kokoro voice ids look like "af_kore", "hf_alpha", "am_puck".
        # Config voices are Edge-style ("en-US-AvaNeural") and must NOT be
        # passed to Kokoro — map them to the per-language Kokoro voice instead.
        _KOKORO_VOICE_RE = re.compile(r"^[a-z0-9]{1,3}_[a-z0-9_]+$")

        if lang in ("hi", "kn"):
            # Pre-trained Indic Voice Model for Hindi & Kannada
            voice = KOKORO_LANG_VOICES.get(lang, "hf_alpha")
        elif clean_voice and _KOKORO_VOICE_RE.match(clean_voice):
            voice = clean_voice
        else:
            voice = KOKORO_LANG_VOICES.get(lang, KOKORO_LANG_VOICES["en"])

        logger.debug("[TTS] Kokoro resolved lang={} voice={} code={}", lang, voice, lang_code)
        return voice, lang_code

    def _prepare_speech_text(self, text: str) -> str:
        """Flatten markdown and whitespace so speech output sounds more natural,
        stripping any URLs, links, or web addresses so they are never spoken aloud."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)

        # 1. Clean markdown links: [Label](URL)
        # If label is itself a URL/web address, replace whole link with empty string, otherwise keep label.
        def _clean_md_link(match: re.Match) -> str:
            label = match.group(1).strip()
            if re.search(r"^(?:https?|ftp|file)://", label, re.I) or re.search(r"^www\.", label, re.I) or re.search(r"^[a-zA-Z0-9.-]+\.(?:com|org|net|gov|edu|io|co|ai|in|dev|app|me|info|biz)\b", label, re.I):
                return ""
            return label
        text = re.sub(r"\[(.*?)\]\((.*?)\)", _clean_md_link, text)

        # 2. Strip raw scheme URLs (http://, https://, ftp://, file://)
        text = re.sub(r"\b(?:https?|ftp|file)://[^\s<>\"'\\]+", "", text, flags=re.IGNORECASE)

        # 3. Strip www. web addresses
        text = re.sub(r"\bwww\.[^\s<>\"'\\]+", "", text, flags=re.IGNORECASE)

        # 4. Strip domain-style website addresses (e.g. web.whatsapp.com, google.com/search, etc.)
        tld_pattern = r"\b[a-zA-Z0-9.-]+\.(?:com|org|net|gov|edu|io|co|ai|in|dev|app|me|info|biz|co\.in|co\.uk|org\.in)(?:/[^\s<>\"'\\]*)?\b"
        text = re.sub(tld_pattern, "", text, flags=re.IGNORECASE)

        # 5. Clean up lingering prepositions/colons that directly preceded URLs
        text = re.sub(r"\b(?:at|to|from|on|via|url|link)\s*:\s*", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:at|to|from|on|via)\s+([,.;:!?])", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:at|to|from|on|via)\s*$", "", text.strip(), flags=re.IGNORECASE)

        # 6. Flatten lists, markdown characters, and whitespace
        text = re.sub(r"(?m)^\s*[-*•]\s+", "", text)
        text = re.sub(r"[*_`#>]", "", text)
        text = re.sub(r"\n{2,}", ". ", text)
        text = re.sub(r"\n+", ", ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        return text.strip()

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def load(self):
        """Load preferred TTS models."""
        if self._config.engine == "xtts":
            self._load_xtts_or_kokoro()
        elif self._config.engine == "gemini":
            self._load_gemini()
        elif self._config.engine == "kokoro":
            self._load_kokoro()
        else:
            self._load_edge()

    def _download_file(self, url: str, path: str, desc: str):
        import urllib.request
        logger.info("Downloading {} from {}...", desc, url)
        try:
            urllib.request.urlretrieve(url, path)
            logger.success("Successfully downloaded {} to {} ✓", desc, path)
        except Exception as e:
            logger.error("Failed to download {}: {}", desc, e)
            raise

    def _load_xtts_or_kokoro(self):
        import os
        from pathlib import Path
        
        # Sourcing speaker reference WAV (default to Mahiru reference if present)
        ref_wav = Path("data/mahiru_reference.wav")
        if not ref_wav.exists():
            ref_wav = Path("data/kore_reference.wav")
        if not ref_wav.exists():
            ref_wav = Path("data/baby_reference.wav")
            
        ref_wav.parent.mkdir(parents=True, exist_ok=True)
        if not ref_wav.exists():
            try:
                self._download_file(
                    "https://raw.githubusercontent.com/coqui-ai/TTS/main/tests/data/ljspeech/wavs/LJ001-0001.wav",
                    str(ref_wav),
                    "BABY speaker reference voice sample"
                )
            except Exception as e:
                logger.error("[TTS] Failed to download reference WAV: {}", e)
        self._speaker_wav = ref_wav

        # 1. Try to load local Coqui XTTS-v2
        try:
            logger.info("[TTS] Loading local Coqui XTTS-v2...")
            os.environ["COQUI_TOS_AGREED"] = "1"
            import torch
            
            # Monkeypatch torch.load to bypass PyTorch 2.6+ strict safe unpickler errors
            orig_load = torch.load
            def patched_load(*args, **kwargs):
                kwargs['weights_only'] = False
                return orig_load(*args, **kwargs)
            torch.load = patched_load

            # Monkeypatch torchaudio.load to bypass torchcodec dependency
            import torchaudio
            import soundfile as sf
            def patched_audio_load(uri, frame_offset=0, num_frames=-1, normalize=True, channels_first=True, format=None, buffer_size=4096, backend=None):
                data, sample_rate = sf.read(uri, dtype="float32", always_2d=True)
                tensor = torch.from_numpy(data)
                if channels_first:
                    tensor = tensor.t()
                if frame_offset > 0 or num_frames > 0:
                    if channels_first:
                        start = frame_offset
                        end = start + num_frames if num_frames > 0 else tensor.shape[1]
                        tensor = tensor[:, start:end]
                    else:
                        start = frame_offset
                        end = start + num_frames if num_frames > 0 else tensor.shape[0]
                        tensor = tensor[start:end, :]
                return tensor, sample_rate
            torchaudio.load = patched_audio_load

            from TTS.api import TTS
            gpu = torch.cuda.is_available()
            # Suppress excessive logging during model download/load
            self._pipeline = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=gpu)
            self._engine_type = "xtts"
            logger.success("[TTS] Local Coqui XTTS-v2 loaded successfully ✓")
            return
        except Exception as e:
            logger.warning("[TTS] Coqui XTTS-v2 load failed: {}. Falling back to Kokoro...", e)

        # 2. Fallback to Kokoro
        self._load_kokoro()

    def _load_kokoro(self):
        self._load_kokoro_fallback()
        self._engine_type = "kokoro"

    def _load_kokoro_fallback(self):
        from pathlib import Path
        onnx_path = Path("kokoro-v1.0.onnx")
        voices_path = Path("voices-v1.0.bin")
        
        if not onnx_path.exists():
            self._download_file("https://github.com/thewh1teagle/kokoro-onnx/releases/download/v0.4.0/kokoro-v1.0.onnx", str(onnx_path), "Kokoro ONNX model")
        if not voices_path.exists():
            self._download_file("https://github.com/thewh1teagle/kokoro-onnx/releases/download/v0.4.0/voices-v1.0.bin", str(voices_path), "Kokoro voices bin file")
            
        try:
            from kokoro_onnx import Kokoro
            self._pipeline = Kokoro(str(onnx_path), str(voices_path))
            logger.success("[TTS] Kokoro-ONNX model loaded successfully ✓")
        except Exception as e:
            logger.error("[TTS] Failed to load Kokoro model: {}", e)
            raise

    @staticmethod
    def _read_env_file_key(name: str) -> str:
        """Read a key from a local, git-ignored .env file (KEY=value per line)."""
        try:
            from pathlib import Path
            env_path = Path(".env")
            if not env_path.exists():
                return ""
            for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == name:
                    return val.strip().strip('"').strip("'")
        except Exception:
            pass
        return ""

    def _load_gemini(self):
        import os
        import httpx
        # Key resolution priority: env var -> config.yaml -> local .env file.
        # NOTE: never hardcode a key in source — it leaks into version control.
        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            api_key = (getattr(self._config, "gemini_api_key", None) or "").strip()
        if not api_key:
            api_key = self._read_env_file_key("GEMINI_API_KEY")
        self._api_key = api_key
        if not self._api_key:
            logger.warning("[TTS] GEMINI_API_KEY not set (env, config.yaml, or .env). Falling back to Kokoro...")
            self._load_kokoro()
            return
        
        self._engine_type = "gemini"
        if hasattr(self, "_http_client") and self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
        self._http_client = httpx.Client(timeout=15.0)
        logger.success("[TTS] Gemini TTS engine initialized successfully ✓")

    # ─── Public API ──────────────────────────────────────────────────────────

    async def speak(self, text: str, voice: str | None = None):
        """
        Synthesise `text` and play it.
        Acquires lock so sentences play sequentially.
        Cancellable via stop().
        """
        if not text.strip() or self._muted:
            logger.info("[TTS] Muted or empty text; skipping playback.")
            return

        text = self._prepare_speech_text(text)
        if not text:
            return

        v = voice or self._config.voice

        # Clear stop event unconditionally for fresh speech requests
        self._stop_evt.clear()

        # 1. Synthesize in parallel (not holding self._lock)
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(
            self._synthesis_executor,
            lambda: self._synthesise(text, v),
        )

        if audio is None or self._stop_evt.is_set():
            return

        # 2. Play sequentially (holding self._lock)
        async with self._lock:
            if not self._stop_evt.is_set():
                await loop.run_in_executor(
                    self._playback_executor,
                    lambda: self._play(audio),
                )

    def stop(self):
        """Immediately halt any ongoing playback (called on barge-in)."""
        self._stop_evt.set()
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            sd.stop()
        except Exception:
            pass

    # ─── Internals ───────────────────────────────────────────────────────────

    def _synthesise(self, text: str, voice: str) -> Any:
        try:
            if self._engine_type == "edge":
                res = self._synthesise_edge(text, voice)
                if res is not None:
                    return res
                logger.warning("[TTS] Edge-TTS failed or unavailable; falling back to Kokoro...")
                if self._pipeline is None:
                    self._load_kokoro_fallback()
                if self._pipeline is None:
                    return None
                k_voice, k_lang = self._resolve_kokoro(text, voice)
                samples, _ = self._pipeline.create(text, voice=k_voice, speed=self._config.speed, lang=k_lang)
                return np.array(samples, dtype=np.float32)
            elif self._engine_type == "xtts":
                # Determine language code
                clean_lang = self._last_lang.lower().strip()
                lang_mapping = {
                    "en": "en",
                    "hi": "hi",
                    "kn": "kn",
                }
                lang_code = lang_mapping.get(clean_lang, "en")
                
                # Check characters for direct script overrides
                if any(0x0900 <= ord(c) <= 0x097F for c in text):
                    lang_code = "hi"
                elif any(0x0C80 <= ord(c) <= 0x0CFF for c in text):
                    lang_code = "kn"

                # Resolve speaker WAV
                from pathlib import Path
                speaker_wav_path = "data/mahiru_reference.wav"
                if voice == "Mahiru" or voice == "Kore":
                    if Path("data/mahiru_reference.wav").exists():
                        speaker_wav_path = "data/mahiru_reference.wav"
                    elif Path("data/kore_reference.wav").exists():
                        speaker_wav_path = "data/kore_reference.wav"
                    else:
                        speaker_wav_path = "data/baby_reference.wav"
                elif Path(voice).exists():
                    speaker_wav_path = voice
                else:
                    speaker_wav_path = str(getattr(self, "_speaker_wav", "data/baby_reference.wav"))
                
                logger.info("[TTS] Synthesizing via local XTTS-v2 (lang={}) using {}...", lang_code, speaker_wav_path)
                if self._pipeline is None:
                    return None
                wav = self._pipeline.tts(
                    text=text,
                    speaker_wav=speaker_wav_path,
                    language=lang_code
                )
                return np.array(wav, dtype=np.float32)
            elif self._engine_type == "gemini":
                return self._synthesise_gemini(text, voice)
            elif self._engine_type == "elevenlabs":
                return self._synthesise_elevenlabs(text, voice)
            else:
                # Kokoro primary engine — auto-select voice + language from text.
                # Kokoro has NO Kannada/Marathi model. If the text is in one of
                # those scripts and a cloud engine (Gemini) is configured, defer to
                # it so the user actually hears intelligible speech instead of a
                # Hindi voice garbling an unsupported script.
                if self._engine_type == "kokoro" and self._has_unsupported_script(text):
                    import os
                    api_key = getattr(self, "_api_key", None) or getattr(self._config, "gemini_api_key", None) or os.environ.get("GEMINI_API_KEY")
                    if api_key:
                        logger.info("[TTS] Kokoro cannot render script; routing to Gemini...")
                        gem = self._synthesise_gemini(text, voice)
                        if gem is not None:
                            return gem
                    else:
                        logger.warning(
                            "[TTS] Text is in Kannada/Marathi but Kokoro has no "
                            "model for it and no cloud TTS is configured. Falling back "
                            "to a Hindi voice (best effort — may be unintelligible)."
                        )
                k_voice, k_lang = self._resolve_kokoro(text, voice)
                if self._pipeline is None:
                    return None
                samples, sr = self._pipeline.create(text, voice=k_voice, speed=self._config.speed, lang=k_lang)
                return np.array(samples, dtype=np.float32)
        except Exception as e:
            logger.error("[TTS] Synthesis failed: {}", e)
            return None

    def _synthesise_gemini(self, text: str, voice: str) -> Any:
        """Synthesise via the Gemini TTS cloud API (supports kn/mr/en/hi/...).

        Used both as the primary engine when engine=="gemini" and as a fallback
        for Kokoro when the text is in a script Kokoro cannot render
        (Kannada/Marathi). Returns float32 PCM or None on failure.
        """
        import base64
        import json

        # Determine voice name — Mahiru maps to Kore on the Gemini API
        GEMINI_VOICES = [
            "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
            "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
            "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
            "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
            "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
        ]
        if voice == "Mahiru":
            voice_name = "Kore"
        else:
            voice_name = voice if voice in GEMINI_VOICES else "Kore"
        logger.info("[TTS] Synthesizing via Gemini TTS (voice={} maps to API voice={})...", voice, voice_name)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={self._api_key}"

        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        # Gemini TTS auto-detects the text's language — Baby must only speak
        # en/hi/kn, so text in any other language skips the API and goes
        # straight to the Kokoro fallback (English voice).
        gemini_failed = self._detect_lang(text) not in SPOKEN_LANGUAGES
        if gemini_failed:
            logger.warning("[TTS] Gemini blocked for non-en/hi/kn text; routing to Kokoro fallback...")
        res_data = None
        if not gemini_failed:
            try:
                # Use connection-pooled HTTP client for ultra-low latency
                response = self._http_client.post(url, json=payload)
                if response.status_code == 200:
                    res_data = response.json()
                elif response.status_code == 429:
                    logger.warning("[TTS] Gemini quota exceeded (429). Falling back to Kokoro instantly...")
                    gemini_failed = True
                else:
                    logger.error("[TTS] Gemini HTTP Error {}: falling back to Kokoro...", response.status_code)
                    gemini_failed = True
            except Exception as e:
                logger.error("[TTS] Gemini connection error: {}. Falling back to Kokoro...", e)
                gemini_failed = True

        if not gemini_failed and res_data is not None and 'candidates' in res_data:
            try:
                base64_audio = res_data['candidates'][0]['content']['parts'][0]['inlineData']['data']
                pcm_bytes = base64.b64decode(base64_audio)
                samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                return samples
            except Exception as e:
                logger.error("[TTS] Error parsing Gemini audio response: {}. Falling back to Kokoro...", e)
                gemini_failed = True
        else:
            gemini_failed = True

        if gemini_failed:
            # Graceful Kokoro fallback
            if self._pipeline is None:
                try:
                    logger.info("[TTS] Lazily loading Kokoro fallback model...")
                    self._load_kokoro_fallback()
                except Exception as ke:
                    logger.error("[TTS] Failed to lazily load Kokoro: {}", ke)
            if self._pipeline is not None:
                try:
                    logger.info("[TTS] Synthesizing fallback using Kokoro...")
                    k_voice, k_lang = self._resolve_kokoro(text, voice)
                    samples, _ = self._pipeline.create(text, voice=k_voice, speed=self._config.speed, lang=k_lang)
                    return np.array(samples, dtype=np.float32)
                except Exception as ke:
                    logger.error("[TTS] Kokoro fallback synthesis failed: {}", ke)
            return None

    def _load_elevenlabs(self):
        import httpx
        import os
        # Key resolution: env var -> config.yaml -> local .env file
        api_key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
        if not api_key:
            api_key = (getattr(self._config, "elevenlabs_api_key", None) or "").strip()
        if not api_key:
            api_key = self._read_env_file_key("ELEVENLABS_API_KEY")
        self._elevenlabs_key = api_key
        if not self._elevenlabs_key:
            logger.warning("[TTS] ELEVENLABS_API_KEY not set (env, config.yaml, or .env). Falling back to Kokoro...")
            self._load_kokoro()
            return

        self._engine_type = "elevenlabs"
        self._elevenlabs_voice_id = getattr(self._config, "elevenlabs_voice_id", "JBFqnCBsd6RMkjVDRZzb")
        self._elevenlabs_stability = getattr(self._config, "elevenlabs_stability", 0.5)
        self._elevenlabs_similarity_boost = getattr(self._config, "elevenlabs_similarity_boost", 0.75)
        self._elevenlabs_style = getattr(self._config, "elevenlabs_style", 0.5)
        self._elevenlabs_use_speaker_boost = getattr(self._config, "elevenlabs_use_speaker_boost", True)
        
        if hasattr(self, "_http_client") and self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
        self._http_client = httpx.Client(timeout=30.0)
        logger.success("[TTS] ElevenLabs TTS engine initialized ✓ (voice: {})", self._elevenlabs_voice_id)

    def _synthesise_elevenlabs(self, text: str, voice: str) -> Any:
        import base64
        import io
        import soundfile as sf
        
        if not hasattr(self, "_elevenlabs_key") or not self._elevenlabs_key:
            logger.warning("[TTS] ElevenLabs key not available, falling back to Kokoro...")
            return None
        
        voice_id = self._elevenlabs_voice_id
        model_id = "eleven_multilingual_v2"
        output_format = "mp3_44100_128"
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": getattr(self, "_elevenlabs_stability", 0.5),
                "similarity_boost": getattr(self, "_elevenlabs_similarity_boost", 0.75),
                "style": getattr(self, "_elevenlabs_style", 0.5),
                "use_speaker_boost": getattr(self, "_elevenlabs_use_speaker_boost", True),
            },
        }
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        params = {"output_format": output_format}
        headers = {
            "xi-api-key": self._elevenlabs_key,
            "Content-Type": "application/json",
        }
        
        try:
            logger.info("[TTS] Synthesizing via ElevenLabs (voice={})...", voice_id)
            response = self._http_client.post(url, json=payload, params=params, headers={"xi-api-key": self._elevenlabs_key, "Content-Type": "application/json"})
            response.raise_for_status()
            
            mp3_bytes = response.content
            if not mp3_bytes:
                return None
            
            # Convert MP3 to float32 array
            data, sr = sf.read(io.BytesIO(mp3_bytes), dtype="float32")
            return data
        except Exception as e:
            logger.error("[TTS] ElevenLabs synthesis error: {}. Falling back to Kokoro...", e)
            return None

    def _load_edge(self):
        try:
            import edge_tts
            self._engine_type = "edge"
            logger.success("[TTS] Edge Neural TTS engine initialized (fluent Kannada: kn-IN-SapnaNeural, Hindi: hi-IN-SwaraNeural) ✓")
        except ImportError:
            logger.warning("[TTS] edge-tts not installed; falling back to Kokoro...")
            self._load_kokoro()

    def _resolve_edge_voice(self, text: str, requested_voice: str | None = None) -> str:
        """
        Select a dedicated, high-fluency neural voice for the detected language.
        Baby speaks ONLY en/hi/kn — each maps to its native Edge neural voice.
        A requested voice is honored for English text only when it belongs to an
        allowed language; anything else falls back to the detected-language voice.
        """
        lang = self._detect_lang(text)
        cfg = self._config

        # Per-language native voices always win for hi/kn — an English voice
        # cannot render Devanagari/Kannada script intelligibly.
        if lang == "hi":
            return getattr(cfg, "hindi_voice", None) or "hi-IN-SwaraNeural"
        if lang == "kn":
            return getattr(cfg, "kannada_voice", None) or "kn-IN-SapnaNeural"

        # English: honor an explicitly requested English voice if it is valid.
        req = (requested_voice or getattr(cfg, "voice", "") or "").split(" ")[0].strip()
        if req:
            if "Neural" in req:
                # Direct Edge Neural voice name (e.g. "en-US-AvaNeural").
                # Only voices from allowed languages may be used.
                req_lang = req.split("-")[0].strip().lower()
                if req_lang in SPOKEN_LANGUAGES:
                    return req
                logger.warning(
                    "[TTS] Requested voice '{}' is not en/hi/kn; using English voice instead.", req
                )

        return getattr(cfg, "english_voice", None) or "en-US-AvaNeural"

    def _synthesise_edge(self, text: str, voice: str | None = None) -> Any:
        import asyncio
        import io
        import soundfile as sf
        try:
            import edge_tts
        except ImportError:
            return None

        edge_voice = self._resolve_edge_voice(text, voice)
        logger.info("[TTS] Synthesizing via Edge Neural TTS (voice={})...", edge_voice)

        # Use plain text for Edge TTS to avoid SSML being spoken literally
        async def _edge_coro():
            communicate = edge_tts.Communicate(text, edge_voice)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and "data" in chunk:
                    buf.extend(chunk["data"])
            return bytes(buf)

        try:
            loop = asyncio.new_event_loop()
            try:
                mp3_bytes = loop.run_until_complete(_edge_coro())
            finally:
                loop.close()

            if not mp3_bytes:
                return None

            data, sr = sf.read(io.BytesIO(mp3_bytes), dtype="float32")
            return data
        except Exception as e:
            logger.error("[TTS] Edge-TTS synthesis error: {}", e)
            return None

    def _play(self, audio: Any) -> None:
        import sounddevice as sd  # type: ignore[import-untyped]
        if audio is None or len(audio) == 0 or self._stop_evt.is_set():
            return

        source_sr = 24000 if self._engine_type in ("gemini", "xtts", "edge") else int(self._config.sample_rate)

        try:
            device_info = sd.query_devices(kind='output')
            device_sr = int(device_info.get('default_samplerate', source_sr))
        except Exception:
            device_sr = source_sr

        if device_sr != source_sr and len(audio) > 0:
            logger.info("[TTS] Resampling audio from {}Hz to device native {}Hz...", source_sr, device_sr)
            try:
                from scipy.signal import resample
                target_len = int(len(audio) * device_sr / source_sr)
                audio = resample(audio, target_len).astype(np.float32)
            except ImportError:
                # Fallback to linear interpolation
                duration = len(audio) / source_sr
                orig_ticks = np.linspace(0, duration, len(audio))
                target_len = int(duration * device_sr)
                if target_len > 0:
                    target_ticks = np.linspace(0, duration, target_len)
                    audio = np.interp(target_ticks, orig_ticks, audio).astype(np.float32)

        # Broadcast 1D mono audio into 2D stereo channels for universal Windows soundcard compatibility
        if isinstance(audio, np.ndarray) and audio.ndim == 1:
            audio = np.column_stack((audio, audio))

        logger.info("[TTS] Playing audio: {} samples at {}Hz...", len(audio), device_sr)
        try:
            sd.play(audio, samplerate=device_sr, blocking=True)
        except Exception as e:
            logger.error("[TTS] Sounddevice playback error: {}", e)



















