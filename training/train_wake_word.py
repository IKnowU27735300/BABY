"""
training/train_wake_word.py — Train custom wake word for Baby.

Uses openwakeword to train a custom wake word model.
Collects audio samples and trains a personal wake word detector.

Usage:
    python training/train_wake_word.py --wake_word "hey Baby"
    python training/train_wake_word.py --wake_word "baby" --samples 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAKE_WORD_DIR = ROOT / "training" / "wake_word"
AUDIO_DIR = WAKE_WORD_DIR / "audio"
MODELS_DIR = ROOT / "audio" / "wakeword" / "models"

# Required packages
REQUIRED = ["openwakeword", "sounddevice", "numpy"]


def check_dependencies():
    """Verify required packages are installed."""
    missing = []
    for pkg in REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print("Missing packages. Install with:")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)


def collect_samples(wake_word: str, num_samples: int = 100):
    """Collect audio samples for wake word training."""
    import sounddevice as sd
    import numpy as np
    
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print(f"Wake Word Sample Collection: '{wake_word}'")
    print("=" * 60)
    print(f"\nYou will record {num_samples} samples of '{wake_word}'.")
    print("Speak naturally, as you would in normal conversation.\n")
    print("Press ENTER to start recording each sample...")
    print("Press Ctrl+C to stop early.\n")
    
    sample_rate = 16000
    duration = 2.0  # seconds
    samples_collected = 0
    
    try:
        for i in range(num_samples):
            input(f"Sample {i + 1}/{num_samples} - Press ENTER to record...")
            
            print("  Recording...", end="", flush=True)
            audio = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype=np.float32,
            )
            sd.wait()
            
            # Save sample
            filename = AUDIO_DIR / f"{wake_word.replace(' ', '_')}_{i:04d}.npy"
            np.save(filename, audio.flatten())
            samples_collected += 1
            print(f" saved ({filename.name})")
    
    except KeyboardInterrupt:
        print(f"\n\nStopped early. Collected {samples_collected} samples.")
    
    print(f"\nTotal samples collected: {samples_collected}")
    return samples_collected


def train_model(wake_word: str):
    """Train wake word model using openwakeword."""
    try:
        from openwakeword.model import Model
        from openwakeword import utils
    except ImportError:
        print("Error: openwakeword not installed")
        print("Install with: pip install openwakeword")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("Training Wake Word Model")
    print("=" * 60)
    
    # Load samples
    samples = list(AUDIO_DIR.glob("*.npy"))
    if not samples:
        print(f"No samples found in {AUDIO_DIR}")
        print("Run with --collect first to record samples.")
        sys.exit(1)
    
    print(f"Found {len(samples)} training samples")
    
    # Create output directory
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    # For openwakeword, we need to:
    # 1. Create a dataset in the correct format
    # 2. Use their training pipeline
    
    print("\nTraining configuration:")
    print(f"  Wake word: '{wake_word}'")
    print(f"  Samples: {len(samples)}")
    print(f"  Output: {MODELS_DIR}")
    
    # Note: openwakeword training requires their specific dataset format
    # and training script. This is a simplified wrapper.
    
    print("\n" + "-" * 60)
    print("OpenWakeWord Training Steps:")
    print("-" * 60)
    print("""
1. Prepare dataset in openwakeword format:
   - Positive samples: your recorded audio
   - Negative samples: general speech/audio
   
2. Use openwakeword's training script:
   openwakeword/train \\
     --train_dir training/wake_word/audio \\
     --output_dir training/wake_word/models \\
     --wake_word "Baby"
     
3. Export to ONNX for inference:
   openwakeword/export \\
     --model_path training/wake_word/models/best_model.ckpt \\
     --output_path audio/wakeword/models/hey_baby.onnx
""")
    
    print("\nThe custom model will be saved to:")
    print(f"  {MODELS_DIR / 'hey_baby.onnx'}")
    print("\nUpdate config.yaml wake_word.model_path to use it.")


def main():
    parser = argparse.ArgumentParser(description="Train custom wake word for Baby")
    parser.add_argument("--wake_word", default="hey baby",
                        help="Wake word phrase (default: 'hey baby')")
    parser.add_argument("--samples", type=int, default=100,
                        help="Number of audio samples to collect")
    parser.add_argument("--collect", action="store_true",
                        help="Collect audio samples only (don't train)")
    parser.add_argument("--train", action="store_true",
                        help="Train model from collected samples")
    
    args = parser.parse_args()
    
    check_dependencies()
    
    if args.collect or not args.train:
        collect_samples(args.wake_word, args.samples)
    
    if args.train:
        train_model(args.wake_word)
    
    if not args.collect and not args.train:
        print("Usage:")
        print(f"  python {sys.argv[0]} --collect --wake_word 'hey Baby'")
        print(f"  python {sys.argv[0]} --train --wake_word 'hey Baby'")


if __name__ == "__main__":
    main()



















