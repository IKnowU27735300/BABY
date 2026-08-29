"""
core/consent_gate.py — The central gatekeeper.
NO system action may execute without passing through this coroutine.

JARVIS-level security protocols:
- Identity verification for sensitive operations
- Threat detection for potentially harmful commands
- Risk assessment with contextual awareness
- Secure execution with audit logging
"""

from __future__ import annotations
import asyncio
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from audio.tts import TTSEngine
    from audio.stt import STTEngine
    from audio.vad import VADEngine
    from core.config import ConsentConfig


RISK_PREAMBLES = {
    "low":    "I'm going to",
    "medium": "I'd like to",
    "high":   "This is an important action. I'm planning to",
}

RISK_COLORS = {          # Used by the UI to colour the consent banner
    "low":    "#28A745",
    "medium": "#FFB347",
    "high":   "#DC3545",
}

# JARVIS Security: Threat detection patterns
THREAT_PATTERNS = {
    "critical": [
        "format", "rm -rf", "delete system", "delete windows", "delete program",
        "disable firewall", "disable antivirus", "shutdown /s", "shutdown /r",
        "bcdedit", "reg delete", "takeown", "icacls", "cipher /w",
    ],
    "high": [
        "delete", "remove", "erase", "uninstall", "wipe", "destroy",
        "override", "force", "bypass", "sudo", "admin", "root",
        "password", "credential", "token", "secret", "private key",
    ],
    "medium": [
        "install", "update", "modify", "change", "replace", "move",
        "rename", "copy", "download", "execute", "run", "start",
    ],
}

# JARVIS Security: Sensitive file paths (never touch without explicit consent)
SENSITIVE_PATHS = [
    "windows", "system32", "program files", "programdata",
    ".ssh", ".env", "credentials", "secrets", "tokens",
    "registry", "boot", "efi", "recovery",
]


@dataclass
class ActionPlan:
    """A fully-described plan that Baby must get consent for before executing."""
    description: str
    risk_level: str = "medium"          # low | medium | high
    tools: list[dict] = field(default_factory=list)
    details: str = ""                   # Extended explanation shown in UI
    speaker: str | None = None          # Identified speaker for verification
    threat_level: str = "none"          # none | low | medium | high | critical


