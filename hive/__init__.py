"""Baby Hive — Filesystem-based multi-agent coordination system."""

from hive.hive_manager import HiveManager, get_hive, AgentMeta, HiveMessage, Task, redact_secrets
from hive.message_router import MessageRouter, MessageSender
from hive.task_manager import TaskManager
from hive.provider_registry import get_provider, list_providers, PROVIDERS
from hive.memory_reflector import MemoryReflector
from hive.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from hive.missions import MissionControl, Mission
from hive.voice_actions import VoiceActionHandler, parse_voice_command, neutralize_for_voice
from hive.completion_watcher import CompletionWatcher

__all__ = [
    "HiveManager", "get_hive", "AgentMeta", "HiveMessage", "Task", "redact_secrets",
    "MessageRouter", "MessageSender",
    "TaskManager",
    "get_provider", "list_providers", "PROVIDERS",
    "MemoryReflector",
    "CircuitBreaker", "CircuitBreakerConfig",
    "MissionControl", "Mission",
    "VoiceActionHandler", "parse_voice_command", "neutralize_for_voice",
    "CompletionWatcher",
]



















