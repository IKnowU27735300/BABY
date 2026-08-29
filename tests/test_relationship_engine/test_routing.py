"""
tests/test_relationship_engine/test_routing — Verify regex routing priority and classification.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.relationship_engine.routing.hard_router import HardRouter, ROUTING_PRIORITY


class TestHardRouter:
    def setup_method(self):
        self.router = HardRouter()

    def test_sequential_detection(self):
        rel_type, conf, kws = self.router.route("open the file", "then read it")
        assert rel_type == "SEQUENTIAL"
        assert conf > 0.5
        assert "then" in kws

    def test_causal_detection(self):
        rel_type, conf, kws = self.router.route("delete the cache", "because the app reloads")
        assert rel_type == "CAUSAL"
        assert "because" in kws

    def test_conditional_detection(self):
        rel_type, conf, kws = self.router.route("if the file exists", "read it")
        assert rel_type == "CONDITIONAL"
        assert "if" in kws

    def test_parallel_detection(self):
        rel_type, conf, kws = self.router.route("open the browser", "simultaneously start music")
        assert rel_type == "PARALLEL"
        assert "simultaneously" in kws

    def test_contradictory_detection(self):
        rel_type, conf, kws = self.router.route("save the file", "but delete it instead")
        assert rel_type == "CONTRADICTORY"
        assert "but" in kws or "instead" in kws

    def test_independent_default(self):
        rel_type, conf, kws = self.router.route("check the weather", "open calculator")
        assert rel_type == "INDEPENDENT"

    def test_priority_conditional_over_sequential(self):
        # "if" should trigger CONDITIONAL before SEQUENTIAL
        rel_type, conf, kws = self.router.route("if the server is up", "then deploy")
        assert rel_type == "CONDITIONAL"

    def test_priority_contradictory_over_causal(self):
        # "instead" should trigger CONTRADICTORY before CAUSAL
        rel_type, conf, kws = self.router.route("start the server", "instead stop it")
        assert rel_type == "CONTRADICTORY"

    def test_batch_routing(self):
        pairs = [
            ("open file", "then read it"),
            ("delete cache", "because app reloads"),
            ("check weather", "open calculator"),
        ]
        results = self.router.route_batch(pairs)
        assert len(results) == 3
        assert results[0][0] == "SEQUENTIAL"
        assert results[1][0] == "CAUSAL"
        assert results[2][0] == "INDEPENDENT"

    def test_update_keywords(self):
        self.router.update_keywords("SEQUENTIAL", ["afterwards"])
        rel_type, conf, kws = self.router.route("open file", "afterwards read it")
        assert "afterwards" in kws

    def test_get_keywords(self):
        kws = self.router.get_keywords("SEQUENTIAL")
        assert isinstance(kws, list)
        assert len(kws) > 0

    def test_priority_order_matches_config(self):
        assert ROUTING_PRIORITY == [
            "CONDITIONAL",
            "CONTRADICTORY",
            "CAUSAL",
            "SEQUENTIAL",
            "PARALLEL",
            "CONTEXTUAL",
            "INDEPENDENT",
        ]



















