"""
core/orchestrator.py — The central async brain of Baby.
Connects every subsystem and drives the full conversation loop.
"""

from __future__ import annotations
import asyncio
import datetime as dt
import re
import sys
import traceback
from pathlib import Path

import numpy as np
from loguru import logger
from PySide6.QtCore import QMetaObject, Qt


def _resolve_bundle_path(rel_path: str) -> Path:
    """Resolve a relative path for both development and PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / rel_path

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from core.config import BabyConfig
from core.context_manager import ContextManager
from core.command_refiner import CommandRefiner
from core.dictation_expander import DictationExpander
from core.consent_gate import ConsentGate, ActionPlan
from core.event_bus import get_bus, Event, EventType
from core.memory_engine import get_memory
from core.languages import SPOKEN_LANGUAGES, LANGUAGE_NAMES
from audio.wake_word import WakeWordDetector
from audio.admin_phrase import AdminPhraseDetector
from audio.vad import VADEngine, BargeInMonitor
from audio.stt import STTEngine
from audio.tts import TTSEngine
from biometrics.biometric_db import BiometricDB
from biometrics.voice_id import VoiceIdentifier
from biometrics.face_id import FaceIdentifier
from llm import get_llm_client
from tools.file_tools import FILE_TOOLS_SCHEMA, execute_tool, TOOL_RISK
from tools.screen_tools import SCREEN_TOOLS_SCHEMA, execute_screen_tool, SCREEN_TOOL_RISK
from tools.math_tools import MATH_TOOLS_SCHEMA, execute_math_tool, MATH_TOOL_RISK
from core.privacy_guard import PrivacyGuard
from antigravity.admin import AntiGravityAdmin
from antigravity.goal_tracker import GoalPlan
from core.relationship_engine import RelationshipEngine, RelationshipEngineConfig

# Enroll trigger — "Baby, this is my friend <Name>"
# Relationship tags the user can use when introducing someone.
_RELATIONSHIP_TAGS = (
    "friend", "best friend", "colleague", "boss", "wife", "husband", "partner",
    "mother", "mom", "mum", "father", "dad", "sister", "brother", "son", "daughter",
    "grandmother", "grandfather", "aunt", "uncle", "cousin", "roommate", "neighbor",
    "girlfriend", "boyfriend", "spouse",
)

# ─── Localized spoken phrases (greetings / reminders / proactive heads-up) ────
_GREETINGS = {
    "en": {"morning": "Good morning, {name}!", "afternoon": "Good afternoon, {name}!", "evening": "Good evening, {name}!"},
    "hi": {"morning": "सुप्रभात, {name}!", "afternoon": "नमस्ते, {name}!", "evening": "शुभ संध्या, {name}!"},
    "kn": {"morning": "ಶುಭೋದಯ, {name}!", "afternoon": "ನಮಸ್ಕಾರ, {name}!", "evening": "ಶುಭ ಸಂಜೆ, {name}!"},
    "mr": {"morning": "शुभ प्रभात, {name}!", "afternoon": "नमस्कार, {name}!", "evening": "शुभ संध्याकाळ, {name}!"},
    "ta": {"morning": "காலை வணக்கம், {name}!", "afternoon": "மதிய வணக்கம், {name}!", "evening": "மாலை வணக்கம், {name}!"},
    "te": {"morning": "శుభోదయం, {name}!", "afternoon": "నమస్కారం, {name}!", "evening": "శుభ సాయంత్రం, {name}!"},
}

_TIMER_PHRASES = {
    "en": "Time's up! Your timer for {text} is done.",
    "hi": "समय पूरा हो गया! आपका {text} टाइमर पूरा हुआ।",
    "kn": "ಸಮಯ ಮುಗಿಯಿತು! ನಿಮ್ಮ {text} ಟೈಮರ್ ಪೂರ್ಣಗೊಂಡಿದೆ.",
    "mr": "वेळ संपली! तुमचा {text} टाइमर पूर्ण झाला.",
    "ta": "நேரம் முடிந்துவிட்டது! உங்கள் {text} டைமர் முடிந்தது.",
    "te": "టైమ్ అయిపోయింది! మీ {text} టైమర్ పూర్తయింది.",
}

_ALARM_PHRASES = {
    "en": "Good morning! It's {clock} — {text}.",
    "hi": "सुप्रभात! {clock} बज गए हैं — {text}।",
    "kn": "ಶುಭೋದಯ! ಈಗ {clock} — {text}.",
    "mr": "शुभ प्रभात! {clock} वाजले — {text}.",
    "ta": "காலை வணக்கம்! இப்போது {clock} — {text}.",
    "te": "శుభోదయం! ఇప్పుడు {clock} — {text}.",
}

_REMINDER_PREFIXES = {
    "en": "Reminder: ",
    "hi": "अनुस्मारक: ",
    "kn": "ಜ್ಞಾಪನೆ: ",
    "mr": "आठवण: ",
    "ta": "நினைவூட்டல்: ",
    "te": "రిమైండర్: ",
}

_HEADS_UP_PHRASES = {
    "en": "By the way, you have {n} upcoming reminder(s): {text}.",
    "hi": "वैसे, आपके पास {n} आने वाले अनुस्मारक हैं: {text}।",
    "kn": "ಅಂದಹಾಗೆ, ನಿಮಗೆ {n} ಮುಂಬರುವ ಜ್ಞಾಪನೆಗಳಿವೆ: {text}.",
    "mr": "तसे, तुमच्याकडे {n} आगामी आठवणी आहेत: {text}.",
    "ta": "மேலும், உங்களுக்கு {n} வரவிருக்கும் நினைவூட்டல்கள் உள்ளன: {text}.",
    "te": "అంతేకాకుండా, మీకు {n} రాబోయే రిమైండర్లు ఉన్నాయి: {text}.",
}

# Captures: "Baby, this is my sister Priya" -> tag="sister", name="Priya"
# Also: "Baby this is Priya" -> no tag, name="Priya"
_ENROLL_RE = re.compile(
    r"(?:baby[,\s]+)?this is (?:my (" + "|".join(_RELATIONSHIP_TAGS) + r")\s+)?([A-Z][a-z]+)",
    re.IGNORECASE,
)

# Face enrollment — "enroll my face as Boss" / "register face as Priya"
_FACE_ENROLL_RE = re.compile(
    r"(?:register|enroll|save)\s+(?:my\s+)?face(?:\s+as\s+([A-Z][\w\s]*))?",
    re.IGNORECASE,
)

# Admin enrollment — "enroll as admin" / "register as master" / "make me admin"
_ADMIN_ENROLL_RE = re.compile(
    r"(?:enroll|register|make)\s+(?:me\s+)?(?:as\s+)?(?:admin|master|owner)",
    re.IGNORECASE,
)

# Admin logout — "log out admin" / "deactivate admin" / "remove admin"
_ADMIN_LOGOUT_RE = re.compile(
    r"(?:log\s+out|deactivate|remove)\s+(?:the\s+)?admin",
    re.IGNORECASE,
)

# Admin-only commands — training, settings, profile management
_ADMIN_COMMANDS_RE = re.compile(
    r"(?:train|fine[\s-]?tune|prepare\s+data|create\s+modelfile|"
    r"open\s+settings|change\s+settings|update\s+settings|"
    r"promote\s+(?:to\s+)?admin|delete\s+profile|remove\s+profile)",
    re.IGNORECASE,
)

# Personal commands — websites, apps, files, messages (admin only)
# Non-admin users can access: chrome, firefox, edge, browser, notepad
_PERSONAL_COMMANDS_RE = re.compile(
    r"open\s+(?:chrome|firefox|edge|browser|website|url|http|www|\.com|\.org|\.net|"
    r"whatsapp|telegram|instagram|email|outlook|gmail|"
    r"file|folder|document|explorer|finder|"
    r"vscode|code|notepad|word|excel|powerpoint|"
    r"spotify|youtube|netflix|steam|discord)|"
    r"send\s+(?:message|email|whatsapp|telegram|instagram)|"
    r"write\s+(?:email|message)|"
    r"access\s+(?:file|folder|document|profile|account)|"
    r"show\s+(?:file|folder|document|photo|image|video)|"
    r"read\s+(?:file|document|email|message)|"
    r"delete\s+(?:file|document|folder)|"
    r"launch\s+(?:app|application|program|website|chrome|firefox|edge|browser|notepad)",
    re.IGNORECASE,
)


def _strip_punct(text: str) -> str:
    """Lower-case, keep alphanumerics + spaces — for echo/copy comparison."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower())


