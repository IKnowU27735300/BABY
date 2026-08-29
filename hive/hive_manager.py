"""
Hive Manager — Filesystem-based multi-agent coordination layer.

Manages agent workspaces, registry, shared resources, and message routing
for the Baby multi-agent hive system.

Directory structure:
    <hiveRoot>/
        agents/<id>/          — Per-agent workspace
            identity.md       — Agent role, capabilities
            memory.md         — Long-term memory (3-region: pinned/condensed/recent)
            inbox/            — Incoming messages (JSON)
            inbox/.done/      — Processed messages
            outbox/           — Outgoing messages
            outbox/.sent/     — Sent messages
            cursor.json       — Last processed inbox message ID
            settings.json     — Per-agent config
        registry.json         — Central agent registry
        board.md              — Shared planning board
        tasks.json            — Task ledger
        log.jsonl             — Append-only event log
        PROTOCOL.md           — Communication protocol
"""

import json
import os
import time
import uuid
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("Baby.hive")

HIVE_ROOT = Path(os.environ.get("BABY_HIVE_ROOT", Path(__file__).parent))
AGENTS_DIR = HIVE_ROOT / "agents"
REGISTRY_PATH = HIVE_ROOT / "registry.json"
BOARD_PATH = HIVE_ROOT / "board.md"
TASKS_PATH = HIVE_ROOT / "tasks.json"
LOG_PATH = HIVE_ROOT / "log.jsonl"
PROTOCOL_PATH = HIVE_ROOT / "PROTOCOL.md"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AgentMeta:
    id: str
    name: str
    provider: str = "ollama"
    role: str = "worker"
    capabilities: list[str] = field(default_factory=list)
    cwd: str = ""
    status: str = "idle"
    session_id: str = ""
    archived: bool = False
    cwd_valid: bool = True


@dataclass
class HiveMessage:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    from_agent: str = ""
    to_agent: str = ""          # "broadcast", "god", or specific agent id
    act: str = "inform"         # request, inform, propose, query, agree, refuse, done
    subject: str = ""
    body: str = ""
    timestamp: float = field(default_factory=time.time)
    reply_to: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Task:
    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    assignee: str = ""
    status: str = "todo"        # todo, doing, blocked, done
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    human_qa: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Secret Redaction
# ---------------------------------------------------------------------------

import re

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.DOTALL),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"),  # JWT
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),           # OpenAI
    re.compile(r"\b(xoxb-[A-Za-z0-9-]+)\b"),             # Slack
    re.compile(r"\b(ghp_[A-Za-z0-9]{36})\b"),            # GitHub
    re.compile(r"\b(AKIA[A-Z0-9]{16})\b"),               # AWS
    re.compile(r"\b(AIza[A-Za-z0-9_-]{35})\b"),          # Google
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|token|secret|password)\s*[=:]\s*\S{8,}", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Strip secrets from text before it leaves the main process."""
    if not text:
        return text
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# ---------------------------------------------------------------------------
# HiveManager
# ---------------------------------------------------------------------------

