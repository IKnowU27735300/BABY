"""
antigravity/goal_tracker.py — Data structures for the Anti-Gravity planner.
GoalPlan, Task, and GoalTracker drive the Orchestrator's retry/satisfaction loop.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from loguru import logger


class AgentType(str, Enum):
    SYSTEM      = "system"      # File ops, app launch, process control
    BROWSER     = "browser"     # Web nav, search, form fill
    VISION      = "vision"      # Screen capture, OCR, coords
    CONTEXT     = "context"     # Memory, prefs, history retrieval
    CONVERSATION = "conversation"  # Pure chat — no tools needed
    LEARN       = "learn"       # Autonomous skill acquisition via RAG


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE    = "done"
    FAILED  = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """A single atomic unit of work to be executed by one sub-agent."""
    description: str
    agent_type:  AgentType
    tools:       list[dict] = field(default_factory=list)      # [{name, args}]
    risk_level:  str        = "low"                             # low | medium | high
    requires_consent: bool  = False

    # DAG & Data Flow
    depends_on:     list[str]  = field(default_factory=list)   # IDs or names of parent tasks
    input_bindings: dict       = field(default_factory=dict)   # {arg_name: "$task_id.result"}
    fault_policy:   str        = "CONTINUE"                    # CONTINUE | SKIP_DEPENDENTS | ABORT_ALL

    # Relationship Engine
    relationship_to_parent: str | None = None
    relationship_explanation: str | None = None

    # Runtime state
    id:          str        = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status:      TaskStatus = TaskStatus.PENDING
    result:      Any        = None
    raw_results: list       = field(default_factory=list)  # Raw dicts from each tool call
    error:       str | None = None
    retries:     int        = 0
    max_retries: int        = 2


@dataclass
class GoalPlan:
    """The complete multi-task DAG plan the Anti-Gravity Planner produces for one user utterance."""
    original_request: str
    intent:           str
    tasks:            list[Task] = field(default_factory=list)
    final_summary:    str        = ""
    is_satisfied:     bool       = False
    user_lang:        str        = "en"
    relationships:    list[dict] = field(default_factory=list)

    # ── Convenience helpers & DAG Scheduler ──────────────────────────────────

    @property
    def pending_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    @property
    def failed_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    @property
    def all_done(self) -> bool:
        return all(t.status in (TaskStatus.DONE, TaskStatus.SKIPPED) for t in self.tasks)

    def mark_satisfied(self, summary: str):
        self.is_satisfied = True
        self.final_summary = summary

    def get_task_by_id(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.id == task_id or t.description == task_id:
                return t
        return None

    def should_skip_due_to_dependency_failure(self, task: Task) -> bool:
        """Return True if any upstream task this task depends on failed or was skipped."""
        for parent_ref in task.depends_on:
            parent = self.get_task_by_id(parent_ref)
            if parent and parent.status in (TaskStatus.FAILED, TaskStatus.SKIPPED):
                return True
        return False

    def get_execution_stages(self) -> list[list[Task]]:
        """
        Topological sorting using Levelized DAG Partitioning.
        Returns a list of stages, where each stage is a list of tasks that can run in parallel.
        """
        if not self.tasks:
            return []

        # Map of task_id -> task
        id_map = {t.id: t for t in self.tasks}
        # Also map index/description as fallbacks if LLM used index "1", "2" or description
        for idx, t in enumerate(self.tasks, start=1):
            id_map[str(idx)] = t
            id_map[t.description] = t

        # In-degree computation
        in_degree: dict[str, int] = {t.id: 0 for t in self.tasks}
        graph: dict[str, list[str]] = {t.id: [] for t in self.tasks}

        for t in self.tasks:
            for dep in t.depends_on:
                parent = id_map.get(str(dep))
                if parent and parent.id != t.id:
                    graph[parent.id].append(t.id)
                    in_degree[t.id] += 1

        stages: list[list[Task]] = []
        visited_count = 0

        # Queue of nodes with 0 in-degree
        current_stage_ids = [t.id for t in self.tasks if in_degree[t.id] == 0]

        while current_stage_ids:
            stage_tasks = [id_map[tid] for tid in current_stage_ids]
            stages.append(stage_tasks)
            visited_count += len(current_stage_ids)

            next_stage_ids = []
            for tid in current_stage_ids:
                for neighbor_id in graph[tid]:
                    in_degree[neighbor_id] -= 1
                    if in_degree[neighbor_id] == 0:
                        next_stage_ids.append(neighbor_id)
            current_stage_ids = next_stage_ids

        # If cycle or invalid DAG, fallback to sequential stages
        if visited_count < len(self.tasks):
            logger.warning("[GoalPlan] Cycle detected or invalid dependencies in task graph. Falling back to sequential execution.")
            return [[t] for t in self.tasks]

        return stages


class GoalTracker:
    """
    Keeps one GoalPlan alive and handles re-planning on partial failure.
    The Admin feeds this tracker; it decides when a goal is "satisfied".
    """

    def __init__(self, max_replan_cycles: int = 3):
        self._max_cycles = max_replan_cycles
        self._cycle      = 0
        self.current_plan: GoalPlan | None = None

    def start(self, plan: GoalPlan):
        self._cycle = 0
        self.current_plan = plan

    def is_done(self) -> bool:
        if self.current_plan is None:
            return True
        return self.current_plan.is_satisfied or self.current_plan.all_done

    def should_replan(self) -> bool:
        if self.current_plan is None:
            return False
        has_failures = bool(self.current_plan.failed_tasks)
        under_limit  = self._cycle < self._max_cycles
        return has_failures and under_limit and not self.current_plan.is_satisfied

    def increment_cycle(self):
        self._cycle += 1

    def reset(self):
        self.current_plan = None
        self._cycle = 0



















