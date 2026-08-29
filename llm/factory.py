"""
llm/factory.py — LLM Client factory module for Baby Desktop Assistant.
"""

from __future__ import annotations
from loguru import logger
from core.config import LLMConfig
from llm.ollama_client import OllamaClient
from llm.airllm_client import AirLLMClient


def get_llm_client(config: LLMConfig):
    """
    Factory function returning the configured LLM client instance.
    Supports provider='ollama' and provider='airllm'.
    """
    provider = getattr(config, "provider", "ollama").lower()

    if provider == "airllm":
        logger.info("[LLM Factory] Initializing AirLLM client (layer-wise low-VRAM inference)...")
        return AirLLMClient(config)
    else:
        logger.info("[LLM Factory] Initializing Ollama client...")
        return OllamaClient(config)



















