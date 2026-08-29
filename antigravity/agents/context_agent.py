"""
antigravity/agents/context_agent.py — Context & Memory Sub-Agent.

Handles: storing and retrieving user preferences, past interactions,
         session summaries, and named user facts.

Uses a lightweight SQLite store (no heavy vector DB required).
Can be upgraded to FAISS for semantic search later.
"""

from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

from antigravity.base_agent import BaseAgent
from antigravity.goal_tracker import Task, TaskStatus

# ─── SQLite Memory Store ──────────────────────────────────────────────────────

_DB_PATH = Path("data/ag_memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    category  TEXT    NOT NULL DEFAULT 'general',
    key       TEXT    NOT NULL,
    value     TEXT    NOT NULL,
    timestamp TEXT    NOT NULL,
    speaker   TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category);
"""


def _get_conn() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _run_query(fn):
    """Execute fn(conn), commit, and ALWAYS close the connection."""
    conn = _get_conn()
    try:
        result = fn(conn)
        conn.commit()
        return result
    finally:
        conn.close()


# ─── Tool functions ────────────────────────────────────────────────────────────

def _store_memory(key: str, value: str, category: str = "general", speaker: str = "") -> dict:
    try:
        def fn(conn):
            conn.execute(
                "INSERT INTO memories (category, key, value, timestamp, speaker) VALUES (?,?,?,?,?)",
                (category, key, value, datetime.now().isoformat(), speaker),
            )
        _run_query(fn)
        return {"success": True, "message": f"Stored memory: {key} = {value}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _recall_memory(key: str, category: str = "") -> dict:
    try:
        def fn(conn):
            if category:
                return conn.execute(
                    "SELECT key, value, timestamp FROM memories WHERE key LIKE ? AND category=? ORDER BY timestamp DESC LIMIT 5",
                    (f"%{key}%", category),
                ).fetchall()
            return conn.execute(
                "SELECT key, value, timestamp FROM memories WHERE key LIKE ? ORDER BY timestamp DESC LIMIT 5",
                (f"%{key}%",),
            ).fetchall()
        rows = _run_query(fn)
        if rows:
            results = [{"key": r[0], "value": r[1], "when": r[2]} for r in rows]
            return {"success": True, "memories": results, "message": f"Found {len(rows)} memory/memories."}
        return {"success": True, "memories": [], "message": f"No memories found for: {key}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _list_memories(category: str = "general", limit: int = 10) -> dict:
    try:
        def fn(conn):
            return conn.execute(
                "SELECT key, value, timestamp FROM memories WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        rows = _run_query(fn)
        memories = [{"key": r[0], "value": r[1], "when": r[2]} for r in rows]
        return {"success": True, "memories": memories, "message": f"{len(memories)} stored memories."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _clear_memory(category: str = "general") -> dict:
    try:
        def fn(conn):
            conn.execute("DELETE FROM memories WHERE category=?", (category,))
        _run_query(fn)
        return {"success": True, "message": f"Cleared memories in category: {category}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Tool registry ────────────────────────────────────────────────────────────

CONTEXT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "memory_store",
            "description": "Store a key-value fact in BABY's long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key":      {"type": "string", "description": "The fact name/label."},
                    "value":    {"type": "string", "description": "The fact value to store."},
                    "category": {"type": "string", "description": "Category bucket. Default: 'general'."},
                    "speaker":  {"type": "string", "description": "Name of the person this memory is about."},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": "Recall stored facts matching a key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key":      {"type": "string", "description": "Search term to match against memory keys."},
                    "category": {"type": "string", "description": "Optional category filter."},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "List all stored memories in a category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "limit":    {"type": "integer", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_clear",
            "description": "Clear stored memories in a specified category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category to clear. Default: 'general'"},
                },
                "required": [],
            },
        },
    },
]

CONTEXT_TOOL_RISK = {t["function"]["name"]: "low" for t in CONTEXT_TOOLS_SCHEMA if isinstance(t, dict) and isinstance(t.get("function"), dict)}


def execute_context_tool(name: str, args: dict) -> dict:
    if name == "memory_store":
        return _store_memory(
            key=args.get("key", ""),
            value=args.get("value", ""),
            category=args.get("category", "general"),
            speaker=args.get("speaker", ""),
        )
    elif name == "memory_recall":
        return _recall_memory(key=args.get("key", ""), category=args.get("category", ""))
    elif name == "memory_list":
        return _list_memories(category=args.get("category", "general"), limit=args.get("limit", 10))
    elif name == "memory_clear":
        return _clear_memory(category=args.get("category", "general"))
    return {"success": False, "error": f"Unknown context tool: {name}"}


# ─── Agent class ──────────────────────────────────────────────────────────────

class ContextAgent(BaseAgent):
    name        = "context"
    description = "Manages long-term memory: stores and retrieves user facts and preferences."

    async def run(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        results = []

        try:
            for tool_call in task.tools:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})

                logger.info("[ContextAgent] Executing tool='{}' args={}", tool_name, tool_args)
                result = execute_context_tool(tool_name, tool_args)
                logger.info("[ContextAgent] Result: {}", result)
                results.append(result)

            has_error = any(isinstance(r, dict) and r.get("error") for r in results)

            if has_error:
                task.status = TaskStatus.FAILED
                task.error  = self._format_result(results)
            else:
                task.status = TaskStatus.DONE
                task.raw_results = results
                task.result = self._format_result(results)

        except Exception as e:
            logger.error("[ContextAgent] Unexpected error: {}", e)
            task.status = TaskStatus.FAILED
            task.error  = str(e)

        return task



