class ConsentGate:
    def __init__(
        self,
        config: "ConsentConfig",
        tts: "TTSEngine",
        stt: "STTEngine",
        vad: "VADEngine",
        ui_controller,                  # BabyIslandController (PySide6 signal bridge)
    ):
        self._config = config
        self._tts = tts
        self._stt = stt
        self._vad = vad
        self._ui = ui_controller
        self._pending: asyncio.Future | None = None
        self._lock = asyncio.Lock()
        self._security_log: list[dict] = []  # Audit trail for security events

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def assess_threat_level(self, plan: ActionPlan) -> str:
        """JARVIS Security: Assess the threat level of an action plan."""
        desc_lower = plan.description.lower()
        all_tool_text = " ".join(
            f"{t.get('name', '')} {str(t.get('args', {}))}" for t in plan.tools
        ).lower()
        combined = f"{desc_lower} {all_tool_text}"

        # Check for critical threats
        for pattern in THREAT_PATTERNS["critical"]:
            if pattern in combined:
                self._log_security_event("critical", plan, f"Critical threat pattern detected: {pattern}")
                return "critical"

        # Check for high threats
        for pattern in THREAT_PATTERNS["high"]:
            if pattern in combined:
                # Check if it's in a sensitive path
                for path in SENSITIVE_PATHS:
                    if path in combined:
                        self._log_security_event("high", plan, f"High threat in sensitive area: {pattern} + {path}")
                        return "high"

        # Check for medium threats
        for pattern in THREAT_PATTERNS["medium"]:
            if pattern in combined:
                return "medium"

        return "none"

    def requires_explicit_consent(self, plan: ActionPlan) -> bool:
        """Determine if explicit consent is required for this action."""
        # JARVIS Security: Always require consent for critical threats
        if plan.threat_level == "critical":
            return True

        # JARVIS Security: Require consent for high threats from unrecognized speakers
        if plan.threat_level == "high" and not self._is_trusted_speaker(plan.speaker):
            return True

        sensitive_keywords = {
            "setting", "settings", "payment", "bank", "finance", "account", "password",
            "email", "credit", "debit", "delete", "erase", "format", "remove",
            "registry", "security", "passcode", "pay", "gpay", "paypal", "wallet",
            "credential", "credentials", "auth", "signin", "sign-in", "login", "log-in",
            "wifi", "wi-fi", "bluetooth", "message", "whatsapp", "telegram", "slack",
            "teams", "mail", "email", "sms"
        }

        # Check description
        desc_lower = plan.description.lower()
        if any(kw in desc_lower for kw in sensitive_keywords):
            return True

        # Check tools
        for tool in plan.tools:
            name = tool.get("name", "")
            args = tool.get("args", {})

            # Any file mutation (create/write/copy/move/delete) requires the
            # user's explicit permission — never silently modified.
            if name in ("write_file", "copy_file", "move_file", "delete_file", "create_directory"):
                return True

            if "delete" in name or "remove" in name:
                return True

            if name == "open_application":
                app_name = str(args.get("app_name", "")).lower()
                if any(kw in app_name for kw in sensitive_keywords):
                    return True

            if name in ("copy_file", "move_file"):
                dest = str(args.get("destination", args.get("dst", ""))).lower()
                src = str(args.get("source", args.get("src", ""))).lower()
                if any(kw in dest or kw in src for kw in sensitive_keywords):
                    return True

            if name in ("send_message", "toggle_wifi", "toggle_bluetooth"):
                return True

            # JARVIS Security: Check for sensitive file paths
            if name in ("write_file", "read_file", "edit_file", "delete_file", "copy_file", "move_file"):
                path = str(args.get("path", "")).lower()
                for sensitive in SENSITIVE_PATHS:
                    if sensitive in path:
                        return True

        return False

    def _is_trusted_speaker(self, speaker: str | None) -> bool:
        """Check if the speaker is a trusted/recognized user."""
        if not speaker:
            return False
        # For now, any recognized speaker is trusted
        # In production, you could check against a whitelist of trusted speakers
        return True

    def _log_security_event(self, level: str, plan: ActionPlan, reason: str) -> None:
        """Log security events for audit trail."""
        import datetime
        event = {
            "timestamp": datetime.datetime.now().isoformat(),
            "level": level,
            "description": plan.description,
            "speaker": plan.speaker,
            "reason": reason,
        }
        self._security_log.append(event)
        # Keep last 100 events
        if len(self._security_log) > 100:
            self._security_log = self._security_log[-100:]
        logger.warning("[Security] {} threat detected: {} — {}", level.upper(), plan.description, reason)

    async def request_consent(self, plan: ActionPlan) -> bool:
        """
        JARVIS Security Protocol:
        1. Assess threat level
        2. Verify speaker identity for sensitive operations
        3. Speak the plan aloud with appropriate risk communication
        4. Show consent UI
        5. Wait for voice OR button approval (with timeout)
        6. Log the decision for audit trail
        Returns True if approved, False if denied or timed out.
        """
        # JARVIS Security: Always require consent for critical threats
        if plan.threat_level == "critical":
            await self._tts.speak(
                "Security alert: This action has been flagged as critical. "
                "I cannot proceed without your explicit confirmation. "
                "This is for your protection."
            )
            # Fall through to consent request

        if not self.requires_explicit_consent(plan):
            logger.info("[Consent] Auto-approving non-sensitive action: {}", plan.description)
            return True

        async with self._lock:
            announcement = self._format_announcement(plan)
            logger.info("[Consent] Requesting consent: {}", plan.description)

            # Update UI
            self._ui.set_plan_text(plan.description)
            self._ui.set_risk_level(plan.risk_level)
            self._ui.set_state("consent")

            # Start speaking the plan (fire-and-forget)
            speak_task = asyncio.create_task(self._tts.speak(announcement))
            speak_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            self._announce_task = speak_task

            # Set up a future that resolves when the user decides
            loop = asyncio.get_running_loop()
            self._pending = loop.create_future()

            # Connect UI button signals
            self._ui.consentGiven.connect(self._resolve_from_ui)

            # Also listen for voice keywords in parallel with explicit cancellation event
            cancel_evt = threading.Event()
            voice_task = asyncio.create_task(self._listen_for_voice(cancel_evt))

            try:
                approved: bool = await asyncio.wait_for(
                    asyncio.shield(self._pending),
                    timeout=self._config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning("[Consent] Timed out after {}s — defaulting to DENY", self._config.timeout_seconds)
                approved = False
            finally:
                cancel_evt.set()
                voice_task.cancel()
                if not speak_task.done():
                    speak_task.cancel()
                self._announce_task = None
                try:
                    self._ui.consentGiven.disconnect(self._resolve_from_ui)
                except Exception as e:
                    logger.debug(f"[ConsentGate] Could not disconnect signal: {e}")
                if self._pending and not self._pending.done():
                    self._pending.cancel()
                self._pending = None

            # JARVIS Security: Log the decision
            self._log_security_event(
                "consent_granted" if approved else "consent_denied",
                plan,
                f"User {'approved' if approved else 'denied'} action"
            )

            # Acknowledge result
            if approved:
                await self._tts.speak("Understood. Proceeding now.")
                logger.info("[Consent] ✓ Approved")
            else:
                await self._tts.speak("Okay, I've cancelled that action.")
                logger.info("[Consent] ✗ Denied")

            self._ui.set_state("idle")
            return approved

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _format_announcement(self, plan: ActionPlan) -> str:
        # NOTE: the closing question must never contain an approval keyword
        # (e.g. "go ahead", "proceed", "okay") — the mic listens while speaking
        # and would otherwise treat Baby's own announcement as consent.
        preamble = RISK_PREAMBLES.get(plan.risk_level, "I'm going to")
        return f"{preamble} {plan.description}. Shall I continue?"

    @staticmethod
    def _matches_keywords(text_lower: str, keywords: list[str]) -> bool:
        """Single words must match exactly; multi-word phrases as substrings.

        Avoids false triggers like "no" inside "know" or "okay" inside a longer
        sentence.
        """
        words = set(text_lower.split())
        for kw in keywords:
            kw = kw.strip().lower()
            if not kw:
                continue
            if " " in kw:
                if kw in text_lower:
                    return True
            elif kw in words:
                return True
        return False

    def _resolve(self, approved: bool):
        if self._pending and not self._pending.done():
            self._pending.set_result(approved)

    def _resolve_from_ui(self, approved: bool):
        """Called by PySide6 signal — needs to be thread-safe."""
        if self._pending and not self._pending.done():
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._resolve, approved)
            except RuntimeError:
                pass

    async def _listen_for_voice(self, cancel_evt: threading.Event):
        """Continuously listen for approval/denial keywords during the consent window.

        Waits for the announcement to finish speaking first, so Baby never
        transcribes (and thereby approves) her own voice.
        """
        task = getattr(self, "_announce_task", None)
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                return
            except Exception:
                pass
        try:
            while True:
                if cancel_evt.is_set():
                    return
                audio = await self._vad.capture_until_silence(silence_ms=500, cancel_token=cancel_evt)
                if cancel_evt.is_set():
                    return
                text, _ = await self._stt.transcribe(audio)
                text_lower = text.lower().strip()
                logger.debug("[Consent] Heard: '{}'", text_lower)

                if self._matches_keywords(text_lower, self._config.approve_keywords):
                    self._resolve(True)
                    return
                elif self._matches_keywords(text_lower, self._config.deny_keywords):
                    self._resolve(False)
                    return
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("[Consent] Voice listen error: {}", e)
            await asyncio.sleep(0.5)
        finally:
            cancel_evt.set()



















