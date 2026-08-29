"""
core/relationship_engine/engine.py — Main orchestrator for the Action Relationship Engine.
Loads 7 networks, routes action pairs, validates, explains, and monitors purity.
"""

from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

import torch

from core.relationship_engine.config import RelationshipEngineConfig, RELATIONSHIP_TYPES
from core.relationship_engine.models.base_network import BaseRelationshipNetwork
from core.relationship_engine.models.sequential_network import SequentialNetwork
from core.relationship_engine.models.causal_network import CausalNetwork
from core.relationship_engine.models.conditional_network import ConditionalNetwork
from core.relationship_engine.models.parallel_network import ParallelNetwork
from core.relationship_engine.models.contextual_network import ContextualNetwork
from core.relationship_engine.models.contradictory_network import ContradictoryNetwork
from core.relationship_engine.models.independent_network import IndependentNetwork
from core.relationship_engine.isolation.gradient_blocker import GradientBlocker
from core.relationship_engine.isolation.memory_isolator import MemoryIsolator
from core.relationship_engine.isolation.embedding_isolator import EmbeddingIsolator
from core.relationship_engine.isolation.weight_isolator import WeightIsolator
from core.relationship_engine.routing.hard_router import HardRouter
from core.relationship_engine.explanation.generator import ExplanationGenerator
from core.relationship_engine.explanation.validator import ExplanationValidator
from core.relationship_engine.monitoring.purity_monitor import PurityMonitor
from core.relationship_engine.training.isolated_trainer import IsolatedTrainer
from core.relationship_engine.training.datasets import VOCABULARY


# Type -> Network class mapping
NETWORK_CLASSES = {
    "sequential": SequentialNetwork,
    "causal": CausalNetwork,
    "conditional": ConditionalNetwork,
    "parallel": ParallelNetwork,
    "contextual": ContextualNetwork,
    "contradictory": ContradictoryNetwork,
    "independent": IndependentNetwork,
}


