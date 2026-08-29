"""
Voice Actions — Tiered safety model for voice-controlled agent operations.

Implements the FIPA-lite speech act protocol for voice commands with
two-tier safety: soft (immediate) and destructive (confirm required).
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("Baby.hive.voice_actions")


@dataclass
class ActionResult:
    ok: bool
    spoken: str
    needs_confirm: bool = False
    pending_action: Optional[dict] = None


# Verb definitions with tier classification
VERBS = {
    # Soft tier — immediate execution
    "ping": {"tier": "soft", "confirm_word": "ping", "agent_targeted": True},
    "create_task": {"tier": "soft", "confirm_word": "create", "agent_targeted": False},
    "assign_task": {"tier": "soft", "confirm_word": "assign", "agent_targeted": True},
    "update_task": {"tier": "soft", "confirm_word": "update", "agent_targeted": False},
    "dispatch": {"tier": "soft", "confirm_word": "dispatch", "agent_targeted": True},
    "steer": {"tier": "soft", "confirm_word": "steer", "agent_targeted": True},
    "resume": {"tier": "soft", "confirm_word": "resume", "agent_targeted": True},
    "query": {"tier": "soft", "confirm_word": "query", "agent_targeted": True},
    "inform": {"tier": "soft", "confirm_word": "inform", "agent_targeted": True},

    # Destructive tier — requires verbal confirmation
    "spawn": {"tier": "destructive", "confirm_word": "spawn", "agent_targeted": False},
    "kill": {"tier": "destructive", "confirm_word": "kill", "agent_targeted": True},
    "pause": {"tier": "destructive", "confirm_word": "pause", "agent_targeted": True},
    "halt": {"tier": "destructive", "confirm_word": "halt", "agent_targeted": False},
    "archive": {"tier": "destructive", "confirm_word": "archive", "agent_targeted": True},
    "clear_context": {"tier": "destructive", "confirm_word": "clear", "agent_targeted": False},
}

# Hard allowlist — voice-forbidden even with confirm
HARD_FORBIDDEN = {
    "kill": ["god", "orchestrator", "Baby"],
    "pause": ["god", "orchestrator", "Baby"],
    "halt": ["god", "orchestrator", "Baby"],
    "archive": ["god", "orchestrator", "Baby"],
}

# Injection patterns to neutralize
INJECTION_PATTERNS = [
    re.compile(r"<\|.*?\|>", re.DOTALL),
    re.compile(r"\[INST\].*?\[/INST\]", re.DOTALL),
    re.compile(r"SYSTEM:\s*", re.IGNORECASE),
    re.compile(r"IGNORE\s+PREVIOUS", re.IGNORECASE),
]


def neutralize_for_voice(text: str, max_length: int = 100) -> str:
    """Strip injection patterns and control chars from spoken text."""
    if not text:
        return ""
    for pattern in INJECTION_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)
    text = text[:max_length]
    return text.strip()


def parse_voice_command(transcript: str) -> Optional[dict]:
    """Parse a voice transcript into a structured command."""
    text = transcript.lower().strip()
    for verb, spec in VERBS.items():
        patterns = [
            rf"\b{verb}\b",
            rf"\b{verb.replace('_', ' ')}\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                # Extract target (word after verb)
                after = text[match.end():].strip()
                target = after.split()[0] if after.split() else ""
                return {
                    "verb": verb,
                    "tier": spec["tier"],
                    "confirm_word": spec["confirm_word"],
                    "agent_targeted": spec["agent_targeted"],
                    "target": target,
                    "raw": transcript,
                }
    return None


class VoiceActionHandler:
    """Handles voice commands with tiered safety."""

    def __init__(self):
        self._pending: Optional[dict] = None

    def handle(self, transcript: str, executor=None) -> ActionResult:
        cmd = parse_voice_command(transcript)
        if not cmd:
            return ActionResult(ok=False, spoken="I didn't understand that command.")

        verb = cmd["verb"]
        target = cmd["target"]

        # Check hard forbidden
        if verb in HARD_FORBIDDEN:
            forbidden_targets = HARD_FORBIDDEN[verb]
            if target in forbidden_targets or target == "":
                return ActionResult(
                    ok=False,
                    spoken=f"I cannot {verb} the {target or 'orchestrator'} by voice.",
                )

        # Soft tier — immediate
        if cmd["tier"] == "soft":
            if executor:
                result = executor(verb, cmd)
                return ActionResult(ok=True, spoken=result.get("spoken", f"Done: {verb}"))
            return ActionResult(ok=True, spoken=f"Executing {verb}.")

        # Destructive tier — confirm required
        if self._pending:
            # Check for confirmation
            confirm = cmd.get("confirm_word", "")
            if confirm == verb or confirm == "confirm":
                action = self._pending
                self._pending = None
                if executor:
                    result = executor(verb, action)
                    return ActionResult(ok=True, spoken=result.get("spoken", f"Confirmed: {verb}"))
                return ActionResult(ok=True, spoken=f"Confirmed: {verb}.")
            else:
                self._pending = None
                return ActionResult(ok=False, spoken="Confirmation cancelled. Pending action cleared.")

        # Request confirmation
        self._pending = cmd
        return ActionResult(
            ok=True,
            spoken=f"You want to {verb} {target}. Say '{verb}' or 'confirm' to proceed.",
            needs_confirm=True,
            pending_action=cmd,
        )

    def cancel_pending(self) -> ActionResult:
        self._pending = None
        return ActionResult(ok=True, spoken="Pending action cancelled.")

    def has_pending(self) -> bool:
        return self._pending is not None



















