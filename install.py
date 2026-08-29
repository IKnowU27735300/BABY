"""
install.py — Install / update the Baby Windows application.

What it does:
  1. Rebuilds the executable from the project (only when sources changed,
     unless --force).
  2. Copies the fresh build to a stable install location
     (%LOCALAPPDATA%\\Programs\\Baby\\Baby.exe) — independent of the
     project folder.
  3. Registers Baby to launch at Windows login (HKCU Run key).
  4. Creates a Desktop shortcut.
  5. Records a manifest of the project sources so future updates are detected.
  6. Launches the installed app.

Auto-update:
  `python install.py --watch` polls the project sources; whenever the project
  is updated (git pull, edits), it automatically rebuilds, reinstalls, kills
  the running app and restarts it with the new build.

Usage:
  python install.py                 # install / update once (rebuild if changed)
  python install.py --force         # always rebuild, then install
  python install.py --watch         # keep watching the project for changes
  python install.py --check         # exit 0 = up to date, 1 = project changed
"""

from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
BUILD_DIR = PROJECT_ROOT / "BUILD"
BUILD_APP_DIR = BUILD_DIR / "BABY"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "BABY"
EXE_NAME = "BABY.exe"
INSTALLED_EXE = INSTALL_DIR / EXE_NAME
MANIFEST_FILE = INSTALL_DIR / "manifest.json"
LOG_FILE = INSTALL_DIR / "updater.log"
SHORTCUT = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / "BABY.lnk"
VENV_PY = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable

# Source locations that drive a rebuild. Everything else (BUILD, data, models,
# .venv, scratch, caches) is intentionally ignored so tests and build outputs
# never trigger pointless rebuilds.
_SOURCE_ROOTS = (
    ("core", ".py"), ("audio", ".py"), ("tools", ".py"), ("biometrics", ".py"),
    ("antigravity", ".py"), ("ui", ".py"), ("ui", ".qml"), ("ui", ".js"),
    ("llm", ".py"), ("hooks", ".py"),
)
_SOURCE_FILES = ("main.py", "app.py", "ai_pointer.py", "config.yaml",
                 "Baby.spec", "requirements.txt", "build_exe.py", "install.py")
_IGNORED_DIRS = {"__pycache__", ".venv", "BUILD", "build_temp", "data", "models",
                 "scratch", ".git", "dist"}


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def source_files() -> list[Path]:
    files: list[Path] = []
    for name in _SOURCE_FILES:
        p = PROJECT_ROOT / name
        if p.is_file():
            files.append(p)
    for sub, ext in _SOURCE_ROOTS:
        base = PROJECT_ROOT / sub
        if not base.is_dir():
            continue
        for p in base.rglob(f"*{ext}"):
            if any(part in _IGNORED_DIRS for part in p.parts):
                continue
            files.append(p)
    return files


def source_manifest() -> str:
    """Aggregate content hash of all source files (deterministic)."""
    digest = hashlib.md5()
    for p in sorted(source_files(), key=lambda x: str(x.relative_to(PROJECT_ROOT))):
        try:
            digest.update(str(p.relative_to(PROJECT_ROOT)).encode("utf-8", "replace"))
            digest.update(p.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


def project_changed() -> bool:
    if not INSTALLED_EXE.exists() or not MANIFEST_FILE.exists():
        return True
    try:
        installed = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return installed.get("source_hash") != source_manifest()


def kill_running_app():
    subprocess.run(
        ["taskkill", "/IM", EXE_NAME, "/F"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def run_build() -> bool:
    """Rebuild the executable. Returns True on success."""
    log("Building Baby.exe (this takes several minutes)...")
    res = subprocess.run(
        [PY, "build_exe.py"],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    ok = res.returncode == 0 and BUILD_APP_DIR.joinpath(EXE_NAME).exists()
    if ok:
        log("Build succeeded.")
    else:
        log(f"BUILD FAILED (exit {res.returncode}):\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")
    return ok


def copy_to_install():
    log(f"Installing to {INSTALL_DIR} ...")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    # Preserve user data (conversations, enrolled profiles) across updates.
    # config.yaml is NOT preserved — the fresh build ships the latest project
    # configuration.
    keep = {}
    for rel in ("data", "models"):
        src = INSTALL_DIR / rel
        if src.exists():
            keep[rel] = str(src)
    # Wipe the ENTIRE install dir (except preserved data/models) so stale
    # build artifacts (e.g. Qt DLLs from a previous PySide6 version) can
    # never survive into a new install.
    for old in INSTALL_DIR.iterdir():
        if old.name in keep:
            continue
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
        else:
            try:
                old.unlink()
            except OSError:
                pass
    shutil.copytree(BUILD_APP_DIR, INSTALL_DIR, dirs_exist_ok=True)
    for rel, tmp in keep.items():
        src = Path(tmp)
        dst = INSTALL_DIR / rel
        if src.resolve() == dst.resolve():
            continue
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            shutil.copy2(src, dst)
    MANIFEST_FILE.write_text(
        json.dumps({"source_hash": source_manifest(), "installed_at": time.strftime("%Y-%m-%d %H:%M:%S")}),
        encoding="utf-8",
    )
    log("Installed.")


def register_startup():
    res = subprocess.run(
        [str(INSTALLED_EXE), "--install-startup"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log(f"Startup registration exit={res.returncode}")


def create_shortcut():
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{SHORTCUT}'); "
        f"$s.TargetPath = '{INSTALLED_EXE}'; "
        f"$s.WorkingDirectory = '{INSTALL_DIR}'; "
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    log(f"Desktop shortcut: {SHORTCUT}")


def launch_app():
    log(f"Launching {INSTALLED_EXE} ...")
    subprocess.Popen([str(INSTALLED_EXE)], cwd=str(INSTALL_DIR), creationflags=subprocess.CREATE_NO_WINDOW)


def install(rebuild: bool):
    if rebuild:
        kill_running_app()
        if not run_build():
            log("Skipping install because the build failed.")
            return False
    copy_to_install()
    register_startup()
    create_shortcut()
    launch_app()
    return True


def watch(interval: float = 8.0, debounce: float = 15.0):
    log(f"Auto-updater watching {PROJECT_ROOT} (every {interval:.0f}s) ...")
    while True:
        if project_changed():
            log("Project changes detected — waiting for edits to settle...")
            current = source_manifest()
            stable_since = None
            while True:
                time.sleep(interval)
                h = source_manifest()
                if h == current:
                    if stable_since is None:
                        stable_since = time.time()
                    elif time.time() - stable_since >= debounce:
                        break
                else:
                    current = h
                    stable_since = None
            log("Sources stable — rebuilding and reinstalling.")
            install(rebuild=True)
        time.sleep(interval)


def main():
    args = set(sys.argv[1:])
    if "--check" in args:
        sys.exit(0 if not project_changed() else 1)
    if "--watch" in args:
        watch()
        return
    changed = project_changed()
    if changed or "--force" in args:
        log("Sources changed or --force: rebuilding.")
        install(rebuild=True)
    else:
        log("Sources unchanged — install/update skipped (use --force to force).")
        launch_app()


if __name__ == "__main__":
    main()



















