"""
build_exe.py — Packaging script for Baby Desktop Assistant.
Compiles Baby into a standalone Windows executable distribution inside S:\\CODE\\BABY\\BUILD.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
BUILD_DIR = PROJECT_ROOT / "BUILD"
DIST_APP_DIR = BUILD_DIR / "BABY"
EXE_PATH = DIST_APP_DIR / "BABY.exe"

VENV_PY = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def build_python() -> str:
    """The build MUST run under the project venv so the spec's `import PySide6`
    resolves to the pinned PySide6 (6.8.3) — never a stray global/user-site copy."""
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def build():
    print(f"=== BABY Standalone Executable Build ===")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Target Build Dir: {BUILD_DIR}\n")

    # 1. Clean previous build artifacts
    if BUILD_DIR.exists():
        print(f"Cleaning previous build at {BUILD_DIR}...")
        try:
            shutil.rmtree(BUILD_DIR)
        except Exception as e:
            print(f"Warning: Could not fully clean BUILD dir: {e}")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Run PyInstaller
    py = build_python()
    cmd = [
        py, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath", str(BUILD_DIR),
        "--workpath", str(PROJECT_ROOT / "build_temp"),
        "Baby.spec"
    ]

    print(f"Executing build command: {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if res.returncode != 0:
        print("\n❌ PyInstaller build failed! Check output errors above.", file=sys.stderr)
        sys.exit(res.returncode)

    # 3. Post-build asset copy & verification
    print("\nVerifying build output...")
    if not EXE_PATH.exists():
        print(f"❌ Error: Expected executable not found at {EXE_PATH}", file=sys.stderr)
        sys.exit(1)

    # Ensure required runtime folders exist inside distribution
    (DIST_APP_DIR / "data" / "logs").mkdir(parents=True, exist_ok=True)
    (DIST_APP_DIR / "data" / "conversations").mkdir(parents=True, exist_ok=True)
    (DIST_APP_DIR / "models").mkdir(parents=True, exist_ok=True)

    # Copy config.yaml template if not already bundled
    config_src = PROJECT_ROOT / "config.yaml"
    config_dst = DIST_APP_DIR / "config.yaml"
    if config_src.exists() and not config_dst.exists():
        shutil.copy2(config_src, config_dst)
        print("Copied default config.yaml to distribution folder.")

    # Copy QML templates folder
    qml_src = PROJECT_ROOT / "ui" / "qml"
    qml_dst = DIST_APP_DIR / "ui" / "qml"
    if qml_src.exists() and not qml_dst.exists():
        shutil.copytree(qml_src, qml_dst)
        print("Copied ui/qml templates to distribution folder.")

    print("\n" + "=" * 60)
    print(" SUCCESS! Baby executable distribution built successfully ✓")
    print(f" Distribution Directory : {DIST_APP_DIR}")
    print(f" Executable File        : {EXE_PATH}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    build()



















