"""
core/languages.py — Canonical registry of languages Baby supports end-to-end.

Single source of truth shared by STT (transcription), the orchestrator (which
language the assistant must reply in) and TTS (voice selection).
"""

# Languages Baby can hear, understand and speak back.
# Whisper (STT) handles all of these; edge-tts / Kokoro / Gemini cover the
# speaking side (see audio/tts.py for the voice maps).
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en", "hi", "kn", "mr", "ta", "te", "bn", "gu", "ml", "ur",
    "es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ru",
)

# The ONLY languages Baby is allowed to SPEAK. Baby may still understand
# any of SUPPORTED_LANGUAGES (STT), but TTS output and the assistant's
# replies are hard-clamped to this set — anything else falls back to English.
SPOKEN_LANGUAGES: tuple[str, ...] = ("en", "hi", "kn")

# Human-readable names used in the LLM language-instruction block so small
# models reply in the correct language instead of drifting to English.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "gu": "Gujarati",
    "ml": "Malayalam",
    "ur": "Urdu",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ru": "Russian",
}



















