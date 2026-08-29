"""
biometrics/voice_id.py — Speaker identification via resemblyzer GE2E embeddings.
"""

from __future__ import annotations
import numpy as np
from loguru import logger
from biometrics.biometric_db import BiometricDB


class VoiceIdentifier:
    def __init__(self, db: BiometricDB, threshold: float = 0.82):
        self._db        = db
        self._threshold = threshold
        self._encoder   = None

    def load(self):
        from resemblyzer import VoiceEncoder
        # Voice encoder runs on CPU: (1) avoids the hard native crash
        # (0xC0000409) when faster-whisper (CUDA) and torch CUDA share one
        # process, (2) frees VRAM for whisper large-v3 on small GPUs.
        # CPU embedding of 16 kHz utterances is fast enough for identify().
        self._encoder = VoiceEncoder(device="cpu")
        logger.success("[VoiceID] resemblyzer encoder loaded ✓ (CPU)")

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        from resemblyzer import preprocess_wav
        if self._encoder is None:
            self.load()
        if self._encoder is None:
            return np.zeros(256, dtype=np.float32)
        wav = preprocess_wav(audio, source_sr=sample_rate)
        res = self._encoder.embed_utterance(wav)
        return np.asarray(res, dtype=np.float32)

    def identify(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str | None, int | None, str | None]:
        """Returns (name, profile_id, relationship) or (None, None, None) if no match."""
        emb      = self.embed(audio, sample_rate)
        profiles = self._db.get_all()
        best_name, best_id, best_score, best_rel = None, None, 0.0, None

        for p in profiles:
            if p["voice_emb"] is None:
                continue
            score = float(np.dot(emb, p["voice_emb"]) /
                          (np.linalg.norm(emb) * np.linalg.norm(p["voice_emb"]) + 1e-9))
            if score > best_score:
                best_score, best_name, best_id = score, p["name"], p["id"]
                best_rel = p.get("relationship", "")

        if best_score >= self._threshold:
            logger.info("[VoiceID] Identified: {} (relationship='{}', score={:.2f})", best_name, best_rel, best_score)
            if best_id:
                self._db.update_last_seen(best_id)
            return best_name, best_id, best_rel

        logger.debug("[VoiceID] No match (best={:.2f})", best_score)
        return None, None, None

    def enroll(self, name: str, audio: np.ndarray, sample_rate: int = 16000, relationship: str = "", is_admin: bool = False):
        """Enroll a new speaker profile, optionally tagged with a relationship."""
        emb = self.embed(audio, sample_rate)
        self._db.upsert_profile(name=name, voice_emb=emb, relationship=relationship, is_admin=is_admin)
        logger.success("[VoiceID] Enrolled voice for '{}' (relationship='{}', admin={})", name, relationship, is_admin)



















