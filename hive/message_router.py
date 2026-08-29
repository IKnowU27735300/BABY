"""
Message Router — Polls agent outboxes, routes messages to recipient inboxes.

Runs as a background thread. Handles broadcast, god-targeted, and direct
agent-to-agent message routing. Redacts secrets before routing.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from hive.hive_manager import get_hive, HiveMessage, redact_secrets

logger = logging.getLogger("Baby.hive.router")


class MessageRouter:
    """Background message router for the hive."""

    def __init__(self, poll_interval: float = 2.0):
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._hive = get_hive()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hive-router")
        self._thread.start()
        logger.info("[Router] Started (poll interval: {}s)", self._poll_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Router] Stopped")

    def _loop(self):
        while self._running:
            try:
                self._route_once()
            except Exception as e:
                logger.debug("[Router] Route tick error: {}", e)
            time.sleep(self._poll_interval)

    def _route_once(self):
        """Check all agent outboxes and route messages."""
        agents = self._hive.list_agents(include_archived=False)
        for agent in agents:
            agent_id = agent["id"]
            outbox = self._hive.agents_dir / agent_id / "outbox"
            if not outbox.exists():
                continue
            for f in sorted(outbox.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    msg = HiveMessage(**data)

                    # Redact secrets before routing
                    msg.subject = redact_secrets(msg.subject)
                    msg.body = redact_secrets(msg.body)

                    # Route the message
                    self._hive.send_message(msg)

                    # Move to .sent
                    sent_dir = outbox / ".sent"
                    sent_dir.mkdir(exist_ok=True)
                    f.rename(sent_dir / f.name)
                    logger.debug("[Router] Routed {} -> {}", agent_id, msg.to_agent)
                except Exception as e:
                    logger.warning("[Router] Failed to route {}: {}", f.name, e)


class MessageSender:
    """Convenience class for agents to send messages via their outbox."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._hive = get_hive()

    def send(self, to: str, act: str, subject: str, body: str,
             reply_to: str = "", metadata: dict | None = None) -> HiveMessage:
        msg = HiveMessage(
            from_agent=self.agent_id,
            to_agent=to,
            act=act,
            subject=subject,
            body=body,
            reply_to=reply_to,
            metadata=metadata or {},
        )
        # Write to agent's outbox (router will pick it up)
        outbox = self._hive.agents_dir / self.agent_id / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        path = outbox / f"{msg.id}.json"
        path.write_text(json.dumps({
            "id": msg.id, "from_agent": msg.from_agent, "to_agent": msg.to_agent,
            "act": msg.act, "subject": msg.subject, "body": msg.body,
            "timestamp": msg.timestamp, "reply_to": msg.reply_to,
            "metadata": msg.metadata,
        }, indent=2, default=str), encoding="utf-8")
        return msg

    def broadcast(self, act: str, subject: str, body: str):
        return self.send(to="broadcast", act=act, subject=subject, body=body)

    def reply(self, original: HiveMessage, act: str, body: str) -> HiveMessage:
        return self.send(
            to=original.from_agent, act=act,
            subject=f"Re: {original.subject}", body=body,
            reply_to=original.id,
        )



















