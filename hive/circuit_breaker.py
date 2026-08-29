"""
Circuit Breaker — Safety mechanism for agent loops and runaway operations.

Monitors consecutive errors, duplicate tool calls, output velocity,
and optionally cost caps. Enforces a ladder: steer -> constrain -> kill.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("Baby.hive.breaker")


@dataclass
class CircuitBreakerConfig:
    max_consecutive_errors: int = 5
    max_consecutive_dupes: int = 3
    max_output_tokens_per_min: int = 10000
    cost_cap_usd: float = 0.0       # 0 = disabled
    window_seconds: float = 60.0
    enabled: bool = True


@dataclass
class BreakerState:
    consecutive_errors: int = 0
    consecutive_dupes: int = 0
    last_tool_call: str = ""
    token_timestamps: deque = field(default_factory=lambda: deque(maxlen=200))
    total_cost: float = 0.0
    tripped: bool = False
    trip_reason: str = ""


class CircuitBreaker:
    """Safety ladder for agent operations."""

    LADDER = ["ok", "steer", "constrain", "kill"]

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._states: dict[str, BreakerState] = {}

    def _get_state(self, agent_id: str) -> BreakerState:
        if agent_id not in self._states:
            self._states[agent_id] = BreakerState()
        return self._states[agent_id]

    def record_tool_call(self, agent_id: str, tool_name: str, tool_input: str = "") -> str:
        """Record a tool call and return the breaker status."""
        if not self.config.enabled:
            return "ok"
        state = self._get_state(agent_id)

        # Check consecutive dupes
        call_sig = f"{tool_name}:{tool_input}"
        if call_sig == state.last_tool_call:
            state.consecutive_dupes += 1
        else:
            state.consecutive_dupes = 0
        state.last_tool_call = call_sig

        if state.consecutive_dupes >= self.config.max_consecutive_dupes:
            return self._trip(agent_id, state, "consecutive_duplicate_calls")

        return "ok"

    def record_error(self, agent_id: str, error_type: str = "") -> str:
        """Record an error and return the breaker status."""
        if not self.config.enabled:
            return "ok"
        state = self._get_state(agent_id)
        state.consecutive_errors += 1

        if state.consecutive_errors >= self.config.max_consecutive_errors:
            return self._trip(agent_id, state, "consecutive_errors")

        return "ok"

    def record_success(self, agent_id: str):
        """Reset error counter on success."""
        state = self._get_state(agent_id)
        state.consecutive_errors = 0

    def record_tokens(self, agent_id: str, token_count: int, cost_usd: float = 0.0) -> str:
        """Record token usage and check velocity/cost."""
        if not self.config.enabled:
            return "ok"
        state = self._get_state(agent_id)
        now = time.time()

        state.token_timestamps.append((now, token_count))
        state.total_cost += cost_usd

        # Prune old entries
        cutoff = now - self.config.window_seconds
        while state.token_timestamps and state.token_timestamps[0][0] < cutoff:
            state.token_timestamps.popleft()

        # Check velocity
        tokens_in_window = sum(t for _, t in state.token_timestamps)
        if tokens_in_window > self.config.max_output_tokens_per_min:
            return self._trip(agent_id, state, "output_token_velocity")

        # Check cost
        if self.config.cost_cap_usd > 0 and state.total_cost >= self.config.cost_cap_usd:
            return self._trip(agent_id, state, "cost_cap_exceeded")

        return "ok"

    def _trip(self, agent_id: str, state: BreakerState, reason: str) -> str:
        state.tripped = True
        state.trip_reason = reason
        logger.warning("[CircuitBreaker] TRIPPED for {}: {}", agent_id, reason)

        # Determine ladder level based on severity
        if reason in ("consecutive_duplicate_calls", "consecutive_errors"):
            return "steer"
        elif reason == "output_token_velocity":
            return "constrain"
        elif reason == "cost_cap_exceeded":
            return "kill"
        return "steer"

    def reset(self, agent_id: str):
        """Manually reset breaker for an agent."""
        self._states[agent_id] = BreakerState()
        logger.info("[CircuitBreaker] Reset for {}", agent_id)

    def is_tripped(self, agent_id: str) -> bool:
        state = self._get_state(agent_id)
        return state.tripped

    def get_status(self, agent_id: str) -> dict:
        state = self._get_state(agent_id)
        tokens_in_window = sum(t for _, t in state.token_timestamps)
        return {
            "tripped": state.tripped,
            "trip_reason": state.trip_reason,
            "consecutive_errors": state.consecutive_errors,
            "consecutive_dupes": state.consecutive_dupes,
            "tokens_in_window": tokens_in_window,
            "total_cost": state.total_cost,
        }

    def get_all_status(self) -> dict[str, dict]:
        return {aid: self.get_status(aid) for aid in self._states}



















