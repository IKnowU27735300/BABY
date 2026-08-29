"""
core/relationship_engine/training/isolated_trainer.py — Sequential training with fresh optimizers.
Trains each network independently with isolated data and fresh optimizer states.
"""

from __future__ import annotations
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from typing import Dict, List, Optional, Tuple
from loguru import logger

from core.relationship_engine.isolation.memory_isolator import MemoryIsolator
from core.relationship_engine.isolation.gradient_blocker import GradientBlocker
from core.relationship_engine.models.base_network import BaseRelationshipNetwork
from core.relationship_engine.training.datasets import SYNTHETIC_DATASET


class RelationshipDataset(Dataset):
    """Dataset of action pairs with relationship labels."""

    def __init__(self, pairs: List[Tuple[str, str, str]], vocab: Dict[str, int], max_len: int = 64):
        self._pairs = pairs
        self._vocab = vocab
        self._max_len = max_len

    def __len__(self):
        return len(self._pairs)

    def __getitem__(self, idx):
        text_a, text_b, label = self._pairs[idx]
        tokens_a = self._tokenize(text_a)
        tokens_b = self._tokenize(text_b)
        combined = tokens_a + [self._vocab.get("[SEP]", 1)] + tokens_b
        if len(combined) < self._max_len:
            combined += [0] * (self._max_len - len(combined))
        else:
            combined = combined[:self._max_len]
        token_ids = torch.tensor(combined, dtype=torch.long)
        mask = token_ids != 0
        return token_ids, mask, label

    def _tokenize(self, text: str) -> List[int]:
        return [self._vocab.get(w.lower(), self._vocab.get("[UNK]", 2)) for w in text.split()]


class IsolatedTrainer:
    """Trains each relationship network independently.

    Key isolation rules:
    1. Sequential training — one network at a time
    2. Fresh optimizer for each network (no state sharing)
    3. Gradient blocking between networks
    4. Per-network training buffers via MemoryIsolator
    """

    def __init__(
        self,
        memory_isolator: MemoryIsolator,
        gradient_blocker: GradientBlocker,
        learning_rate: float = 1e-3,
        max_seq_len: int = 64,
    ):
        self._memory_isolator = memory_isolator
        self._gradient_blocker = gradient_blocker
        self._learning_rate = learning_rate
        self._max_seq_len = max_seq_len

    def train_network(
        self,
        network_name: str,
        model: BaseRelationshipNetwork,
        vocab: Dict[str, int],
        type_label: str,
        epochs: int = 10,
        batch_size: int = 8,
    ) -> Dict[str, float]:
        """Train a single network in complete isolation.

        Args:
            network_name: Unique identifier for this network.
            model: The network to train.
            vocab: Token vocabulary mapping.
            type_label: The relationship type this network classifies.
            epochs: Number of training epochs.
            batch_size: Batch size.

        Returns:
            Training metrics dict.
        """
        # Create isolated training buffer
        buffer_name = f"{network_name}_training_buffer"
        try:
            self._memory_isolator.create_buffer(buffer_name, network_name)
        except ValueError:
            pass  # Buffer already exists

        # Filter dataset for this type
        type_pairs = [(a, b, t) for a, b, t, _conf in SYNTHETIC_DATASET if t == type_label]
        if not type_pairs:
            logger.warning("[Trainer] No training data for type '{}'", type_label)
            return {"loss": 0.0, "accuracy": 0.0, "epochs": 0}

        dataset = RelationshipDataset(type_pairs, vocab, self._max_seq_len)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Fresh optimizer for each network
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=self._learning_rate,
            weight_decay=0.01,
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=epochs
        )
        criterion = nn.BCEWithLogitsLoss()

        model.train()
        type_idx = list(SYNTHETIC_DATASET[0][2] for _ in range(1))  # Not used directly
        total_loss = 0.0
        correct = 0
        total = 0

        for epoch in range(epochs):
            epoch_loss = 0.0
            epoch_correct = 0
            epoch_total = 0

            for token_ids, mask, _labels in dataloader:
                optimizer.zero_grad()

                logits = model(token_ids, mask)  # (B, 1)

                # Binary target: 1.0 for this type
                targets = torch.ones(logits.shape[0], 1)

                loss = criterion(logits, targets)
                loss.backward()

                # Gradient blocking at network boundary
                for param in model.parameters():
                    if param.grad is not None:
                        param.grad = self._gradient_blocker.detach_input(param.grad)

                optimizer.step()

                preds = (logits.sigmoid() > 0.5).float()
                epoch_correct += (preds == targets).sum().item()
                epoch_total += targets.shape[0]
                epoch_loss += loss.item()

            scheduler.step()
            total_loss += epoch_loss
            correct += epoch_correct
            total += epoch_total

            # Record to isolated buffer
            self._memory_isolator.write(
                buffer_name,
                network_name,
                {"epoch": epoch, "loss": epoch_loss, "accuracy": epoch_correct / max(epoch_total, 1)},
            )

        avg_loss = total_loss / max(epochs, 1)
        accuracy = correct / max(total, 1)

        logger.info(
            "[Trainer] '{}' trained: loss={:.4f}, accuracy={:.2%}, epochs={}",
            network_name, avg_loss, accuracy, epochs,
        )

        return {"loss": avg_loss, "accuracy": accuracy, "epochs": epochs}

    def train_all(
        self,
        networks: Dict[str, BaseRelationshipNetwork],
        vocab: Dict[str, int],
        type_labels: Dict[str, str],
        epochs: int = 10,
    ) -> Dict[str, Dict[str, float]]:
        """Train all networks sequentially (never in parallel).

        Each network gets a fresh optimizer and isolated training buffer.
        """
        results = {}
        for name, model in networks.items():
            label = type_labels.get(name, "INDEPENDENT")
            results[name] = self.train_network(
                network_name=name,
                model=model,
                vocab=vocab,
                type_label=label,
                epochs=epochs,
            )
        return results

    def save_trained_weights(
        self,
        networks: Dict[str, BaseRelationshipNetwork],
        weights_path: str,
    ) -> None:
        """Save each network's weights to its own directory."""
        from pathlib import Path
        for name, model in networks.items():
            save_dir = Path(weights_path) / name.replace("_network", "")
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / "model.pt"
            torch.save(model.state_dict(), save_path)
            logger.info("[Trainer] Saved weights for '{}' to {}", name, save_path)

    def load_weights(
        self,
        model: BaseRelationshipNetwork,
        weights_path: str,
    ) -> bool:
        """Load weights for a single network. Returns True if successful."""
        from pathlib import Path
        path = Path(weights_path) / "model.pt"
        if path.exists():
            state_dict = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(state_dict)
            return True
        return False



















