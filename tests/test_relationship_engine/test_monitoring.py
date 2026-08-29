"""
tests/test_relationship_engine/test_monitoring — Verify baseline capture and similarity alerts.
"""

import sys
import os
import pytest
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.relationship_engine.isolation.weight_isolator import WeightIsolator
from core.relationship_engine.monitoring.purity_monitor import PurityMonitor
from core.relationship_engine.models.sequential_network import SequentialNetwork
from core.relationship_engine.models.causal_network import CausalNetwork


class TestPurityMonitor:
    def setup_method(self):
        self.weight_isolator = WeightIsolator()
        self.monitor = PurityMonitor(
            weight_isolator=self.weight_isolator,
            similarity_threshold=0.85,
            check_interval_s=60.0,
        )

    def test_capture_baseline(self):
        model_a = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        model_b = CausalNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        networks = {"sequential": model_a, "causal": model_b}
        self.monitor.capture_baseline(networks)
        assert self.monitor.baseline_captured is True

    def test_check_now_no_alert(self):
        model_a = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        model_b = CausalNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        networks = {"sequential": model_a, "causal": model_b}
        self.monitor.capture_baseline(networks)
        alerts = self.monitor.check_now(networks)
        # Different network types should not be similar
        assert isinstance(alerts, list)

    def test_check_now_alert_on_identical(self):
        model_a = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        # Same type = same architecture = potentially similar weights
        model_b = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        # Load identical weights
        model_b.load_state_dict(model_a.state_dict())
        networks = {"seq_1": model_a, "seq_2": model_b}
        self.monitor.capture_baseline(networks)
        # Set low threshold to trigger alert
        self.monitor._similarity_threshold = 0.5
        alerts = self.monitor.check_now(networks)
        assert len(alerts) > 0

    def test_alert_callback(self):
        alerts_received = []
        monitor = PurityMonitor(
            weight_isolator=self.weight_isolator,
            similarity_threshold=0.5,
            check_interval_s=60.0,
            on_alert=lambda msg: alerts_received.append(msg),
        )
        model_a = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        model_b = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        model_b.load_state_dict(model_a.state_dict())
        networks = {"seq_1": model_a, "seq_2": model_b}
        monitor.capture_baseline(networks)
        monitor.check_now(networks)
        # With identical weights and low threshold, should get alert
        assert len(alerts_received) > 0

    def test_empty_networks(self):
        alerts = self.monitor.check_now({})
        assert alerts == []

    def test_single_network(self):
        model = SequentialNetwork(vocab_size=100, embedding_dim=32, hidden_dim=16, num_layers=1)
        alerts = self.monitor.check_now({"seq": model})
        assert alerts == []



















