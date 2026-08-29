"""
core/relationship_engine/explanation/validator.py — Cross-contamination checker for explanations.
Validates that explanations use only vocabulary appropriate for their type.
"""

from __future__ import annotations
import re
from typing import Dict, List, Set


# Type-specific allowed vocabulary patterns
TYPE_VOCABULARY: Dict[str, Set[str]] = {
    "SEQUENTIAL": {
        "before", "after", "first", "second", "third", "next", "then",
        "followed", "subsequently", "finally", "lastly", "precedes",
        "succeeds", "order", "sequence", "chain", "step",
    },
    "CAUSAL": {
        "cause", "causes", "caused", "leads", "results", "trigger",
        "triggers", "triggered", "affects", "effect", "consequence",
        "because", "therefore", "thus", "hence", "since", "due",
    },
    "CONDITIONAL": {
        "if", "unless", "provided", "assuming", "condition", "depends",
        "outcome", "satisfied", "met", "contingent", "whether", "case",
    },
    "PARALLEL": {
        "simultaneous", "concurrent", "parallel", "together", "same time",
        "independent", "simultaneously", "concurrently", "both", "alongside",
    },
    "CONTEXTUAL": {
        "context", "related", "regarding", "concerning", "about",
        "respect", "terms", "relevant", "associated", "connected",
    },
    "CONTRADICTORY": {
        "conflict", "contradict", "instead", "however", "opposite",
        "contrary", "overrides", "replaces", "cancels", "negates",
        "but", "yet", "although", "despite", "conflicting",
    },
    "INDEPENDENT": {
        "independent", "unrelated", "separate", "standalone", "distinct",
        "disconnected", "isolated", "no relationship", "any order",
    },
}

# Patterns that indicate contamination (wrong type's vocabulary)
CONTAMINATION_PATTERNS: Dict[str, List[re.Pattern]] = {
    "SEQUENTIAL": [
        re.compile(r"\b(causes?|leads?\s+to|results?\s+in|conflicts?)\b", re.I),
    ],
    "CAUSAL": [
        re.compile(r"\b(precedes?|succeeds?|first|second|third|finally)\b", re.I),
    ],
    "CONDITIONAL": [
        re.compile(r"\b(causes?|precedes?|succeeds?|parallel|simultaneous)\b", re.I),
    ],
    "PARALLEL": [
        re.compile(r"\b(because|therefore|causes?|leads?\s+to|conflicts?|if\s+.*then)\b", re.I),
    ],
    "CONTEXTUAL": [
        re.compile(r"\b(causes?|leads?\s+to|parallel|conflicts?|if\s+.*then|precedes?)\b", re.I),
    ],
    "CONTRADICTORY": [
        re.compile(r"\b(causes?|leads?\s+to|parallel|simultaneous|precedes?|if\s+.*then)\b", re.I),
    ],
    "INDEPENDENT": [
        re.compile(r"\b(causes?|leads?\s+to|conflicts?|parallel|precedes?|if\s+.*then)\b", re.I),
    ],
}


class ExplanationValidator:
    """Validates that explanations don't contain cross-type vocabulary.

    Each relationship type has a set of allowed vocabulary patterns.
    If an explanation for type X contains vocabulary primarily associated
    with type Y, the validator flags it as contaminated.
    """

    def __init__(self):
        self._vocabulary = dict(TYPE_VOCABULARY)
        self._contamination = dict(CONTAMINATION_PATTERNS)

    def validate(
        self,
        explanation: str,
        declared_type: str,
    ) -> tuple[bool, List[str]]:
        """Validate an explanation against its declared type.

        Args:
            explanation: The explanation text to validate.
            declared_type: The type the explanation claims to represent.

        Returns:
            (is_valid, list_of_contamination_issues)
        """
        issues = []
        patterns = self._contamination.get(declared_type, [])

        for pattern in patterns:
            matches = pattern.findall(explanation)
            if matches:
                issues.append(
                    f"Type '{declared_type}' explanation contains "
                    f"contaminating vocabulary: {matches}"
                )

        return len(issues) == 0, issues

    def check_vocabulary(
        self,
        explanation: str,
        declared_type: str,
    ) -> Dict[str, float]:
        """Compute vocabulary overlap with each type's allowed set.

        Returns a dict of type -> overlap_ratio (0.0 to 1.0).
        """
        words = set(re.findall(r"\b\w+\b", explanation.lower()))
        results = {}

        for rel_type, allowed in self._vocabulary.items():
            if not words:
                results[rel_type] = 0.0
                continue
            overlap = len(words & allowed)
            results[rel_type] = overlap / len(words)

        return results

    def get_expected_type(self, explanation: str) -> str:
        """Determine which type best matches the explanation vocabulary.

        Used for automated contamination detection.
        """
        scores = self.check_vocabulary(explanation, "")
        if not scores:
            return "INDEPENDENT"
        return max(scores, key=lambda k: scores[k])



















