"""
tests/test_relationship_engine/test_isolation.py — Verify isolation guarantees.
"""

import sys
import os
import pytest
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.relationship_engine.isolation.gradient_blocker import GradientBlocker
from core.relationship_engine.isolation.memory_isolator import MemoryIsolator
from core.relationship_engine.isolation.embedding_isolator import EmbeddingIsolator
from core.relationship_engine.isolation.weight_isolator import WeightIsolator
from core.relationship_engine.models.sequential_network import SequentialNetwork
from core.relationship_engine.models.causal_network import CausalNetwork


class TestGradientBlocker:
    def test_detach_input(self):
        blocker = GradientBlocker()
        x = torch.randn(3, requires_grad=True)
        y = blocker.detach_input(x)
        assert y.requires_grad is False
        assert y.data_ptr() != x.data_ptr() or torch.equal(x, y)

    def test_detach_inputs(self):
        blocker = GradientBlocker()
        tensors = [torch.randn(3, requires_grad=True) for _ in range(5)]
        detached = blocker.detach_inputs(tensors)
        assert all(t.requires_grad is False for t in detached)

    def test_validate_no_shared_grad(self):
        blocker = GradientBlocker()
        a = torch.randn(3)
        b = torch.randn(3)
        assert blocker.validate_no_shared_grad(a, b) is True

    def test_block_gradient_flow(self):
        blocker = GradientBlocker()
        source = torch.randn(3, requires_grad=True)
        target = torch.randn(3, requires_grad=True)
        result = blocker.block_gradient_flow(source, target)
        assert result.requires_grad is False


class TestMemoryIsolator:
    def test_create_buffer(self):
        iso = MemoryIsolator()
        iso.create_buffer("test_buffer", "network_a")
        assert "test_buffer" in iso.list_buffers()

    def test_write_read_own_buffer(self):
        iso = MemoryIsolator()
        iso.create_buffer("buf1", "net_a")
        iso.write("buf1", "net_a", {"data": 42})
        data = iso.read("buf1", "net_a")
        assert len(data) == 1
        assert data[0]["data"] == 42

    def test_cross_network_read_blocked(self):
        iso = MemoryIsolator()
        iso.create_buffer("buf2", "net_a")
        iso.write("buf2", "net_a", {"data": 1})
        with pytest.raises(PermissionError):
            iso.read("buf2", "net_b")

    def test_cross_network_write_blocked(self):
        iso = MemoryIsolator()
        iso.create_buffer("buf3", "net_a")
        with pytest.raises(PermissionError):
            iso.write("buf3", "net_b", {"data": 2})

    def test_cross_read_explicit_block(self):
        iso = MemoryIsolator()
        iso.create_buffer("buf4", "net_a")
        with pytest.raises(PermissionError):
            iso.read_cross("buf4", "net_b")

    def test_buffer_not_found(self):
        iso = MemoryIsolator()
        with pytest.raises(KeyError):
            iso.read("nonexistent", "net_a")


class TestEmbeddingIsolator:
    def test_register_and_record(self):
        iso = EmbeddingIsolator()
        iso.register_network("net_a")
        emb = torch.randn(10)
        iso.record_embedding("net_a", 1, emb)
        assert iso.get_embedding("net_a", 1) is not None

    def test_validate_isolation_different(self):
        iso = EmbeddingIsolator()
        iso.register_network("net_a")
        iso.register_network("net_b")
        iso.record_embedding("net_a", 1, torch.randn(10))
        iso.record_embedding("net_b", 1, torch.randn(10))
        assert iso.validate_isolation("net_a", "net_b", 1) is True

    def test_validate_isolation_same_fails(self):
        iso = EmbeddingIsolator()
        iso.register_network("net_a")
        iso.register_network("net_b")
        emb = torch.randn(10)
        iso.record_embedding("net_a", 1, emb)
        iso.record_embedding("net_b", 1, emb.clone())
        # Same values = not isolated
        assert iso.validate_isolation("net_a", "net_b", 1) is False

    def test_unregistered_network(self):
        iso = EmbeddingIsolator()
        assert iso.validate_isolation("net_a", "net_b", 1) is True


class TestWeightIsolator:
    def test_compute_signature(self):
        iso = WeightIsolator()
        model = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        sig = iso.compute_signature("seq", model)
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_validate_no_shared_data_ptr(self):
        iso = WeightIsolator()
        model_a = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        model_b = CausalNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        assert iso.validate_no_shared_data_ptr(model_a, model_b) is True

    def test_same_model_shares_data_ptr(self):
        iso = WeightIsolator()
        model = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        # Same model instance shares data pointers (expected behavior)
        assert iso.validate_no_shared_data_ptr(model, model) is False

    def test_compute_similarity_identical(self):
        iso = WeightIsolator()
        model = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        iso.compute_signature("net_a", model)
        iso.compute_signature("net_b", model)
        sim = iso.compute_similarity("net_a", "net_b")
        assert sim == 1.0

    def test_compute_weight_cosine_similarity(self):
        iso = WeightIsolator()
        model_a = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        model_b = CausalNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        sim = iso.compute_weight_cosine_similarity(model_a, model_b)
        # Cosine similarity can be negative for random weights
        assert -1.0 <= sim <= 1.0



















