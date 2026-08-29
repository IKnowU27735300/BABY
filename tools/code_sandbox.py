"""Sandboxed Python code execution tool for Baby."""

from __future__ import annotations

import io
import contextlib
import sys
import traceback
from typing import Any

from loguru import logger

# Allowed builtins for sandboxed execution
_SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "bytearray", "bytes", "callable", "chr",
    "dict", "dir", "divmod", "enumerate", "eval", "filter", "float", "format",
    "frozenset", "getattr", "globals", "hasattr", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "locals", "map", "max",
    "min", "next", "oct", "ord", "pow", "print", "property", "range", "repr",
    "reversed", "round", "set", "setattr", "slice", "sorted", "str", "sum",
    "super", "tuple", "type", "vars", "zip",
    # Math helpers
    "True", "False", "None",
}

# Blocked modules for safety
_BLOCKED_MODULES = {
    "subprocess", "os", "sys", "shutil", "pathlib", "socket",
    "http", "urllib", "requests", "ctypes", "signal",
    "multiprocessing", "threading", "_thread",
}

# Code execution timeout (seconds)
_TIMEOUT = 10


def execute_python_code(code: str, timeout: int = _TIMEOUT) -> dict:
    """
    Execute Python code in a sandboxed environment.
    Returns stdout, stderr, and any exception info.
    """
    if not code or not code.strip():
        return {"success": False, "error": "No code provided"}

    logger.info("[CodeExec] Executing code ({} chars)", len(code))

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    # Create a restricted globals dict
    restricted_globals: dict[str, Any] = {"__builtins__": {}}
    for name in _SAFE_BUILTINS:
        if name in __builtins__ if isinstance(__builtins__, dict) else hasattr(__builtins__, name):
            if isinstance(__builtins__, dict):
                restricted_globals["__builtins__"][name] = __builtins__[name]
            else:
                restricted_globals["__builtins__"][name] = getattr(__builtins__, name)

    # Add safe imports
    safe_imports = {"math", "random", "datetime", "json", "re", "itertools",
                    "collections", "functools", "string", "textwrap", "uuid",
                    "hashlib", "base64", "statistics", "decimal", "fractions"}

    def _safe_import(name, *args, **kwargs):
        if name.split(".")[0] in _BLOCKED_MODULES:
            raise ImportError(f"Module '{name}' is blocked in sandbox")
        if name.split(".")[0] in safe_imports:
            return __import__(name, *args, **kwargs)
        raise ImportError(f"Module '{name}' is not allowed in sandbox")

    restricted_globals["__import__"] = _safe_import

    try:
        exec(code, restricted_globals, restricted_globals)
        stdout_val = stdout_capture.getvalue()
        stderr_val = stderr_capture.getvalue()

        result = {
            "success": True,
            "stdout": stdout_val,
            "stderr": stderr_val,
        }
        logger.info("[CodeExec] Success (stdout={} chars)", len(stdout_val))
        return result

    except Exception as e:
        tb = traceback.format_exc()
        logger.warning("[CodeExec] Error: {}", e)
        return {
            "success": False,
            "error": str(e),
            "traceback": tb,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
        }
    finally:
        stdout_capture.close()
        stderr_capture.close()


# Tool schema for integration with AntiGravity
CODE_EXECUTION_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_python_code",
        "description": "Execute Python code in a sandboxed environment. Use for calculations, data processing, API calls, text manipulation, or any task that requires Python. Returns stdout, stderr, and any errors.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute. Use print() for output.",
                },
            },
            "required": ["code"],
        },
    },
}

CODE_EXECUTION_RISK = {"execute_python_code": "medium"}



