class BabyOrchestrator:
    def __init__(self, config: BabyConfig, ui, pointer):
        self._cfg     = config
        self._ui      = ui
        self._pointer = pointer
        self._bus     = get_bus()

        # ── Audio subsystems ──────────────────────────────────────────────────
        self._vad         = VADEngine(
            threshold=config.audio.vad_threshold,
            silence_ms=config.audio.silence_threshold_ms,
            device_index=config.audio.device_index,
        )
        self._stt         = STTEngine(config.stt)
        self._tts         = TTSEngine(config.tts)
        self._barge_in    = BargeInMonitor(
            threshold=config.audio.barge_in_vad_threshold,
            device_index=config.audio.device_index,
        )
        self._wake        = WakeWordDetector(
            model_path=str(_resolve_bundle_path(config.wake_word.model_path)),
            threshold=config.wake_word.threshold,
            device_index=config.audio.device_index,
        )
        self._admin_phrase = AdminPhraseDetector(
            model_path=str(_resolve_bundle_path(config.admin_phrase.model_path)),
            threshold=config.admin_phrase.threshold,
            device_index=config.audio.device_index,
        )

        # ── Biometrics ────────────────────────────────────────────────────────
        self._bio_db      = BiometricDB(
            db_path=config.biometrics.db_path,
            key_backend=config.biometrics.key_backend,
        )
        self._voice_id    = VoiceIdentifier(
            db=self._bio_db,
            threshold=config.biometrics.voice_similarity_threshold,
        )
        self._face_id     = FaceIdentifier(
            db=self._bio_db,
            threshold=config.biometrics.face.similarity_threshold,
        )

        # ── Home Assistant ──────────────────────────────────────────────────────
        from tools.home_assistant_tools import HomeAssistantClient, set_ha_client
        ha_cfg = config.home_assistant
        if ha_cfg.url and ha_cfg.token:
            self._ha_client = HomeAssistantClient(ha_cfg)  # type: ignore[arg-type]
            asyncio.create_task(self._ha_client.connect())
            set_ha_client(self._ha_client)
            logger.info("[Orchestrator] Home Assistant client initialized")
        else:
            self._ha_client = None
            logger.info("[Orchestrator] Home Assistant not configured (set URL and token in config.yaml)")

        # ── LLM ───────────────────────────────────────────────────────────────
        self._llm         = get_llm_client(config.llm)
        self._planner_llm = get_llm_client(config.llm)  # Separate planner model (can be overridden)

        # ── Context & consent ─────────────────────────────────────────────────
        self._ctx         = ContextManager(persona=getattr(config.tts, "persona", "friendly"))
        self._consent     = ConsentGate(
            config=config.consent,
            tts=self._tts,
            stt=self._stt,
            vad=self._vad,
            ui_controller=self._ui,
        )

        # ── Privacy Middleware ────────────────────────────────────────────────
        self._privacy     = PrivacyGuard(enabled=config.privacy.pii_redaction_enabled)

        # ── Command refiner (summarize + grammar-correct before the assistant) ──
        self._refine_enabled = getattr(config.llm, "refine_commands", True)
        self._refiner        = CommandRefiner(self._llm)

        # ── Anti-Gravity Administrator (multi-agent backend brain) ─────────────
        self._antigravity = AntiGravityAdmin(
            llm=self._llm,
            guard=self._privacy,
            learner_config=config.learner
        )

        # ── Relationship Engine (action pair classification) ──────────────────
        self._relationship_engine = RelationshipEngine(config.relationship_engine)  # type: ignore[arg-type]
        self._current_relationships: list[dict] = []

        # ── Background Task Queue ─────────────────────────────────────────────
        from core.background_tasks import BackgroundTaskQueue
        self._bg_queue = BackgroundTaskQueue(max_concurrent=2)
        self._bg_queue.on_complete(self._on_background_task_complete)

        # ── Adaptive Memory (learns from every turn) ─────────────────────────
        self._memory      = get_memory()

        # ── Context Awareness (JARVIS-level system intelligence) ──────────────
        from core.context_awareness import get_context_awareness
        self._context = get_context_awareness()

        # ── Timer / Reminder / Alarm engine ─────────────────────────────────
        from core.reminders import ReminderService, init_reminder_service
        self._reminders = ReminderService(store_path=Path(self._cfg.app.data_dir) / "reminders.json")
        init_reminder_service(self._reminders)
        self._reminder_task: asyncio.Task | None = None
        self._reminder_running = False

        # ── Fast-path plan cache ─────────────────────────────────────────────
        self._fast_path_cache: dict[str, tuple[float, GoalPlan]] = {}
        self._fast_path_cache_ttl = 300.0  # 5 minutes

        # ── Intent classifier (lightweight, runs before LLM planner) ─────────
        self._intent_classifier = None
        self._init_intent_classifier()

        # ── Ollama health check ──────────────────────────────────────────────
        self._ollama_health_task: asyncio.Task | None = None
        self._ollama_healthy = True

        # ── State ─────────────────────────────────────────────────────────────
        self._current_speaker: str | None = None
        self._current_speaker_relationship: str = ""
        self._current_speaker_id: int | None = None
        self._last_user_text: str = ""
        self._last_partial_resp: str = ""
        self._is_activated: bool = False
        self._last_toggle_at: float | None = None
        self._current_turn_task: asyncio.Task | None = None
        self._last_user_lang: str = "en"

        # ── Enrollment State ──────────────────────────────────────────────────
        self._enrollment_state: str | None = None  # "waiting_for_name", "capturing_face", "waiting_for_voice"
        self._enrollment_name: str | None = None
        self._enrollment_relationship: str | None = None

        # ── Session State ───────────────────────────────────────────────────────
        self._greeting_spoken_this_session: bool = False
        self._is_recording_voice: bool = False
        self._admin_voice_audio = None
        self._admin_voice_frames: list = []
        self._admin_face_frame = None

        # ── Security State ────────────────────────────────────────────────────
        self._security_lockout_until: float = 0  # Timestamp when lockout expires
        self._security_violations: int = 0  # Count of violations by non-admin
        self._max_violations_before_lock: int = 3

        # ── Last opened app/window for pronoun resolution ─────────────────────
        self._last_opened_app: str | None = None
        self._last_opened_window: str | None = None

        # ── Event Subscriptions ───────────────────────────────────────────────
        self._bus.subscribe(EventType.CONFIG_CHANGED, self._on_config_changed)
        self._bus.subscribe(EventType.WAKE_WORD_DETECTED, self._on_wake_word_detected)
        self._bus.subscribe(EventType.ADMIN_PHRASE_DETECTED, self._on_admin_phrase_detected)

    def _is_current_speaker_admin(self) -> bool:
        """All users are treated as admin."""
        return True

    async def _verify_admin_via_face(self) -> bool:
        """Verify if the person in front of the camera is the admin.
        Turns on camera, captures frame, runs face identification, then turns off camera.
        Returns True if admin face detected, False otherwise.
        """
        try:
            logger.info("[FaceVerify] Starting admin face verification...")
            
            # Turn on camera preview
            self._ui.setCameraPreviewVisible(True)
            
            # Wait for camera to start and capture a frame
            await asyncio.sleep(1.5)  # Give camera time to initialize
            
            # Get camera frame
            frame = self._ui.get_camera_frame()
            if frame is None:
                logger.warning("[FaceVerify] No camera frame available")
                self._ui.setCameraPreviewVisible(False)
                return False
            
            # Identify face
            name, profile_id, _rel = self._face_id.identify(frame)
            
            # Turn off camera preview
            self._ui.setCameraPreviewVisible(False)
            
            if profile_id is not None and self._bio_db.is_admin(profile_id):
                logger.success(f"[FaceVerify] Admin verified: {name} (id={profile_id})")
                # Update current speaker to admin
                self._current_speaker = name
                self._current_speaker_id = profile_id
                self._ui.set_speaker(name)
                return True
            
            logger.warning(f"[FaceVerify] Face not recognized as admin: {name} (id={profile_id})")
            return False
            
        except Exception as e:
            logger.error(f"[FaceVerify] Error during face verification: {e}")
            try:
                self._ui.setCameraPreviewVisible(False)
            except Exception as e:
                logger.debug(f"[FaceVerify] Could not hide camera preview: {e}")
            return False

    async def _ensure_admin_verified(self) -> bool:
        """Verify admin via face recognition if admin has face enrolled."""
        admin = self._bio_db.get_admin()
        if admin is None:
            logger.warning("[Auth] No admin profile — treating as unverified")
            return False
        if admin["face_emb"] is None:
            logger.info("[Auth] Admin has no face enrolled — skipping face check")
            return True
        return await self._verify_admin_via_face()

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def shutdown(self):
        """Best-effort synchronous stop of audio threads before process exit.

        Called on exit: the capture/barge-in workers must be stopped BEFORE the
        process exits, otherwise they race it and can crash in qwindows.dll /
        ucrtbase.dll. VAD.stop() and BargeIn.shutdown() wait for the workers.
        """
        self._reminder_running = False
        if self._reminder_task is not None:
            try:
                self._reminder_task.cancel()
            except Exception as e:
                logger.debug(f"[Orchestrator] Error cancelling reminder task: {e}")
            self._reminder_task = None

        # Cancel Ollama health check task
        if self._ollama_health_task is not None:
            try:
                self._ollama_health_task.cancel()
            except Exception as e:
                logger.debug(f"[Orchestrator] Error cancelling health check task: {e}")
            self._ollama_health_task = None

        # Stop relationship engine purity monitor
        if self._relationship_engine.enabled:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._relationship_engine.stop())
                else:
                    loop.run_until_complete(self._relationship_engine.stop())
            except Exception as e:
                logger.debug(f"[Orchestrator] Error stopping relationship engine: {e}")

        for sub in (self._vad, self._wake, self._admin_phrase, self._barge_in):
            try:
                if sub is self._barge_in:
                    sub.shutdown()
                else:
                    sub.stop()
            except Exception as e:
                logger.debug(f"[Orchestrator] Error stopping subsystem {sub.__class__.__name__}: {e}")

    # ─── Relationship Engine API ─────────────────────────────────────────────

    async def explain_relationship(self, action_a: str, action_b: str) -> dict:
        """Explain the relationship between two actions.

        Public API for the relationship engine. Returns a dict with:
        type, confidence, keywords, explanation, validated, networks_used
        """
        return await self._relationship_engine.explain_relationship(action_a, action_b)

    # ─── Reminder / timer / alarm loop ────────────────────────────────────────

    async def _reminder_loop(self) -> None:
        """Poll the reminder store every 5s and announce anything due."""
        import time
        last_cleanup = time.time()
        while self._reminder_running:
            try:
                for entry in self._reminders.due():
                    self._reminders.mark_fired(entry)
                    asyncio.create_task(self._announce_reminder(entry))
                now = time.time()
                if now - last_cleanup > 3600:
                    self._reminders.clear_fired()
                    last_cleanup = now
            except Exception as e:
                logger.warning("[Reminders] Loop error: {}", e)
            await asyncio.sleep(5)

    async def _announce_reminder(self, entry) -> None:
        text = self._format_reminder_announcement(entry)
        logger.info("[Reminders] FIRING: {}", text)
        try:
            self._ui.set_state("speaking")
            self._ui.set_transcript(text)
            self._ui.set_assistant_response(text)
            await self._tts.speak(text)
        except Exception as e:
            logger.warning("[Reminders] Announcement failed: {}", e)
        finally:
            self._ui.set_state("idle")

    def _format_reminder_announcement(self, entry) -> str:
        lang = self._announce_lang()
        clock = dt.datetime.fromtimestamp(entry.due_at).strftime("%I:%M %p").lstrip("0")
        text = entry.text or ""
        if entry.kind == "timer":
            return _TIMER_PHRASES.get(lang, _TIMER_PHRASES["en"]).format(text=text or "this task")
        if entry.kind == "alarm":
            return _ALARM_PHRASES.get(lang, _ALARM_PHRASES["en"]).format(clock=clock, text=text or "the alarm is ringing")
        return f"{_REMINDER_PREFIXES.get(lang, _REMINDER_PREFIXES['en'])}{text}"

    async def start(self):
        """Load all models, warm up LLM, enter event loop."""
        logger.info("[Orchestrator] Loading subsystems...")
        self._ui.set_state("loading")

        results = await asyncio.gather(
            asyncio.to_thread(self._stt.load),
            asyncio.to_thread(self._tts.load),
            asyncio.to_thread(self._voice_id.load),
            asyncio.to_thread(self._face_id.load),
            asyncio.to_thread(self._warm_vision_ocr),  # Warm OCR model in parallel
            return_exceptions=True,
        )
        for res in results:
            if isinstance(res, Exception):
                logger.warning("[Orchestrator] Subsystem load error (continuing): {}", res)
        await self._llm.warm_up()

        # Connect UI activation and mute signals
        self._ui.toggleActivation.connect(self._on_ui_toggle_threadsafe)
        self._ui.micMutedChanged.connect(self._on_mic_mute_changed_threadsafe)
        self._ui.speakerMutedChanged.connect(self._on_speaker_mute_changed_threadsafe)

        # Apply the CURRENT privacy state (OS mic toggle off / volume at 0
        # detected at startup) so the assistant starts silent if it must.
        self._on_mic_mute_changed(self._ui.micMuted)
        self._on_speaker_mute_changed(self._ui.speakerMuted)

        # Start relationship engine purity monitor
        if self._relationship_engine.enabled:
            await self._relationship_engine.start()
            logger.info("[Orchestrator] Relationship engine started ✓")

        logger.success("[Orchestrator] BABY is ready ✓")

        # Pre-warm the Silero VAD so the FIRST conversation turn starts
        # immediately instead of stalling while the model loads.
        try:
            from audio.vad import get_silero
            await asyncio.to_thread(get_silero)
            logger.success("[Orchestrator] Silero VAD pre-warmed ✓")
        except Exception as _vad_err:
            logger.warning("[Orchestrator] Silero pre-warm failed (non-fatal): {}", _vad_err)

        self._wake.set_muted(False)
        self._wake.start()

        # Start admin phrase detector if enabled
        if self._cfg.admin_phrase.enabled:
            self._admin_phrase.set_muted(False)
            self._admin_phrase.start()
            logger.info("[Orchestrator] Admin phrase detector started ✓")

        # Start the reminder/timer/alarm engine — catches up anything missed
        # while the app was closed (within a sane window).
        self._reminder_running = True
        self._reminder_task = asyncio.create_task(self._reminder_loop())

        # Start Ollama health check background task
        self._ollama_health_task = asyncio.create_task(self._ollama_health_check_loop())

        self._ui.set_state("idle")

    # ─── Intent Classifier ────────────────────────────────────────────────────

    def _init_intent_classifier(self):
        """Initialize lightweight intent classifier for common commands.
        Disabled for now — not used in the conversation flow.
        """
        logger.debug("[Orchestrator] Intent classifier disabled (not used in flow)")
        self._intent_classifier = None

    def _classify_intent(self, text: str) -> str | None:
        """Classify user intent using lightweight classifier."""
        if self._intent_classifier is None:
            return None
        try:
            return self._intent_classifier.predict([text.lower()])[0]
        except Exception as e:
            logger.debug(f"[Orchestrator] Intent classifier error: {e}")
            return None

    # ─── Fast-Path Plan Cache ────────────────────────────────────────────────

    def _get_cached_fast_path(self, key: str) -> GoalPlan | None:
        """Retrieve cached fast-path plan if not expired."""
        import time
        if key in self._fast_path_cache:
            ts, plan = self._fast_path_cache[key]
            if time.time() - ts < self._fast_path_cache_ttl:
                logger.debug("[Orchestrator] Fast-path cache hit for: {}", key)
                return plan
            else:
                del self._fast_path_cache[key]
        return None

    def _cache_fast_path(self, key: str, plan: GoalPlan):
        """Cache fast-path plan with timestamp."""
        import time
        self._fast_path_cache[key] = (time.time(), plan)

    # ─── Ollama Health Check ────────────────────────────────────────────────

    async def _ollama_health_check_loop(self):
        """Background task: ping Ollama /api/tags every 30s, auto-reconnect on failure."""
        import httpx
        base_url = getattr(self._cfg.llm, "base_url", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=5.0) as client:
            while True:
                try:
                    await asyncio.sleep(30)
                    if not self._is_activated:
                        continue
                    resp = await client.get(f"{base_url}/api/tags")
                    was_healthy = self._ollama_healthy
                    self._ollama_healthy = resp.status_code == 200
                    if not was_healthy and self._ollama_healthy:
                        logger.success("[Orchestrator] Ollama reconnected ✓")
                        self._llm = get_llm_client(self._cfg.llm)
                        self._planner_llm = get_llm_client(self._cfg.llm)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self._ollama_healthy = False
                    logger.warning("[Orchestrator] Ollama health check failed: {}", e)

    # ─── LLM Warm-up on Idle ────────────────────────────────────────────────

    async def _warm_llm_on_idle(self):
        """Warm up LLM during wake-word cooldown / idle periods."""
        if self._llm is None or getattr(self._cfg.llm, "test_mode", False):
            return
        try:
            await self._llm.warm_up()
            logger.debug("[Orchestrator] LLM warm-up on idle completed")
        except Exception as e:
            logger.debug("[Orchestrator] LLM warm-up on idle failed: {}", e)

    # ─── Pronoun Resolution ──────────────────────────────────────────────────

    def _resolve_pronoun(self, text: str) -> str:
        """Resolve 'it', 'that', 'them' to last opened app/window."""
        text_lower = text.lower()
        if any(p in text_lower for p in ["close it", "close that", "close them",
                                          "quit it", "quit that", "exit it", "exit that"]):
            if self._last_opened_app:
                return text_lower.replace("it", self._last_opened_app).replace("that", self._last_opened_app)
            elif self._last_opened_window:
                return text_lower.replace("it", self._last_opened_window).replace("that", self._last_opened_window)
        return text

    # ─── Wake word handler ────────────────────────────────────────────────────

    def _dispatch_threadsafe(self, func, *args):
        try:
            loop = getattr(self, "_loop", None)
            if loop is None or not loop.is_running():
                loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(func, *args)
        except Exception as e:
            logger.debug("[Orchestrator] Threadsafe dispatch skipped: {}", e)

    def _on_ui_toggle_threadsafe(self, *a):
        self._dispatch_threadsafe(self._on_ui_toggle)

    def _warm_vision_ocr(self):
        """Pre-warm the OCR engine (pytesseract) so first vision task is fast."""
        try:
            from antigravity.agents.vision_agent import _ensure_tesseract_configured
            _ensure_tesseract_configured()
            import pytesseract
            from PIL import Image
            # Create a tiny dummy image and run OCR to warm up the engine
            img = Image.new('RGB', (100, 30), color='white')
            pytesseract.image_to_string(img)
            logger.debug("[Orchestrator] Vision OCR pre-warmed")
        except Exception as e:
            logger.debug(f"[Orchestrator] OCR warm-up skipped (non-fatal): {e}")

    def _on_mic_mute_changed_threadsafe(self, muted: bool):
        self._dispatch_threadsafe(self._on_mic_mute_changed, muted)

    def _on_speaker_mute_changed_threadsafe(self, muted: bool):
        self._dispatch_threadsafe(self._on_speaker_mute_changed, muted)

    def _on_mic_mute_changed(self, muted: bool):
        logger.info("[Orchestrator] Applying mic mute: {}", muted)
        self._vad.set_muted(muted)
        self._barge_in.set_muted(muted)
        self._wake.set_muted(muted)
        self._admin_phrase.set_muted(muted)

    def _on_speaker_mute_changed(self, muted: bool):
        logger.info("[Orchestrator] Applying speaker mute: {}", muted)
        self._tts.set_muted(muted)

    def _on_ui_toggle(self):
        asyncio.create_task(self._toggle_assistant())

    async def _on_wake_word_detected(self, event: Event):
        if self._is_activated:
            return
        logger.info("[Orchestrator] Wake word detected — activating assistant.")
        await self._toggle_assistant()

    async def _on_admin_phrase_detected(self, event: Event):
        """Handle admin phrase detection — verify voice and grant admin access."""
        logger.info("[Orchestrator] Admin phrase detected — starting voice verification...")
        
        # Capture audio for voice verification
        try:
            # Use VAD to capture a few seconds of audio
            audio = await self._vad.capture_until_silence(lead_in_skip_s=0.0, max_duration_s=5.0)
            if audio is None or len(audio) == 0:
                logger.warning("[AdminAuth] No audio captured for verification")
                await self._tts.speak("I didn't hear anything. Please try again.")
                return
            
            # Verify voice against enrolled admin
            name, profile_id, relationship = self._voice_id.identify(audio)
            
            if profile_id is not None and self._bio_db.is_admin(profile_id):
                # Success - grant admin access
                self._current_speaker = name
                self._current_speaker_id = profile_id
                self._current_speaker_relationship = "admin"
                self._ui.set_speaker(f"{name} (admin)")
                
                logger.success(f"[AdminAuth] Admin verified via voice: {name} (id={profile_id})")
                await self._tts.speak(f"Welcome back, {name}. Admin access granted.")
                
                # Activate admin theme (black + gold)
                self._set_admin_theme(True)
                
                # If assistant is not activated, activate it
                if not self._is_activated:
                    await self._toggle_assistant()
            else:
                logger.warning(f"[AdminAuth] Voice verification failed: {name} (id={profile_id})")
                await self._tts.speak("Voice not recognized as admin. Access denied.")
                
        except Exception as e:
            logger.error(f"[AdminAuth] Error during admin verification: {e}")
            await self._tts.speak("Verification failed. Please try again.")

    def _set_admin_theme(self, active: bool):
        """Activate/deactivate admin theme (black + gold) on the UI."""
        try:
            self._dispatch_threadsafe(lambda: getattr(self._ui, "setAdminTheme", lambda a: None)(active))
        except Exception as e:
            logger.warning("[Orchestrator] Failed to set admin theme: {}", e)

    async def _toggle_assistant(self):
        # Guard against rapid re-toggles (e.g. a stray second toggle signal
        # firing milliseconds after activation, or the wake-word keyboard
        # fallback echoing a toggle). Without this, a double-signal would
        # activate then immediately deactivate — ending the continuous loop
        # right after the greeting.
        import time as _time
        now = _time.monotonic()
        if self._last_toggle_at is not None and (now - self._last_toggle_at) < 0.6:
            logger.info("[Orchestrator] Ignored toggle within cooldown window.")
            return
        self._last_toggle_at = now

        if self._is_activated:
            logger.info("[Orchestrator] Deactivating assistant...")
            self._is_activated = False
            self._ui.set_activated(False)
            self._tts.stop()
            if self._current_turn_task and not self._current_turn_task.done():
                self._current_turn_task.cancel()
            self._ui.set_state("idle")
            self._ui.set_mic_active(False)
            # Deactivate admin theme on deactivation
            self._set_admin_theme(False)
            await self._tts.speak("Goodbye!")
            self._wake.set_muted(False)
            return

        # Activate assistant
        self._is_activated = True
        self._greeting_spoken_this_session = False
        self._ui.set_activated(True)
        self._wake.set_muted(True)
        self._ui.set_state("activating")
        logger.info("[Orchestrator] Activating assistant (continuous mode)...")
        if self._current_turn_task and not self._current_turn_task.done():
            self._current_turn_task.cancel()

        # Warm up LLM in background while UI activates (parallel with first turn)
        asyncio.create_task(self._warm_llm_on_idle())

        self._current_turn_task = asyncio.create_task(self._continuous_loop())

    async def _continuous_loop(self):
        try:
            is_first = True
            while self._is_activated:
                try:
                    await self._conversation_turn(speak_prompt=is_first)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # A single bad turn must never terminate the whole session.
                    logger.exception("[Orchestrator] Turn failed, continuing: {}", exc)
                    self._ui.set_state("idle")
                    self._ui.set_mic_active(False)
                    if self._is_activated:
                        await self._tts.speak("Oops, something went wrong on my end. Let's try that again.")
                is_first = False
                # Keep the turn loop tight so the assistant feels responsive.
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            logger.info("[Orchestrator] Continuous loop task cancelled.")
        finally:
            self._is_activated = False
            self._ui.set_activated(False)
            self._ui.set_state("idle")
            self._ui.set_mic_active(False)

    def _reminder_heads_up(self) -> str:
        """Proactive: mention pending reminders at the start of a session."""
        try:
            items = self._reminders.list()
            if not items:
                return ""
            upcoming = items[:3]
            parts = []
            for r in upcoming:
                t = dt.datetime.fromtimestamp(r.due_at).strftime("%I:%M %p").lstrip("0")
                parts.append(f"{r.text} at {t}")
            text = ", and ".join(parts)
            n = len(items)
            if n > 3:
                text += f", and {n - 3} more"
            lang = self._announce_lang()
            phrase = _HEADS_UP_PHRASES.get(lang, _HEADS_UP_PHRASES["en"])
            return phrase.format(n=n, text=text)
        except Exception as e:
            logger.warning("[Orchestrator] Reminder heads-up failed: {}", e)
            return ""

    def _announce_lang(self) -> str:
        """Language for proactive announcements (reminders etc.)."""
        if getattr(self, "_last_user_lang", None) in SPOKEN_LANGUAGES:
            return self._last_user_lang
        configured = (self._cfg.ui.language or "auto").strip().lower()
        if configured in SPOKEN_LANGUAGES:
            return configured
        return "en"

    # ─── Main conversation turn ───────────────────────────────────────────────

    async def _conversation_turn(self, merged_prompt: str | None = None, speak_prompt: bool = True):
        # 1. Listen
        self._ui.set_state("listening")
        self._ui.set_mic_active(True)
        if speak_prompt:
            greeting = self._get_time_based_greeting()
            heads_up = self._reminder_heads_up()
            if heads_up:
                greeting = f"{greeting} {heads_up}"
            self._last_partial_resp = greeting
            await self._tts.speak(greeting)

        audio = None
        user_lang = "en"
        if merged_prompt:
            user_text = merged_prompt
        else:
            # Skip a short lead-in so Baby's own reply (still echoing from the
            # speakers) is not captured as the user's next command. Also retry a
            # few times so a single empty/hallucinated transcription does not
            # silently end the turn.
            MAX_LISTEN_TRIES = 3
            lead_in = getattr(self._cfg.audio, "listen_lead_in_s", 0.0)
            for attempt in range(MAX_LISTEN_TRIES):
                audio = await self._vad.capture_until_silence(lead_in_skip_s=lead_in)
                if not self._is_activated:
                    return
                if audio is None:
                    audio = np.zeros(0, dtype=np.float32)
                logger.info("[Orchestrator] Captured {} audio samples — transcribing...", len(audio))
                user_text, user_lang = await self._stt.transcribe(audio)
                logger.info("[Orchestrator] Transcription: '{}' (lang={})", user_text, user_lang)

                # Resolve pronouns (it/that) to last opened app/window
                user_text = self._resolve_pronoun(user_text)
                if user_text != user_text.lower():  # Only log if changed
                    logger.info("[Orchestrator] Pronoun resolved: '{}'", user_text)

                # Scrub PII before any echo / emptiness checks.
                user_text, was_redacted = self._privacy.scrub(user_text)
                if was_redacted:
                    logger.info("[Orchestrator] PII redacted from prompt: {}", user_text)

                # Ignore empty transcriptions (silence / hallucination discarded).
                if not user_text.strip():
                    logger.info("[Orchestrator] Empty transcription (attempt {}/{}).", attempt + 1, MAX_LISTEN_TRIES)
                    continue

                # Ignore echo of Baby's own last reply bleeding into the mic.
                if self._last_partial_resp and self._looks_like_echo(user_text):
                    logger.info("[Orchestrator] Ignored self-echo transcription: '{}'", user_text)
                    user_text = ""
                    continue

                break
            else:
                # No speech detected during this listen window — remain active in continuous mode
                logger.info("[Orchestrator] Silence during listen window — remaining active in continuous listening mode.")
                return

        # Scrub PII (only on the merged-prompt branch; listen branch already scrubbed)
        if merged_prompt:
            user_text, was_redacted = self._privacy.scrub(user_text)
            if was_redacted:
                logger.info("[Orchestrator] PII redacted from prompt: {}", user_text)

        self._tts.set_last_language(user_lang)
        self._last_user_lang = user_lang

        self._ui.set_state("thinking")
        self._ui.set_mic_active(False)
        self._last_user_text = user_text
        self._ui.set_transcript(user_text)
        logger.info("[User] {}", user_text)

        if not user_text.strip():
            logger.info("[Orchestrator] Empty transcription. Returning.")
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 2. Biometric speaker ID
        if not merged_prompt and audio is not None:
            name, pid, rel = self._voice_id.identify(audio)
            if name:
                self._current_speaker = name
                self._current_speaker_id = pid
                if rel:
                    self._current_speaker_relationship = rel
                self._ui.set_speaker(name)

        # 2a. Handle enrollment state
        if self._enrollment_state == "waiting_for_name":
            # Extract name from user text
            name_match = re.search(r"(?:my name is|i am|i'm)\s+([A-Z][a-z]+)", user_text, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip().title()
                await self._continue_admin_enrollment_name(name)
            else:
                # Try to use the text as a name
                words = user_text.strip().split()
                if len(words) <= 3 and all(w[0].isupper() for w in words if w):
                    await self._continue_admin_enrollment_name(user_text.strip().title())
                else:
                    await self._tts.speak("I didn't catch your name. Please say 'My name is' followed by your name.")
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        elif self._enrollment_state == "waiting_for_voice":
            if audio is not None:
                await self._complete_admin_enrollment_voice(audio)
            else:
                await self._tts.speak("I couldn't hear your voice. Please read the paragraph again.")
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 3. Check for enroll command
        if await self._check_enroll(user_text, audio if (not merged_prompt and audio is not None) else None):
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 3a. Check for face enroll command
        if await self._check_face_enroll(user_text):
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 3b. Check for admin enrollment command
        if await self._check_admin_enroll(user_text, audio if (not merged_prompt and audio is not None) else None):
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 3b. Help command for regular users
        if re.search(r"\b(?:what\s+can\s+you\s+do|help|commands|capabilities)\b", user_text, re.IGNORECASE):
            if not await self._ensure_admin_verified():
                await self._tts.speak(
                    "Hello! I can help you with several things. "
                    "You can ask me to calculate math problems like 'calculate 2 plus 2'. "
                    "You can ask me questions like 'what is artificial intelligence'. "
                    "You can set reminders like 'remind me at 3pm to call mom'. "
                    "You can ask me to explain things like 'explain quantum physics'. "
                    "You can also open Chrome, Firefox, Edge, or Notepad. "
                    "For other personal tasks like opening apps or files, please ask the admin."
                )
                if not self._is_activated:
                    self._ui.set_state("idle")
                return

        # 3c. Security lockout check
        import time
        if time.time() < self._security_lockout_until:
            remaining = int(self._security_lockout_until - time.time())
            await self._tts.speak(
                f"Security lockout active. Please wait {remaining} seconds."
            )
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 3c. Admin logout command
        if _ADMIN_LOGOUT_RE.search(user_text):
            if self._current_speaker_id is not None and self._bio_db.is_admin(self._current_speaker_id):
                self._current_speaker = None
                self._current_speaker_id = None
                self._current_speaker_relationship = ""
                self._ui.set_speaker("")
                self._set_admin_theme(False)
                await self._tts.speak("Admin access revoked. Goodbye.")
                logger.info("[Orchestrator] Admin logged out via voice command")
            else:
                await self._tts.speak("No admin is currently logged in.")
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 3d. Admin-only command check (settings, training)
        if _ADMIN_COMMANDS_RE.search(user_text):
            if not await self._ensure_admin_verified():
                self._security_violations += 1
                if self._security_violations >= self._max_violations_before_lock:
                    self._security_lockout_until = time.time() + 300  # 5 min lock
                    self._security_violations = 0
                    await self._tts.speak(
                        "Security lockout activated. You have attempted restricted commands multiple times. "
                        "The system is now locked for 5 minutes."
                    )
                else:
                    remaining_attempts = self._max_violations_before_lock - self._security_violations
                    await self._tts.speak(
                        f"Sorry, only the admin can perform that action. "
                        f"You have {remaining_attempts} attempts remaining before lockout."
                    )
                if not self._is_activated:
                    self._ui.set_state("idle")
                return

        # 3e. Personal command check (websites, apps, files, messages)
        # Allow Chrome and Notepad for all users
        personal_match = _PERSONAL_COMMANDS_RE.search(user_text)
        if personal_match:
            matched_cmd = personal_match.group(0).lower()
            # Check if it's only chrome or notepad - allow for all users
            is_chrome_or_notepad = any(x in matched_cmd for x in ["chrome", "firefox", "edge", "browser", "notepad"])
            
            if not is_chrome_or_notepad:
                # For other apps/files, require admin
                if not await self._ensure_admin_verified():
                    self._security_violations += 1
                    if self._security_violations >= self._max_violations_before_lock:
                        self._security_lockout_until = time.time() + 300  # 5 min lock
                        self._security_violations = 0
                        await self._tts.speak(
                            "Security lockout activated. You have attempted restricted commands multiple times. "
                            "The system is now locked for 5 minutes."
                        )
                    else:
                        remaining_attempts = self._max_violations_before_lock - self._security_violations
                        await self._tts.speak(
                            f"Sorry, I cannot open applications or access personal files for non-admin users. "
                            f"You have {remaining_attempts} attempts remaining before lockout."
                        )
                    if not self._is_activated:
                        self._ui.set_state("idle")
                    return

        # 3e. Voice-dictation expansion: "open bracket" → "(", "excetra" → "etc",
        # "next" → "," (only in dictation context — see dictation_expander).
        if getattr(self._cfg.audio, "expand_dictation", True):
            expanded = DictationExpander.expand(user_text)
            if expanded != user_text:
                logger.info("[Orchestrator] Dictation expanded: '{}' → '{}'", user_text, expanded)
                user_text = expanded

        # 3c. Summarize / grammar-correct the command BEFORE the assistant sees it.
        # Zero-LLM fast-path commands are skipped (their keyword parsers run on
        # the raw text); everything else is rewritten preserving the exact
        # meaning and language (en/hi/kn).
        if self._refine_enabled:
            fast_path_used = False
            try:
                fast_path_used = self._antigravity._fast_path_plan(user_text, user_lang) is not None
            except Exception:
                fast_path_used = False
            if not fast_path_used:
                original = user_text
                user_text = await self._refiner.refine(user_text, user_lang)
                if user_text != original:
                    logger.info("[Orchestrator] Command refined: '{}' → '{}'", original, user_text)

        # 4. Build message context
        # Use the speaker's actual name if known, otherwise "master"
        if self._current_speaker:
            display_name = self._current_speaker
            if self._current_speaker_relationship:
                display_name = f"{self._current_speaker} (the admin's {self._current_speaker_relationship})"
        else:
            display_name = "master"
        greeting = f"[Speaking with: {display_name}] " if self._current_speaker else ""
        self._ctx.add_message("user", greeting + user_text, speaker=display_name)
        messages = self._ctx.build_ollama_messages(lang=self._resolve_assistant_language(user_lang))

        # Inject dynamic language instruction EARLY (right after system prompt at index 1)
        # Small LLMs prioritize early context — appending at the end often gets ignored
        assistant_lang = self._resolve_assistant_language(user_lang)
        if assistant_lang == "en":
            lang_instruction = {"role": "system", "content": "IMPORTANT: You MUST respond ONLY in English."}
        else:
            lang_name = LANGUAGE_NAMES.get(assistant_lang, assistant_lang)
            lang_instruction = {
                "role": "system",
                "content": (
                    f"IMPORTANT: The user is speaking in {lang_name}. "
                    f"You MUST respond ONLY in {lang_name}, written in its proper script. "
                    "Do NOT switch to English or any other language."
                ),
            }
        messages.insert(1, lang_instruction)
        user_lang = assistant_lang  # Use the resolved language for TTS + downstream

        # 4b. Inject adaptive personal memory profile into LLM context
        profile_block = self._memory.get_profile_system_block()
        if profile_block:
            messages.insert(2, {"role": "system", "content": profile_block})

        # 4c. Inject real-time system context for JARVIS-level intelligence
        context_block = self._context.get_context_block()
        if context_block:
            messages.insert(3, {"role": "system", "content": context_block})

        # 5a. Fast-path: check command cache before hitting the LLM
        cached_resp = self._memory.get_cached_response(user_text, user_lang)
        if cached_resp:
            logger.info("[Orchestrator] Fast-path cache hit — skipping LLM round-trip.")
            self._ui.set_state("speaking")
            self._ui.set_transcript(cached_resp)
            self._ui.set_assistant_response(cached_resp)
            self._ctx.add_message("assistant", cached_resp)
            await self._tts.speak(cached_resp)
            # Still record the turn so hit count continues to accumulate
            self._memory.record_turn(user_text, user_lang, cached_resp, action_taken="cache_hit")
            if not self._is_activated:
                self._ui.set_state("idle")
            return

        # 5. Anti-Gravity Engine: plan → consent → execute → respond
        self._ui.set_state("thinking")

        # Check if this is a multi-step request that should run in background
        _MULTI_STEP_RE = re.compile(
            r"\b(?:and then|and also|after that|once that(?:'s| is) done|also)\b"
            r"|\b(?:and|then)\b.*\b(?:and|then)\b",
            re.IGNORECASE,
        )
        is_multi_step = bool(_MULTI_STEP_RE.search(user_text))

        if is_multi_step:
            # Run in background — assistant stays responsive
            task_id = await self._bg_queue.submit(
                coro_factory=lambda: self._antigravity.process(
                    user_text=user_text, user_lang=user_lang,
                    consent_gate=self._consent, tts=self._tts,
                    ui=self._ui, pointer=self._pointer,
                ),
                description=user_text,
            )
            self._ui.set_state("speaking")
            ack = f"Running that in the background. I'll let you know when it's done."
            self._ui.set_transcript(ack)
            self._ui.set_assistant_response(ack)
            self._ctx.add_message("assistant", ack)
            await self._tts.speak(ack)
            self._memory.record_turn(user_text, user_lang, ack, action_taken="bg_queued")
        else:
            ag_response = await self._antigravity.process(
                user_text    = user_text,
                user_lang    = user_lang,
                consent_gate = self._consent,
                tts          = self._tts,
                ui           = self._ui,
                pointer      = self._pointer,
            )

            if ag_response:
                # Anti-Gravity executed task(s) — speak the short localized result
                self._ui.set_state("speaking")
                if ag_response.startswith("__CLARIFY__:"):
                    ag_response = ag_response[len("__CLARIFY__:"):]
                    logger.info("[Orchestrator] Requesting clarification from user.")
                self._ui.set_transcript(ag_response)
                self._ui.set_assistant_response(ag_response)
                self._ctx.add_message("assistant", ag_response)
                await self._tts.speak(ag_response)
                # Record turn in adaptive memory
                self._memory.record_turn(user_text, user_lang, ag_response, action_taken="antigravity")

                # Analyze action relationships if multi-step
                if self._relationship_engine.enabled and is_multi_step:
                    try:
                        plan = self._antigravity._tracker.current_plan
                        if plan and len(plan.tasks) > 1:
                            # Strip PII from action descriptions before analysis
                            sanitized_tasks = []
                            for task in plan.tasks:
                                clean_desc, _ = self._privacy.scrub(task.description)
                                sanitized_tasks.append(type(task).__new__(type(task)))
                                sanitized_tasks[-1].__dict__.update(task.__dict__)
                                sanitized_tasks[-1].description = clean_desc

                            relationships = await self._relationship_engine.analyze_task_chain(sanitized_tasks)
                            if relationships:
                                self._current_relationships = relationships
                                plan.relationships = relationships

                                # Check for contradictions → flag for consent
                                contradictions = [r for r in relationships if r["type"] == "CONTRADICTORY"]
                                if contradictions:
                                    logger.info("[Orchestrator] Contradictory actions detected — requesting consent")
                                    from core.event_bus import Event, EventType
                                    self._bus.publish_sync(Event(
                                        type=EventType.RELATIONSHIP_DETECTED,
                                        data=contradictions,
                                        source="orchestrator",
                                    ))

                                # Store in knowledge graph
                                from core.knowledge_graph import knowledge_graph
                                for rel in relationships:
                                    knowledge_graph.store_action_relationship(
                                        rel.get("action_a", ""),
                                        rel.get("action_b", ""),
                                        rel["type"],
                                        rel.get("explanation", ""),
                                    )

                                # Emit event
                                from core.event_bus import Event, EventType
                                self._bus.publish_sync(Event(
                                    type=EventType.RELATIONSHIP_DETECTED,
                                    data=relationships,
                                    source="orchestrator",
                                ))

                                # Append to response if explain_by_default
                                if self._cfg.relationship_engine.explain_by_default:
                                    rel_text = "\n".join(
                                        f"  [{r['type']}] {r['explanation']}"
                                        for r in relationships
                                    )
                                    ag_response = f"{ag_response}\n\nRelationships:\n{rel_text}"
                                    self._ui.set_assistant_response(ag_response)
                    except Exception as e:
                        logger.warning("[Orchestrator] Relationship analysis error: {}", e)
            else:
                # Anti-Gravity classified request as conversational — stream LLM response
                partial = await self._stream_response_with_memory(messages, user_text, user_lang)

        if not self._is_activated:
            self._ui.set_state("idle")

    # ─── Background task completion callback ──────────────────────────────────

    async def _on_background_task_complete(self, bg_task):
        """Called when a background task finishes. Speaks the result to the user."""
        from core.background_tasks import TaskState
        if bg_task.state == TaskState.COMPLETED and bg_task.result:
            result = bg_task.result
            if isinstance(result, str) and result.strip():
                self._ui.set_state("speaking")
                self._ui.set_transcript(result)
                self._ui.set_assistant_response(result)
                self._ctx.add_message("assistant", result)
                await self._tts.speak(result)
                if not self._is_activated:
                    self._ui.set_state("idle")
        elif bg_task.state == TaskState.FAILED:
            error_msg = f"Background task failed: {bg_task.error}"
            logger.warning("[Orchestrator] {}", error_msg)
            self._ui.set_state("speaking")
            self._ui.set_transcript(error_msg)
            await self._tts.speak("Sorry, that background task hit an error.")
            if not self._is_activated:
                self._ui.set_state("idle")

    # ─── Execution with consent ───────────────────────────────────────────────

    def _resolve_assistant_language(self, detected_lang: str) -> str:
        """Return the language the assistant should respond in.

        Baby only SPEAKS en/hi/kn — everything else clamps to "en".
        Respects the user's setting in config.ui.language:
          - "auto" → follow the detected spoken language (defaults to "en")
          - any supported spoken code (e.g. "en"/"hi"/"kn") → force it
        """
        configured = (self._cfg.ui.language or "auto").strip().lower()
        if configured in ("auto", ""):
            return detected_lang if detected_lang in SPOKEN_LANGUAGES else "en"
        return configured if configured in SPOKEN_LANGUAGES else "en"

    def _looks_like_echo(self, user_text: str) -> bool:
        """Heuristic: is `user_text` just Baby's own last reply echoed by the mic?

        Only flags as echo when BOTH texts are nearly identical — this prevents
        discarding user speech that merely contains a word from Baby's last
        response (e.g. "Good morning, open notepad" is NOT echo just because
        it starts with "good morning").
        """
        prev = (self._last_partial_resp or "").strip().lower()
        cur = user_text.strip().lower()
        if not prev or not cur:
            return False

        prev_clean = _strip_punct(prev)
        cur_clean = _strip_punct(cur)
        if not prev_clean or not cur_clean:
            return False

        prev_tokens = set(prev_clean.split())
        cur_tokens = set(cur_clean.split())
        if not prev_tokens or not cur_tokens:
            return False

        overlap = prev_tokens & cur_tokens
        if not overlap:
            return False

        # Require BOTH directions: >80% of Baby's words AND >80% of user's
        # words overlap. This catches identical/echoed text while letting
        # "Good morning, open notepad" pass through.
        prev_ratio = len(overlap) / len(prev_tokens)
        cur_ratio = len(overlap) / len(cur_tokens)
        return prev_ratio >= 0.80 and cur_ratio >= 0.80

    def _get_time_based_greeting(self) -> str:
        import datetime
        hour = datetime.datetime.now().hour
        lang = self._announce_lang()
        if hour < 12:
            key = "morning"
        elif hour < 17:
            key = "afternoon"
        else:
            key = "evening"
        # Use the speaker's actual name if known, otherwise "master"
        if self._current_speaker:
            name = self._current_speaker
            if self._current_speaker_relationship:
                name = self._current_speaker_relationship.title()
        else:
            name = "master"
        return _GREETINGS.get(lang, _GREETINGS["en"])[key].format(name=name)

    async def _execute_with_consent(self, plan_data: dict, messages: list[dict]):
        # Security: Read/Write authorities are ONLY active if there is a direct, active user command session
        if not self._last_user_text or not self._is_activated:
            logger.warning("[Security] Blocked tool execution: No active user command session.")
            await self._tts.speak("I'm sorry, but I cannot execute system actions unless I am actively commanded by you.")
            return

        # JARVIS Security: Assess threat level
        plan = ActionPlan(
            description=plan_data["description"],
            risk_level=plan_data.get("risk_level", "medium"),
            tools=plan_data.get("tools", []),
            speaker=self._current_speaker,
        )
        plan.threat_level = self._consent.assess_threat_level(plan)

        # JARVIS Security: Block critical threats immediately
        if plan.threat_level == "critical":
            logger.warning("[Security] CRITICAL threat blocked: {}", plan.description)
            await self._tts.speak(
                "Security alert: I've detected a potentially dangerous action. "
                "For your protection, I cannot execute this. "
                "If you believe this is an error, please try a different approach."
            )
            return

        # JARVIS Security: Auto-execute low-risk read-only operations
        if plan.risk_level == "low" and plan.threat_level == "none":
            # Check if all tools are read-only
            read_only_tools = {
                "clipboard_read", "get_system_status", "get_weather",
                "list_directory", "read_file", "read_pdf", "search_files",
                "take_screenshot", "scroll_at", "point_at", "highlight_region",
                "list_scheduled", "memory_recall",
                # Math tools are all read-only and safe
                "evaluate_expression", "solve_equation", "simplify_expression",
                "differentiate", "integrate", "factorize", "expand_expression",
                "calculate_statistics", "convert_units",
                "matrix_operations", "base_conversion", "list_primes", "scientific_constants",
            }
            all_read_only = all(
                tool.get("name", "") in read_only_tools
                for tool in plan.tools
            )
            if all_read_only:
                logger.info("[JARVIS] Auto-executing read-only operation: {}", plan.description)
                # Execute without consent
                approved = True
            else:
                approved = await self._consent.request_consent(plan)
        else:
            approved = await self._consent.request_consent(plan)

        if not approved:
            return

        # Execute each tool
        tool_results = []
        for tool_call in plan.tools:
            name = tool_call.get("name", "")
            args = tool_call.get("args", {})

            if name in TOOL_RISK:
                result = execute_tool(name, args)
            elif name in SCREEN_TOOL_RISK:
                # If the tool has coordinate parameters (x, y), move the visual AI pointer there first
                if "x" in args and "y" in args:
                    label = "Click" if name == "click_at" else "Point"
                    await self._pointer.async_move_to(args["x"], args["y"], label)
                    await asyncio.sleep(0.8)  # Let the user see the pointer move to coordinate

                result = execute_screen_tool(name, args)

                # Hide the pointer after execution
                if "x" in args and "y" in args:
                    await asyncio.sleep(0.4)
                    self._pointer.hide_pointer()
            elif name in MATH_TOOL_RISK:
                result = execute_math_tool(name, args)
            else:
                result = {"error": f"Unknown tool: {name}"}

            tool_results.append(f"Tool '{name}' result: {result}")
            self._ctx.add_message("tool", str(result), metadata={"tool": name})

        # Localized instant response (avoids LLM latency and verbose text)
        has_error = any("error" in res.lower() for res in tool_results)
        lang = getattr(self, "_last_user_lang", "en")

        if has_error:
            if lang == "hi":
                response_text = "काम पूरा करने में कुछ समस्या आई है।"
            elif lang == "kn":
                response_text = "ಕೆಲಸವನ್ನು ಪೂರ್ಣಗೊಳಿಸಲು ಕೆಲವು ಸಮಸ್ಯೆ ಎದುರಾಗಿದೆ."
            else:
                response_text = "I encountered an issue trying to execute that action."
        else:
            if lang == "hi":
                response_text = "काम पूरा हो गया है, कृपया देख लें!"
            elif lang == "kn":
                response_text = "ಕೆಲಸ ಪೂರ್ಣಗೊಂಡಿದೆ, ದಯವಿಟ್ಟು ನೋಡಿ!"
            else:
                response_text = "It has been executed. Please check it!"

        self._ui.set_state("speaking")
        self._ui.set_transcript(response_text)
        self._ui.set_assistant_response(response_text)
        self._ctx.add_message("assistant", response_text)
        await self._tts.speak(response_text)

    # ─── Streaming response with barge-in ─────────────────────────────────────

    async def _stream_response(self, messages: list[dict]) -> str:
        """Stream LLM response to TTS. Returns the final partial text."""
        self._ui.set_state("speaking")
        self._ui.set_transcript("")
        self._ui.set_assistant_response("")

        barge_in_enabled = self._cfg.audio.barge_in_enabled
        if barge_in_enabled:
            self._barge_in.start()

        def _on_token_cb(t: str):
            self._ui.set_transcript(t)
            self._ui.set_assistant_response(t)

        try:
            partial = await self._llm.stream_to_tts(
                messages=messages,
                tts=self._tts,
                barge_in_event=self._barge_in.barge_in_event,
                on_token=_on_token_cb,
            )
            self._last_partial_resp = partial
        except RuntimeError as e:
            logger.error("[Orchestrator] LLM runtime error (event loop issue?): {}", e)
            logger.debug("[Orchestrator] Full traceback:\n{}", traceback.format_exc())
            partial = ""
        except Exception as e:
            logger.error("[Orchestrator] LLM streaming error: {}", e)
            logger.debug("[Orchestrator] Full traceback:\n{}", traceback.format_exc())
            partial = ""
        finally:
            if barge_in_enabled:
                self._barge_in.stop()

        if barge_in_enabled and self._barge_in.barge_in_event.is_set():
            await self._handle_barge_in()
        else:
            if partial:
                self._ctx.add_message("assistant", partial)

        return partial

    async def _stream_response_with_memory(
        self,
        messages: list[dict],
        user_text: str,
        user_lang: str,
    ) -> str:
        """
        Stream LLM response, then record the completed turn in adaptive memory.
        The memory engine will:
          - Add the user's words to their personal vocabulary (boosting future STT)
          - Accumulate command cache hits for fast-path responses
          - Infer user profile facts (name, preferences, frequent apps)
        """
        partial = await self._stream_response(messages)
        if partial and partial.strip():
            self._memory.record_turn(
                user_text=user_text,
                user_lang=user_lang,
                assistant_response=partial,
                action_taken="llm",
            )
        return partial

    # ─── Barge-in handler ─────────────────────────────────────────────────────

    async def _handle_barge_in(self):
        self._tts.stop()
        logger.info("[Barge-in] Merging context...")
        self._ui.set_state("listening")
        self._ui.set_mic_active(True)

        # Capture the interrupting speech
        interrupt_silence_ms = max(self._cfg.audio.silence_threshold_ms, 1500)
        interrupt_audio = await self._vad.capture_until_silence(silence_ms=interrupt_silence_ms)
        interrupt_text, interrupt_lang = await self._stt.transcribe(interrupt_audio)
        self._tts.set_last_language(interrupt_lang)
        self._ui.set_mic_active(False)

        # Merge context
        merged = self._ctx.merge_barge_in_context(
            original_prompt=self._last_user_text,
            partial_ai_response=self._last_partial_resp,
            interrupt_text=interrupt_text,
        )

        # Re-enter conversation turn immediately with combined merged prompt
        await self._conversation_turn(merged_prompt=merged, speak_prompt=False)

    # ─── Enroll detection ─────────────────────────────────────────────────────

    async def _check_enroll(self, text: str, audio: np.ndarray | None) -> bool:
        match = _ENROLL_RE.search(text)
        if not match:
            return False

        # Admin check: if admin exists, only admin can enroll others
        if self._bio_db.has_admin() and not await self._ensure_admin_verified():
            await self._tts.speak("Only the admin can enroll new users.")
            return True

        tag  = (match.group(1) or "").strip().lower()
        name = match.group(2).strip().title()
        logger.info("[Enroll] Detected enroll request for '{}' (relationship='{}')", name, tag)

        # Normalize common short forms to canonical relationship labels.
        _REL_NORMALIZE = {
            "mom": "mother", "mum": "mother", "dad": "father",
            "best friend": "friend", "spouse": "partner",
        }
        relationship = _REL_NORMALIZE.get(tag, tag)

        # ── Capture face from camera ────────────────────────────────────────
        face_ok = False
        try:
            self._ui.setCameraPreviewVisible(True)
            await asyncio.sleep(1.5)  # Camera warm-up
            frame = self._ui.get_camera_frame()
            if frame is not None:
                try:
                    self._face_id.enroll(name, frame, is_admin=False, relationship=relationship)
                    face_ok = True
                    logger.info("[Enroll] Captured face for '{}'", name)
                except ValueError:
                    logger.warning("[Enroll] No face detected in camera frame for '{}'", name)
            else:
                logger.warning("[Enroll] No camera frame available for '{}'", name)
        except Exception as e:
            logger.error("[Enroll] Face capture error: {}", e)
        finally:
            self._ui.setCameraPreviewVisible(False)

        # ── Capture voice ───────────────────────────────────────────────────
        voice_ok = False
        if audio is not None:
            self._voice_id.enroll(name=name, audio=audio, relationship=relationship)
            voice_ok = True
        else:
            logger.warning("[Enroll] No audio sample for '{}'", name)

        # ── Update relationship in DB (face enroll may not set it) ──────────
        profile = self._bio_db.get_profile_by_name(name)
        if profile and relationship:
            self._bio_db.update_relationship(profile["id"], relationship)

        # ── Respond to user ─────────────────────────────────────────────────
        parts = []
        if face_ok:
            parts.append("face")
        if voice_ok:
            parts.append("voice")
        captured = " and ".join(parts) if parts else "nothing"

        if relationship:
            await self._tts.speak(
                f"Lovely! I've saved {captured} for {name} as your {relationship}. "
                f"I'll recognise them when they walk in or speak to me."
            )
        else:
            await self._tts.speak(
                f"Got it! I've saved {captured} for {name}. "
                f"I'll recognise them next time they interact with me."
            )
        return True

    # ─── Face enrollment detection ────────────────────────────────────────────

    async def _check_face_enroll(self, text: str) -> bool:
        match = _FACE_ENROLL_RE.search(text)
        if not match:
            return False

        name = (match.group(1) or "User").strip().title()
        logger.info("[Enroll] Face enrollment request for '{}'", name)

        # Get camera frame via the UI controller
        try:
            frame = self._ui.get_camera_frame()
        except Exception:
            frame = None

        if frame is None:
            await self._tts.speak(
                "Please enable the camera first, then say 'enroll my face' again."
            )
            return True

        try:
            self._face_id.enroll(name, frame)
            await self._tts.speak(
                f"I've enrolled your face as {name}. "
                f"I'll recognise you when the camera is active."
            )
        except ValueError as e:
            await self._tts.speak(f"Face enrollment failed: {e}")

        return True

    # ─── Admin enrollment detection ──────────────────────────────────────────

    async def _check_admin_enroll(self, text: str, audio: np.ndarray | None) -> bool:
        match = _ADMIN_ENROLL_RE.search(text)
        if not match:
            return False

        # If admin already exists, block
        if self._bio_db.has_admin():
            await self._tts.speak("An admin is already registered. Cannot enroll another admin.")
            return True

        # Determine name from current speaker or prompt
        name = self._current_speaker or "Master"
        logger.info("[Enroll] Admin enrollment request for '{}'", name)

        # Enroll voice if audio provided
        if audio is not None:
            self._voice_id.enroll(name=name, audio=audio, is_admin=True)
            await self._tts.speak(
                f"I've enrolled you as the admin, {name}. "
                f"You now have full access to all features."
            )
        else:
            await self._tts.speak(
                f"Please say 'my name is {name}' out loud so I can record your voice as admin."
            )

        # Prompt for face enrollment
        await self._tts.speak("Would you also like to enroll your face? Say 'enroll my face' after enabling the camera.")

        return True

    # ─── Guided Admin Enrollment ──────────────────────────────────────────────

    async def _guided_admin_enrollment(self):
        """
        Guided admin enrollment flow:
        1. Ask for name
        2. Capture face from multiple angles (front, left, right)
        3. Record voice reading a paragraph
        4. Store as admin in memory
        """
        if self._bio_db.has_admin():
            await self._tts.speak("An admin is already registered. Cannot enroll another admin.")
            return

        # Store enrollment state
        self._enrollment_state = "waiting_for_name"
        self._enrollment_name = None

        # Step 1: Ask for name
        await self._tts.speak(
            "Let's set you up as the admin. "
            "First, what is your name? Please say it clearly."
        )
        # Wait will be handled by conversation turn checking _enrollment_state

    async def _continue_admin_enrollment_name(self, name: str):
        """Continue admin enrollment after name is captured."""
        self._enrollment_name = name
        self._enrollment_state = "capturing_face"
        logger.info("[Enroll] Admin name captured: {}", name)

        # Step 2: Enable camera for face capture
        await self._tts.speak(
            f"Nice to meet you, {name}! Now I'll capture your face from different angles. "
            "Please enable the camera and look straight at it."
        )
        self._ui.setCameraPreviewVisible(True)
        await asyncio.sleep(2)

        # Capture front face
        await self._tts.speak("Look straight at the camera. Capturing in 3... 2... 1...")
        await asyncio.sleep(3)
        front_frame = self._ui.get_camera_frame()
        if front_frame is not None:
            self._face_id.enroll(name, front_frame, is_admin=True)
            logger.info("[Enroll] Captured front face for admin '{}'", name)
        else:
            await self._tts.speak("Could not capture face. Please ensure camera is enabled.")

        # Capture left angle
        await self._tts.speak("Now turn your head slightly to the left. Capturing in 3... 2... 1...")
        await asyncio.sleep(4)
        left_frame = self._ui.get_camera_frame()
        if left_frame is not None:
            self._face_id.enroll(name, left_frame, is_admin=True)
            logger.info("[Enroll] Captured left face for admin '{}'", name)

        # Capture right angle
        await self._tts.speak("Now turn your head slightly to the right. Capturing in 3... 2... 1...")
        await asyncio.sleep(4)
        right_frame = self._ui.get_camera_frame()
        if right_frame is not None:
            self._face_id.enroll(name, right_frame, is_admin=True)
            logger.info("[Enroll] Captured right face for admin '{}'", name)

        self._ui.setCameraPreviewVisible(False)

        # Step 3: Voice enrollment
        self._enrollment_state = "waiting_for_voice"
        await self._tts.speak(
            "Excellent! Face enrollment complete. Now I need to record your voice. "
            "Please read the following paragraph aloud: "
            "The quick brown fox jumps over the lazy dog. "
            "I am the admin of this system and I have full access to all features. "
            "My voice is my password and my face is my identity."
        )

        await self._tts.speak(
            "After you finish reading, say 'I am done' to complete enrollment."
        )

    async def _complete_admin_enrollment_voice(self, audio):
        """Complete admin enrollment with voice capture."""
        if self._enrollment_state != "waiting_for_voice":
            return

        name = self._enrollment_name or "Admin"
        if audio is not None:
            self._voice_id.enroll(name=name, audio=audio, is_admin=True)
            logger.info("[Enroll] Voice enrolled for admin '{}'", name)
        else:
            logger.warning("[Enroll] No audio captured for admin voice")

        self._enrollment_state = None
        self._enrollment_name = None

        await self._tts.speak(
            f"Admin enrollment complete! Welcome, {name}. "
            "You now have full access to all features."
        )

    # ─── Form-based Admin Enrollment ──────────────────────────────────────────

    async def _start_voice_recording(self):
        """Start recording voice for admin enrollment."""
        self._is_recording_voice = True
        self._admin_voice_audio = None
        logger.info("[Enroll] Voice recording started - speak now")

        # Capture audio for up to 10 seconds
        try:
            audio = await self._vad.capture_until_silence(
                silence_ms=1500,
                max_duration_s=10,
                lead_in_skip_s=0.5
            )
            if audio is not None and len(audio) > 0:
                self._admin_voice_audio = audio
                logger.info("[Enroll] Voice captured successfully, duration: {} samples", len(audio))
            else:
                logger.warning("[Enroll] No voice audio captured")
        except Exception as e:
            logger.error("[Enroll] Voice capture failed: {}", e)

        self._is_recording_voice = False

    def _stop_voice_recording(self):
        """Stop recording voice for admin enrollment."""
        self._is_recording_voice = False
        logger.info("[Enroll] Voice recording stopped")

    def _capture_admin_face(self):
        """Capture face for admin enrollment from camera."""
        try:
            frame = self._ui.get_camera_frame()
            if frame is not None:
                self._admin_face_frame = frame
                logger.info("[Enroll] Face captured for admin")
                return True
            else:
                logger.warning("[Enroll] No camera frame available - please enable camera first")
                return False
        except Exception as e:
            logger.error("[Enroll] Failed to capture face: {}", e)
            return False

    def _complete_admin_setup(self, name: str):
        """Complete admin setup with name, voice, and face."""
        if self._bio_db.has_admin():
            logger.warning("[Enroll] Admin already exists")
            return False

        # Always save the profile with name, even without biometrics
        try:
            # Use save_profile to create/update the profile
            self._bio_db.save_profile(
                name=name,
                relationship="admin",
                is_admin=True
            )
            logger.info("[Enroll] Admin profile created for '{}'", name)
        except Exception as e:
            logger.error("[Enroll] Failed to save admin profile: {}", e)
            return False

        # Save face if captured
        if hasattr(self, '_admin_face_frame') and self._admin_face_frame is not None:
            try:
                self._face_id.enroll(name, self._admin_face_frame, is_admin=True)
                logger.info("[Enroll] Face enrolled for admin '{}'", name)
            except Exception as e:
                logger.error("[Enroll] Failed to enroll face: {}", e)

        # Save voice if recorded
        if hasattr(self, '_admin_voice_audio') and self._admin_voice_audio is not None:
            try:
                self._voice_id.enroll(name=name, audio=self._admin_voice_audio, is_admin=True)
                logger.info("[Enroll] Voice enrolled for admin '{}'", name)
            except Exception as e:
                logger.error("[Enroll] Failed to enroll voice: {}", e)

        # Store in memory engine
        try:
            from core.memory_engine import get_memory
            memory = get_memory()
            if memory:
                memory._profile['name'] = name
                memory._profile['role'] = 'admin'
                memory._save_if_dirty()
                logger.info("[Enroll] Admin info stored in memory engine")
        except Exception as e:
            logger.warning("[Enroll] Could not store in memory engine: {}", e)

        # Reset state
        self._admin_face_frame = None
        self._admin_voice_audio = None

        logger.info("[Enroll] Admin setup completed for '{}'", name)
        return True

    async def _guided_member_enrollment(self, relationship: str):
        """
        Guided enrollment for a new member:
        1. Ask for name
        2. Capture face
        3. Record voice
        4. Store with relationship
        """
        if not self._bio_db.has_admin():
            await self._tts.speak("Please set up admin first before enrolling other members.")
            return

        if not await self._ensure_admin_verified():
            await self._tts.speak("Only the admin can enroll new members.")
            return

        await self._tts.speak(
            f"Let's enroll a new {relationship}. "
            "What is their name? Please say it clearly."
        )
        # Name will be captured in next conversation turn

        # Enable camera
        await self._tts.speak(
            "Now I'll capture their face. Please have them look at the camera."
        )
        self._ui.setCameraPreviewVisible(True)
        await asyncio.sleep(2)

        # Capture face
        await self._tts.speak("Look straight at the camera. Capturing in 3... 2... 1...")
        await asyncio.sleep(1)
        frame = self._ui.get_camera_frame()
        if frame is not None:
            self._face_id.enroll("Member", frame)
            logger.info("[Enroll] Captured face for member")

        self._ui.setCameraPreviewVisible(False)

        # Voice enrollment
        await self._tts.speak(
            "Now please have them read the following paragraph: "
            "Hello, I am a trusted member of this household. "
            "I am here to interact with the assistant and learn together."
        )

        await self._tts.speak(
            "After they finish reading, say 'enrollment complete' to finish."
        )

    # ─── Config Change Handler ────────────────────────────────────────────────

    async def _on_config_changed(self, event: Event):
        data = event.data
        if not data:
            return
        category = data.get("category")
        key = data.get("key")
        value = data.get("value")

        logger.info("[Orchestrator] Applying config change: {}.{} = {}", category, key, value)

        # 1. LLM Engine updates
        if category == "llm":
            if key == "model":
                self._llm._cfg.model = value
            elif key == "planner_model":
                self._planner_llm._cfg.model = value
            elif key == "tool_model":
                self._llm._cfg.tool_model = value
            elif key == "base_url":
                self._llm._cfg.base_url = value
                self._planner_llm._cfg.base_url = value
                if getattr(self._llm, "_provider", "ollama") == "ollama":
                    try:
                        import ollama
                        self._llm._client = ollama.AsyncClient(host=value)
                        self._planner_llm._client = ollama.AsyncClient(host=value)
                        logger.info("[Orchestrator] Ollama client re-initialized with host: {}", value)
                    except Exception as e:
                        logger.warning("[Orchestrator] Could not re-initialize Ollama client: {}", e)
            elif key == "test_mode":
                self._llm._cfg.test_mode = value
                self._planner_llm._cfg.test_mode = value

        # 2. TTS Engine updates
        elif category == "tts":
            if key == "voice":
                self._tts._config.voice = value
            elif key == "speed":
                self._tts._config.speed = value
            elif key == "engine":
                self._tts._config.engine = value
                # Dynamically reload the TTS engine (Kokoro vs XTTS)
                await asyncio.to_thread(self._tts.load)
                logger.info("[Orchestrator] TTS engine reloaded as: {}", value)
            elif key == "persona":
                self._tts._config.persona = value
                self._ctx.set_persona(value)
                logger.info("[Orchestrator] Persona set to: {}", value)

        # 3. Audio & VAD updates
        elif category == "audio":
            if key == "barge_in_vad_threshold":
                self._vad._threshold = value
                self._barge_in._threshold = value
            elif key == "silence_threshold_ms":
                self._vad._silence_ms = value
            elif key == "device_index":
                self._vad._device_index = value
                self._barge_in._device_index = value
                self._wake.update_device(value)
                self._admin_phrase.update_device(value)

        # 4. Admin phrase updates
        elif category == "admin_phrase":
            if key == "enabled":
                if value:
                    self._admin_phrase.set_muted(False)
                    self._admin_phrase.start()
                else:
                    self._admin_phrase.stop()
            elif key == "threshold":
                self._admin_phrase._threshold = value
            elif key == "model_path":
                # Restart with new model
                self._admin_phrase.stop()
                self._admin_phrase._model_path = str(_resolve_bundle_path(value))
                if self._cfg.admin_phrase.enabled:
                    self._admin_phrase.start()

        # 5. Biometrics updates
        elif category == "biometrics":
            if key == "voice_similarity_threshold":
                self._voice_id._threshold = value

        # 5. STT updates
        elif category == "stt":
            if key == "language":
                self._stt._config.language = value



















