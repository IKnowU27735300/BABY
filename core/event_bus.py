"""
core/event_bus.py — Central async pub/sub event bus.
All modules communicate through typed events — no direct coupling.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Awaitable


class EventType(Enum):
    # Wake
    WAKE_WORD_DETECTED    = auto()
    ADMIN_PHRASE_DETECTED = auto()
    # Audio
    SPEECH_STARTED        = auto()
    SPEECH_ENDED          = auto()
    BARGE_IN_DETECTED     = auto()
    # Recognition
    TRANSCRIPT_READY      = auto()
    SPEAKER_IDENTIFIED    = auto()
    # LLM
    LLM_TOKEN             = auto()
    LLM_DONE              = auto()
    ACTION_PLAN_READY     = auto()
    # Consent
    CONSENT_REQUESTED     = auto()
    CONSENT_GIVEN         = auto()      # data: bool
    # Tool execution
    TOOL_STARTED          = auto()
    TOOL_DONE             = auto()
    # TTS
    TTS_STARTED           = auto()
    TTS_CHUNK_DONE        = auto()
    TTS_DONE              = auto()
    TTS_STOPPED           = auto()
    # UI
    UI_STATE_CHANGE       = auto()
    # System
    SHUTDOWN              = auto()
    ERROR                 = auto()
    CONFIG_CHANGED        = auto()
    # Relationship Engine
    RELATIONSHIP_DETECTED    = auto()
    RELATIONSHIP_EXPLAINED   = auto()
    RELATIONSHIP_CONTAMINATION = auto()
    RELATIONSHIP_TRAINED     = auto()


@dataclass
class Event:
    type: EventType
    data: Any = None
    source: str = ""


Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    Lightweight async pub/sub bus.
    Handlers are awaited in the order they were registered.
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Handler]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, event_type: EventType, handler: Handler):
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler):
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event):
        """Fire and forget — puts the event in queue."""
        await self._queue.put(event)

    def publish_sync(self, event: Event):
        """Thread-safe version — use from non-async context."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        else:
            self._queue.put_nowait(event)

    async def run(self):
        """Process events from the queue forever."""
        self._loop = asyncio.get_running_loop()
        while True:
            event = await self._queue.get()
            if event.type == EventType.SHUTDOWN:
                break
            handlers = self._handlers.get(event.type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    from loguru import logger
                    logger.exception("Unhandled error in event handler for {}: {}", event.type, e)


# Global singleton
_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus



















