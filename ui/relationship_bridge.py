"""
ui/relationship_bridge.py — QObject bridge for Relationship Engine UI.
Exposes signals and slots for QML to display relationship results.
"""

from __future__ import annotations
from typing import Any, Dict, List

from PySide6.QtCore import QObject, Signal, Slot


class RelationshipBridge(QObject):
    """QML↔Python bridge for the Action Relationship Engine.

    Signals emit relationship results, purity alerts, and training status.
    Slots receive user feedback and trigger analyses.
    """

    # Signals
    relationshipsReady = Signal(list)
    relationshipAnalyzed = Signal(str, str, str, float, str)  # type, actionA, actionB, confidence, explanation
    purityAlert = Signal(str)
    trainingComplete = Signal(str)  # JSON results
    relationshipError = Signal(str)
    engineStatusChanged = Signal(bool)  # enabled/disabled

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._last_results: List[Dict] = []

    @Slot(list)
    def on_relationships_ready(self, results: list) -> None:
        """Slot called when relationship analysis completes for a task chain."""
        self._last_results = results
        self.relationshipsReady.emit(results)

    @Slot(str, str, str, float, str)
    def on_relationship_analyzed(
        self,
        rel_type: str,
        action_a: str,
        action_b: str,
        confidence: float,
        explanation: str,
    ) -> None:
        """Slot called when a single pair analysis completes."""
        self.relationshipAnalyzed.emit(rel_type, action_a, action_b, confidence, explanation)

    @Slot(str)
    def on_purity_alert(self, message: str) -> None:
        """Slot called when purity monitor detects high similarity."""
        self.purityAlert.emit(message)

    @Slot(str)
    def on_training_complete(self, results_json: str) -> None:
        """Slot called when training completes."""
        self.trainingComplete.emit(results_json)

    @Slot(str)
    def on_relationship_error(self, error: str) -> None:
        """Slot called on error."""
        self.relationshipError.emit(error)

    @Slot(bool)
    def on_engine_status_changed(self, enabled: bool) -> None:
        """Slot called when engine is enabled/disabled."""
        self._enabled = enabled
        self.engineStatusChanged.emit(enabled)

    @Slot(result=list)
    def getLastResults(self) -> list:
        """QML-callable getter for last analysis results."""
        return self._last_results

    @Slot(result=bool)
    def isEnabled(self) -> bool:
        """QML-callable getter for engine status."""
        return self._enabled



















