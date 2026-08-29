"""
core/ollama_wizard.py — Automated Ollama Pre-flight Setup Wizard.

Ensures:
  1. Ollama server is running locally (launches `ollama serve` if not running).
  2. Required LLM model (e.g. `llama3.1:8b`) is pulled and ready.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.config import BabyConfig


def is_ollama_installed() -> bool:
    """Check if Ollama executable is on system PATH."""
    return shutil.which("ollama") is not None


def start_ollama_server(wait_seconds: int = 8) -> bool:
    """Launch `ollama serve` as a background process and wait for port readiness."""
    if not is_ollama_installed():
        logger.warning("[OllamaWizard] 'ollama' executable not found on system PATH.")
        return False

    logger.info("[OllamaWizard] Launching background Ollama server ('ollama serve')...")
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )

        # Wait for service to bind to localhost:11434
        import ollama
        client = ollama.Client()
        for attempt in range(wait_seconds):
            time.sleep(1.0)
            try:
                client.list()
                logger.success("[OllamaWizard] Background Ollama server started successfully ✓")
                return True
            except Exception:
                pass
    except Exception as e:
        logger.error("[OllamaWizard] Failed to start Ollama server: {}", e)

    return False


def ensure_model_pulled(client, model_name: str, config: BabyConfig | None = None) -> bool:
    """Check if model_name is downloaded in Ollama; pull automatically if missing.
    Falls back to any installed model if target pull fails.
    """
    try:
        models_res = client.list()
        existing_models = []

        # Handle different response structures across ollama-python versions
        raw_list = getattr(models_res, "models", models_res)
        if isinstance(raw_list, list):
            for m in raw_list:
                name = getattr(m, "model", None) or getattr(m, "name", None) or str(m)
                existing_models.append(name)
        elif isinstance(raw_list, dict):
            for m in raw_list.get("models", []):
                name = m.get("model") or m.get("name") or str(m)
                existing_models.append(name)

        target = model_name.strip().lower()
        target_base = target.split(":")[0]

        # 1. Exact match
        for m in existing_models:
            if target == m.lower():
                logger.info("[OllamaWizard] Model '{}' is ready ✓", m)
                return True

        # 2. Substring or base-name match (e.g. llama3.1:8b vs llama3.1:8b-instruct-q4_0)
        for m in existing_models:
            m_lower = m.lower()
            m_base = m_lower.split(":")[0]
            if target in m_lower or m_lower in target or target_base == m_base:
                logger.info("[OllamaWizard] Found compatible installed model '{}' for target '{}' ✓", m, model_name)
                if config:
                    if config.llm.model == model_name:
                        config.llm.model = m
                    if config.llm.tool_model == model_name:
                        config.llm.tool_model = m
                return True

        logger.warning(
            "[OllamaWizard] Model '{}' not found locally. "
            "Starting automatic pull (this may take a few minutes)...",
            model_name,
        )

        # Stream pull progress
        progress_stream = client.pull(model_name, stream=True)
        last_status = ""
        for chunk in progress_stream:
            status = getattr(chunk, "status", None) or chunk.get("status", "")
            if status and status != last_status:
                logger.info("[OllamaWizard] Pulling '{}': {}", model_name, status)
                last_status = status

        logger.success("[OllamaWizard] Model '{}' pulled successfully ✓", model_name)
        return True

    except Exception as e:
        logger.error("[OllamaWizard] Error verifying/pulling model '{}': {}", model_name, e)
        if existing_models if 'existing_models' in locals() else []:
            fallback = existing_models[0]
            logger.warning("[OllamaWizard] Falling back to installed model '{}'", fallback)
            if config:
                config.llm.model = fallback
                config.llm.tool_model = fallback
            return True
        return False


def ensure_ollama_ready(config: "BabyConfig") -> bool:
    """
    Main preflight entry point.
    Guarantees Ollama server is reachable and target models are pulled.
    """
    if config.llm.test_mode:
        logger.info("[OllamaWizard] Test mode enabled; skipping Ollama preflight setup.")
        return True

    import ollama
    client = ollama.Client(host=config.llm.base_url)

    # 1. Test server connection
    server_online = False
    try:
        client.list()
        server_online = True
        logger.success("[OllamaWizard] Ollama server online at {}", config.llm.base_url)
    except Exception:
        logger.warning("[OllamaWizard] Cannot connect to Ollama at {}. Attempting auto-start...", config.llm.base_url)
        server_online = start_ollama_server()

    if not server_online:
        logger.error(
            "[OllamaWizard] Could not reach or start Ollama server at {}. "
            "Please ensure Ollama is installed from https://ollama.com and run 'ollama serve'.",
            config.llm.base_url,
        )
        return False

    # 2. Check main conversation model
    main_ok = ensure_model_pulled(client, config.llm.model, config=config)

    # 3. Check tool/planner model if different
    if config.llm.tool_model != config.llm.model:
        ensure_model_pulled(client, config.llm.tool_model, config=config)

    return main_ok



