class HiveManager:
    """Core filesystem-based multi-agent coordination."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or HIVE_ROOT
        self.agents_dir = self.root / "agents"
        self.registry_path = self.root / "registry.json"
        self.board_path = self.root / "board.md"
        self.tasks_path = self.root / "tasks.json"
        self.log_path = self.root / "log.jsonl"
        self._ensure_structure()

    # -- Structure ----------------------------------------------------------

    def _ensure_structure(self):
        """Create hive directories and files if missing."""
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        (self.root / "backups").mkdir(exist_ok=True)
        if not self.registry_path.exists():
            self._write_json(self.registry_path, {"god_id": "Baby", "agents": {}})
        if not self.tasks_path.exists():
            self._write_json(self.tasks_path, [])
        if not self.log_path.exists():
            self.log_path.touch()
        if not self.board_path.exists():
            self.board_path.write_text("# Planning Board\n\n_Central planning space for the hive._\n", encoding="utf-8")

    # -- Registry -----------------------------------------------------------

    def _load_registry(self) -> dict:
        data = self._read_json(self.registry_path)
        if isinstance(data, dict):
            return data
        return {"god_id": "Baby", "agents": {}}

    def _save_registry(self, reg: dict):
        self._write_json(self.registry_path, reg)

    def register_agent(self, agent: AgentMeta):
        reg = self._load_registry()
        reg["agents"][agent.id] = asdict(agent)
        self._save_registry(reg)
        self._log_event("agent_registered", {"agent_id": agent.id, "name": agent.name})
        logger.info("[Hive] Agent registered: {} ({})", agent.name, agent.id)

    def get_agent(self, agent_id: str) -> Optional[dict]:
        reg = self._load_registry()
        return reg.get("agents", {}).get(agent_id)

    def list_agents(self, include_archived: bool = False) -> list[dict]:
        reg = self._load_registry()
        agents = list(reg.get("agents", {}).values())
        if not include_archived:
            agents = [a for a in agents if not a.get("archived")]
        return agents

    def set_agent_status(self, agent_id: str, status: str):
        reg = self._load_registry()
        if agent_id in reg.get("agents", {}):
            reg["agents"][agent_id]["status"] = status
            self._save_registry(reg)

    def archive_agent(self, agent_id: str):
        reg = self._load_registry()
        if agent_id in reg.get("agents", {}):
            reg["agents"][agent_id]["archived"] = True
            self._save_registry(reg)
            self._log_event("agent_archived", {"agent_id": agent_id})

    # -- Agent Workspaces ---------------------------------------------------

    def init_workspace(self, agent_id: str, name: str, role: str = "worker",
                       capabilities: list[str] | None = None, provider: str = "ollama"):
        """Create a full agent workspace with identity, memory, and maildirs."""
        ws = self.agents_dir / agent_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "inbox").mkdir(exist_ok=True)
        (ws / "inbox" / ".done").mkdir(exist_ok=True)
        (ws / "outbox").mkdir(exist_ok=True)
        (ws / "outbox" / ".sent").mkdir(exist_ok=True)

        identity = ws / "identity.md"
        if not identity.exists():
            caps = ", ".join(capabilities or ["general"])
            identity.write_text(
                f"# {name} ({agent_id})\n\n"
                f"**Role:** {role}\n"
                f"**Provider:** {provider}\n"
                f"**Capabilities:** {caps}\n\n"
                f"_This agent workspace was initialized by the hive manager._\n",
                encoding="utf-8",
            )

        memory = ws / "memory.md"
        if not memory.exists():
            memory.write_text(
                f"# Memory — {name} ({agent_id})\n\n"
                "## Pinned facts\n\n\n## Condensed history\n\n\n## Recent\n\n\n",
                encoding="utf-8",
            )

        cursor = ws / "cursor.json"
        if not cursor.exists():
            self._write_json(cursor, {"last_message_id": ""})

        settings = ws / "settings.json"
        if not settings.exists():
            self._write_json(settings, {})

        gitignore = ws / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("settings.json\ncursor.json\ninbox/\noutbox/\n", encoding="utf-8")

        self.register_agent(AgentMeta(
            id=agent_id, name=name, provider=provider, role=role,
            capabilities=capabilities or [], cwd=str(ws),
        ))
        logger.info("[Hive] Workspace initialized: {}", ws)

    def get_workspace(self, agent_id: str) -> Optional[Path]:
        ws = self.agents_dir / agent_id
        return ws if ws.exists() else None

    # -- Messages -----------------------------------------------------------

    def send_message(self, msg: HiveMessage):
        """Route a message to the recipient's inbox."""
        if msg.to_agent in ("broadcast", ""):
            self._broadcast(msg)
            return
        if msg.to_agent == "god":
            msg.to_agent = self._load_registry().get("god_id", "Baby")

        recipient_dir = self.agents_dir / msg.to_agent / "inbox"
        recipient_dir.mkdir(parents=True, exist_ok=True)
        path = recipient_dir / f"{msg.id}.json"
        path.write_text(json.dumps(asdict(msg), indent=2, default=str), encoding="utf-8")
        self._log_event("message_sent", {
            "from": msg.from_agent, "to": msg.to_agent,
            "act": msg.act, "subject": msg.subject,
        })

    def _broadcast(self, msg: HiveMessage):
        for agent_info in self.list_agents():
            agent_id = str(agent_info.get("id", "")) if isinstance(agent_info, dict) else str(agent_info)
            if not agent_id or agent_id == msg.from_agent:
                continue
            copy = HiveMessage(
                id=msg.id, from_agent=msg.from_agent, to_agent=agent_id,
                act=msg.act, subject=msg.subject, body=msg.body,
                timestamp=msg.timestamp, reply_to=msg.reply_to,
                metadata={**msg.metadata, "broadcast": True},
            )
            inbox = self.agents_dir / agent_id / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            (inbox / f"{copy.id}.json").write_text(
                json.dumps(asdict(copy), indent=2, default=str), encoding="utf-8"
            )

    def poll_inbox(self, agent_id: str) -> list[HiveMessage]:
        """Return unread messages for an agent, moving processed ones to .done."""
        inbox = self.agents_dir / agent_id / "inbox"
        if not inbox.exists():
            return []
        messages = []
        for f in sorted(inbox.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                messages.append(HiveMessage(**data))
                done_dir = inbox / ".done"
                done_dir.mkdir(exist_ok=True)
                f.rename(done_dir / f.name)
            except Exception as e:
                logger.warning("[Hive] Failed to parse message {}: {}", f.name, e)
        return messages

    def send_reply(self, original: HiveMessage, act: str, body: str) -> HiveMessage:
        reply = HiveMessage(
            from_agent=original.to_agent,
            to_agent=original.from_agent,
            act=act,
            subject=f"Re: {original.subject}",
            body=body,
            reply_to=original.id,
        )
        self.send_message(reply)
        return reply

    # -- Tasks ---------------------------------------------------------------

    def _load_tasks(self) -> list[dict]:
        data = self._read_json(self.tasks_path)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []

    def _save_tasks(self, tasks: list[dict]):
        self._write_json(self.tasks_path, tasks)

    def create_task(self, task: Task) -> Task:
        tasks = self._load_tasks()
        tasks.append(asdict(task))
        self._save_tasks(tasks)
        self._log_event("task_created", {"task_id": task.id, "title": task.title, "assignee": task.assignee})
        return task

    def update_task(self, task_id: str, updates: dict) -> Optional[dict]:
        tasks = self._load_tasks()
        for t in tasks:
            if t["id"] == task_id:
                t.update(updates)
                t["updated_at"] = time.time()
                self._save_tasks(tasks)
                self._log_event("task_updated", {"task_id": task_id, **updates})
                return t
        return None

    def get_task(self, task_id: str) -> Optional[dict]:
        for t in self._load_tasks():
            if t["id"] == task_id:
                return t
        return None

    def list_tasks(self, status: str = "", assignee: str = "") -> list[dict]:
        tasks = self._load_tasks()
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        if assignee:
            tasks = [t for t in tasks if t["assignee"] == assignee]
        return tasks

    def complete_task(self, task_id: str) -> Optional[dict]:
        return self.update_task(task_id, {"status": "done"})

    def get_ready_tasks(self) -> list[dict]:
        """Return tasks whose dependencies are all done."""
        tasks = self._load_tasks()
        done_ids = {t["id"] for t in tasks if t["status"] == "done"}
        return [
            t for t in tasks
            if t["status"] == "todo" and all(d in done_ids for d in t["dependencies"])
        ]

    # -- Event Log -----------------------------------------------------------

    def _log_event(self, event_type: str, data: dict):
        entry = {
            "ts": time.time(),
            "type": event_type,
            **data,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def get_recent_events(self, n: int = 50) -> list[dict]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").strip().split("\n")
        events = []
        for line in lines[-n:]:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events

    # -- Board ---------------------------------------------------------------

    def update_board(self, content: str):
        self.board_path.write_text(content, encoding="utf-8")

    def read_board(self) -> str:
        if self.board_path.exists():
            return self.board_path.read_text(encoding="utf-8")
        return ""

    # -- Backups -------------------------------------------------------------

    def backup_agent_memory(self, agent_id: str):
        """Cold-copy agent memory.md to backups."""
        src = self.agents_dir / agent_id / "memory.md"
        if not src.exists():
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        dst_dir = self.root / "backups" / ts / agent_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / "memory.md"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("[Hive] Backed up memory for {}: {}", agent_id, dst)

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> Optional[dict | list]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _write_json(path: Path, data):
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_hive: Optional[HiveManager] = None


def get_hive(root: Optional[Path] = None) -> HiveManager:
    global _hive
    if _hive is None:
        _hive = HiveManager(root)
    return _hive



















