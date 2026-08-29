"""
training/prepare_llm_data.py — Convert Baby conversation logs into LLM fine-tuning data.

Processes session_*.json files from data/conversations/ and generates:
  - training_data.json  (Alpaca-style instruction/response pairs)
  - training_data.jsonl (same, one per line for streaming)

Usage:
    python training/prepare_llm_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CONV_DIR = ROOT / "data" / "conversations"
OUTPUT_DIR = ROOT / "training" / "output"
OUTPUT_JSON = OUTPUT_DIR / "training_data.json"
OUTPUT_JSONL = OUTPUT_DIR / "training_data.jsonl"

# ─── System prompt (from core/context_manager.py) ─────────────────────────────
SYSTEM_PROMPT = (
    "You are Baby (\"Baby\"), a warm, emotionally-intelligent desktop assistant. "
    "You help with daily tasks, answer questions, and provide companionship. "
    "You use tools when needed (file ops, web search, math, screen control). "
    "You are concise, friendly, and speak naturally — not robotically. "
    "You call the user by their preferred name and remember past conversations."
)

# ── Minimum quality thresholds ────────────────────────────────────────────────
MIN_USER_LEN = 3        # skip trivially short user messages
MIN_ASST_LEN = 5        # skip empty/very short assistant replies
MAX_PAIRS_PER_SESSION = 50  # cap to avoid over-representing long sessions


def load_session(path: Path) -> list[dict[str, Any]]:
    """Load a single session JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"  [WARN] Skipping {path.name}: {e}")
    return []


def extract_turn_pairs(messages: list[dict]) -> list[dict[str, str]]:
    """
    Extract user→assistant turn pairs from a conversation.
    Skips tool-result messages and consecutive same-role messages.
    """
    pairs = []
    i = 0
    while i < len(messages) - 1:
        msg = messages[i]
        next_msg = messages[i + 1]

        # We want user → assistant pairs
        if msg.get("role") == "user" and next_msg.get("role") == "assistant":
            user_text = msg.get("content", "").strip()
            asst_text = next_msg.get("content", "").strip()

            # Skip low-quality pairs
            if len(user_text) < MIN_USER_LEN or len(asst_text) < MIN_ASST_LEN:
                i += 2
                continue

            # Skip if assistant response is just a tool result dump
            if asst_text.startswith("Completed:\n•") and len(asst_text) > 500:
                # Tool-heavy response — extract just the summary if possible
                lines = asst_text.split("\n")
                summary_lines = [l for l in lines if not l.startswith("•")]
                if summary_lines:
                    asst_text = "\n".join(summary_lines).strip()
                # If still too tool-ish, skip
                if asst_text.startswith("Completed:"):
                    i += 2
                    continue

            pairs.append({
                "instruction": user_text,
                "response": asst_text,
                "system": SYSTEM_PROMPT,
            })
            i += 2
        else:
            i += 1

    return pairs


def process_all_sessions() -> list[dict]:
    """Process all conversation sessions and return training pairs."""
    all_pairs = []
    session_files = sorted(CONV_DIR.glob("session_*.json"))

    print(f"Found {len(session_files)} session files")

    for path in session_files:
        messages = load_session(path)
        if not messages:
            continue

        pairs = extract_turn_pairs(messages)
        # Cap pairs per session
        pairs = pairs[:MAX_PAIRS_PER_SESSION]
        all_pairs.extend(pairs)
        print(f"  {path.name}: {len(pairs)} pairs")

    return all_pairs


def save_alpaca_json(pairs: list[dict], output_path: Path):
    """Save in Alpaca JSON format (list of dicts)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(pairs)} pairs → {output_path}")


def save_alpaca_jsonl(pairs: list[dict], output_path: Path):
    """Save in JSONL format (one JSON object per line) for streaming."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    print(f"Saved {len(pairs)} lines → {output_path}")


def print_stats(pairs: list[dict]):
    """Print dataset statistics."""
    if not pairs:
        print("No pairs to analyze.")
        return

    user_lens = [len(p["instruction"]) for p in pairs]
    asst_lens = [len(p["response"]) for p in pairs]

    print("\n" + "=" * 50)
    print("DATASET STATISTICS")
    print("=" * 50)
    print(f"Total pairs:       {len(pairs)}")
    print(f"Avg user length:   {sum(user_lens) / len(user_lens):.0f} chars")
    print(f"Avg asst length:   {sum(asst_lens) / len(asst_lens):.0f} chars")
    print(f"Min user length:   {min(user_lens)} chars")
    print(f"Max user length:   {max(user_lens)} chars")
    print(f"Min asst length:   {min(asst_lens)} chars")
    print(f"Max asst length:   {max(asst_lens)} chars")
    print(f"Total dataset size: {sum(u + a for u, a in zip(user_lens, asst_lens)) / 1024:.1f} KB")


def main():
    print("=" * 50)
    print("Baby LLM Training Data Preparation")
    print("=" * 50)

    if not CONV_DIR.exists():
        print(f"Error: Conversation directory not found: {CONV_DIR}")
        sys.exit(1)

    pairs = process_all_sessions()

    if not pairs:
        print("No training pairs extracted. Check conversation logs.")
        sys.exit(1)

    save_alpaca_json(pairs, OUTPUT_JSON)
    save_alpaca_jsonl(pairs, OUTPUT_JSONL)
    print_stats(pairs)

    print("\n" + "=" * 50)
    print("NEXT STEPS:")
    print("=" * 50)
    print("1. Review training_data.json for quality")
    print("2. Run: python training/train_ollama.py (Phase 4)")
    print("=" * 50)


if __name__ == "__main__":
    main()



















