"""
tests/test_relationship_engine/test_explanation — Verify template generation and contamination detection.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.relationship_engine.explanation.generator import ExplanationGenerator
from core.relationship_engine.explanation.validator import ExplanationValidator


class TestExplanationGenerator:
    def setup_method(self):
        self.gen = ExplanationGenerator()

    def test_generate_sequential(self):
        exp = self.gen.generate("SEQUENTIAL", "open file", "read file", ["then"], 0.9)
        assert "then" in exp
        assert len(exp) > 0

    def test_generate_causal(self):
        exp = self.gen.generate("CAUSAL", "click button", "form submits", ["because"], 0.85)
        assert "because" in exp
        assert len(exp) > 0

    def test_generate_conditional(self):
        exp = self.gen.generate("CONDITIONAL", "check exists", "read it", ["if"], 0.9)
        assert "if" in exp

    def test_generate_parallel(self):
        exp = self.gen.generate("PARALLEL", "open browser", "start music", ["simultaneously"], 0.8)
        assert "simultaneously" in exp

    def test_generate_contradictory(self):
        exp = self.gen.generate("CONTRADICTORY", "save file", "delete file", ["but"], 0.9)
        assert "but" in exp

    def test_generate_independent(self):
        exp = self.gen.generate("INDEPENDENT", "check weather", "open calc", [], 0.6)
        assert len(exp) > 0

    def test_generate_detailed(self):
        exp = self.gen.generate("SEQUENTIAL", "open file", "read file", ["then"], 0.9, detailed=True)
        assert "open file" in exp
        assert "read file" in exp

    def test_generate_keyword_based(self):
        exp = self.gen.generate("CAUSAL", "click", "submit", ["leads to"], 0.8)
        assert "leads to" in exp

    def test_generate_batch(self):
        results = [
            {"type": "SEQUENTIAL", "action_a": "a", "action_b": "b", "keywords": ["then"], "confidence": 0.9},
            {"type": "CAUSAL", "action_a": "c", "action_b": "d", "keywords": ["because"], "confidence": 0.8},
        ]
        exps = self.gen.generate_batch(results)
        assert len(exps) == 2

    def test_get_template(self):
        t = self.gen.get_template("SEQUENTIAL", "default")
        assert isinstance(t, str)
        assert len(t) > 0


class TestExplanationValidator:
    def setup_method(self):
        self.validator = ExplanationValidator()

    def test_valid_sequential_explanation(self):
        exp = "Action A must be completed before Action B begins."
        is_valid, issues = self.validator.validate(exp, "SEQUENTIAL")
        assert is_valid is True
        assert len(issues) == 0

    def test_contaminated_sequential(self):
        # SEQUENTIAL explanation containing CAUSAL vocabulary
        exp = "Action A causes Action B to happen, leading to results."
        is_valid, issues = self.validator.validate(exp, "SEQUENTIAL")
        assert is_valid is False
        assert len(issues) > 0

    def test_valid_contradictory_explanation(self):
        exp = "Actions A and B conflict with each other."
        is_valid, issues = self.validator.validate(exp, "CONTRADICTORY")
        assert is_valid is True

    def test_check_vocabulary(self):
        scores = self.validator.check_vocabulary("before after first second", "SEQUENTIAL")
        assert scores["SEQUENTIAL"] > 0

    def test_get_expected_type(self):
        t = self.validator.get_expected_type("because causes leads to results")
        assert t == "CAUSAL"

    def test_valid_independent(self):
        exp = "Actions A and B are unrelated and can execute in any order."
        is_valid, issues = self.validator.validate(exp, "INDEPENDENT")
        assert is_valid is True



















