"""
core/dictation_expander.py — Voice-dictation phrase → symbol expansion.

When the user speaks symbol names, the STT transcript contains words like
"open bracket" instead of "(". This module rewrites those spoken phrases into
the actual characters BEFORE the text reaches the assistant, so commands such
as "print open bracket 1 comma 2 closed bracket" arrive as "print (1, 2)".

Design:
  - ALWAYS  — unambiguous phrases (multi-word or rare words) applied to every
              utterance ("open bracket", "full stop", "excetra", ...).
  - GUARDED — common English words that could appear in normal speech
              ("next", "comma", "period", "dot", "plus", ...). These are ONLY
              expanded when the utterance already contains an ALWAYS phrase,
              i.e. the user is clearly dictating. This guarantees commands like
              "play the next song" or "open amazon dot com" are never mangled.

Mapping curated from standard dictation command sets (Microsoft Voice Access,
Apple Dictation, Dragon) plus the user-defined pronunciations.
"""

from __future__ import annotations
import re
from typing import Pattern

# ─── User-defined pronunciations (always applied) ────────────────────────────
_ALWAYS: dict[str, str] = {
    # Brackets / parentheses / braces / angles
    "open bracket": "(",
    "bracket open": "(",
    "left bracket": "(",
    "closed bracket": ")",
    "close bracket": ")",
    "bracket closed": ")",
    "right bracket": ")",
    "open square bracket": "[",
    "open square": "[",
    "square bracket open": "[",
    "left square bracket": "[",
    "closed square bracket": "]",
    "closed square": "]",
    "close square bracket": "]",
    "square bracket closed": "]",
    "right square bracket": "]",
    "open parenthesis": "(",
    "parenthesis open": "(",
    "left parenthesis": "(",
    "close parenthesis": ")",
    "closed parenthesis": ")",
    "parenthesis closed": ")",
    "right parenthesis": ")",
    "open parentheses": "(",
    "close parentheses": ")",
    "open brace": "{",
    "brace open": "{",
    "left brace": "{",
    "close brace": "}",
    "closed brace": "}",
    "brace closed": "}",
    "right brace": "}",
    "open curly bracket": "{",
    "open curly brace": "{",
    "open curly": "{",
    "curly bracket open": "{",
    "closed curly bracket": "}",
    "closed curly brace": "}",
    "closed curly": "}",
    "close curly bracket": "}",
    "curly bracket closed": "}",
    "open angle bracket": "<",
    "angle bracket open": "<",
    "left angle bracket": "<",
    "open angle": "<",
    "left angle": "<",
    "close angle bracket": ">",
    "closed angle bracket": ">",
    "angle bracket closed": ">",
    "right angle bracket": ">",
    "close angle": ">",
    "right angle": ">",
    # Punctuation
    "full stop": ".",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "apostrophe s": "'s",
    "hyphen": "-",
    "minus sign": "-",
    "underscore": "_",
    "under score": "_",
    "ellipsis": "...",
    "dot dot dot": "...",
    "new line": "\n",
    "new paragraph": "\n\n",
    "paragraph sign": "¶",
    "section sign": "§",
    "space bar": " ",
    # Quotes
    "open quotes": '"',
    "close quotes": '"',
    "double quote": '"',
    "open double quote": '"',
    "close double quote": '"',
    "open single quote": "'",
    "close single quote": "'",
    "begin single quote": "'",
    "end single quote": "'",
    "single quote": "'",
    # Symbols
    "asterisk": "*",
    "star symbol": "*",
    "backslash": "\\",
    "forward slash": "/",
    "vertical bar sign": "|",
    "vertical bar": "|",
    "pipe character": "|",
    "pipe symbol": "|",
    "ampersand": "&",
    "and sign": "&",
    "at sign": "@",
    "at the rate": "@",
    "percent sign": "%",
    "number sign": "#",
    "hash sign": "#",
    "hash symbol": "#",
    "pound sign": "#",
    "plus sign": "+",
    "times sign": "*",
    "multiplication sign": "*",
    "division sign": "/",
    "equal sign": "=",
    "equals sign": "=",
    "less than sign": "<",
    "greater than sign": ">",
    "dollar sign": "$",
    "euro sign": "€",
    "pound sterling sign": "£",
    "yen sign": "¥",
    "degree symbol": "°",
    "copyright sign": "©",
    "registered sign": "®",
    "tilde sign": "~",
    "caret sign": "^",
    "hash tag": "#",
    # User-defined spoken words
    "excetra": "etc",
    "xcetra": "etc",
    "et cetera": "etc",
}

# ─── Common speech words — expanded ONLY in dictation context ────────────────
_GUARDED: dict[str, str] = {
    "next line": "\n",
    "next point": ",",
    "next": ",",        # user-defined: "next" means next line/next point = comma
    "comma": ",",
    "colon": ":",
    "semicolon": ";",
    "period": ".",
    "dot": ".",
    "point": ".",
    "slash": "/",
    "pipe": "|",
    "quote": '"',
    "star": "*",
    "equals": "=",
    "plus": "+",
    "minus": "-",
    "dash": "-",
    "brace": "{",        # bare "brace" only makes sense while dictating
    "question": "?",     # bare "question" (rarely said alone outside dictation)
    "exclamation": "!",
}

_WORD_BOUNDARY = re.compile(r"\b{phrase}\b", re.IGNORECASE)


def _compile(entries: dict[str, str]) -> list[tuple[Pattern[str], str]]:
    """Compile phrases longest-first so 'open square bracket' wins over 'open square'."""
    return [
        (re.compile(_WORD_BOUNDARY.pattern.replace("{phrase}", re.escape(p)), re.IGNORECASE), r)
        for p, r in sorted(entries.items(), key=lambda kv: -len(kv[0]))
    ]


_ALWAYS_RULES = _compile(_ALWAYS)
_GUARDED_RULES = _compile(_GUARDED)

# Post-expansion spacing cleanup: "print ( 1 , 2 )" → "print (1, 2)".
_SPACE_BEFORE_CLOSERS = re.compile(r"\s+([,.;:!?)\]}>])")
_SPACE_AFTER_OPENERS = re.compile(r"([(\[{<])\s+")
_SPACE_AROUND_UNDERSCORE = re.compile(r"\s+(_)\s+")
_SPACE_AFTER_NEWLINE = re.compile(r"(\n)\s+")
_SPACE_BEFORE_NEWLINE = re.compile(r"\s+(\n)")


class DictationExpander:
    """Stateless voice-dictation phrase → symbol expansion."""

    @staticmethod
    def expand(text: str) -> str:
        """Expand spoken symbol phrases into characters.

        Guarded words are applied only when the utterance shows clear
        dictation intent (contains at least one unguarded phrase).
        """
        if not text:
            return text
        result = text
        dictation_mode = False
        for pattern, repl in _ALWAYS_RULES:
            if pattern.search(result):
                dictation_mode = True
                result = pattern.sub(repl, result)
        if dictation_mode:
            for pattern, repl in _GUARDED_RULES:
                result = pattern.sub(repl, result)
        result = _SPACE_BEFORE_CLOSERS.sub(r"\1", result)
        result = _SPACE_AFTER_OPENERS.sub(r"\1", result)
        result = _SPACE_AROUND_UNDERSCORE.sub(r"\1", result)
        result = _SPACE_AFTER_NEWLINE.sub(r"\1", result)
        result = _SPACE_BEFORE_NEWLINE.sub(r"\1", result)
        return result



















