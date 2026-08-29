# -*- mode: python ; coding: utf-8 -*-

import os
import site
from pathlib import Path
import PySide6

block_cipher = None

project_dir = Path(os.getcwd()).resolve()
pyside_dir = Path(PySide6.__file__).parent.resolve()

# Do not add global user site-packages to pathex to prevent mixing incompatible package versions (e.g. PyTorch)
pathex_additions = []

datas = [
    (str(project_dir / "ui" / "qml"), "ui/qml"),
    (str(pyside_dir / "qml"), "PySide6/qml"),
    (str(pyside_dir / "plugins"), "PySide6/plugins"),
]

# Bundle the app icon so it's available in the frozen build
icon_path = project_dir / "dist" / "BABY.ico"
if icon_path.exists():
    datas.append((str(icon_path), "."))

# Optional bundled files if present
for extra_file in ["config.yaml", "kokoro-v1.0.onnx", "voices-v1.0.bin"]:
    p = project_dir / extra_file
    if p.exists():
        datas.append((str(p), "."))

# Wake-word model (hey_baby) — bundled so the always-on wake trigger works
# instead of falling back to Ctrl+F12. Also checks onnx variant.
for ww_model in ["models/hey_baby.tflite", "models/hey_baby.onnx"]:
    p = project_dir / ww_model
    if p.exists():
        datas.append((str(p), "models"))

# openwakeword frontend models (melspectrogram + embedding). Not shipped by
# pip — downloaded at first use, which is impossible inside a frozen build.
oww_res = project_dir / "models" / "oww_resources"
if oww_res.exists():
    datas.append((str(oww_res), "openwakeword/resources/models"))

# Force include websockets package (PyInstaller misses dynamic imports)
import websockets
ws_path = Path(websockets.__file__).parent
datas.append((str(ws_path), "websockets"))

# numpy C-extensions are auto-collected by PyInstaller from the venv

# Force include google packages (namespace packages in user site-packages)
import google.generativeai
import google.auth
import google.protobuf
import google.api_core
import google.cloud
import google.oauth2
import googleapiclient
import google.auth.transport.requests
import google.auth.transport.urllib3
import httplib2
import uritemplate
import google_auth_httplib2
import google_auth_oauthlib
import oauthlib
import requests_oauthlib

google_modules = [
    ("google.generativeai", google.generativeai),
    ("google.auth", google.auth),
    ("google.protobuf", google.protobuf),
    ("google.api_core", google.api_core),
    ("google.cloud", google.cloud),
    ("google.oauth2", google.oauth2),
    ("googleapiclient", __import__("googleapiclient")),
    ("google.auth.transport.requests", __import__("google.auth.transport.requests")),
    ("google.auth.transport.urllib3", __import__("google.auth.transport.urllib3")),
]
for name, mod in google_modules:
    if mod.__file__:
        datas.append((str(Path(mod.__file__).parent), "google"))

