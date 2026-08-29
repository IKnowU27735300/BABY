# Baby Training Pipeline

Training scripts for personalizing Baby's AI capabilities.

## Overview

| Script | Purpose | Time |
|--------|---------|------|
| `prepare_llm_data.py` | Convert conversation logs to training format | ~1 min |
| `train_ollama.py` | Fine-tune LLM with LoRA | ~30-60 min |
| `train_wake_word.py` | Train custom wake word | ~15 min |
| `train_embeddings.py` | Fine-tune semantic search | ~10 min |
| `create_modelfile.py` | Generate Ollama Modelfile | ~1 sec |

## Quick Start

```bash
# 1. Prepare training data from conversations
python training/prepare_llm_data.py

# 2. Fine-tune LLM (requires GPU)
python training/train_ollama.py --epochs 3

# 3. Create Ollama model
python training/create_modelfile.py
ollama create Baby -f training/Modelfile

# 4. (Optional) Fine-tune embeddings
python training/train_embeddings.py

# 5. (Optional) Train custom wake word
python training/train_wake_word.py --collect --wake_word "hey Baby"
```

## Requirements

```bash
# Core training packages
pip install unsloth transformers datasets trl
pip install --no-deps bitsandbytes accelerate

# Embeddings training
pip install sentence-transformers torch

# Wake word training
pip install openwakeword sounddevice

# Voice cloning (already in project)
pip install resemblyzer
```

## Data Format

Training data uses Alpaca format:

```json
[
  {
    "instruction": "user message",
    "assistant": "assistant response",
    "system": "system prompt"
  }
]
```

## Model Outputs

- **LLM**: `training/models/Baby-lora.gguf` (GGUF for Ollama)
- **Embeddings**: `training/models/embeddings/` (sentence-transformers)
- **Wake Word**: `audio/wakeword/models/` (ONNX format)

## Configuration

Edit `config.yaml` to point to fine-tuned models:

```yaml
llm:
  model: "Baby"  # Ollama model name

wake_word:
  model_path: "audio/wakeword/models/hey_baby_clara.onnx"

memory:
  embedding_model: "training/models/embeddings"
```

## Notes

- LLM fine-tuning requires NVIDIA GPU with 8GB+ VRAM
- Wake word training works on CPU
- Embeddings training works on CPU (slower)
- All training is optional — Baby works out of the box with base models




