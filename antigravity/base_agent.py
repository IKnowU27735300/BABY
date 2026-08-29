"""
antigravity/base_agent.py — Abstract contract every sub-agent must satisfy.
"""

from __future__ import annotations
import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from antigravity.goal_tracker import Task


class BaseAgent(abc.ABC):
    """
    All Anti-Gravity sub-agents inherit from this class.
    They receive a Task, execute it, mutate task.result / task.status,
    and return the task back to the Admin.
    """

    name:        str = "base"
    description: str = "Abstract agent"

    @abc.abstractmethod
    async def run(self, task: "Task") -> "Task":
        """
        Execute the task.
        Must set task.status to DONE or FAILED.
        Must set task.result (string summary) on success.
        Must set task.error on failure.
        """
        ...

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _format_result(results: list) -> str:
        """Flatten a list of tool result dicts to a human-readable string."""
        parts = []
        for r in results:
            if isinstance(r, dict):
                if r.get("error"):
                    parts.append(f"Error: {r['error']}")
                elif r.get("success"):
                    message = r.get("message")
                    if message:
                        parts.append(str(message))
                    else:
                        # Surface the useful payload (cpu_percent, path, count, ...)
                        payload = {k: v for k, v in r.items()
                                   if k not in ("success", "message") and v is not None}
                        parts.append(str(payload) if payload else "Done.")
                else:
                    parts.append(str(r))
            else:
                parts.append(str(r))
        return " | ".join(parts) if parts else "No results."



















