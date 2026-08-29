"""
core/reminders.py — Timer / Reminder / Alarm engine.

Persistent JSON store of scheduled items. The orchestrator runs a background
loop that polls ``due()`` and fires each entry through a callback (TTS + UI),
rescheduling repeating items.

Time parsing supports natural language:
    "in 10 minutes", "in an hour", "in half an hour",
    "at 3pm", "at 15:30", "at 8 am",
    "every day at 8am", "every morning", "every 2 hours", "every day",
    "tomorrow 9am"
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from loguru import logger

KIND_TIMER = "timer"
KIND_REMINDER = "reminder"
KIND_ALARM = "alarm"

_MINUTES = 60
_HOURS = 3600
_DAYS = 86400

_DURATION_RE = re.compile(
    r"(?P<n>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>sec|secs|second|seconds|min|mins|minute|minutes|"
    r"hr|hrs|hour|hours|h|day|days|d)\b",
    re.IGNORECASE,
)
_CLOCK_RE = re.compile(
    r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)\b", re.IGNORECASE
)
_CLOCK_24_RE = re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{2})\b")


def parse_duration(text: str) -> float | None:
    """Parse a human duration ("10 minutes", "1.5 hours") → seconds."""
    if not text:
        return None
    t = text.strip().lower()
    if not t:
        return None
    if "half an hour" in t or "half hour" in t:
        return 30 * _MINUTES
    if t in ("an hour", "one hour", "1hr") or "an hour" in t:
        return _HOURS
    if t in ("a minute", "one minute") or "a minute" in t:
        return _MINUTES
    if t in ("a second", "one second"):
        return 1
    if t in ("a day", "one day") or "a day" in t:
        return _DAYS
    m = _DURATION_RE.search(t)
    if not m:
        return None
    n = float(m.group("n"))
    unit = m.group("unit").lower()
    mult = {
        "sec": 1, "secs": 1, "second": 1, "seconds": 1,
        "min": _MINUTES, "mins": _MINUTES, "minute": _MINUTES, "minutes": _MINUTES,
        "hr": _HOURS, "hrs": _HOURS, "hour": _HOURS, "hours": _HOURS, "h": _HOURS,
        "day": _DAYS, "days": _DAYS, "d": _DAYS,
    }.get(unit, _MINUTES)
    return n * mult


def _parse_clock_times(text: str) -> list[datetime]:
    """Return all clock times mentioned in text (today/next occurrence)."""
    now = datetime.now()
    hits: list[datetime] = []
    low = text.lower()
    for m in _CLOCK_RE.finditer(low):
        h = int(m.group("h")) % 24
        mi = int(m.group("m")) if m.group("m") else 0
        if m.group("ampm") and m.group("ampm").lower() == "pm" and h < 12:
            h += 12
        if m.group("ampm") and m.group("ampm").lower() == "am" and h == 12:
            h = 0
        candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if "tomorrow" in low or candidate <= now:
            candidate += timedelta(days=1)
        hits.append(candidate)
    if not hits:
        for m in _CLOCK_24_RE.finditer(low):
            h = int(m.group("h")) % 24
            mi = int(m.group("m"))
            candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if "tomorrow" in low or candidate <= now:
                candidate += timedelta(days=1)
            hits.append(candidate)
    return hits


def _parse_repeat(text: str) -> str | None:
    """Detect a repeat schedule from natural language."""
    low = text.lower()
    if "every day" in low or "daily" in low or "every morning" in low or "every evening" in low:
        return "daily"
    if "every hour" in low or "hourly" in low:
        return "hourly"
    m = re.search(r"every\s+(\d+(?:\.\d+)?)\s*(min|mins|minute|minutes|hour|hours|hr|hrs|day|days)\b", low)
    if m:
        secs = parse_duration(f"{m.group(1)} {m.group(2)}")
        if secs:
            return f"interval:{int(secs)}"
    return None


@dataclass
class Reminder:
    id: str
    kind: str
    text: str
    due_at: float
    repeat: str | None = None
    created_at: float = field(default_factory=time.time)
    fired: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "due_at": self.due_at,
            "repeat": self.repeat,
            "created_at": self.created_at,
            "fired": self.fired,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Reminder":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            kind=d.get("kind", KIND_REMINDER),
            text=d.get("text", ""),
            due_at=float(d.get("due_at", 0)),
            repeat=d.get("repeat"),
            created_at=float(d.get("created_at", time.time())),
            fired=bool(d.get("fired", False)),
        )


class ReminderService:
    """Thread-safe, JSON-persisted timer/reminder/alarm store + dispatcher."""

    def __init__(self, store_path: Path | str = "data/reminders.json"):
        self._store = Path(store_path)
        self._items: list[Reminder] = []
        self._lock = threading.RLock()
        self.on_fire: Callable[[Reminder], None] | None = None
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._store.exists():
                raw = json.loads(self._store.read_text(encoding="utf-8"))
                self._items = [Reminder.from_dict(d) for d in raw]
        except Exception as e:
            logger.warning("[Reminders] Failed to load store: {}", e)
            self._items = []

    def _save(self) -> None:
        try:
            self._store.parent.mkdir(parents=True, exist_ok=True)
            self._store.write_text(
                json.dumps([r.to_dict() for r in self._items], indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[Reminders] Failed to save store: {}", e)

    # ── scheduling ───────────────────────────────────────────────────────────

    def schedule(
        self, kind: str, text: str, due_at: float, repeat: str | None = None
    ) -> Reminder:
        entry = Reminder(
            id=uuid.uuid4().hex[:10],
            kind=kind,
            text=text,
            due_at=due_at,
            repeat=repeat,
        )
        with self._lock:
            self._items.append(entry)
            self._save()
        logger.info("[Reminders] Scheduled {} '{}' at {}", kind, text, datetime.fromtimestamp(due_at).strftime("%H:%M:%S"))
        return entry

    def cancel(self, query: str = "") -> list[Reminder]:
        """Cancel matching items. Empty/'all' cancels everything."""
        q = (query or "").strip().lower()
        with self._lock:
            kept, removed = [], []
            for r in self._items:
                if not r.fired:
                    matched = (
                        q in ("", "all", "everything")
                        or q in (r.kind.lower(),)
                        or q in r.text.lower()
                        or r.id.startswith(q)
                    )
                    if matched:
                        removed.append(r)
                    else:
                        kept.append(r)
            self._items = kept
            self._save()
        if removed:
            logger.info("[Reminders] Cancelled {} scheduled item(s)", len(removed))
        return removed

    def cancel_by_id(self, rid: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [r for r in self._items if r.id != rid]
            self._save()
        return len(self._items) < before

    def list(self) -> list[Reminder]:
        now = time.time()
        with self._lock:
            upcoming = sorted(
                (r for r in self._items if not r.fired and r.due_at > now),
                key=lambda r: r.due_at,
            )
        return upcoming

    def due(self, now: float | None = None) -> list[Reminder]:
        now = now if now is not None else time.time()
        with self._lock:
            return [r for r in self._items if not r.fired and r.due_at <= now]

    def mark_fired(self, entry: Reminder) -> None:
        """Mark fired; if repeating, roll it forward to the next occurrence."""
        with self._lock:
            if entry.fired:
                return
            if entry.repeat:
                step = _repeat_step(entry.repeat)
                if step:
                    while entry.due_at <= time.time():
                        entry.due_at += step
                    logger.info("[Reminders] Rescheduled recurring '{}' to {}", entry.text, datetime.fromtimestamp(entry.due_at).strftime("%H:%M:%S"))
                    self._save()
                    return
            entry.fired = True
            self._save()

    def clear_fired(self) -> None:
        with self._lock:
            self._items = [r for r in self._items if not r.fired]
            self._save()

    def count(self) -> int:
        with self._lock:
            return len([r for r in self._items if not r.fired])

    # ── high-level helpers used by tools ─────────────────────────────────────

    def schedule_from_when(self, kind: str, text: str, when: str = "") -> Reminder:
        """Parse 'when' (duration / clock / repeat) and schedule accordingly."""
        w = (when or "").strip().lower()
        repeat = _parse_repeat(w)
        if repeat:
            if "daily" in repeat or "hourly" in repeat:
                clocks = _parse_clock_times(w)
                if clocks:
                    due = clocks[0].timestamp()
                else:
                    due = time.time() + (60 if repeat == "daily" else 3600)
            else:
                step = _repeat_step(repeat)
                due = time.time() + (step if step else 3600)
        else:
            secs = parse_duration(w)
            if secs:
                due = time.time() + secs
            else:
                clocks = _parse_clock_times(w)
                if clocks:
                    due = clocks[0].timestamp()
                else:
                    raise ValueError(
                        f"Could not understand when '{when}'. Use e.g. 'in 10 minutes', 'at 3pm', 'every day at 8am'."
                    )
        return self.schedule(kind, text, due, repeat)

    def describe(self, entry: Reminder) -> str:
        when = datetime.fromtimestamp(entry.due_at)
        if entry.repeat:
            return f"{entry.kind} '{entry.text}' repeating {entry.repeat} at {when.strftime('%H:%M')}"
        return f"{entry.kind} '{entry.text}' at {when.strftime('%H:%M')}"


def _repeat_step(repeat: str) -> int | None:
    if repeat == "daily":
        return _DAYS
    if repeat == "hourly":
        return _HOURS
    if repeat.startswith("interval:"):
        try:
            return int(repeat.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


# ── module-level singleton wiring (tools call through this) ──────────────────

_service: ReminderService | None = None
_service_lock = threading.Lock()


def init_reminder_service(svc: ReminderService) -> None:
    global _service
    with _service_lock:
        _service = svc


def get_reminder_service() -> ReminderService | None:
    with _service_lock:
        return _service



















