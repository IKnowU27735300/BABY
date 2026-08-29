"""
training/train_ollama.py — Fine-tune LLM for Baby using LoRA + Ollama.

Uses unsloth for efficient LoRA training on consumer GPUs.
Exports to GGUF format for direct use with Ollama.

Requirements (install separately):
    pip install unsloth transformers datasets trl
    pip install --no-deps bitsandbytes accelerate

Usage:
    python training/train_ollama.py
    python training/train_ollama.py --epochs 3 --lr 2e-4 --rank 16
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
TRAINING_DATA = ROOT / "training" / "output" / "training_data.json"
MODEL_DIR = ROOT / "training" / "models"
GGUF_OUTPUT = ROOT / "training" / "models" / "Baby-lora.gguf"


def check_dependencies():
    """Verify required packages are installed."""
    missing = []
    for pkg in ["unsloth", "transformers", "datasets", "trl"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print("Missing packages. Install with:")
        print(f"  pip install {' '.join(missing)}")
        print("  pip install --no-deps bitsandbytes accelerate")
        sys.exit(1)


def load_training_data() -> list[dict]:
    """Load the Alpaca-format training data."""
    if not TRAINING_DATA.exists():
        print(f"Error: Training data not found: {TRAINING_DATA}")
        print("Run: python training/prepare_llm_data.py")
        sys.exit(1)
    
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} training pairs")
    return data


def format_for_unsloth(data: list[dict]) -> list[dict]:
    """
    Format data for unsloth training.
    Creates ChatML-formatted conversations.
    """
    formatted = []
    for pair in data:
        # ChatML format for Llama 3.1
        text = (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            f"{pair['system']}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n\n"
            f"{pair['instruction']}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n\n"
            f"{pair['response']}<|eot_id|>"
        )
        formatted.append({"text": text})
    
    return formatted


def train_model(args):
    """Run LoRA fine-tuning with unsloth."""
    import torch
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import Dataset
    
    print("=" * 60)
    print("Baby LLM Fine-Tuning (LoRA + Unsloth)")
    print("=" * 60)
    
    # ── Load base model ──────────────────────────────────────────────────────
    print(f"\nLoading base model: {args.base_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )
    
    # ── Apply LoRA ───────────────────────────────────────────────────────────
    print(f"\nApplying LoRA (rank={args.rank}, alpha={args.alpha})")
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=args.alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    
    # ── Prepare data ─────────────────────────────────────────────────────────
    print("\nPreparing training data...")
    raw_data = load_training_data()
    formatted_data = format_for_unsloth(raw_data)
    dataset = Dataset.from_list(formatted_data)
    
    # ── Training arguments ───────────────────────────────────────────────────
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    training_args = TrainingArguments(
        output_dir=str(MODEL_DIR),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        weight_decay=0.01,
        warmup_steps=args.warmup,
        lr_scheduler_type="cosine",
        logging_steps=1,
        save_strategy="epoch",
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        seed=3407,
        report_to="none",
    )
    
    # ── Trainer ──────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        args=training_args,
    )
    
    # ── Train ────────────────────────────────────────────────────────────────
    print("\nStarting training...")
    trainer_stats = trainer.train()
    
    print(f"\nTraining complete! Loss: {trainer_stats.training_loss:.4f}")
    
    # ── Save LoRA adapter ────────────────────────────────────────────────────
    lora_path = MODEL_DIR / "Baby-lora-adapter"
    print(f"\nSaving LoRA adapter to {lora_path}")
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    
    # ── Export to GGUF ───────────────────────────────────────────────────────
    print("\nExporting to GGUF format for Ollama...")
    try:
        model.save_pretrained_gguf(
            str(MODEL_DIR),
            tokenizer,
            quantization_method="q4_k_m",
        )
        
        # Rename to Baby-lora.gguf
        gguf_files = list(MODEL_DIR.glob("*.gguf"))
        if gguf_files:
            gguf_files[0].rename(GGUF_OUTPUT)
            print(f"GGUF saved to: {GGUF_OUTPUT}")
        else:
            print("Warning: GGUF file not found after export")
    except Exception as e:
        print(f"GGUF export failed: {e}")
        print("You can export manually later with:")
        print(f"  python -m unsloth.save_pretrained_gguf {lora_path}")
    
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. Create Modelfile for Ollama:")
    print(f"   training/create_modelfile.py")
    print("2. Build Ollama model:")
    print(f"   ollama create Baby -f training/Modelfile")
    print("3. Test:")
    print(f"   ollama run Baby")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fine-tune LLM for Baby")
    parser.add_argument("--base_model", default="unsloth/Meta-Llama-3.1-8B-Instruct",
                        help="Base model to fine-tune")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--rank", type=int, default=16, help="LoRA rank")
    parser.add_argument("--alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--batch_size", type=int, default=2, help="Batch size")
    parser.add_argument("--grad_accum", type=int, default=4, help="Gradient accumulation")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup steps")
    parser.add_argument("--max_seq_length", type=int, default=2048,
                        help="Max sequence length")
    
    args = parser.parse_args()
    
    check_dependencies()
    train_model(args)


if __name__ == "__main__":
    main()



















