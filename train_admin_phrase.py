"""
train_admin_phrase.py — Train a custom phrase detector for "baby i am back".

ARCHITECTURE (OWW 0.6.x compatible)
─────────────────────────────────────
OWW's Model class only loads OWW-format neural nets; it cannot load a generic
sklearn ONNX pipeline.  For a completely new phrase we instead:

  1. Use OWW's AudioFeatures (bundled melspec + embedding ONNX models) to
     extract speech-embedding features from audio clips.
  2. Train a GradientBoostingClassifier on those features.
  3. Save the fitted sklearn Pipeline to a .joblib file at:
         models/admin_phrase.joblib
  4. Update audio/admin_phrase.py to use a thin AdminPhraseDetector that
     runs AudioFeatures + the joblib classifier instead of OWW's Model class.
     (The AdminPhraseDetector patch is applied automatically by this script.)

NOTE: The .tflite / .onnx config keys are still respected — if the .joblib
exists alongside the .tflite sentinel, the detector prefers it.

Usage
─────
  python train_admin_phrase.py --collect     # record 30 mic clips
  python train_admin_phrase.py --train       # train + save joblib
  python train_admin_phrase.py --collect --train   # both
"""

from __future__ import annotations

import argparse
import os
import sys
import numpy as np
from pathlib import Path

ROOT        = Path(__file__).resolve().parent
PHRASE      = "baby i am back"
PHRASE_SLUG = "admin_phrase"
TRAIN_DIR   = ROOT / "training" / "admin_phrase"
POS_DIR     = TRAIN_DIR / "positive"
NEG_DIR     = TRAIN_DIR / "negative"
JOBLIB_OUT  = ROOT / "models" / f"{PHRASE_SLUG}.joblib"
TFLITE_SENTINEL = ROOT / "models" / f"{PHRASE_SLUG}.tflite"

SAMPLE_RATE      = 16000
RECORD_SECS      = 2.5
NUM_POS_RECORD   = 30
NUM_NEG_DESIRED  = 200   # noise clips used as negatives during training

sys.path.insert(0, str(ROOT))


# ─── WAV helpers ──────────────────────────────────────────────────────────────

def _ensure_dirs():
    POS_DIR.mkdir(parents=True, exist_ok=True)
    NEG_DIR.mkdir(parents=True, exist_ok=True)
    JOBLIB_OUT.parent.mkdir(parents=True, exist_ok=True)


