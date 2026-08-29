"""
core/relationship_engine/routing/hard_router.py — Regex-only priority routing.
No neural routing. Routes action pairs to the correct type-specific network
using keyword matching with strict priority ordering.
"""

from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple

from core.relationship_engine.config import RELATIONSHIP_TYPES, DEFAULT_KEYWORDS


# Priority order: CONDITIONAL > CONTRADICTORY > CAUSAL > SEQUENTIAL > PARALLEL > CONTEXTUAL > INDEPENDENT
ROUTING_PRIORITY = [
    "CONDITIONAL",
    "CONTRADICTORY",
    "CAUSAL",
    "SEQUENTIAL",
    "PARALLEL",
    "CONTEXTUAL",
    "INDEPENDENT",
]


class HardRouter:
    """Regex-only router that maps action pairs to relationship types.

    No neural components. Pure keyword matching with priority ordering.
    Higher-priority types are checked first. First match wins.
    """

    def __init__(self, keywords: Optional[Dict[str, List[str]]] = None):
        self._keywords = keywords or dict(DEFAULT_KEYWORDS)
        self._compiled: Dict[str, List[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for each type."""
        for rel_type, kw_list in self._keywords.items():
            patterns = []
            for kw in kw_list:
                escaped = re.escape(kw)
                patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
            self._compiled[rel_type] = patterns

    def route(self, text_a: str, text_b: str) -> Tuple[str, float, List[str]]:
        """Route a pair of action descriptions to a relationship type.

        Args:
            text_a: First action description.
            text_b: Second action description.

        Returns:
            (relationship_type, confidence, matched_keywords)
            confidence is 0.0-1.0 based on number of keyword matches.
        """
        combined = f"{text_a} {text_b}".lower()

        for rel_type in ROUTING_PRIORITY:
            if rel_type not in self._compiled:
                continue
            matches = []
            for pattern in self._compiled[rel_type]:
                if pattern.search(combined):
                    matches.append(pattern.pattern.replace(r"\b", "").replace("\\", ""))

            if matches:
                confidence = min(1.0, 0.5 + 0.1 * len(matches))
                return rel_type, confidence, matches

        return "INDEPENDENT", 0.6, []

    def route_batch(
        self, pairs: List[Tuple[str, str]]
    ) -> List[Tuple[str, float, List[str]]]:
        """Route multiple pairs efficiently."""
        return [self.route(a, b) for a, b in pairs]

    def update_keywords(self, rel_type: str, new_keywords: List[str]) -> None:
        """Add new keywords for a relationship type and recompile."""
        if rel_type not in self._keywords:
            raise ValueError(f"Unknown relationship type: {rel_type}")
        self._keywords[rel_type].extend(new_keywords)
        patterns = []
        for kw in new_keywords:
            escaped = re.escape(kw)
            patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
        self._compiled[rel_type].extend(patterns)

    def get_keywords(self, rel_type: str) -> List[str]:
        """Get all keywords for a type."""
        return list(self._keywords.get(rel_type, []))

    def get_all_keywords(self) -> Dict[str, List[str]]:
        """Get all keywords for all types."""
        return {k: list(v) for k, v in self._keywords.items()}



