class RelationshipEngine:
    """Main orchestrator for action relationship classification.

    Architecture:
    1. HardRouter routes action pairs via regex (no neural routing)
    2. Type-specific neural network classifies the pair
    3. ExplanationGenerator creates template-based explanation
    4. ExplanationValidator checks for cross-contamination
    5. PurityMonitor watches weight similarity in background
    """

    def __init__(self, config: RelationshipEngineConfig):
        self._config = config
        self._enabled = config.enabled

        if not self._enabled:
            return

        # Build vocabulary
        self._vocab: Dict[str, int] = {"[PAD]": 0, "[UNK]": 1, "[SEP]": 2}
        for i, word in enumerate(VOCABULARY):
            if word not in self._vocab:
                self._vocab[word] = len(self._vocab)

        # Initialize isolation layers
        self._gradient_blocker = GradientBlocker()
        self._memory_isolator = MemoryIsolator()
        self._embedding_isolator = EmbeddingIsolator()
        self._weight_isolator = WeightIsolator()

        # Initialize 7 isolated networks
        net_cfg = config.network_config
        self._networks: Dict[str, BaseRelationshipNetwork] = {}
        self._network_map: Dict[str, str] = {}  # type_label -> network_name

        type_names = ["sequential", "causal", "conditional", "parallel",
                       "contextual", "contradictory", "independent"]

        for type_name in type_names:
            net_class = NETWORK_CLASSES[type_name]
            net_name = f"{type_name}_network"
            model = net_class(
                vocab_size=len(self._vocab),
                embedding_dim=net_cfg.embedding_dim,
                hidden_dim=net_cfg.hidden_dim,
                num_layers=net_cfg.num_layers,
                dropout=net_cfg.dropout,
                max_seq_len=net_cfg.max_seq_len,
            )
            self._networks[net_name] = model
            self._network_map[type_name.upper()] = net_name
            self._embedding_isolator.register_network(net_name)

        # Router
        self._router = HardRouter(keywords=config.keywords)

        # Explanation
        self._explanation_generator = ExplanationGenerator()
        self._explanation_validator = ExplanationValidator()

        # Purity monitor
        self._purity_monitor = PurityMonitor(
            weight_isolator=self._weight_isolator,
            similarity_threshold=config.similarity_threshold,
            check_interval_s=config.purity_check_interval_s,
            on_alert=self._on_purity_alert,
        )

        # Trainer
        self._trainer = IsolatedTrainer(
            memory_isolator=self._memory_isolator,
            gradient_blocker=self._gradient_blocker,
            learning_rate=net_cfg.learning_rate,
            max_seq_len=net_cfg.max_seq_len,
        )

        # State
        self._last_analysis: List[Dict] = []
        self._purity_alerts: List[str] = []

        # Load pre-trained weights if available (after all components are initialized)
        self._load_weights()

        logger.info("[RelationshipEngine] Initialized with {} networks", len(self._networks))

    def _load_weights(self) -> None:
        """Load pre-trained weights for each network from disk."""
        weights_path = Path(self._config.weights_path)
        for net_name, model in self._networks.items():
            type_label = net_name.replace("_network", "")
            model_dir = weights_path / type_label
            model_file = model_dir / "model.pt"
            if model_file.exists():
                try:
                    state_dict = torch.load(model_file, map_location="cpu", weights_only=True)
                    model.load_state_dict(state_dict)
                    logger.debug("[RelationshipEngine] Loaded weights for {}", net_name)
                except Exception as e:
                    logger.warning("[RelationshipEngine] Could not load weights for {}: {}", net_name, e)

        # Capture baseline for purity monitoring
        self._purity_monitor.capture_baseline(self._networks)

    async def start(self) -> None:
        """Start the purity monitor background task."""
        if not self._enabled:
            return
        await self._purity_monitor.start()

    async def stop(self) -> None:
        """Stop the purity monitor."""
        if not self._enabled:
            return
        await self._purity_monitor.stop()

    async def analyze_task_chain(
        self, tasks: List[Any]
    ) -> List[Dict]:
        """Analyze a chain of tasks for pairwise relationships.

        Args:
            tasks: List of Task objects (must have .description attribute).

        Returns:
            List of relationship result dicts.
        """
        if not self._enabled or len(tasks) < 2:
            return []

        results = []
        for i in range(len(tasks) - 1):
            desc_a = getattr(tasks[i], "description", str(tasks[i]))
            desc_b = getattr(tasks[i + 1], "description", str(tasks[i + 1]))
            result = await self.analyze_pair(desc_a, desc_b)
            result["task_a_index"] = i
            result["task_b_index"] = i + 1
            results.append(result)

        self._last_analysis = results
        return results

    async def analyze_pair(
        self,
        action_a: str,
        action_b: str,
    ) -> Dict[str, Any]:
        """Analyze a single pair of actions for their relationship.

        Pipeline:
        1. HardRouter classifies via regex (no neural routing)
        2. Type-specific network scores the pair
        3. ExplanationGenerator creates template explanation
        4. ExplanationValidator checks for contamination

        Returns:
            Dict with keys: type, confidence, keywords, explanation, validated, networks_used
        """
        if not self._enabled:
            return {"type": "INDEPENDENT", "confidence": 0.0, "keywords": [],
                    "explanation": "", "validated": True, "networks_used": []}

        # Step 1: Regex routing (no neural router)
        rel_type, router_confidence, keywords = self._router.route(action_a, action_b)

        # Step 2: Type-specific network scoring
        token_ids = self._encode_pair(action_a, action_b)
        net_name = self._network_map.get(rel_type, "independent_network")
        model = self._networks[net_name]

        with torch.no_grad():
            mask = token_ids != 0
            logit = model(token_ids, mask)
            neural_confidence = torch.sigmoid(logit).item()

        # Combine router and neural confidence
        combined_confidence = 0.4 * router_confidence + 0.6 * neural_confidence

        # Step 3: Generate explanation
        explanation = self._explanation_generator.generate(
            rel_type=rel_type,
            action_a=action_a,
            action_b=action_b,
            keywords=keywords,
            confidence=combined_confidence,
        )

        # Step 4: Validate explanation
        is_valid, issues = self._explanation_validator.validate(explanation, rel_type)
        if not is_valid:
            logger.warning("[RelationshipEngine] Explanation contamination: {}", issues)

        return {
            "type": rel_type,
            "confidence": round(combined_confidence, 4),
            "keywords": keywords,
            "explanation": explanation,
            "validated": is_valid,
            "contamination_issues": issues,
            "networks_used": [net_name],
            "action_a": action_a,
            "action_b": action_b,
        }

    async def explain_relationship(
        self,
        action_a: str,
        action_b: str,
    ) -> Dict[str, Any]:
        """Public API for explaining a relationship between two actions."""
        return await self.analyze_pair(action_a, action_b)

    def _encode_pair(self, action_a: str, action_b: str) -> torch.Tensor:
        """Encode an action pair into token IDs."""
        tokens_a = [self._vocab.get(w.lower(), 1) for w in action_a.split()]
        tokens_b = [self._vocab.get(w.lower(), 1) for w in action_b.split()]
        combined = tokens_a + [2] + tokens_b  # [SEP] between
        max_len = self._config.network_config.max_seq_len
        if len(combined) < max_len:
            combined += [0] * (max_len - len(combined))
        else:
            combined = combined[:max_len]
        return torch.tensor([combined], dtype=torch.long)

    def _on_purity_alert(self, message: str) -> None:
        """Callback for purity monitor alerts."""
        self._purity_alerts.append(message)
        logger.warning("[RelationshipEngine] {}", message)

    # --- Training API ---

    async def train(
        self,
        epochs: int = 10,
        batch_size: int = 8,
    ) -> Dict[str, Dict[str, float]]:
        """Train all networks sequentially with isolated optimizers."""
        if not self._enabled:
            return {}

        type_labels = {
            name: name.replace("_network", "").upper()
            for name in self._networks
        }

        results = self._trainer.train_all(
            networks=self._networks,
            vocab=self._vocab,
            type_labels=type_labels,
            epochs=epochs,
        )

        # Save trained weights
        self._trainer.save_trained_weights(self._networks, self._config.weights_path)

        # Update purity baseline
        self._purity_monitor.capture_baseline(self._networks)

        return results

    # --- Accessors ---

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def last_analysis(self) -> List[Dict]:
        return list(self._last_analysis)

    @property
    def purity_alerts(self) -> List[str]:
        return list(self._purity_alerts)

    def get_network(self, type_name: str) -> Optional[BaseRelationshipNetwork]:
        """Get a specific type's network."""
        net_name = self._network_map.get(type_name.upper())
        if net_name is None:
            return None
        return self._networks.get(net_name)

    def check_purity(self) -> List[str]:
        """Run immediate purity check."""
        return self._purity_monitor.check_now(self._networks)



















