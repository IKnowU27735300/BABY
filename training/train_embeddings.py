"""
training/train_embeddings.py — Fine-tune embeddings for Baby's memory system.

Fine-tunes sentence-transformers on Baby's conversation data to improve
semantic search in the memory/knowledge graph system.

Uses multiple negative ranking loss for better retrieval.

Usage:
    python training/train_embeddings.py
    python training/train_embeddings.py --epochs 5 --batch_size 32
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAINING_DATA = ROOT / "training" / "output" / "training_data.json"
OUTPUT_DIR = ROOT / "training" / "models" / "embeddings"
BASE_MODEL = "all-MiniLM-L6-v2"

REQUIRED = ["sentence_transformers", "torch"]


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


def load_training_pairs() -> list[dict]:
    """Load conversation pairs for embedding training."""
    if not TRAINING_DATA.exists():
        print(f"Error: Training data not found: {TRAINING_DATA}")
        print("Run: python training/prepare_llm_data.py")
        sys.exit(1)
    
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} training pairs")
    return data


def create_training_examples(pairs: list[dict]) -> list[dict]:
    """
    Create training examples for sentence-transformers.
    
    Uses (query, positive_response, negative_response) triplets.
    Generates negatives by sampling random responses.
    """
    import random
    
    examples = []
    responses = [p["response"] for p in pairs]
    
    for pair in pairs:
        query = pair["instruction"]
        positive = pair["response"]
        
        # Sample a random negative (different from positive)
        negative = random.choice(responses)
        while negative == positive and len(responses) > 1:
            negative = random.choice(responses)
        
        examples.append({
            "anchor": query,
            "positive": positive,
            "negative": negative,
        })
    
    return examples


def train_model(args):
    """Fine-tune sentence-transformers model."""
    from sentence_transformers import SentenceTransformer, losses, InputExample
    from torch.utils.data import DataLoader
    
    print("=" * 60)
    print("Baby Embeddings Fine-Tuning")
    print("=" * 60)
    
    # Load base model
    print(f"\nLoading base model: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL)
    
    # Load and prepare data
    pairs = load_training_pairs()
    examples = create_training_examples(pairs)
    
    print(f"Created {len(examples)} training triplets")
    
    # Create DataLoader
    train_examples = [
        InputExample(texts=[e["anchor"], e["positive"], e["negative"]])
        for e in examples
    ]
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=args.batch_size)
    
    # Loss function
    train_loss = losses.MultipleNegativesRankingLoss(model)
    
    # Training
    print("\nStarting training...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=args.warmup,
        output_path=str(OUTPUT_DIR),
        show_progress_bar=True,
    )
    
    print(f"\nModel saved to: {OUTPUT_DIR}")
    
    # Test the model
    print("\n" + "=" * 60)
    print("Testing fine-tuned model")
    print("=" * 60)
    
    test_queries = [
        "what did we talk about yesterday",
        "remind me about my meetings",
        "help me with math",
        "who is my friend",
    ]
    
    test_responses = [
        "We discussed your project deadline and team meeting schedule.",
        "You have a meeting at 3 PM today with the design team.",
        "I can help you solve equations, calculate statistics, or simplify expressions.",
        "Your friend Priya called earlier while you were out.",
    ]
    
    query_embeddings = model.encode(test_queries)
    response_embeddings = model.encode(test_responses)
    
    # Compute similarities
    for i, query in enumerate(test_queries):
        similarities = model.similarity(query_embeddings[i:i+1], response_embeddings)[0]
        print(f"\nQuery: '{query}'")
        for j, resp in enumerate(test_responses):
            print(f"  [{similarities[j]:.3f}] {resp[:60]}...")
    
    print("\n" + "=" * 60)
    print("INTEGRATION:")
    print("=" * 60)
    print(f"""
1. Copy model to embeddings directory:
   cp -r {OUTPUT_DIR}/* data/embeddings/

2. Update memory_engine.py to use fine-tuned model:
   model_path = "data/embeddings"

3. Restart Baby to use improved semantic search.
""")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune embeddings for Baby")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size")
    parser.add_argument("--warmup", type=int, default=100, help="Warmup steps")
    
    args = parser.parse_args()
    
    check_dependencies()
    train_model(args)


if __name__ == "__main__":
    main()



















