"""
core/command_refiner.py — Summarize & grammar-correct user commands.

Every command is rewritten into clear, grammatically correct language BEFORE
it reaches the assistant (LLM planner / conversational model), so Baby
executes exactly what the user meant — with the same meaning and the same
language (English / Hindi / Kannada only).

Flow:
  1. Try the local LLM to rewrite the command (strict rules: same meaning,
     same language, no additions/removals, concise).
  2. If the LLM is unavailable/test mode/unreliable → conservative local
     normalization (whitespace, punctuation, capitalization).
  3. A small in-memory cache avoids repeating the LLM call for repeat commands.
"""

from __future__ import annotations
import re
from loguru import logger


_REFINER_SYSTEM_PROMPT = (
    "You are a command rewriter for a desktop assistant. "
    "Rewrite the user's command to be grammatically correct, clear, and concise.\n"
    "Strict rules:\n"
    "1. Preserve the EXACT meaning and intent. Never add, remove, or change any "
    "request, detail, number, name, or action.\n"
    "2. Keep the SAME language the user used (English, Hindi, or Kannada). Never translate.\n"
    "3. Fix grammar, word order, punctuation, spelling, and repetitions. Make it concise "
    "by removing filler words only.\n"
    "4. Keep file paths, URLs, app names, and quoted phrases verbatim.\n"
    "5. Output ONLY the rewritten command — no quotes, no explanation, no preamble.\n"
    "6. If the command is already perfect, output it unchanged."
)

# Text the test mode LLM returns — never let it replace a real command.
_TEST_MODE_LLM_MARKER = "This is a test mode chat response."

_MULTI_SPACE = re.compile(r"[ \t]+")
_PUNCT_SPACE = re.compile(r"\s+([,.;:!?])")
_REPEAT_PUNCT = re.compile(r"([!?.])\1+")
_SKIP_CACHE_WHEN = 64


class CommandRefiner:
    def __init__(self, llm, max_cache: int = 64):
        self._llm = llm
        self._max_cache = max_cache
        self._cache: dict[tuple[str, str], str] = {}

    # ─── Public API ───────────────────────────────────────────────────────────

    async def refine(self, raw: str, lang: str) -> str:
        """Return the summarized, grammar-corrected command (same meaning/language).

        Falls back to conservative local normalization whenever the LLM path
        is unavailable, running in test mode, or produces an unsafe rewrite.
        """
        text = (raw or "").strip()
        if not text:
            return raw

        key = (lang, text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        test_mode = bool(getattr(getattr(self._llm, "_cfg", None), "test_mode", False))
        if not test_mode:
            try:
                result = await self._llm.chat(
                    messages=[
                        {"role": "system", "content": _REFINER_SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    max_tokens=256,
                    temperature=0.0,
                )
                result = self._clean_output(result)
                if not self._is_sane(text, result):
                    logger.warning(
                        "[CommandRefiner] LLM rewrite rejected ('{}'); keeping original.", text
                    )
                    result = text
            except Exception as e:
                logger.warning(
                    "[CommandRefiner] Refinement failed ({}); using local normalization.", e
                )
                result = self._local_normalize(text)
        else:
            result = self._local_normalize(text)

        self._remember(key, result)
        return result

    def _clean_output(self, result: str) -> str:
        """Strip quotes, fences and whitespace the LLM may wrap around the rewrite."""
        if result is None:
            return ""
        result = result.strip()
        if result.startswith("```"):
            result = result.strip("`")
            if result.lower().startswith(("json", "text")):
                result = result.split("\n", 1)[-1]
            result = result.strip()
        if (result.startswith('"') and result.endswith('"')) or (
            result.startswith("'") and result.endswith("'")
        ):
            result = result[1:-1].strip()
        if result.lower().strip() == _TEST_MODE_LLM_MARKER.lower():
            return ""
        return result

    def _is_sane(self, original: str, refined: str) -> bool:
        """Reject rewrites that changed the command beyond acceptable limits."""
        if not refined or not refined.strip():
            return False
        if refined.lower().strip() == _TEST_MODE_LLM_MARKER.lower():
            return False
        if len(refined) > max(64, len(original) * 3):  # never bloat the command
            return False
        return True

    @staticmethod
    def _local_normalize(text: str) -> str:
        """Zero-LLM fallback: conservative grammar/spacing cleanup, no meaning change."""
        text = _MULTI_SPACE.sub(" ", text).strip()
        text = _PUNCT_SPACE.sub(r"\1", text)
        text = _REPEAT_PUNCT.sub(r"\1", text)
        text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        return text.strip()

    def _remember(self, key: tuple[str, str], value: str) -> None:
        if len(self._cache) >= self._max_cache:
            try:
                self._cache.pop(next(iter(self._cache)))
            except StopIteration:
                pass
        self._cache[key] = value



