hidden_imports = [
    "_socket",
    "socket",
    "email",
    "email.parser",
    "email.feedparser",
    "email._policybase",
    "email.utils",
    "_multiprocessing",
    "multiprocessing",
    "multiprocessing.reduction",
    "multiprocessing.popen_spawn_win32",
    "multiprocessing.spawn",
    "select",
    "_ssl",
    "ssl",
    "_asyncio",
    "asyncio",
    "_ctypes",
    "_overlapped",
    "_winapi",
    "numpy",
    "numpy._core",
    "numpy._core.multiarray",
    "numpy._core.umath",
    "numpy._core._multiarray_umath",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "qasync",
    "loguru",
    "yaml",
    "rich",
    "sounddevice",
    "numpy",
    "faster_whisper",
    "kokoro_onnx",
    "resemblyzer",
    "cryptography",
    "cryptography.fernet",
    "pynput",
    "pyautogui",
    "psutil",
    "httpx",
    "ollama",
    "openwakeword",
    "openwakeword.model",
    "sklearn",
    "sklearn.linear_model",
    # Local packages
    "core.config",
    "core.orchestrator",
    "core.ollama_wizard",
    "core.privacy_guard",
    "core.consent_gate",
    "core.context_manager",
    "core.event_bus",
    "core.command_refiner",
    "core.languages",
    "core.memory_engine",
    "core.training_manager",
    "audio.stt",
    "audio.tts",
    "audio.vad",
    "audio.wake_word",
    "biometrics.biometric_db",
    "biometrics.face_id",
    "biometrics.voice_id",
    "tools.file_tools",
    "tools.screen_tools",
    "tools.system_tools",
    "tools.math_tools",
    "tools.extract_gemini_voice",
    "ui.app",
    "ui.island_controller",
    "ui.settings_bridge",
    "ui.ai_pointer",
    "ui.camera_preview",
    "ui.image_provider",
    "ui.system_tray",
    "ui.neural_backend",
    "antigravity.admin",
    "antigravity.goal_tracker",
    "antigravity.base_agent",
    "antigravity.agents.browser_agent",
    "antigravity.agents.context_agent",
    "antigravity.agents.learner_agent",
    "antigravity.agents.system_agent",
    "antigravity.agents.vision_agent",
    # LLM package
    "llm.ollama_client",
    "llm.airllm_client",
    "llm.factory",
    # Optional but commonly used
    "chromadb",
    "chromadb.db",
    "chromadb.api",
    "chromadb.api.models",
    "chromadb.segment",
    "sentence_transformers",
    "sentence_transformers.models",
    "sentence_transformers.util",
    # Home Assistant
    "httpx",
    "websockets",
    # Google Generative AI (Gemini)
    "google.generativeai",
    "google.ai.generativelanguage",
    "google.api_core",
    "google.auth",
    "google.protobuf",
    "google.api_core",
    "google.cloud",
    "google.oauth2",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    "httplib2",
    "google.auth.transport.requests",
    "google.auth.transport.urllib3",
    # Google namespace packages and submodules
    "google",
    "google.generativeai",
    "google.genai",
    "google.protobuf",
    "google.protobuf.descriptor",
    "google.protobuf.message",
    "google.protobuf.descriptor_pool",
    "google.protobuf.symbol_database",
    "google.protobuf.internal.builder",
    "google.protobuf.internal.containers",
    "google.protobuf.internal.enum_type_wrapper",
    "google.protobuf.timestamp_pb2",
    "google.protobuf.struct_pb2",
    "google.protobuf.empty_pb2",
    "google.auth",
    "google.auth.credentials",
    "google.auth.default",
    "google.auth.exceptions",
    "google.auth.transport.requests",
    "google.auth.transport.urllib3",
    "google.oauth2",
    "google.api_core",
    "google.api_core.retry",
    "google.cloud",
    "google.cloud.storage",
    "google.cloud.storage.transfer_manager",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    "httplib2",
    "google.auth.transport.requests",
    "google.auth.transport.urllib3",
    "uritemplate",
    "google_auth_httplib2",
    "google_auth_oauthlib",
    "oauthlib",
    "requests_oauthlib",
]

# Exclude heavy unused modules and conflicting Qt bindings to ensure clean PySide6 build
excludes = [
    "PyQt6",
    "PyQt5",
    "PySide2",
    "PyQt6-sip",
    "PyQt5-sip",
    "tkinter",
    "matplotlib",
    "transformers",
    "spacy",
    "thinc",
    "torchvision",
    "tensorflow",
    "tensorboard",
    "langchain",
    "notebook",
    "IPython",
    "google",
    "grpc",
    "googleapiclient",
    "httplib2",
    "opentelemetry",
    "uvicorn",
    "websockets",
    "rdflib",
    "phonenumbers",
    "boto3",
    "botocore",
    "fitz",
    "docx",
    "openpyxl",
    "pandas",
    "sympy",
    "lxml",
    "jinja2",
    "sqlalchemy",
    "pydub",
]

a = Analysis(
    ['main.py'],
    pathex=[str(project_dir)] + pathex_additions,
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[str(project_dir / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BABY',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # Windows GUI app (no CMD console pop-up)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "dist" / "BABY.ico") if (project_dir / "dist" / "BABY.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BABY',
)




