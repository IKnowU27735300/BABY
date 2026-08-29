"""
Task Manager — CRUD for the hive task ledger with dependency tracking.

Provides higher-level operations on top of HiveManager's task storage,
including dependency resolution, priority sorting, and stage-based execution.
"""

import time
import logging
from typing import Optional
from collections import defaultdict

from hive.hive_manager import get_hive, Task

logger = logging.getLogger("Baby.hive.tasks")


class TaskManager:
    """High-level task management for the hive."""

    def __init__(self):
        self._hive = get_hive()

    def create(self, title: str, description: str = "", assignee: str = "",
               dependencies: list[str] | None = None, priority: int = 0) -> Task:
        task = Task(
            title=title,
            description=description,
            assignee=assignee,
            dependencies=dependencies or [],
            priority=priority,
        )
        return self._hive.create_task(task)

    def update(self, task_id: str, **kwargs) -> Optional[dict]:
        return self._hive.update_task(task_id, kwargs)

    def complete(self, task_id: str) -> Optional[dict]:
        return self._hive.complete_task(task_id)

    def get(self, task_id: str) -> Optional[dict]:
        return self._hive.get_task(task_id)

    def list_by_status(self, status: str) -> list[dict]:
        return self._hive.list_tasks(status=status)

    def list_by_assignee(self, assignee: str) -> list[dict]:
        return self._hive.list_tasks(assignee=assignee)

    def get_ready(self) -> list[dict]:
        """Get tasks whose dependencies are satisfied, sorted by priority."""
        tasks = self._hive.get_ready_tasks()
        return sorted(tasks, key=lambda t: -t.get("priority", 0))

    def get_execution_stages(self) -> list[list[dict]]:
        """Topological sort of tasks into execution stages (DAG levels)."""
        tasks = self._hive._load_tasks()
        if not tasks:
            return []

        task_map = {t["id"]: t for t in tasks}
        in_degree = {t["id"]: len(t["dependencies"]) for t in tasks}
        stages = []

        while True:
            # Find all tasks with zero in-degree
            ready = [
                task_map[tid] for tid, deg in in_degree.items()
                if deg == 0 and tid in task_map
            ]
            if not ready:
                break

            # Sort by priority within stage
            ready.sort(key=lambda t: -t.get("priority", 0))
            stages.append(ready)

            # Remove these tasks and decrement dependents
            ready_ids = {t["id"] for t in ready}
            for tid in ready_ids:
                del in_degree[tid]
            for tid in list(in_degree.keys()):
                if tid in task_map:
                    in_degree[tid] = sum(
                        1 for d in task_map[tid]["dependencies"]
                        if d not in ready_ids and d in in_degree
                    )

        return stages

    def propagate_failure(self, failed_task_id: str):
        """Mark all downstream tasks as blocked when a dependency fails."""
        tasks = self._hive._load_tasks()
        changed = True
        while changed:
            changed = False
            for t in tasks:
                if t["status"] == "todo" and failed_task_id in t["dependencies"]:
                    t["status"] = "blocked"
                    t["updated_at"] = time.time()
                    changed = True
        self._hive._save_tasks(tasks)
        logger.info("[Tasks] Propagated failure from task {}", failed_task_id)

    def get_dependency_chain(self, task_id: str) -> list[str]:
        """Get the full dependency chain for a task."""
        tasks = self._hive._load_tasks()
        task_map = {t["id"]: t for t in tasks}
        visited = set()
        chain = []

        def _walk(tid):
            if tid in visited or tid not in task_map:
                return
            visited.add(tid)
            for dep in task_map[tid].get("dependencies", []):
                _walk(dep)
            chain.append(tid)

        _walk(task_id)
        return chain

    def get_stats(self) -> dict:
        """Get task statistics."""
        tasks = self._hive._load_tasks()
        by_status = defaultdict(int)
        for t in tasks:
            by_status[t["status"]] += 1
        return {
            "total": len(tasks),
            "todo": by_status["todo"],
            "doing": by_status["doing"],
            "blocked": by_status["blocked"],
            "done": by_status["done"],
        }



















