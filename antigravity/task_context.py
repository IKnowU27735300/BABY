"""
antigravity/task_context.py — Runtime state and dynamic parameter resolution for multi-task DAG execution.
"""

from __future__ import annotations
import re
from typing import Any
from loguru import logger


class TaskExecutionContext:
    """
    Stores intermediate outputs of executed DAG task nodes and resolves dynamic
    bindings/placeholders in downstream task arguments.

    Example placeholders in tool arguments:
      - "$task_1" or "$task_1.result" -> value of task_1's result
      - "$task_1.filepath" or "$task_1.result.filepath" -> nested dictionary lookup
      - "${task_1.result}" -> string template format
    """

    def __init__(self):
        self._results: dict[str, Any] = {}

    def store_result(self, task_id: str, result: Any, raw_result: Any = None):
        """Store the output of a completed task node."""
        self._results[task_id] = raw_result if raw_result is not None else result
        logger.debug("[TaskContext] Stored result for task '{}': {}", task_id, self._results[task_id])

    def get_result(self, task_id: str) -> Any:
        return self._results.get(task_id)

    def resolve_value(self, val: Any) -> Any:
        """Recursively resolve dynamic variable references in strings, dicts, or lists."""
        if isinstance(val, str):
            return self._resolve_string_binding(val)
        elif isinstance(val, dict):
            return {k: self.resolve_value(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [self.resolve_value(item) for item in val]
        return val

    def _resolve_string_binding(self, text: str) -> Any:
        # 1. Exact variable match: "$task_1.result" or "$task_1.result.key"
        exact_pattern = r"^\$([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*)$"
        exact_match = re.match(exact_pattern, text.strip())
        if exact_match:
            path = exact_match.group(1).split(".")
            resolved = self._lookup_path(path)
            if resolved is not None:
                return resolved

        # 2. Template string match: "Found file: ${task_1.result}"
        def replace_match(match: re.Match) -> str:
            path_str = match.group(1)
            path = path_str.split(".")
            val = self._lookup_path(path)
            return str(val) if val is not None else match.group(0)

        template_pattern = r"\$\{([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*)\}"
        return re.sub(template_pattern, replace_match, text)

    def _lookup_path(self, path: list[str]) -> Any:
        if not path:
            return None

        task_id = path[0]
        if task_id not in self._results:
            return None

        cur = self._results[task_id]
        remaining = path[1:]

        # If cur is a string containing JSON, attempt to parse it
        if isinstance(cur, str):
            s = cur.strip()
            if s.startswith(("{", "[")):
                try:
                    import json
                    cur = json.loads(s)
                except Exception:
                    pass

        # If the first attribute in path is "result", check if "result" is an explicit key/attr in cur;
        # if not, skip "result" since cur is already the stored result object.
        if remaining and remaining[0] == "result":
            if isinstance(cur, dict) and "result" not in cur:
                remaining = remaining[1:]
            elif not isinstance(cur, dict) and not hasattr(cur, "result"):
                remaining = remaining[1:]

        for key in remaining:
            if isinstance(cur, list) and cur:
                if key.isdigit():
                    idx = int(key)
                    if 0 <= idx < len(cur):
                        cur = cur[idx]
                        continue
                    else:
                        return None
                elif isinstance(cur[0], dict) and key in cur[0]:
                    cur = cur[0][key]
                    continue
                elif hasattr(cur[0], key):
                    cur = getattr(cur[0], key)
                    continue

            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            elif hasattr(cur, key):
                cur = getattr(cur, key)
            else:
                return None
        return cur

    def clear(self):
        self._results.clear()



















