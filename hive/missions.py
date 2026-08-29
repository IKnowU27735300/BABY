"""
Scheduled Missions — Auto-dispatch, heartbeat, and compact tasks.

Runs periodic missions: dispatching messages to agents, monitoring
floor activity, and triggering maintenance operations.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from hive.hive_manager import get_hive, HiveMessage
from hive.message_router import MessageSender

logger = logging.getLogger("Baby.hive.missions")


@dataclass
class Mission:
    id: str
    name: str
    mission_type: str   # dispatch, heartbeat, compact
    target: str = ""    # agent_id for dispatch
    interval: float = 60.0
    enabled: bool = True
    payload: str = ""
    last_run: float = 0.0
    run_count: int = 0


class MissionControl:
    """Scheduler for periodic hive missions."""

    def __init__(self):
        self._hive = get_hive()
        self._missions: dict[str, Mission] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: dict[str, list[Callable]] = {}
        self._register_builtins()

    def _register_builtins(self):
        self.register(Mission(
            id="ops_standup", name="Ops Standup",
            mission_type="dispatch", target="god",
            interval=3600, enabled=True,
            payload="Review agent statuses, task progress, and compact contexts.",
        ))
        self.register(Mission(
            id="heartbeat", name="Floor Heartbeat",
            mission_type="heartbeat",
            interval=120, enabled=False,
        ))
        self.register(Mission(
            id="compact_maintenance", name="Compact Maintenance",
            mission_type="compact",
            interval=7200, enabled=False,
        ))

    def register(self, mission: Mission):
        self._missions[mission.id] = mission

    def unregister(self, mission_id: str):
        self._missions.pop(mission_id, None)

    def enable(self, mission_id: str):
        if mission_id in self._missions:
            self._missions[mission_id].enabled = True

    def disable(self, mission_id: str):
        if mission_id in self._missions:
            self._missions[mission_id].enabled = False

    def on(self, event: str, callback: Callable):
        self._callbacks.setdefault(event, []).append(callback)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hive-missions")
        self._thread.start()
        logger.info("[Missions] Started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Missions] Stopped")

    def _loop(self):
        while self._running:
            now = time.time()
            for mission in self._missions.values():
                if not mission.enabled:
                    continue
                if now - mission.last_run >= mission.interval:
                    try:
                        self._execute(mission)
                        mission.last_run = now
                        mission.run_count += 1
                    except Exception as e:
                        logger.error("[Missions] Error executing {}: {}", mission.name, e)
            time.sleep(10)

    def _execute(self, mission: Mission):
        if mission.mission_type == "dispatch":
            self._dispatch(mission)
        elif mission.mission_type == "heartbeat":
            self._heartbeat(mission)
        elif mission.mission_type == "compact":
            self._compact(mission)

    def _dispatch(self, mission: Mission):
        sender = MessageSender("mission_control")
        msg = HiveMessage(
            from_agent="mission_control",
            to_agent=mission.target,
            act="request",
            subject=mission.name,
            body=mission.payload,
        )
        self._hive.send_message(msg)
        logger.info("[Missions] Dispatched '{}' to {}", mission.name, mission.target)

    def _heartbeat(self, mission: Mission):
        agents = self._hive.list_agents()
        quiet = [a for a in agents if a.get("status") == "idle"]
        for cb in self._callbacks.get("heartbeat", []):
            cb(agents, quiet)

    def _compact(self, mission: Mission):
        for cb in self._callbacks.get("compact", []):
            cb()

    def get_missions(self) -> list[dict]:
        return [
            {"id": m.id, "name": m.name, "type": m.mission_type,
             "enabled": m.enabled, "interval": m.interval,
             "last_run": m.last_run, "run_count": m.run_count}
            for m in self._missions.values()
        ]

    def trigger_now(self, mission_id: str):
        mission = self._missions.get(mission_id)
        if mission:
            self._execute(mission)
            mission.last_run = time.time()
            mission.run_count += 1



















