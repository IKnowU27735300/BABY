"""
Completion Watcher — Detects when dispatched tasks complete.

Polls task status and agent inbox for completion signals, enabling
the voice system to announce when work is done.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from hive.hive_manager import get_hive

logger = logging.getLogger("Baby.hive.watcher")


@dataclass
class PendingWatch:
    task_id: str
    agent_id: str
    started_at: float
    timeout_ms: float = 300000  # 5 min default
    callback: Optional[Callable] = None


@dataclass
class CompletionResult:
    completed: bool
    task_id: str = ""
    agent_id: str = ""
    source: str = ""   # "task_done" or "inbox_reply"
    summary: str = ""


class CompletionWatcher:
    """Polls for task completion and emits events."""

    def __init__(self, poll_interval: float = 4.0):
        self._poll_interval = poll_interval
        self._hive = get_hive()
        self._pending: dict[str, PendingWatch] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._queue: list[CompletionResult] = []

    def on_completion(self, callback: Callable):
        self._callbacks.append(callback)

    def watch(self, task_id: str, agent_id: str, timeout_ms: float = 300000,
              callback: Optional[Callable] = None):
        self._pending[task_id] = PendingWatch(
            task_id=task_id, agent_id=agent_id,
            started_at=time.time(), timeout_ms=timeout_ms,
            callback=callback,
        )
        logger.info("[Watcher] Watching task {} for agent {}", task_id, agent_id)

    def unwatch(self, task_id: str):
        self._pending.pop(task_id, None)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hive-watcher")
        self._thread.start()
        logger.info("[Watcher] Started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._check_completions()
            except Exception as e:
                logger.debug("[Watcher] Check tick: {}", e)
            time.sleep(self._poll_interval)

    def _check_completions(self):
        now = time.time()
        completed = []

        for task_id, watch in list(self._pending.items()):
            # Check timeout
            if (now - watch.started_at) * 1000 > watch.timeout_ms:
                result = CompletionResult(
                    completed=False, task_id=task_id,
                    agent_id=watch.agent_id, source="timeout",
                    summary="Task timed out",
                )
                self._emit(result)
                completed.append(task_id)
                continue

            # Check task status
            task = self._hive.get_task(task_id)
            if task and task["status"] == "done":
                result = CompletionResult(
                    completed=True, task_id=task_id,
                    agent_id=watch.agent_id, source="task_done",
                    summary=f"Task '{task.get('title', task_id)}' completed",
                )
                self._emit(result)
                completed.append(task_id)

        for tid in completed:
            self._pending.pop(tid, None)

    def _emit(self, result: CompletionResult):
        self._queue.append(result)
        for cb in self._callbacks:
            try:
                cb(result)
            except Exception as e:
                logger.debug("[Watcher] Callback error: {}", e)

    def drain_queue(self) -> list[CompletionResult]:
        results = list(self._queue)
        self._queue.clear()
        return results

    def get_pending(self) -> list[dict]:
        return [
            {"task_id": w.task_id, "agent_id": w.agent_id,
             "elapsed_ms": (time.time() - w.started_at) * 1000,
             "timeout_ms": w.timeout_ms}
            for w in self._pending.values()
        ]



















