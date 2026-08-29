"""
ui/settings_bridge.py — PySide6 QObject bridge between Python configuration and settings QML.
"""

from PySide6.QtCore import QObject, Slot, Signal, Property
from loguru import logger
from core.config import BabyConfig


class BabySettingsBridge(QObject):
    configSaved = Signal()
    trainingProgressUpdated = Signal(str, int, str)  # task, percent, message
    trainingCompleted = Signal(str, bool, str)  # task, success, message
    biometricProfilesChanged = Signal()  # Emitted after enrollment/deletion to refresh UI

    # Training state properties with notify signals for QML binding
    trainingRunningChanged = Signal()
    currentTrainingTaskChanged = Signal()
    trainingProgressChanged = Signal()

    def __init__(self, config: BabyConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._backup = {}
        self._bio_db = None  # Set by app.py after orchestrator init
        self._training_manager = None  # Set by app.py
        self._orchestrator = None  # Set by app.py for security lock state
        self._training_running = False
        self._current_training_task = ""
        self._training_progress = 0

    @Slot()
    def beginEdit(self):
        """Create a backup of current settings before editing."""
        self._backup = {}
        settings_to_backup = {
            "llm": ["model", "base_url", "test_mode"],
            "tts": ["provider", "voice", "speed", "persona"],
            "ui": ["language", "theme_color", "animation_speed"],
            "audio": ["barge_in_vad_threshold", "silence_threshold_ms", "device_index"],
            "biometrics": ["voice_similarity_threshold"],
        }
        for category, keys in settings_to_backup.items():
            cat_obj = getattr(self._config, category, None)
            if cat_obj:
                for key in keys:
                    self._backup[(category, key)] = getattr(cat_obj, key, None)
        logger.info("[Settings] Backup of settings created.")

    @Slot(result=list)
    def getInputDevices(self) -> list:
        """Return list of names of available audio input devices."""
        devices = ["-1: System Default Microphone"]
        try:
            import sounddevice as sd
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get('max_input_channels', 0) > 0:
                    devices.append(f"{idx}: {dev.get('name', f'Device {idx}')}")
        except Exception as e:
            logger.error("[Settings] Failed to query audio devices: {}", e)
        return devices

    @Slot()
    def cancelEdit(self):
        """Revert settings to the backup state and notify assistant to apply changes."""
        if not self._backup:
            logger.info("[Settings] Revert requested, but no backup exists.")
            return

        logger.info("[Settings] Reverting unsaved settings...")
        for (category, key), val in list(self._backup.items()):
            cat_obj = getattr(self._config, category, None)
            if cat_obj:
                setattr(cat_obj, key, val)
                # Notify active subsystems of reverted values
                try:
                    from core.event_bus import get_bus, Event, EventType
                    bus = get_bus()
                    bus.publish_sync(Event(
                        type=EventType.CONFIG_CHANGED,
                        data={"category": category, "key": key, "value": val}
                    ))
                except Exception as e:
                    logger.error("[Settings] Revert event error: {}", e)
        self._backup = {}

    @Slot(str, str, result=str)
    def getValue(self, category: str, key: str) -> str:
        """Get value of a config parameter as a string."""
        cat_obj = getattr(self._config, category, None)
        if cat_obj is None:
            return ""
        val = getattr(cat_obj, key, "")
        if val is None:
            return ""
        return str(val)

    @Slot(str, str, str)
    def setValue(self, category: str, key: str, value: str):
        """Set a config parameter value, parsing it into its original type."""
        cat_obj = getattr(self._config, category, None)
        if cat_obj is None:
            return
        
        orig_val = getattr(cat_obj, key, None)
        
        if isinstance(orig_val, bool):
            parsed_val = value.lower() in ("true", "1", "yes")
        elif isinstance(orig_val, int):
            try:
                parsed_val = int(value)
            except ValueError:
                parsed_val = orig_val
        elif isinstance(orig_val, float):
            try:
                parsed_val = float(value)
            except ValueError:
                parsed_val = orig_val
        else:
            parsed_val = value
            
        setattr(cat_obj, key, parsed_val)
        logger.info("[Settings] Local update: {}.{} = {}", category, key, parsed_val)

        # Notify active subsystems of the changes immediately
        try:
            from core.event_bus import get_bus, Event, EventType
            bus = get_bus()
            bus.publish_sync(Event(
                type=EventType.CONFIG_CHANGED,
                data={"category": category, "key": key, "value": parsed_val}
            ))
        except Exception as e:
            logger.error("[Settings] Failed to publish config change event: {}", e)

    @Slot()
    def saveConfig(self):
        """Write the updated config structure back to config.yaml."""
        try:
            self._config.save("config.yaml")
            logger.success("[Settings] Saved config.yaml successfully ✓")
            self._backup = {}  # Clear backup as settings are now saved
            self.configSaved.emit()
        except Exception as e:
            logger.error("[Settings] Failed to save config.yaml: {}", e)

    # ── Biometric Profile Management ──────────────────────────────────────────

    @Slot(result=list)
    def getBiometricProfiles(self) -> list[dict]:
        """Return list of profile summary dicts for QML table."""
        if not self._bio_db:
            return []
        try:
            raw_profiles = self._bio_db.get_all()
            profiles: list[dict] = list(raw_profiles) if raw_profiles else []
            return [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "relationship": p.get("relationship", ""),
                    "has_voice": p.get("voice_emb") is not None,
                    "has_face": p.get("face_emb") is not None,
                    "last_seen": str(p.get("last_seen", "Never")),
                    "is_admin": p.get("is_admin", False),
                }
                for p in profiles
            ]
        except Exception as e:
            logger.error("[Settings] Failed to get biometric profiles: {}", e)
            return []

    @Slot()
    def reloadProfiles(self):
        """Signal QML to reload the biometric profiles list."""
        self.biometricProfilesChanged.emit()
        logger.info("[Settings] biometricProfilesChanged emitted")

    @Slot(int)
    def deleteBiometricProfile(self, profile_id: int):
        """Delete a biometric profile by ID."""
        if not self._bio_db:
            return
        try:
            self._bio_db.delete_profile(profile_id)
            logger.info("[Settings] Deleted biometric profile #{}", profile_id)
            self.biometricProfilesChanged.emit()
        except Exception as e:
            logger.error("[Settings] Failed to delete profile #{}: {}", profile_id, e)

    @Slot(int)
    def promoteToAdmin(self, profile_id: int):
        """Promote a profile to admin (permanent, one-time only)."""
        if not self._bio_db:
            return
        if self._bio_db.has_admin():
            logger.warning("[Settings] Admin already exists — cannot promote another user")
            return
        try:
            self._bio_db.set_admin(profile_id)
            logger.info("[Settings] Promoted profile #{} to admin (permanent)", profile_id)
            self.biometricProfilesChanged.emit()
        except Exception as e:
            logger.error("[Settings] Failed to promote profile #{}: {}", profile_id, e)

    @Slot()
    def startVoiceRecording(self):
        """Start recording voice for admin enrollment."""
        if self._orchestrator:
            import asyncio
            asyncio.ensure_future(self._orchestrator._start_voice_recording())
            logger.info("[Settings] Voice recording started")

    @Slot()
    def stopVoiceRecording(self):
        """Stop recording voice for admin enrollment."""
        if self._orchestrator:
            self._orchestrator._stop_voice_recording()
            logger.info("[Settings] Voice recording stopped")

    @Slot(result=bool)
    def captureAdminFace(self):
        """Capture face for admin enrollment from camera. Returns true if face detected."""
        if self._orchestrator:
            result = self._orchestrator._capture_admin_face()
            logger.info("[Settings] Face capture result: {}", result)
            return result
        return False

    @Slot(result=bool)
    def isVoiceRecording(self) -> bool:
        """Check if voice recording is currently active."""
        if self._orchestrator:
            return getattr(self._orchestrator, '_is_recording_voice', False)
        return False

    @Slot(result=bool)
    def hasVoiceData(self) -> bool:
        """Check if voice audio was captured for admin enrollment."""
        if self._orchestrator:
            audio = getattr(self._orchestrator, '_admin_voice_audio', None)
            return audio is not None and len(audio) > 0
        return False

    @Slot(str, result=bool)
    def completeAdminSetup(self, name: str):
        """Complete admin setup with name, voice, and face."""
        if self._bio_db and self._bio_db.has_admin():
            logger.warning("[Settings] Admin already exists")
            return False
        if self._orchestrator:
            result = self._orchestrator._complete_admin_setup(name)
            logger.info("[Settings] Admin setup completed for '{}', success: {}", name, result)
            if result:
                self.biometricProfilesChanged.emit()
            return result
        return False

    @Slot(str)
    def startMemberEnrollment(self, relationship: str):
        """Start guided enrollment for a new member with relationship."""
        if self._orchestrator:
            import asyncio
            asyncio.ensure_future(self._orchestrator._guided_member_enrollment(relationship))

    @Slot(result=bool)
    def hasAdmin(self) -> bool:
        """Check if an admin profile exists."""
        if not self._bio_db:
            return False
        return self._bio_db.has_admin()

    @Slot(result=str)
    def getAdminName(self) -> str:
        """Get the name of the admin user."""
        if not self._bio_db:
            return ""
        admin = self._bio_db.get_admin()
        return admin["name"] if admin else ""

    @Slot(result=bool)
    def adminHasFace(self) -> bool:
        """Check if the admin has a face enrolled."""
        if not self._bio_db:
            return False
        admin = self._bio_db.get_admin()
        return admin["face_emb"] is not None if admin else False

    @Slot(result=bool)
    def captureAdminFaceForExisting(self):
        """Re-enroll face for existing admin. Returns True if face detected."""
        if not self._orchestrator:
            return False
        admin = self._bio_db.get_admin() if self._bio_db else None
        if not admin:
            logger.warning("[Settings] No admin to re-enroll")
            return False
        frame = self._orchestrator._ui.get_camera_frame()
        if frame is None:
            logger.warning("[Settings] No camera frame for face re-enroll")
            return False
        try:
            self._orchestrator._face_id.enroll(admin["name"], frame, is_admin=True)
            logger.info("[Settings] Face re-enrolled for admin '{}'", admin["name"])
            return True
        except Exception as e:
            logger.error("[Settings] Face re-enroll failed: {}", e)
            return False

    # ── Security Status ───────────────────────────────────────────────────────

    @Slot(result=bool)
    def isSecurityLocked(self) -> bool:
        """Check if the system is currently locked due to security violations."""
        if self._orchestrator:
            import time
            return time.time() < self._orchestrator._security_lockout_until
        return False

    @Slot(result=int)
    def getSecurityLockRemaining(self) -> int:
        """Get remaining lockout time in seconds."""
        if self._orchestrator:
            import time
            remaining = self._orchestrator._security_lockout_until - time.time()
            return max(0, int(remaining))
        return 0

    # ── Training Management ───────────────────────────────────────────────────

    def _on_training_progress(self, task: str, percent: int, msg: str):
        """Forward training manager progress to QML properties."""
        self._training_running = True
        self._current_training_task = task
        self._training_progress = percent
        self.trainingRunningChanged.emit()
        self.currentTrainingTaskChanged.emit()
        self.trainingProgressChanged.emit()
        self.trainingProgressUpdated.emit(task, percent, msg)

    def _on_training_completed(self, task: str, success: bool, msg: str):
        """Forward training completion to QML properties."""
        self._training_running = False
        self._current_training_task = ""
        self._training_progress = 0
        self.trainingRunningChanged.emit()
        self.currentTrainingTaskChanged.emit()
        self.trainingProgressChanged.emit()
        self.trainingCompleted.emit(task, success, msg)

    def set_training_manager(self, manager):
        """Set the training manager and connect its signals."""
        if self._training_manager:
            try:
                self._training_manager.progressChanged.disconnect(self._on_training_progress)
                self._training_manager.taskCompleted.disconnect(self._on_training_completed)
            except Exception:
                pass
        self._training_manager = manager
        if manager:
            manager.progressChanged.connect(self._on_training_progress)
            manager.taskCompleted.connect(self._on_training_completed)

    @Slot(str)
    def startTraining(self, task: str):
        """Start a training task (prepare_data, train_llm, train_embeddings, create_modelfile)."""
        if not self._training_manager:
            logger.error("[Settings] Training manager not initialized")
            return

        if self._training_manager.is_running:
            logger.warning("[Settings] Training already in progress: {}", self._training_manager.current_task)
            return

        logger.info("[Settings] Starting training task: {}", task)
        self._training_manager.start_training(task)

    @Slot(result=bool)
    def isTrainingRunning(self) -> bool:
        """Check if training is currently running."""
        return self._training_running

    @Slot(result=str)
    def getCurrentTrainingTask(self) -> str:
        """Get the name of the currently running training task."""
        return self._current_training_task

    @Slot(result=int)
    def getTrainingProgress(self) -> int:
        """Get current training progress percent (0-100)."""
        return self._training_progress

    @Slot(str, result=int)
    def getTaskProgress(self, task_id: str) -> int:
        """Get progress for a specific task."""
        if self._current_training_task == task_id:
            return self._training_progress
        return 0

    @Property(bool, notify=trainingRunningChanged)  # type: ignore[call-overload]
    def trainingRunning(self) -> bool:
        """QML-bindable property: true if training is running."""
        return self._training_running

    @Property(str, notify=currentTrainingTaskChanged)  # type: ignore[call-overload]
    def currentTrainingTask(self) -> str:
        """QML-bindable property: current training task name."""
        return self._current_training_task

    @Property(int, notify=trainingProgressChanged)  # type: ignore[call-overload]
    def trainingProgress(self) -> int:
        """QML-bindable property: current training progress percent."""
        return self._training_progress

    @Slot(result=list)
    def getTrainingStatus(self) -> list:
        """Return status of all training tasks."""
        tasks = [
            {"id": "prepare_data", "name": "Prepare Training Data", "description": "Convert conversations to training format"},
            {"id": "train_llm", "name": "Fine-tune LLM", "description": "Train custom personality with LoRA (requires GPU)"},
            {"id": "train_embeddings", "name": "Fine-tune Embeddings", "description": "Improve semantic search accuracy"},
            {"id": "create_modelfile", "name": "Create Ollama Model", "description": "Generate Modelfile for Ollama"},
        ]

        if self._training_manager:
            for task in tasks:
                task["running"] = self._training_manager.is_running and self._training_manager.current_task == task["id"]

        return tasks



















