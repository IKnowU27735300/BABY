"""
core/relationship_engine/isolation/weight_isolator.py — Weight isolation between networks.
Ensures no shared data_ptr() between any two network weight tensors.
Provides weight signature computation for purity monitoring.
"""

from __future__ import annotations
import hashlib
import torch
from typing import Dict, List, Optional, Tuple


class WeightIsolator:
    """Tracks and validates weight isolation across networks.

    Each network must have completely independent weight tensors with no
    shared data pointers. This isolator computes weight signatures for:
    1. Purity monitoring (similarity detection)
    2. Weight isolation validation
    3. Integrity checks
    """

    def __init__(self):
        self._weight_signatures: Dict[str, str] = {}
        self._weight_checksums: Dict[str, List[str]] = {}

    def compute_signature(self, network_name: str, model: torch.nn.Module) -> str:
        """Compute a hash signature of all model parameters.

        This is a stable hash of the parameter data — same weights produce
        the same signature regardless of which network loaded them.
        """
        hasher = hashlib.sha256()
        for param in model.parameters():
            param_bytes = param.data.cpu().numpy().tobytes()
            hasher.update(param_bytes)
        sig = hasher.hexdigest()[:16]
        self._weight_signatures[network_name] = sig
        return sig

    def compute_per_layer_checksums(
        self, network_name: str, model: torch.nn.Module
    ) -> List[str]:
        """Compute per-layer checksums for fine-grained comparison."""
        checksums = []
        for name, param in model.named_parameters():
            layer_hash = hashlib.sha256(param.data.cpu().numpy().tobytes()).hexdigest()[:8]
            checksums.append(f"{name}:{layer_hash}")
        self._weight_checksums[network_name] = checksums
        return checksums

    def validate_no_shared_data_ptr(
        self,
        model_a: torch.nn.Module,
        model_b: torch.nn.Module,
    ) -> bool:
        """Verify two models have no shared parameter data pointers.

        Returns True if fully isolated, False if any parameter shares memory.
        """
        ptrs_a = set()
        for param in model_a.parameters():
            ptrs_a.add(param.data.data_ptr())

        for param in model_b.parameters():
            if param.data.data_ptr() in ptrs_a:
                return False
        return True

    def compute_similarity(
        self,
        network_a: str,
        network_b: str,
    ) -> float:
        """Compute cosine similarity between two networks' weight signatures.

        This is a fast string-based similarity (not actual weight comparison).
        Used for quick purity checks in the background monitor.
        """
        if network_a not in self._weight_signatures:
            return 0.0
        if network_b not in self._weight_signatures:
            return 0.0

        sig_a = self._weight_signatures[network_a]
        sig_b = self._weight_signatures[network_b]

        if sig_a == sig_b:
            return 1.0

        matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
        return matches / max(len(sig_a), len(sig_b))

    def compute_weight_cosine_similarity(
        self,
        model_a: torch.nn.Module,
        model_b: torch.nn.Module,
    ) -> float:
        """Compute actual cosine similarity between flattened weight vectors.

        This is the heavy-weight comparison used when precise similarity is needed.
        """
        vec_a = torch.cat([p.data.flatten() for p in model_a.parameters()])
        vec_b = torch.cat([p.data.flatten() for p in model_b.parameters()])

        if vec_a.numel() != vec_b.numel():
            return 0.0

        cos_sim = torch.nn.functional.cosine_similarity(
            vec_a.unsqueeze(0), vec_b.unsqueeze(0)
        )
        return cos_sim.item()

    def get_signature(self, network_name: str) -> Optional[str]:
        """Get stored signature for a network."""
        return self._weight_signatures.get(network_name)

    def get_all_signatures(self) -> Dict[str, str]:
        """Get all stored signatures."""
        return dict(self._weight_signatures)



















