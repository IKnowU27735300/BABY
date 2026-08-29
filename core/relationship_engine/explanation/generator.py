"""
core/relationship_engine/explanation/generator.py — Template-based explanation generator.
Explanations are generated from templates, never from neural output.
"""

from __future__ import annotations
from typing import Dict, List, Optional


EXPLANATION_TEMPLATES: Dict[str, Dict[str, str]] = {
    "SEQUENTIAL": {
        "default": "Action A must be completed before Action B begins.",
        "keyword_based": "Because '{kw}' was detected, Action A precedes Action B.",
        "detailed": "These actions have a sequential dependency: Action A ({a}) must execute first, followed by Action B ({b}).",
    },
    "CAUSAL": {
        "default": "Action A causes or leads to Action B.",
        "keyword_based": "The keyword '{kw}' indicates that Action A causes Action B.",
        "detailed": "There is a causal relationship: Action A ({a}) directly causes or triggers Action B ({b}).",
    },
    "CONDITIONAL": {
        "default": "Action B depends on the outcome of Action A.",
        "keyword_based": "The condition '{kw}' means Action B only proceeds if Action A's outcome is met.",
        "detailed": "Action B ({b}) is conditional on Action A ({a}) — it only executes if the condition is satisfied.",
    },
    "PARALLEL": {
        "default": "Actions A and B can execute simultaneously.",
        "keyword_based": "The term '{kw}' indicates these actions can run in parallel.",
        "detailed": "Actions A ({a}) and B ({b}) are independent and can execute concurrently.",
    },
    "CONTEXTUAL": {
        "default": "Action B is contextually related to Action A.",
        "keyword_based": "The phrase '{kw}' links Action B to the context of Action A.",
        "detailed": "Action B ({b}) operates in the context established by Action A ({a}).",
    },
    "CONTRADICTORY": {
        "default": "Actions A and B conflict with each other.",
        "keyword_based": "The word '{kw}' signals a contradiction between the actions.",
        "detailed": "Actions A ({a}) and B ({b}) are contradictory — executing both may cause errors or unexpected behavior.",
    },
    "INDEPENDENT": {
        "default": "Actions A and B are unrelated and can execute in any order.",
        "keyword_based": "No relationship keywords found; actions appear independent.",
        "detailed": "Actions A ({a}) and B ({b}) have no detected relationship and can execute in any order.",
    },
}


class ExplanationGenerator:
    """Generates human-readable explanations from templates.

    All explanations are template-based. The neural network provides
    a classification score, but the explanation text is always deterministic
    based on the type and matched keywords.
    """

    def __init__(self, templates: Optional[Dict[str, Dict[str, str]]] = None):
        self._templates = templates or dict(EXPLANATION_TEMPLATES)

    def generate(
        self,
        rel_type: str,
        action_a: str,
        action_b: str,
        keywords: List[str],
        confidence: float,
        detailed: bool = False,
    ) -> str:
        """Generate an explanation for a classified relationship.

        Args:
            rel_type: One of the 7 relationship types.
            action_a: Description of first action.
            action_b: Description of second action.
            keywords: Matched routing keywords.
            confidence: Classification confidence (0.0-1.0).
            detailed: If True, use the detailed template.

        Returns:
            Human-readable explanation string.
        """
        templates = self._templates.get(rel_type, self._templates["INDEPENDENT"])

        if detailed:
            template = templates.get("detailed", templates["default"])
        elif keywords:
            template = templates.get("keyword_based", templates["default"])
        else:
            template = templates["default"]

        keyword_str = keywords[0] if keywords else "unknown"
        return template.format(
            a=action_a[:100],
            b=action_b[:100],
            kw=keyword_str,
        )

    def generate_batch(
        self,
        results: List[Dict],
    ) -> List[str]:
        """Generate explanations for multiple classification results."""
        return [
            self.generate(
                rel_type=r["type"],
                action_a=r.get("action_a", ""),
                action_b=r.get("action_b", ""),
                keywords=r.get("keywords", []),
                confidence=r.get("confidence", 0.0),
                detailed=r.get("detailed", False),
            )
            for r in results
        ]

    def get_template(self, rel_type: str, variant: str = "default") -> str:
        """Get a specific template for inspection/testing."""
        return self._templates.get(rel_type, {}).get(variant, "")



















