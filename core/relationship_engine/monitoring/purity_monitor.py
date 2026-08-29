"""
core/relationship_engine/monitoring/purity_monitor.py — Background purity monitoring.
Alerts if weight signature similarity between any two networks exceeds threshold.
"""

from __future__ import annotations
import asyncio
import time
from typing import Any, Callable, Dict, List, Optional
from loguru import logger

from core.relationship_engine.isolation.weight_isolator import WeightIsolator


class PurityMonitor:
    """Background task that monitors weight purity across networks.

    Periodically computes weight signatures and checks that no two
    networks have drifted too similar (default threshold: 85%).

    Raises alerts via callback when contamination is detected.
    """

    def __init__(
        self,
        weight_isolator: WeightIsolator,
        similarity_threshold: float = 0.85,
        check_interval_s: float = 300.0,
        on_alert: Optional[Callable[[str], None]] = None,
    ):
        self._weight_isolator = weight_isolator
        self._similarity_threshold = similarity_threshold
        self._check_interval_s = check_interval_s
        self._on_alert = on_alert
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_signatures: Dict[str, str] = {}
        self._baseline_captured = False

    def capture_baseline(self, networks: Dict[str, Any]) -> None:
        """Capture initial weight signatures for all networks.

        Call this after loading/initializing all 7 networks.
        """
        for name, model in networks.items():
            self._weight_isolator.compute_signature(name, model)  # type: ignore[arg-type]
        self._last_signatures = dict(self._weight_isolator.get_all_signatures())
        self._baseline_captured = True
        logger.info("[PurityMonitor] Baseline captured for {} networks", len(networks))

    async def start(self) -> None:
        """Start the background purity checking loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[PurityMonitor] Started (interval={}s)", self._check_interval_s)

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[PurityMonitor] Stopped")

    async def _monitor_loop(self) -> None:
        """Background loop that checks purity periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval_s)
                self._check_purity()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[PurityMonitor] Check error: {}", e)

    def _check_purity(self) -> None:
        """Compute pairwise similarities and alert if any exceed threshold."""
        current_sigs = dict(self._weight_isolator.get_all_signatures())
        network_names = list(current_sigs.keys())

        if len(network_names) < 2:
            return

        alerts = []
        for i in range(len(network_names)):
            for j in range(i + 1, len(network_names)):
                name_a = network_names[i]
                name_b = network_names[j]
                sig_a = current_sigs.get(name_a, "")
                sig_b = current_sigs.get(name_b, "")

                if not sig_a or not sig_b:
                    continue

                similarity = self._weight_isolator.compute_similarity(name_a, name_b)
                if similarity >= self._similarity_threshold:
                    msg = (
                        f"PURITY ALERT: Networks '{name_a}' and '{name_b}' "
                        f"have {similarity:.1%} weight similarity "
                        f"(threshold: {self._similarity_threshold:.0%})"
                    )
                    alerts.append(msg)
                    logger.warning("[PurityMonitor] {}", msg)

        self._last_signatures = current_sigs

        if alerts and self._on_alert:
            combined = "\n".join(alerts)
            self._on_alert(combined)

    def check_now(self, networks: Dict[str, Any]) -> List[str]:
        """Run an immediate purity check and return any alerts."""
        for name, model in networks.items():
            self._weight_isolator.compute_signature(name, model)  # type: ignore[arg-type]

        alerts = []
        current_sigs = dict(self._weight_isolator.get_all_signatures())
        network_names = list(current_sigs.keys())

        for i in range(len(network_names)):
            for j in range(i + 1, len(network_names)):
                name_a = network_names[i]
                name_b = network_names[j]
                similarity = self._weight_isolator.compute_similarity(name_a, name_b)
                if similarity >= self._similarity_threshold:
                    alerts.append(
                        f"{name_a} <-> {name_b}: {similarity:.1%} similar"
                    )

        if alerts and self._on_alert:
            combined = "\n".join(alerts)
            self._on_alert(combined)

        return alerts

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def baseline_captured(self) -> bool:
        return self._baseline_captured



















