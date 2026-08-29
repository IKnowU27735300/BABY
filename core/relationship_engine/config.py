"""
core/relationship_engine/config.py — Configuration for the Action Relationship Engine.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


RELATIONSHIP_TYPES = [
    "SEQUENTIAL",
    "CAUSAL",
    "CONDITIONAL",
    "PARALLEL",
    "CONTEXTUAL",
    "CONTRADICTORY",
    "INDEPENDENT",
]

DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "SEQUENTIAL": ["then", "after", "afterwards", "next", "followed by", "subsequently", "first", "second", "third", "finally", "lastly", "before", "once", "when done"],
    "CAUSAL": ["because", "caused", "leads to", "results in", "therefore", "thus", "hence", "since", "due to", "as a result", "consequently", "so that", "trigger", "affects"],
    "CONDITIONAL": ["if", "unless", "provided that", "assuming", "when", "whenever", "in case", "should", "given that", "on condition", "contingent", "depending on"],
    "PARALLEL": ["simultaneously", "at the same time", "concurrently", "in parallel", "together", "while", "meanwhile", "alongside", "both", "and also", "as well as"],
    "CONTEXTUAL": ["regarding", "in the context of", "related to", "concerning", "about", "with respect to", "in terms of", "speaking of", "related", "relevant to"],
    "CONTRADICTORY": ["but", "however", "instead", "rather", "contrary to", "opposite of", "conflicts with", "overrides", "replaces", "cancels", "negates", "contradicts"],
    "INDEPENDENT": ["separate", "unrelated", "independent", "standalone", "separately", "on its own", "distinct", "disconnected", "isolated"],
}


@dataclass
class NetworkConfig:
    """Per-network hyperparameters."""
    embedding_dim: int = 256
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.1
    learning_rate: float = 1e-3
    max_seq_len: int = 64


@dataclass
class RelationshipEngineConfig:
    """Top-level config for the relationship engine."""
    enabled: bool = True
    weights_path: str = "data/relationship_weights"
    similarity_threshold: float = 0.85
    embedding_dim: int = 256
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.1
    learning_rate: float = 1e-3
    explain_by_default: bool = False
    purity_check_interval_s: float = 300.0
    keywords: Dict[str, List[str]] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    network_config: NetworkConfig = field(default_factory=NetworkConfig)



















