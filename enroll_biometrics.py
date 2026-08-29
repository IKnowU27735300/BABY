"""
enroll_biometrics.py — Interactive enrollment for admin face + voice.

Usage:
    python enroll_biometrics.py                  # enroll both face + voice for ANISH
    python enroll_biometrics.py --voice-only      # voice only
    python enroll_biometrics.py --face-only       # face only
    python enroll_biometrics.py --name "Bob"      # different admin name

The script re-uses the EXISTING admin profile (updates embeddings in-place via upsert).
It does NOT create a new profile — ANISH already exists as admin.
"""

from __future__ import annotations
import argparse
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from loguru import logger

from biometrics.biometric_db import BiometricDB

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_RATE   = 16000
RECORD_SECS   = 8       # seconds of voice to capture per sample
NUM_VOICE_SAMPLES = 5   # multiple samples averaged for a robust embedding
FACE_CAPTURE_SECS = 3   # seconds of webcam frames to average face embedding from


def enroll_voice(db: BiometricDB, name: str):
    """Record NUM_VOICE_SAMPLES clips, embed each with resemblyzer, average & store."""
    from resemblyzer import VoiceEncoder, preprocess_wav
    import sounddevice as sd

    print(f"\n{'='*60}")
    print(f"  VOICE ENROLLMENT — {name}")
    print(f"{'='*60}")
    print(f"  We will record {NUM_VOICE_SAMPLES} samples of ~{RECORD_SECS}s each.")
    print("  Speak naturally — say a few sentences (e.g. 'baby I am back,")
    print("  how are you today, the quick brown fox jumps over the lazy dog').")
    print()

    encoder = VoiceEncoder(device="cpu")

    embeddings = []
    for i in range(NUM_VOICE_SAMPLES):
        input(f"  [{i+1}/{NUM_VOICE_SAMPLES}] Press ENTER, then speak for {RECORD_SECS}s... ")
        print("  ● Recording...", end="", flush=True)
        audio = sd.rec(
            int(RECORD_SECS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32,
        )
        sd.wait()
        audio = audio.flatten()
        wav   = preprocess_wav(audio, source_sr=SAMPLE_RATE)
        emb   = encoder.embed_utterance(wav)
        embeddings.append(emb)
        print(f" done (emb norm={float(np.linalg.norm(emb)):.3f})")

    # Average the embeddings → more robust than a single clip
    avg_emb = np.mean(embeddings, axis=0).astype(np.float32)

    # Upsert (updates existing profile, preserves is_admin flag)
    existing = db.get_profile_by_name(name)
    if existing:
        db.upsert_profile(name=name, voice_emb=avg_emb)
        logger.success(f"[Enroll] Voice embedding updated for existing profile '{name}'")
    else:
        db.save_profile(name=name, voice_emb=avg_emb, relationship="admin", is_admin=True)
        logger.success(f"[Enroll] Voice embedding saved for new profile '{name}'")

    print(f"\n  ✓ Voice enrolled for '{name}' ({NUM_VOICE_SAMPLES} samples averaged)")
    return avg_emb


def enroll_face(db: BiometricDB, name: str):
    """Open webcam, collect FACE_CAPTURE_SECS of face embeddings, average & store."""
    import cv2
    from insightface.app import FaceAnalysis

    print(f"\n{'='*60}")
    print(f"  FACE ENROLLMENT — {name}")
    print(f"{'='*60}")
    print(f"  A webcam window will open. Look directly at the camera.")
    print(f"  We will capture face embeddings for ~{FACE_CAPTURE_SECS}s.")
    print("  Press ENTER to start...")
    input()

    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("  ✗ Could not open webcam. Check camera index or permissions.")
        return None

    embeddings    = []
    start         = time.time()
    frames_seen   = 0
    faces_found   = 0

    print(f"  ● Capturing for {FACE_CAPTURE_SECS}s — look at the camera...")

    while time.time() - start < FACE_CAPTURE_SECS:
        ret, frame = cap.read()
        if not ret:
            continue
        frames_seen += 1

        faces = app.get(frame)
        if not faces:
            cv2.putText(frame, "No face detected", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        else:
            largest = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
            embeddings.append(largest.embedding)
            faces_found += 1
            # Draw a green box
            x1, y1, x2, y2 = [int(c) for c in largest.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            elapsed = time.time() - start
            remaining = max(0.0, FACE_CAPTURE_SECS - elapsed)
            cv2.putText(frame, f"Capturing... {remaining:.1f}s", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

        cv2.imshow(f"Enroll Face — {name} (press Q to abort)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n  Aborted by user.")
            break

    cap.release()
    cv2.destroyAllWindows()

    if not embeddings:
        print(f"  ✗ No faces captured (saw {frames_seen} frames). Enrollment failed.")
        return None

    avg_emb = np.mean(embeddings, axis=0).astype(np.float32)

    existing = db.get_profile_by_name(name)
    if existing:
        db.upsert_profile(name=name, face_emb=avg_emb)
        logger.success(f"[Enroll] Face embedding updated for existing profile '{name}'")
    else:
        db.save_profile(name=name, face_emb=avg_emb, relationship="admin", is_admin=True)
        logger.success(f"[Enroll] Face embedding saved for new profile '{name}'")

    print(f"\n  ✓ Face enrolled for '{name}' ({faces_found} frames averaged over {FACE_CAPTURE_SECS}s)")
    return avg_emb


def verify_enrollment(db: BiometricDB, name: str):
    """Print a summary of what's now stored."""
    profile = db.get_profile_by_name(name)
    print(f"\n{'='*60}")
    print("  ENROLLMENT SUMMARY")
    print(f"{'='*60}")
    if not profile:
        print(f"  ✗ Profile '{name}' not found in DB!")
        return
    has_face  = profile["face_emb"]  is not None
    has_voice = profile["voice_emb"] is not None
    is_admin  = profile["is_admin"]
    print(f"  Name       : {profile['name']}")
    print(f"  Admin      : {is_admin}")
    print(f"  Relationship: {profile['relationship']}")
    print(f"  Face emb   : {'✓ enrolled' if has_face  else '✗ missing'}")
    print(f"  Voice emb  : {'✓ enrolled' if has_voice else '✗ missing'}")
    print()
    if has_face and has_voice and is_admin:
        print("  🟢 Admin is fully enrolled — voice & face verification will work.")
    elif has_voice and is_admin:
        print("  🟡 Voice enrolled. Face missing — face auth will be skipped (OK).")
    elif has_face and is_admin:
        print("  🟡 Face enrolled. Voice missing — voice auth may fail.")
    else:
        print("  🔴 Neither face nor voice enrolled — verification WILL fail.")


def main():
    parser = argparse.ArgumentParser(
        description="Enroll admin face + voice biometrics for BABY."
    )
    parser.add_argument("--name", default="ANISH",
                        help="Admin profile name (default: ANISH)")
    parser.add_argument("--voice-only", action="store_true",
                        help="Only enroll voice (skip face)")
    parser.add_argument("--face-only", action="store_true",
                        help="Only enroll face (skip voice)")
    parser.add_argument("--db-path", default="data/biometrics.db",
                        help="Path to biometrics DB")
    args = parser.parse_args()

    db = BiometricDB(db_path=args.db_path)

    do_voice = not args.face_only
    do_face  = not args.voice_only

    if do_voice:
        enroll_voice(db, args.name)

    if do_face:
        enroll_face(db, args.name)

    verify_enrollment(db, args.name)


if __name__ == "__main__":
    main()
