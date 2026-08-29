"""
core/privacy_guard.py — Ironclad Privacy Middleware for Baby.

Every user message passes through this guard BEFORE reaching any sub-agent
or web search. It:
  1. Strips PII (names, phones, emails, Aadhaar, PAN) using local NER
  2. Manages a machine-derived Fernet encryption key for data-at-rest
  3. Provides encrypt() / decrypt() helpers used by SkillStore & ContextAgent

No data leaves the machine. All processing is local.
"""

from __future__ import annotations

import re
import uuid
import platform
from typing import Tuple

from cryptography.fernet import Fernet
from loguru import logger

# ─── Optional Presidio import (graceful fallback to regex) ────────────────────

import importlib.util
_PRESIDIO_AVAILABLE = importlib.util.find_spec("presidio_analyzer") is not None
if not _PRESIDIO_AVAILABLE:
    logger.warning(
        "[PrivacyGuard] presidio-analyzer not installed — "
        "falling back to regex-only PII redaction. "
        "Run: pip install presidio-analyzer presidio-anonymizer && "
        "python -m spacy download en_core_web_sm"
    )


# ─── Regex fallback patterns (cover common Indian + global PII) ───────────────

_REGEX_RULES: list[tuple[str, str]] = [
    # Indian mobile (10-digit, optional country code)
    (r"(?<!\d)(\+?91[-\s]?)?[6-9]\d{9}(?!\d)",          "[REDACTED_PHONE]"),
    # Generic international phone
    (r"\b\+?[\d][\d\s\-\(\)]{7,}\d\b",                   "[REDACTED_PHONE]"),
    # Email
    (r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[REDACTED_EMAIL]"),
    # Aadhaar (12-digit, often space/dash separated)
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",               "[REDACTED_AADHAAR]"),
    # PAN card (AAAAA9999A)
    (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",                        "[REDACTED_PAN]"),
    # Credit/debit card (basic Luhn pattern)
    (r"\b(?:\d{4}[\s\-]?){3}\d{4}\b",                     "[REDACTED_CARD]"),
    # File paths that may contain username (Windows)
    (r"C:\\Users\\[^\\]+",                                 r"C:\\Users\\[REDACTED_USER]"),
]

_COMPILED_RULES = [(re.compile(p, re.IGNORECASE), r) for p, r in _REGEX_RULES]


# ─── Fernet key management ────────────────────────────────────────────────────

def _get_machine_id() -> str:
    """Return a stable identifier tied to this specific machine."""
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                return machine_guid
        except Exception:
            pass
    return str(uuid.getnode())  # MAC address fallback


def _get_or_create_key() -> bytes:
    """
    Load or create a Fernet encryption key.
    Key is stored in the OS keyring under service='baby_privacy'.
    Falls back to a per-machine derived key if keyring is unavailable.
    """
    SERVICE = "baby_privacy"
    ACCOUNT = "fernet_key"

    try:
        import keyring
        existing = keyring.get_password(SERVICE, ACCOUNT)
        if existing:
            return existing.encode()
        # Generate a new key and persist it
        key = Fernet.generate_key()
        keyring.set_password(SERVICE, ACCOUNT, key.decode())
        logger.info("[PrivacyGuard] New Fernet key generated and stored in OS keyring.")
        return key
    except Exception as e:
        logger.warning("[PrivacyGuard] Keyring unavailable ({}), using machine-derived key.", e)
        # Deterministic key from machine ID — not ideal but still local
        import hashlib, base64
        machine_bytes = _get_machine_id().encode()
        digest = hashlib.sha256(machine_bytes).digest()
        return base64.urlsafe_b64encode(digest)


# ─── PrivacyGuard class ───────────────────────────────────────────────────────

class PrivacyGuard:
    """
    Drop-in middleware that:
      - Scrubs PII from text using Presidio (or regex fallback)
      - Provides encrypt() / decrypt() for data-at-rest security

    Usage:
        guard = PrivacyGuard()
        clean, was_redacted = guard.scrub("My name is Anish and my phone is 9876543210")
        # clean → "My name is [REDACTED_PERSON] and my phone is [REDACTED_PHONE]"
    """

    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._fernet = Fernet(_get_or_create_key())
        self._analyzer = None
        self._anonymizer = None
        self._presidio_loaded = False
        self._presidio_enabled = _PRESIDIO_AVAILABLE and enabled

    def _get_presidio_engines(self):
        if not self._presidio_enabled:
            return None, None
        if not self._presidio_loaded:
            try:
                import os
                os.environ.setdefault("PRESIDIO_DEVICE", "cpu")
                from presidio_analyzer import AnalyzerEngine
                from presidio_anonymizer import AnonymizerEngine
                self._analyzer = AnalyzerEngine()
                self._anonymizer = AnonymizerEngine()
                self._presidio_loaded = True
                logger.info("[PrivacyGuard] Presidio NER engine loaded (full PII redaction).")
            except Exception as e:
                logger.warning("[PrivacyGuard] Presidio init failed: {}. Using regex fallback.", e)
                self._presidio_enabled = False
                return None, None
        return self._analyzer, self._anonymizer

    # ── Public API ────────────────────────────────────────────────────────────

    def scrub(self, text: str) -> Tuple[str, bool]:
        """
        Remove PII from text.
        Returns (clean_text, was_anything_redacted).
        """
        if not self._enabled or not text:
            return text, False

        original = text

        if self._presidio_enabled:
            text = self._presidio_scrub(text)
        
        # Always run regex on top (catches Indian-specific patterns Presidio may miss)
        text = self._regex_scrub(text)

        was_redacted = text != original
        if was_redacted:
            logger.debug("[PrivacyGuard] PII redacted from text.")
        return text, was_redacted

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string for safe storage on disk."""
        try:
            return self._fernet.encrypt(plaintext.encode()).decode()
        except Exception as e:
            logger.error("[PrivacyGuard] Encryption failed: {}", e)
            return plaintext  # Graceful degradation — store plaintext

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string retrieved from disk."""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception as e:
            # May be unencrypted legacy data — return as-is
            logger.debug("[PrivacyGuard] Decrypt failed (possibly unencrypted legacy): {}", e)
            return ciphertext

    # ── Private helpers ───────────────────────────────────────────────────────

    def _presidio_scrub(self, text: str) -> str:
        """Use Presidio's NER engine for entity recognition and anonymization."""
        analyzer, anonymizer = self._get_presidio_engines()
        if analyzer is None or anonymizer is None:
            return text
        try:
            from presidio_anonymizer.entities import OperatorConfig
            results = analyzer.analyze(
                text=text,
                language="en",
                entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS",
                          "CREDIT_CARD", "US_SSN", "LOCATION", "NRP"],
            )
            if not results:
                return text

            operators = {
                "PERSON":        OperatorConfig("replace", {"new_value": "[REDACTED_NAME]"}),
                "PHONE_NUMBER":  OperatorConfig("replace", {"new_value": "[REDACTED_PHONE]"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED_EMAIL]"}),
                "CREDIT_CARD":   OperatorConfig("replace", {"new_value": "[REDACTED_CARD]"}),
                "US_SSN":        OperatorConfig("replace", {"new_value": "[REDACTED_ID]"}),
                "LOCATION":      OperatorConfig("replace", {"new_value": "[REDACTED_LOCATION]"}),
                "NRP":           OperatorConfig("replace", {"new_value": "[REDACTED_ID]"}),
            }
            from typing import cast, Any
            anonymized = anonymizer.anonymize(
                text=text,
                analyzer_results=cast(Any, results),
                operators=operators,
            )
            return anonymized.text
        except Exception as e:
            logger.warning("[PrivacyGuard] Presidio scrub error: {}. Falling back to regex.", e)
            return text

    def _regex_scrub(self, text: str) -> str:
        """Apply all regex-based PII redaction rules."""
        for pattern, replacement in _COMPILED_RULES:
            text = pattern.sub(replacement, text)
        return text


# ─── Module-level singleton helper ───────────────────────────────────────────

_guard_instance: PrivacyGuard | None = None

def get_guard(enabled: bool = True) -> PrivacyGuard:
    """Return the shared PrivacyGuard singleton."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = PrivacyGuard(enabled=enabled)
    return _guard_instance



















