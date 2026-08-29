"""
core/relationship_engine/isolation/embedding_isolator.py — Embedding isolation between networks.
Same token must yield different vectors per network. Enforces separate embedding spaces.
"""

from __future__ import annotations
import torch
import torch.nn as nn
from typing import Dict, Optional


class EmbeddingIsolator:
    """Ensures each network maintains a completely isolated embedding space.

    The same token ID produces different embeddings in each network because
    each network has its own nn.Embedding layer with independent weights.
    This isolator tracks and validates that embeddings differ across networks.
    """

    def __init__(self):
        self._embedding_hashes: Dict[str, Dict[int, str]] = {}
        self._token_signatures: Dict[str, Dict[int, torch.Tensor]] = {}

    def register_network(self, network_name: str) -> None:
        """Register a network for embedding isolation tracking."""
        self._embedding_hashes[network_name] = {}
        self._token_signatures[network_name] = {}

    def record_embedding(
        self,
        network_name: str,
        token_id: int,
        embedding: torch.Tensor,
    ) -> None:
        """Record an embedding for a specific network and token.

        The embedding is detached and stored for cross-network comparison.
        """
        if network_name not in self._embedding_hashes:
            raise KeyError(f"Network '{network_name}' not registered")
        emb_detached = embedding.detach().cpu()
        self._token_signatures[network_name][token_id] = emb_detached
        self._embedding_hashes[network_name][token_id] = str(emb_detached.data_ptr())

    def validate_isolation(
        self,
        network_a: str,
        network_b: str,
        token_id: int,
    ) -> bool:
        """Verify that the same token has different embeddings in two networks.

        Returns True if embeddings are isolated (different), False if identical.
        """
        if network_a not in self._token_signatures:
            return True
        if network_b not in self._token_signatures:
            return True
        if token_id not in self._token_signatures[network_a]:
            return True
        if token_id not in self._token_signatures[network_b]:
            return True

        emb_a = self._token_signatures[network_a][token_id]
        emb_b = self._token_signatures[network_b][token_id]

        if emb_a.shape != emb_b.shape:
            return True

        return not torch.equal(emb_a, emb_b)

    def validate_all_isolated(self, token_id: int) -> Dict[tuple, bool]:
        """Check that a token is isolated across ALL registered network pairs."""
        networks = list(self._embedding_hashes.keys())
        results = {}
        for i in range(len(networks)):
            for j in range(i + 1, len(networks)):
                pair = (networks[i], networks[j])
                results[pair] = self.validate_isolation(
                    networks[i], networks[j], token_id
                )
        return results

    def get_embedding(self, network_name: str, token_id: int) -> Optional[torch.Tensor]:
        """Get the recorded embedding for a network+token (for debugging)."""
        if network_name not in self._token_signatures:
            return None
        return self._token_signatures[network_name].get(token_id)



