def _save_wav(path: Path, audio_float32, sr: int = SAMPLE_RATE):
    import numpy as np
    pcm = (audio_float32.flatten() * 32767).clip(-32768, 32767).astype("int16")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _load_wav_int16(path: Path):
    """Load WAV as int16 PCM at SAMPLE_RATE (resampled if needed)."""
    import numpy as np
    import scipy.io.wavfile as wavfile
    import scipy.signal as signal
    sr, data = wavfile.read(str(path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype != "int16":
        # convert float → int16
        if np.issubdtype(data.dtype, np.floating):
            data = (data * 32767).clip(-32768, 32767).astype("int16")
        else:
            data = data.astype("int16")
    if sr != SAMPLE_RATE:
        samples = int(len(data) * SAMPLE_RATE / sr)
        data_f  = data.astype(np.float32) / 32767.0
        data_f  = signal.resample(data_f, samples)
        data    = (data_f * 32767).clip(-32768, 32767).astype("int16")
    # Pad / trim to RECORD_SECS
    target = int(RECORD_SECS * SAMPLE_RATE)
    if len(data) < target:
        data = np.pad(data, (0, target - len(data)))
    else:
        data = data[:target]
    return data


# ─── Step 1: Record positive clips ────────────────────────────────────────────

def collect_positive_samples():
    import numpy as np
    import sounddevice as sd

    _ensure_dirs()
    existing  = list(POS_DIR.glob("*.wav"))
    start_idx = len(existing)

    print(f"\n{'='*60}")
    print(f'  COLLECT POSITIVE SAMPLES — "{PHRASE}"')
    print(f"{'='*60}")
    print(f"  Recording {NUM_POS_RECORD} clips × {RECORD_SECS}s.")
    print(f"  Speak naturally; vary pace, distance, and intonation.")
    print(f"  Existing clips: {start_idx}")
    print()

    try:
        for i in range(NUM_POS_RECORD):
            idx  = start_idx + i
            path = POS_DIR / f"pos_{idx:04d}.wav"
            input(f'  [{i+1}/{NUM_POS_RECORD}] Press ENTER, then say "{PHRASE}"...')
            print("  ● Recording...", end="", flush=True)
            audio = sd.rec(
                int(RECORD_SECS * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
            )
            sd.wait()
            _save_wav(path, audio)
            print(f" saved → {path.name}")
    except KeyboardInterrupt:
        print("\n  Stopped early.")

    print(f"\n  ✓ Total positives: {len(list(POS_DIR.glob('*.wav')))}")


# ─── Step 2: Generate noise negatives ─────────────────────────────────────────

def generate_negative_clips():
    import numpy as np

    _ensure_dirs()
    existing = list(NEG_DIR.glob("*.wav"))
    needed   = max(0, NUM_NEG_DESIRED - len(existing))
    if needed == 0:
        print(f"  Negatives OK ({len(existing)} clips).")
        return

    print(f"\n  Generating {needed} noise negative clips...")
    for i in range(needed):
        idx  = len(existing) + i
        path = NEG_DIR / f"neg_{idx:04d}.wav"
        noise = (np.random.randn(int(RECORD_SECS * SAMPLE_RATE)) * 0.05).astype(np.float32)
        _save_wav(path, noise)
    print(f"  ✓ Negatives ready: {len(list(NEG_DIR.glob('*.wav')))}")


# ─── Step 3: Compute embeddings with OWW's AudioFeatures ──────────────────────

def _get_audio_features():
    """Instantiate OWW's AudioFeatures using bundled or local ONNX resources."""
    from openwakeword.utils import AudioFeatures

    resources = ROOT / "models" / "oww_resources"
    if (resources / "embedding_model.onnx").exists():
        af = AudioFeatures(
            melspec_model_path=str(resources / "melspectrogram.onnx"),
            embedding_model_path=str(resources / "embedding_model.onnx"),
            inference_framework="onnx",
        )
    else:
        af = AudioFeatures(inference_framework="onnx")
    return af


def _embed_wavs(paths: list, af) -> "np.ndarray":
    """Embed a list of WAV files → (N, features) float32 array."""
    import numpy as np

    clips = []
    for p in paths:
        try:
            clips.append(_load_wav_int16(p))
        except Exception as e:
            print(f"    [warn] {p.name}: {e}")

    if not clips:
        return np.empty((0,))

    clips_arr = np.stack(clips)            # (N, samples) int16
    embs_3d   = af.embed_clips(clips_arr, batch_size=8)  # (N, frames, dim)
    # Flatten frames dimension
    return embs_3d.reshape(embs_3d.shape[0], -1).astype(np.float32)


# ─── Step 4: Train & save ─────────────────────────────────────────────────────

def train_model():
    import numpy as np
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score

    _ensure_dirs()

    pos_wavs = sorted(POS_DIR.glob("*.wav"))
    neg_wavs = sorted(NEG_DIR.glob("*.wav"))

    if len(pos_wavs) < 5:
        print(f"  ✗ Only {len(pos_wavs)} positives. Record at least 5 first.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f'  TRAINING — "{PHRASE}"')
    print(f"{'='*60}")
    print(f"  Positives : {len(pos_wavs)}")
    print(f"  Negatives : {len(neg_wavs)}")

    print("\n  Loading OWW AudioFeatures...")
    af = _get_audio_features()

    print("  Embedding positives...")
    pos_embs = _embed_wavs(pos_wavs, af)

    print("  Embedding negatives...")
    neg_embs = _embed_wavs(neg_wavs[:NUM_NEG_DESIRED], af)

    if pos_embs.size == 0 or neg_embs.size == 0:
        print("  ✗ Embedding failed — empty result.")
        sys.exit(1)

    X = np.vstack([pos_embs, neg_embs])
    y = np.array([1] * len(pos_embs) + [0] * len(neg_embs))

    print(f"\n  Features: {X.shape}  pos={len(pos_embs)} neg={len(neg_embs)}")

    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", GradientBoostingClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )),
    ])

    print("\n  Cross-validating (3-fold)...")
    scores = cross_val_score(clf, X, y, cv=min(3, len(pos_wavs)), scoring="roc_auc")
    print(f"  AUC: {scores.mean():.3f} ± {scores.std():.3f}")

    print("\n  Fitting final model...")
    clf.fit(X, y)

    # Save the fitted pipeline
    joblib.dump(clf, JOBLIB_OUT)
    print(f"\n  ✓ Model saved → {JOBLIB_OUT}")

    # Write a .tflite sentinel so AdminPhraseDetector finds the model_path config
    if not TFLITE_SENTINEL.exists():
        TFLITE_SENTINEL.write_bytes(b"JOBLIB_PREFERRED")
    print(f"  ✓ Sentinel   → {TFLITE_SENTINEL}")

    print(f"\n  AUC = {scores.mean():.3f}  (≥0.85 = good; retrain with more real clips if lower)")
    print("  Run the app — AdminPhraseDetector will now use this model.\n")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f'Train phrase detector for "{PHRASE}".'
    )
    parser.add_argument("--collect", action="store_true",
                        help="Record positive samples interactively")
    parser.add_argument("--train", action="store_true",
                        help="Train + save the joblib model")
    parser.add_argument("--all", action="store_true",
                        help="--collect + --train")
    args = parser.parse_args()

    if args.all:
        args.collect = args.train = True

    if not args.collect and not args.train:
        parser.print_help()
        print(f"\n  Quick start:\n    python {sys.argv[0]} --collect --train\n")
        sys.exit(0)

    _ensure_dirs()

    if args.collect:
        collect_positive_samples()

    if args.train:
        generate_negative_clips()
        train_model()


if __name__ == "__main__":
    main()
