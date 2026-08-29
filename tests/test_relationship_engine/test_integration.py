"""
tests/test_relationship_engine/test_integration — End-to-end pipeline, training isolation, batch processing.
"""

import sys
import os
import pytest
import asyncio
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.relationship_engine.config import RelationshipEngineConfig
from core.relationship_engine.engine import RelationshipEngine
from core.relationship_engine.isolation.memory_isolator import MemoryIsolator
from core.relationship_engine.isolation.gradient_blocker import GradientBlocker
from core.relationship_engine.training.isolated_trainer import IsolatedTrainer
from core.relationship_engine.training.datasets import SYNTHETIC_DATASET, VOCABULARY


class TestRelationshipEngineIntegration:
    def setup_method(self):
        self.config = RelationshipEngineConfig(
            enabled=True,
            weights_path="data/relationship_weights",
            similarity_threshold=0.85,
        )
        self.engine = RelationshipEngine(self.config)

    def test_engine_initialization(self):
        assert self.engine.enabled is True
        assert len(self.engine._networks) == 7

    def test_analyze_pair_sequential(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.engine.analyze_pair("open the file", "then read it")
        )
        assert result["type"] == "SEQUENTIAL"
        assert result["confidence"] > 0
        assert len(result["explanation"]) > 0
        assert result["validated"] is True

    def test_analyze_pair_causal(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.engine.analyze_pair("delete the cache", "because the app reloads")
        )
        assert result["type"] == "CAUSAL"
        assert "because" in result["keywords"]

    def test_analyze_pair_contradictory(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.engine.analyze_pair("save the file", "but delete it")
        )
        assert result["type"] == "CONTRADICTORY"

    def test_analyze_pair_independent(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.engine.analyze_pair("check the weather", "open the calculator")
        )
        assert result["type"] == "INDEPENDENT"

    def test_analyze_task_chain(self):
        class MockTask:
            def __init__(self, desc):
                self.description = desc
        tasks = [MockTask("open file"), MockTask("then read it"), MockTask("close file")]
        results = asyncio.get_event_loop().run_until_complete(
            self.engine.analyze_task_chain(tasks)
        )
        assert len(results) == 2  # pairs: (0,1) and (1,2)
        assert results[0]["type"] == "SEQUENTIAL"

    def test_explain_relationship(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.engine.explain_relationship("click submit", "form gets submitted")
        )
        assert "type" in result
        assert "explanation" in result

    def test_disabled_engine(self):
        config = RelationshipEngineConfig(enabled=False)
        engine = RelationshipEngine(config)
        assert engine.enabled is False
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_pair("a", "b")
        )
        assert result["type"] == "INDEPENDENT"
        assert result["confidence"] == 0.0

    def test_batch_analysis(self):
        pairs = [
            ("open file", "then read it"),
            ("delete cache", "because app reloads"),
            ("check weather", "open calculator"),
        ]
        async def run_batch():
            return [await self.engine.analyze_pair(a, b) for a, b in pairs]
        results = asyncio.get_event_loop().run_until_complete(run_batch())
        assert len(results) == 3
        types = [r["type"] for r in results]
        assert "SEQUENTIAL" in types
        assert "CAUSAL" in types


class TestTrainingIsolation:
    def setup_method(self):
        self.memory_isolator = MemoryIsolator()
        self.gradient_blocker = GradientBlocker()
        self.trainer = IsolatedTrainer(
            memory_isolator=self.memory_isolator,
            gradient_blocker=self.gradient_blocker,
            learning_rate=1e-3,
            max_seq_len=64,
        )

    def test_train_single_network(self):
        from core.relationship_engine.models.sequential_network import SequentialNetwork
        vocab = {w: i + 3 for i, w in enumerate(VOCABULARY[:100])}
        vocab["[PAD]"] = 0
        vocab["[UNK]"] = 1
        vocab["[SEP]"] = 2

        model = SequentialNetwork(vocab_size=len(vocab), embedding_dim=32, hidden_dim=16, num_layers=1)
        result = self.trainer.train_network(
            network_name="sequential_network",
            model=model,
            vocab=vocab,
            type_label="SEQUENTIAL",
            epochs=2,
            batch_size=4,
        )
        assert result["epochs"] == 2
        assert result["loss"] >= 0

    def test_training_creates_isolated_buffer(self):
        from core.relationship_engine.models.sequential_network import SequentialNetwork
        vocab = {w: i + 3 for i, w in enumerate(VOCABULARY[:100])}
        vocab["[PAD]"] = 0
        vocab["[UNK]"] = 1
        vocab["[SEP]"] = 2

        model = SequentialNetwork(vocab_size=len(vocab), embedding_dim=32, hidden_dim=16, num_layers=1)
        self.trainer.train_network(
            network_name="test_net",
            model=model,
            vocab=vocab,
            type_label="SEQUENTIAL",
            epochs=1,
            batch_size=4,
        )
        # Buffer should exist
        buffers = self.memory_isolator.list_buffers()
        assert "test_net_training_buffer" in buffers

    def test_cross_network_buffer_access_blocked(self):
        self.memory_isolator.create_buffer("net_a_buffer", "net_a")
        self.memory_isolator.write("net_a_buffer", "net_a", {"data": 1})
        with pytest.raises(PermissionError):
            self.memory_isolator.read("net_a_buffer", "net_b")


class TestDatasets:
    def test_synthetic_dataset_structure(self):
        assert len(SYNTHETIC_DATASET) > 0
        for item in SYNTHETIC_DATASET:
            assert len(item) == 4
            assert item[2] in ["SEQUENTIAL", "CAUSAL", "CONDITIONAL", "PARALLEL",
                                "CONTEXTUAL", "CONTRADICTORY", "INDEPENDENT"]

    def test_vocabulary(self):
        assert len(VOCABULARY) > 100
        assert "then" in VOCABULARY
        assert "because" in VOCABULARY
        assert "if" in VOCABULARY



















