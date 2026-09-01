"""
core/config.py — Typed configuration loader from config.yaml
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List
import yaml
from loguru import logger

from core.relationship_engine.config import NetworkConfig, DEFAULT_KEYWORDS


@dataclass
class AppConfig:
    name: str = "BABY"
    version: str = "1.0.0"
    data_dir: str = "data"
    log_level: str = "INFO"


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "llama3.1:8b"
    base_url: str = "http://localhost:11434"
    keep_alive: int = -1
    num_ctx: int = 4096
    temperature: float = 0.7
    tool_model: str = "llama3.1:8b"
    test_mode: bool = False
    # Summarize + grammar-correct every user command before handing it to the
    # assistant (same meaning, same language — en/hi/kn only).
    refine_commands: bool = True
    airllm_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    airllm_compression: str = "4bit"
    airllm_max_length: int = 2048
    device: str = "cuda"



@dataclass
class WakeWordConfig:
    model_path: str = "models/hey_baby.tflite"
    threshold: float = 0.70
    chunk_samples: int = 1280


@dataclass
class AdminPhraseConfig:
    enabled: bool = True
    model_path: str = "models/admin_phrase.tflite"
    threshold: float = 0.75
    phrase: str = "baby i am back"
    verification_threshold: float = 0.98


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    silence_threshold_ms: int = 1000
    vad_threshold: float = 0.25
    barge_in_vad_threshold: float = 0.5
    barge_in_enabled: bool = False
    device_index: int = -1
    # Seconds of mic audio to discard at the start of every capture. Prevents
    # Baby's own TTS playback from being heard back as the user's next command.
    listen_lead_in_s: float = 0.8
    # Expand spoken symbol phrases into characters before the assistant sees
    # the text ("open bracket" → "(", "excetra" → "etc", "next" → ",").
    expand_dictation: bool = True



@dataclass
class STTConfig:
    model: str = "large-v3"
    device: str = "auto"
    compute_type: str = "int8"
    language: Optional[str] = None
    beam_size: int = 7


@dataclass
class TTSConfig:
    engine: str = "edge"
    voice: str = "en-US-AvaNeural"
    english_voice: str = "en-US-AvaNeural"
    hindi_voice: str = "hi-IN-SwaraNeural"
    kannada_voice: str = "kn-IN-SapnaNeural"
    indic_voice: str = "hi-IN-SwaraNeural"
    sample_rate: int = 24000
    speed: float = 1.0
    # Assistant personality. One of: "friendly", "naughty", "professional", "jarvis".
    persona: str = "friendly"
    # Gemini TTS API key (used when engine == "gemini"). Keep this out of
    # version control — prefer the GEMINI_API_KEY environment variable.
    gemini_api_key: str = ""
    # ElevenLabs TTS API key (used when engine == "elevenlabs").
    # Get your key from https://elevenlabs.io/app/settings/api-keys
    elevenlabs_api_key: str = ""
    # ElevenLabs voice ID (default: naughty Indian voice)
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    # ElevenLabs voice settings
    elevenlabs_stability: float = 0.5
    elevenlabs_similarity_boost: float = 0.75
    elevenlabs_style: float = 0.5
    elevenlabs_use_speaker_boost: bool = True


@dataclass
class FaceBiometricConfig:
    model_name: str = "buffalo_s"
    det_size: list = field(default_factory=lambda: [640, 640])
    similarity_threshold: float = 0.50


@dataclass
class BiometricConfig:
    face: FaceBiometricConfig = field(default_factory=FaceBiometricConfig)
    voice_similarity_threshold: float = 0.82
    db_path: str = "data/biometrics.db"
    key_backend: str = "file"


@dataclass
class UIConfig:
    island_x: int = -1
    island_y: int = 12
    island_y_offset: int = 12
    theme_color: str = "#7C7CFF"
    theme_mode: str = "dark"  # "dark", "light", "system"
    animation_speed: float = 1.0
    # Assistant response language. One of: "auto", "en", "hi", "kn".
    # "auto" follows the user's detected spoken language.
    language: str = "auto"


@dataclass
class ConsentConfig:
    timeout_seconds: int = 30
    approve_keywords: list = field(default_factory=lambda: [
        "yes", "proceed", "confirm", "do it", "go ahead",
        "okay", "sure", "yep", "haan", "theek hai"
    ])
    deny_keywords: list = field(default_factory=lambda: [
        "no", "cancel", "stop", "don't", "abort", "nope", "nahi"
    ])


@dataclass
class ToolsConfig:
    enabled: list = field(default_factory=lambda: [
        "list_directory", "search_files", "copy_file", "move_file", "delete_file",
        "open_application", "take_screenshot", "type_text",
        "click_at", "browser_navigate", "browser_click", "trigger_n8n_webhook", "point_at",
        "clipboard_read", "clipboard_write", "get_system_status", "get_weather", "adjust_volume",
        "open_settings", "open_camera", "toggle_wifi", "toggle_bluetooth", "send_message",
        "browser_search_text", "browser_fetch_page_text", "vision_locate_text"
    ])


@dataclass
class PrivacyConfig:
    pii_redaction_enabled: bool = True
    encryption_enabled: bool = True


@dataclass
class LearnerConfig:
    vector_db_path: str = "data/skill_store"
    min_confidence: float = 0.75
    max_search_results: int = 4
    embedding_model: str = "bge-small-en-v1.5"


@dataclass
class HomeAssistantConfig:
    url: str = ""
    token: str = ""
    verify_ssl: bool = True
    timeout: float = 10.0


@dataclass
class RelationshipEngineConfig:
    enabled: bool = True
    weights_path: str = "data/relationship_weights"
    similarity_threshold: float = 0.85
    embedding_dim: int = 256
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.1
    learning_rate: float = 1e-3
    explain_by_default: bool = False
    purity_check_interval_s: float = 300.0
    keywords: Dict[str, List[str]] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    network_config: NetworkConfig = field(default_factory=NetworkConfig)


@dataclass
class CircuitBreakerConfig:
    enabled: bool = True
    max_consecutive_errors: int = 5
    max_consecutive_dupes: int = 3
    max_output_tokens_per_min: int = 10000
    cost_cap_usd: float = 0.0
    window_seconds: float = 60.0


@dataclass
class ReflectConfig:
    enabled: bool = True
    interval_s: float = 180.0
    byte_trigger_pct: int = 80
    section_trigger: int = 10
    min_bytes: int = 4096
    recent_keep: int = 3


@dataclass
class HiveConfig:
    enabled: bool = True
    hive_root: str = "data/hive"
    auto_mode: bool = True
    router_interval_s: float = 2.0
    mission_control_enabled: bool = True
    completion_watcher_enabled: bool = True
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    reflect: ReflectConfig = field(default_factory=ReflectConfig)


@dataclass
class BabyConfig:
    app: AppConfig = field(default_factory=AppConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    admin_phrase: AdminPhraseConfig = field(default_factory=AdminPhraseConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    biometrics: BiometricConfig = field(default_factory=BiometricConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    consent: ConsentConfig = field(default_factory=ConsentConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    learner: LearnerConfig = field(default_factory=LearnerConfig)
    home_assistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    relationship_engine: RelationshipEngineConfig = field(default_factory=RelationshipEngineConfig)
    hive: HiveConfig = field(default_factory=HiveConfig)

    @classmethod
    def load(cls, path: str = "config.yaml") -> "BabyConfig":
        p = Path(path)
        if not p.exists():
            return cls()  # Return defaults if no config file

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("[Config] Error loading YAML from {}: {}. Falling back to default configuration.", p, e)
            data = {}

        cfg = cls()

        # App
        if "app" in data:
            a = data["app"]
            cfg.app = AppConfig(**{k: v for k, v in a.items() if hasattr(AppConfig, k)})

        # LLM
        if "llm" in data:
            cfg.llm = LLMConfig(**{k: v for k, v in data["llm"].items() if hasattr(LLMConfig, k)})

        # Wake word
        if "wake_word" in data:
            cfg.wake_word = WakeWordConfig(**{k: v for k, v in data["wake_word"].items() if hasattr(WakeWordConfig, k)})

        # Admin phrase
        if "admin_phrase" in data:
            cfg.admin_phrase = AdminPhraseConfig(**{k: v for k, v in data["admin_phrase"].items() if hasattr(AdminPhraseConfig, k)})

        # Audio
        if "audio" in data:
            cfg.audio = AudioConfig(**{k: v for k, v in data["audio"].items() if hasattr(AudioConfig, k)})

        # STT
        if "stt" in data:
            cfg.stt = STTConfig(**{k: v for k, v in data["stt"].items() if hasattr(STTConfig, k)})

        # TTS
        if "tts" in data:
            cfg.tts = TTSConfig(**{k: v for k, v in data["tts"].items() if hasattr(TTSConfig, k)})

        # Biometrics
        if "biometrics" in data:
            b = data["biometrics"] or {}
            face_data = (b.get("face") or {})
            voice_data = (b.get("voice") or {})
            cfg.biometrics = BiometricConfig(
                face=FaceBiometricConfig(**{k: v for k, v in face_data.items() if hasattr(FaceBiometricConfig, k)}),
                voice_similarity_threshold=voice_data.get("similarity_threshold", 0.82),
                db_path=b.get("db_path", "data/biometrics.db"),
                key_backend=b.get("key_backend", "file"),
            )

        # UI
        if "ui" in data:
            cfg.ui = UIConfig(**{k: v for k, v in data["ui"].items() if hasattr(UIConfig, k)})

        # Consent
        if "consent" in data:
            c = data["consent"] or {}
            vk = (c.get("voice_keywords") or {})
            cfg.consent = ConsentConfig(
                timeout_seconds=c.get("timeout_seconds", 30),
                approve_keywords=vk.get("approve", cfg.consent.approve_keywords),
                deny_keywords=vk.get("deny", cfg.consent.deny_keywords),
            )

        # Tools
        if "tools" in data:
            cfg.tools = ToolsConfig(enabled=data["tools"].get("enabled", cfg.tools.enabled))

        # Privacy
        if "privacy" in data:
            p = data["privacy"]
            cfg.privacy = PrivacyConfig(
                pii_redaction_enabled=p.get("pii_redaction_enabled", True),
                encryption_enabled=p.get("encryption_enabled", True),
            )

        # Learner
        if "learner" in data:
            l = data["learner"]
            cfg.learner = LearnerConfig(
                vector_db_path=l.get("vector_db_path", "data/skill_store"),
                min_confidence=l.get("min_confidence", 0.75),
                max_search_results=l.get("max_search_results", 4),
                embedding_model=l.get("embedding_model", "bge-small-en-v1.5"),
            )

        # Home Assistant
        if "home_assistant" in data:
            ha = data["home_assistant"]
            cfg.home_assistant = HomeAssistantConfig(
                url=ha.get("url", ""),
                token=ha.get("token", ""),
                verify_ssl=ha.get("verify_ssl", True),
                timeout=ha.get("timeout", 10),
            )

        # Relationship Engine
        if "relationship_engine" in data:
            re_data = data["relationship_engine"]
            cfg.relationship_engine = RelationshipEngineConfig(
                enabled=re_data.get("enabled", True),
                weights_path=re_data.get("weights_path", "data/relationship_weights"),
                similarity_threshold=re_data.get("similarity_threshold", 0.85),
                embedding_dim=re_data.get("embedding_dim", 256),
                hidden_dim=re_data.get("hidden_dim", 128),
                num_layers=re_data.get("num_layers", 2),
                dropout=re_data.get("dropout", 0.1),
                learning_rate=re_data.get("learning_rate", 1e-3),
                explain_by_default=re_data.get("explain_by_default", False),
                purity_check_interval_s=re_data.get("purity_check_interval_s", 300.0),
            )

        # Hive
        if "hive" in data:
            h = data["hive"] or {}
            cb_data = h.get("circuit_breaker") or {}
            ref_data = h.get("reflect") or {}
            cfg.hive = HiveConfig(
                enabled=h.get("enabled", True),
                hive_root=h.get("hive_root", "data/hive"),
                auto_mode=h.get("auto_mode", True),
                router_interval_s=h.get("router_interval_s", 2.0),
                mission_control_enabled=h.get("mission_control_enabled", True),
                completion_watcher_enabled=h.get("completion_watcher_enabled", True),
                circuit_breaker=CircuitBreakerConfig(**{k: v for k, v in cb_data.items() if hasattr(CircuitBreakerConfig, k)}),
                reflect=ReflectConfig(**{k: v for k, v in ref_data.items() if hasattr(ReflectConfig, k)}),
            )

        return cfg

    def save(self, path: str = "config.yaml"):
        import dataclasses
        
        data = {
            "app": dataclasses.asdict(self.app),
            "llm": dataclasses.asdict(self.llm),
            "wake_word": dataclasses.asdict(self.wake_word),
            "admin_phrase": dataclasses.asdict(self.admin_phrase),
            "audio": dataclasses.asdict(self.audio),
            "stt": dataclasses.asdict(self.stt),
            "tts": dataclasses.asdict(self.tts),
            "biometrics": {
                "face": dataclasses.asdict(self.biometrics.face),
                "voice": {
                    "similarity_threshold": self.biometrics.voice_similarity_threshold,
                },
                "db_path": self.biometrics.db_path,
                "key_backend": self.biometrics.key_backend,
            },
            "ui": dataclasses.asdict(self.ui),
            "consent": {
                "timeout_seconds": self.consent.timeout_seconds,
                "voice_keywords": {
                    "approve": self.consent.approve_keywords,
                    "deny": self.consent.deny_keywords,
                }
            },
            "tools": {
                "enabled": self.tools.enabled
            },
            "privacy": dataclasses.asdict(self.privacy),
            "learner": dataclasses.asdict(self.learner),
            "home_assistant": {
                "url": self.home_assistant.url,
                "token": self.home_assistant.token,
                "verify_ssl": self.home_assistant.verify_ssl,
                "timeout": self.home_assistant.timeout,
            },
            "relationship_engine": {
                "enabled": self.relationship_engine.enabled,
                "weights_path": self.relationship_engine.weights_path,
                "similarity_threshold": self.relationship_engine.similarity_threshold,
                "embedding_dim": self.relationship_engine.embedding_dim,
                "hidden_dim": self.relationship_engine.hidden_dim,
                "num_layers": self.relationship_engine.num_layers,
                "dropout": self.relationship_engine.dropout,
                "learning_rate": self.relationship_engine.learning_rate,
                "explain_by_default": self.relationship_engine.explain_by_default,
                "purity_check_interval_s": self.relationship_engine.purity_check_interval_s,
            },
            "hive": {
                "enabled": self.hive.enabled,
                "hive_root": self.hive.hive_root,
                "auto_mode": self.hive.auto_mode,
                "router_interval_s": self.hive.router_interval_s,
                "mission_control_enabled": self.hive.mission_control_enabled,
                "completion_watcher_enabled": self.hive.completion_watcher_enabled,
                "circuit_breaker": dataclasses.asdict(self.hive.circuit_breaker),
                "reflect": dataclasses.asdict(self.hive.reflect),
            },
        }
        
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)



















