"""Background task queue for running multi-step plans without blocking the conversation."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from loguru import logger


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    id: str
    description: str
    state: TaskState = TaskState.PENDING
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    progress: str = ""


class BackgroundTaskQueue:
    """Manages background tasks that run without blocking the conversation loop."""

    def __init__(self, max_concurrent: int = 2):
        self._tasks: dict[str, BackgroundTask] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._on_complete_callbacks: list[Callable[[BackgroundTask], Coroutine]] = []

    def on_complete(self, callback: Callable[[BackgroundTask], Coroutine]):
        """Register a callback for when any task completes."""
        self._on_complete_callbacks.append(callback)

    async def submit(
        self,
        coro_factory: Callable[[], Coroutine],
        description: str = "",
    ) -> str:
        """Submit a coroutine to run in the background. Returns task ID."""
        task_id = f"bg_{uuid.uuid4().hex[:8]}"
        bg_task = BackgroundTask(id=task_id, description=description)
        self._tasks[task_id] = bg_task

        asyncio.create_task(self._run(task_id, coro_factory))
        logger.info("[BgQueue] Submitted task {}: {}", task_id, description)
        return task_id

    async def _run(self, task_id: str, coro_factory: Callable[[], Coroutine]):
        bg = self._tasks[task_id]
        async with self._semaphore:
            bg.state = TaskState.RUNNING
            bg.started_at = time.time()
            try:
                result = await coro_factory()
                bg.result = result
                bg.state = TaskState.COMPLETED
            except asyncio.CancelledError:
                bg.state = TaskState.CANCELLED
                bg.error = "Cancelled"
            except Exception as e:
                bg.state = TaskState.FAILED
                bg.error = str(e)
                logger.error("[BgQueue] Task {} failed: {}", task_id, e)
            finally:
                bg.finished_at = time.time()
                elapsed = (bg.finished_at - bg.started_at) if bg.started_at else 0
                logger.info(
                    "[BgQueue] Task {} → {} ({:.1f}s)",
                    task_id, bg.state.value, elapsed,
                )
                for cb in self._on_complete_callbacks:
                    try:
                        await cb(bg)
                    except Exception as e:
                        logger.debug(f"[BgQueue] Callback error for task {task_id}: {e}")

    def get(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def get_running(self) -> list[BackgroundTask]:
        return [t for t in self._tasks.values() if t.state == TaskState.RUNNING]

    def get_recent(self, limit: int = 5) -> list[BackgroundTask]:
        sorted_tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return sorted_tasks[:limit]

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending/running task."""
        # Note: actual cancellation requires the asyncio.Task reference
        bg = self._tasks.get(task_id)
        if bg and bg.state in (TaskState.PENDING, TaskState.RUNNING):
            bg.state = TaskState.CANCELLED
            bg.error = "Cancelled by user"
            return True
        return False



















