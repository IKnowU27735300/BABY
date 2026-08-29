"""
core/training_manager.py — Manages AI training tasks within Baby.

Runs training scripts as background processes with progress tracking.
Emits signals for UI updates.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Signal

ROOT = Path(__file__).resolve().parent.parent
TRAINING_DIR = ROOT / "training"


class TrainingManager(QObject):
    """Runs training tasks in background threads with progress updates."""

    # Signals for UI updates
    progressChanged = Signal(str, int, str)  # task_name, percent, message
    taskCompleted = Signal(str, bool, str)   # task_name, success, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._current_task = None
        self._current_percent = 0
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_task(self) -> str | None:
        return self._current_task

    @property
    def current_percent(self) -> int:
        return self._current_percent

    def start_training(self, task: str):
        """Start a training task in background thread."""
        if self._running:
            logger.warning("[Training] Already running: {}", self._current_task)
            return

        self._running = True
        self._current_task = task
        self._thread = threading.Thread(
            target=self._run_task,
            args=(task,),
            daemon=True,
            name=f"Training-{task}",
        )
        self._thread.start()

    def _run_task(self, task: str):
        """Execute training task (runs in background thread)."""
        try:
            if task == "prepare_data":
                self._run_prepare_data()
            elif task == "train_llm":
                self._run_train_llm()
            elif task == "train_embeddings":
                self._run_train_embeddings()
            elif task == "create_modelfile":
                self._run_create_modelfile()
            else:
                self.taskCompleted.emit(task, False, f"Unknown task: {task}")
        except Exception as e:
            logger.error("[Training] Task '{}' failed: {}", task, e)
            self.taskCompleted.emit(task, False, str(e))
        finally:
            self._running = False
            self._current_task = None
            self._current_percent = 0

    def _emit_progress(self, task: str, percent: int, msg: str):
        """Thread-safe progress emit."""
        self._current_percent = percent
        self.progressChanged.emit(task, percent, msg)

    def _run_prepare_data(self):
        """Run prepare_llm_data.py"""
        script = TRAINING_DIR / "prepare_llm_data.py"
        if not script.exists():
            self.taskCompleted.emit("prepare_data", False, f"Script not found: {script}")
            return

        self._emit_progress("prepare_data", 10, "Starting data preparation...")

        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )

        if result.returncode == 0:
            # Parse output for stats
            lines = result.stdout.strip().split("\n")
            stats_line = next((l for l in lines if "pairs" in l.lower()), "")
            self._emit_progress("prepare_data", 100, stats_line or "Done")
            self.taskCompleted.emit("prepare_data", True, result.stdout)
        else:
            self.taskCompleted.emit("prepare_data", False, result.stderr)

    def _run_train_llm(self):
        """Run train_ollama.py"""
        script = TRAINING_DIR / "train_ollama.py"
        if not script.exists():
            self.taskCompleted.emit("train_llm", False, f"Script not found: {script}")
            return

        self._emit_progress("train_llm", 5, "Starting LLM training...")

        # Stream output for progress
        process = subprocess.Popen(
            [sys.executable, str(script), "--epochs", "3"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT),
        )

        output_lines = []
        if process.stdout:
            for line in process.stdout:
                output_lines.append(line)
                line_lower = line.lower()

                # Parse progress from output
                if "epoch" in line_lower:
                    self._emit_progress("train_llm", 30, line.strip())
                elif "training" in line_lower and "loss" in line_lower:
                    self._emit_progress("train_llm", 60, line.strip())
                elif "saving" in line_lower:
                    self._emit_progress("train_llm", 85, line.strip())
                elif "gguf" in line_lower:
                    self._emit_progress("train_llm", 95, line.strip())

            process.stdout.close()
        process.wait()
        full_output = "".join(output_lines)

        if process.returncode == 0:
            self._emit_progress("train_llm", 100, "Training complete")
            self.taskCompleted.emit("train_llm", True, full_output)
        else:
            self.taskCompleted.emit("train_llm", False, full_output)

    def _run_train_embeddings(self):
        """Run train_embeddings.py"""
        script = TRAINING_DIR / "train_embeddings.py"
        if not script.exists():
            self.taskCompleted.emit("train_embeddings", False, f"Script not found: {script}")
            return

        self._emit_progress("train_embeddings", 10, "Starting embeddings training...")

        process = subprocess.Popen(
            [sys.executable, str(script), "--epochs", "3"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT),
        )

        output_lines = []
        if process.stdout:
            for line in process.stdout:
                output_lines.append(line)
                if "epoch" in line.lower():
                    self._emit_progress("train_embeddings", 50, line.strip())
                elif "saved" in line.lower():
                    self._emit_progress("train_embeddings", 90, line.strip())

            process.stdout.close()
        process.wait()
        full_output = "".join(output_lines)

        if process.returncode == 0:
            self._emit_progress("train_embeddings", 100, "Done")
            self.taskCompleted.emit("train_embeddings", True, full_output)
        else:
            self.taskCompleted.emit("train_embeddings", False, full_output)

    def _run_create_modelfile(self):
        """Run create_modelfile.py"""
        script = TRAINING_DIR / "create_modelfile.py"
        if not script.exists():
            self.taskCompleted.emit("create_modelfile", False, f"Script not found: {script}")
            return

        self._emit_progress("create_modelfile", 50, "Generating Modelfile...")

        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )

        if result.returncode == 0:
            self._emit_progress("create_modelfile", 100, "Modelfile created")
            self.taskCompleted.emit("create_modelfile", True, result.stdout)
        else:
            self.taskCompleted.emit("create_modelfile", False, result.stderr)



















