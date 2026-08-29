"""
biometrics/face_id.py — Face recognition via InsightFace (buffalo_l).
Used for greeting users by name when camera is active.
"""

from __future__ import annotations
import numpy as np
from loguru import logger
from biometrics.biometric_db import BiometricDB


class FaceIdentifier:
    def __init__(self, db: BiometricDB, threshold: float = 0.50):
        self._db        = db
        self._threshold = threshold
        self._app       = None

    def load(self):
        from insightface.app import FaceAnalysis
        self._app = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._app.prepare(ctx_id=0, det_size=(640, 640))
        logger.success("[FaceID] InsightFace loaded ✓")

    def get_embedding(self, frame: np.ndarray) -> np.ndarray | None:
        """Extract face embedding from a BGR frame. Returns None if no face."""
        if self._app is None:
            self.load()
        if self._app is None:
            return None
        faces = self._app.get(frame)
        if not faces:
            return None
        # Use largest detected face
        largest = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
        return largest.embedding

    def identify(self, frame: np.ndarray) -> tuple[str | None, int | None, str | None]:
        """Returns (name, profile_id, relationship) of best matching face or (None, None, None)."""
        emb = self.get_embedding(frame)
        if emb is None:
            return None, None, None

        profiles    = self._db.get_all()
        best_name, best_id, best_score, best_rel = None, None, 0.0, None

        for p in profiles:
            if p["face_emb"] is None:
                continue
            score = float(np.dot(emb, p["face_emb"]) /
                          (np.linalg.norm(emb) * np.linalg.norm(p["face_emb"]) + 1e-9))
            if score > best_score:
                best_score, best_name, best_id = score, p["name"], p["id"]
                best_rel = p.get("relationship", "")

        if best_score >= self._threshold:
            logger.info("[FaceID] Identified: {} (relationship='{}', score={:.2f})", best_name, best_rel, best_score)
            if best_id:
                self._db.update_last_seen(best_id)
            return best_name, best_id, best_rel

        return None, None, None

    def enroll(self, name: str, frame: np.ndarray, is_admin: bool = False, relationship: str = ""):
        """Enroll a new face from a webcam frame."""
        emb = self.get_embedding(frame)
        if emb is None:
            raise ValueError("No face detected in frame — please look at the camera.")
        self._db.upsert_profile(name=name, face_emb=emb, is_admin=is_admin, relationship=relationship)
        logger.success("[FaceID] Enrolled face for '{}' (relationship='{}')", name, relationship)



















