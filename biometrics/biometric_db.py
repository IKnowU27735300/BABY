"""
biometrics/biometric_db.py — Encrypted SQLite database for biometric profiles.
Uses Fernet symmetric encryption. Optional OS keychain backend.
"""

from __future__ import annotations
import os
import pickle
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from cryptography.fernet import Fernet
from loguru import logger


class BiometricDB:
    def __init__(self, db_path: str = "data/biometrics.db", key_backend: str = "file"):
        self._db_path     = Path(db_path)
        self._key_backend = key_backend
        self._fernet      = Fernet(self._get_or_create_key())
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.success("[BiometricDB] Ready at '{}'", self._db_path)

    # ─── Connection management ───────────────────────────────────────────────

    @contextmanager
    def _connect(self):
        """sqlite3 connection that commits AND always closes (no leaks)."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            yield conn
            conn.commit()
        finally:
            if conn is not None:
                conn.close()

    # ─── Key management ──────────────────────────────────────────────────────

    def _get_or_create_key(self) -> bytes:
        if self._key_backend == "keyring":
            return self._keyring_key()
        return self._file_key()

    def _file_key(self) -> bytes:
        key_path = self._db_path.parent / ".biometric.key"
        if key_path.exists():
            return key_path.read_bytes()
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        logger.info("[BiometricDB] New encryption key created at '{}'", key_path)
        return key

    def _keyring_key(self) -> bytes:
        import keyring
        service, username = "BABY-AI", "biometric_key"
        stored = keyring.get_password(service, username)
        if stored:
            return stored.encode()
        key = Fernet.generate_key()
        keyring.set_password(service, username, key.decode())
        logger.info("[BiometricDB] Encryption key stored in OS keychain")
        return key

    # ─── Schema ──────────────────────────────────────────────────────────────

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    name          TEXT NOT NULL,
                    relationship  TEXT DEFAULT '',
                    face_emb      BLOB,
                    voice_emb     BLOB,
                    is_admin      INTEGER DEFAULT 0,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen     TIMESTAMP
                )
            """)
            # Migrate existing databases that predate the relationship column.
            cols = [r[1] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()]
            if "relationship" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN relationship TEXT DEFAULT ''")
            if "is_admin" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN is_admin INTEGER DEFAULT 0")

    # ─── CRUD ────────────────────────────────────────────────────────────────

    def save_profile(self, name: str, face_emb=None, voice_emb=None, relationship: str = "", is_admin: bool = False):
        face_blob  = self._enc(face_emb)  if face_emb  is not None else None
        voice_blob = self._enc(voice_emb) if voice_emb is not None else None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO profiles (name, relationship, face_emb, voice_emb, is_admin) VALUES (?, ?, ?, ?, ?)",
                (name, relationship, face_blob, voice_blob, 1 if is_admin else 0),
            )
            return cur.lastrowid

    def upsert_profile(self, name: str, face_emb=None, voice_emb=None, relationship: str = "", is_admin: bool | None = None):
        existing = self.get_profile_by_name(name)
        if existing:
            with self._connect() as conn:
                updates = []
                params = []
                if face_emb is not None:
                    updates.append("face_emb = ?")
                    params.append(self._enc(face_emb))
                if voice_emb is not None:
                    updates.append("voice_emb = ?")
                    params.append(self._enc(voice_emb))
                if relationship:
                    updates.append("relationship = ?")
                    params.append(relationship)
                if is_admin is not None:
                    updates.append("is_admin = ?")
                    params.append(1 if is_admin else 0)
                if updates:
                    params.append(existing["id"])
                    conn.execute(f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?", params)
                    conn.commit()
            return existing["id"]
        else:
            return self.save_profile(name, face_emb, voice_emb, relationship, is_admin or False)

    def get_profile_by_name(self, name: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, relationship, face_emb, voice_emb, is_admin FROM profiles WHERE name = ?",
                (name,),
            ).fetchone()
        if not row:
            return None
        return {
            "id":          row[0],
            "name":        row[1],
            "relationship": row[2] or "",
            "face_emb":    self._dec(row[3]) if row[3] else None,
            "voice_emb":   self._dec(row[4]) if row[4] else None,
            "is_admin":    bool(row[5]),
        }

    def update_relationship(self, profile_id: int, relationship: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE profiles SET relationship = ? WHERE id = ?",
                (relationship, profile_id),
            )

    def update_last_seen(self, profile_id: int):
        with self._connect() as conn:
            conn.execute(
                "UPDATE profiles SET last_seen = CURRENT_TIMESTAMP WHERE id = ?",
                (profile_id,),
            )

    def get_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, relationship, face_emb, voice_emb, last_seen, is_admin FROM profiles"
            ).fetchall()
        return [
            {
                "id":          r[0],
                "name":        r[1],
                "relationship": r[2] or "",
                "face_emb":    self._dec(r[3]) if r[3] else None,
                "voice_emb":   self._dec(r[4]) if r[4] else None,
                "last_seen":   r[5],
                "is_admin":    bool(r[6]),
            }
            for r in rows
        ]

    def delete_profile(self, profile_id: int):
        with self._connect() as conn:
            row = conn.execute("SELECT is_admin FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            if row and row[0]:
                logger.warning("[BiometricDB] Cannot delete admin profile #{}", profile_id)
                return
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        logger.info("[BiometricDB] Profile #{} deleted", profile_id)

    def list_names(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM profiles ORDER BY name").fetchall()
        return [r[0] for r in rows]

    # ─── Admin management ─────────────────────────────────────────────────────

    def get_admin(self) -> dict | None:
        """Return the admin profile, or None if no admin exists."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, relationship, face_emb, voice_emb, is_admin FROM profiles WHERE is_admin = 1"
            ).fetchone()
        if not row:
            return None
        return {
            "id":          row[0],
            "name":        row[1],
            "relationship": row[2] or "",
            "face_emb":    self._dec(row[3]) if row[3] else None,
            "voice_emb":   self._dec(row[4]) if row[4] else None,
            "is_admin":    bool(row[5]),
        }

    def set_admin(self, profile_id: int):
        """Promote a profile to admin (permanent, cannot be undone)."""
        if self.has_admin():
            logger.warning("[BiometricDB] Admin already exists — cannot promote another user")
            return False
        with self._connect() as conn:
            conn.execute("UPDATE profiles SET is_admin = 1 WHERE id = ?", (profile_id,))
        logger.info("[BiometricDB] Profile #{} promoted to admin (permanent)", profile_id)
        return True

    def is_admin(self, profile_id: int) -> bool:
        """Check if a profile is admin."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_admin FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return bool(row[0]) if row else False

    def has_admin(self) -> bool:
        """Check if any admin exists."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM profiles WHERE is_admin = 1"
            ).fetchone()
        return row[0] > 0

    # ─── Encryption helpers ──────────────────────────────────────────────────

    def _enc(self, obj) -> bytes:
        """Encode with an explicit type marker so decoding is unambiguous."""
        if obj is None:
            return b""
        if isinstance(obj, np.ndarray):
            payload = b"A" + obj.astype(np.float32).tobytes()
        else:
            payload = b"P" + pickle.dumps(obj)
        return self._fernet.encrypt(payload)

    def _dec(self, data: bytes):
        if not data:
            return None
        try:
            decrypted = self._fernet.decrypt(data)
        except Exception as e:
            logger.error("[BioDB] Could not decrypt stored biometric data: {}", e)
            return None
        try:
            if decrypted[:1] == b"A":
                return np.frombuffer(decrypted[1:], dtype=np.float32)
            if decrypted[:1] == b"P":
                return pickle.loads(decrypted[1:])
            # Legacy blobs written before type markers: raw float32 bytes
            # (arrays) or unpickled objects. Try array first, then pickle.
            try:
                return np.frombuffer(decrypted, dtype=np.float32)
            except Exception:
                return pickle.loads(decrypted)
        except Exception as e:
            logger.error("[BioDB] Could not decode stored biometric data: {}", e)
            return None



















