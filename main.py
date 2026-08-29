"""
Baby Desktop AI Assistant — Entry Point
Initialises all subsystems and starts the main event loop.
"""

import sys
import os
import asyncio
from pathlib import Path

# Ensure project root is on sys.path and set working directory to app root
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))

# Windowed (frozen) builds have no console: sys.stdout/sys.stderr are None,
# which crashes third-party libs (torch.hub's tqdm, print(), etc.) with
# 'NoneType' object has no attribute 'write'. Fall back to a null stream so
# every subsystem can write safely.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Windows DLL path resolution for PySide6 QML plugins
if sys.platform == "win32":
    try:
        import PySide6
        pyside_dir = os.path.dirname(PySide6.__file__)
        os.add_dll_directory(pyside_dir)
    except Exception:
        pass

from loguru import logger
from rich.console import Console
from rich.panel import Panel

from core.config import BabyConfig
from core.orchestrator import BabyOrchestrator
from ui.app import BabyApp

console = Console()


def print_banner():
    console.print(Panel.fit(
        "[bold violet]✦ BABY — Local AI Desktop Assistant ✦[/bold violet]\n"
        "[dim]100% private · 100% local · 100% yours[/dim]",
        border_style="violet",
        padding=(1, 4),
    ))


def setup_logging(log_level: str):
    logger.remove()
    stream = next((s for s in (sys.stderr, sys.stdout) if s is not None), None)
    if stream is not None:
        logger.add(
            stream,
            level=log_level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
            colorize=stream.isatty(),
        )
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    logger.add(
        "data/logs/baby_{time}.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )


def _startup_registry_path() -> tuple[int, str]:
    import winreg
    return winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"


def install_startup(verbose: bool = True) -> str:
    """Register Baby to launch automatically when the user logs in to Windows."""
    import winreg
    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        launcher = str(pythonw if pythonw.exists() else sys.executable)
        command = f'"{launcher}" "{Path(__file__).resolve()}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "BABY", 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        if verbose:
            print(f"✓ BABY registered to start with Windows: {command}")
        return command
    except OSError as e:
        if verbose:
            print(f"✗ Failed to register startup entry: {e}")
        return ""


def remove_startup() -> bool:
    """Remove Baby from the Windows startup list."""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "BABY")
            print("✓ BABY removed from Windows startup.")
        except FileNotFoundError:
            print("BABY was not in the startup list.")
        winreg.CloseKey(key)
        return True
    except OSError as e:
        print(f"✗ Failed to remove startup entry: {e}")
        return False


def main():
    # CLI flags: startup registration / uninstall (handled before the UI starts)
    if "--install-startup" in sys.argv:
        install_startup()
        return
    if "--remove-startup" in sys.argv:
        remove_startup()
        return

    print_banner()

    # tqdm's background monitor thread segfaults (0xC0000005) on os._exit at
    # shutdown; progress bars refresh fine without it.
    try:
        import tqdm
        tqdm.tqdm.monitor_interval = 0
    except Exception:
        pass

    # Load config
    config = BabyConfig.load("config.yaml")
    setup_logging(config.app.log_level)

    logger.info("Starting BABY v{}", config.app.version)

    # Ensure data directories exist
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    Path("data/conversations").mkdir(parents=True, exist_ok=True)
    Path("models").mkdir(parents=True, exist_ok=True)

    # Dump Python stacks on native crashes (e.g. the exit-time fail-fast) so
    # the faulting call site can be identified without a debugger.
    import faulthandler
    _fault_log = Path("data/logs/faulthandler.log")
    try:
        _fault_file = open(_fault_log, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except Exception:
        pass

    # Check critical dependencies
    _preflight_check(config)

    # Start the PySide6 app (UI runs on main thread; async loop runs alongside)
    app = BabyApp(config)
    app.run()

    logger.info("[Main] run() returned — exiting via TerminateProcess")
    # Skip Python module teardown: CUDA/onnxruntime/PySide6 native libs segfault
    # during interpreter finalization on Windows (access violation 0xC0000005).
    # TerminateProcess is atomic and skips DLL detach handlers that can hang.
    import ctypes
    ctypes.windll.kernel32.TerminateProcess(ctypes.windll.kernel32.GetCurrentProcess(), 0)


def _preflight_check(config: "BabyConfig"):
    """Check Ollama connectivity and audio device availability."""

    _resolve_audio_device(config)

    from core.ollama_wizard import ensure_ollama_ready
    ensure_ollama_ready(config)


def _resolve_audio_device(config: "BabyConfig"):
    """Validate the configured microphone device; fall back to the default.

    If `audio.device_index` points at a missing/invalid input device, reset it
    to -1 so every audio subsystem uses the system default input instead of
    failing or timing out on a dead index.
    """
    idx = getattr(config.audio, "device_index", -1)
    if idx is None or idx < 0:
        logger.info("[Audio] Using default system input device.")
    else:
        logger.info("[Audio] Using configured device index: {}", idx)

    # Quick live test — try opening and closing a mic stream.
    _test_microphone(config)


def _test_microphone(config: "BabyConfig"):
    """Open a brief test stream to verify the microphone hardware works."""
    import sounddevice as sd
    dev_idx = getattr(config.audio, "device_index", -1)
    target_dev = None if dev_idx == -1 else dev_idx
    try:
        with sd.RawInputStream(
            samplerate=16000, channels=1, dtype="int16",
            blocksize=512, device=target_dev,
        ):
            pass
        logger.success("[Audio] Microphone opened successfully ✓")
    except Exception as e:
        logger.error("[Audio] FAILED to open microphone (device={}): {}", target_dev, e)
        logger.error("[Audio] Possible causes: no mic connected, Windows mic permission denied, "
                      "another app has exclusive access, or PortAudio incompatibility with Python 3.14.")
        try:
            devices = sd.query_devices()
            inputs = [(i, d.get("name")) for i, d in enumerate(devices)
                      if d.get("max_input_channels", 0) > 0]
            if inputs:
                logger.info("[Audio] Available input devices:")
                for i, name in inputs:
                    logger.info("[Audio]   #{}: {}", i, name)
            else:
                logger.error("[Audio] NO input devices found on this system!")
        except Exception:
            pass

    # Finally, validate / resolve the configured device index.
    _validate_device_index(config)


def _validate_device_index(config: "BabyConfig"):
    """Check device_index is a valid input device; fall back to default if not.

    Supports an int index, a substring name, or -1/None for default.
    """
    idx = getattr(config.audio, "device_index", -1)
    if idx is None or idx == -1:
        return

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        default_input = sd.default.device[0]
    except Exception as e:
        logger.warning("[Audio] Could not enumerate devices ({}); using default.", e)
        config.audio.device_index = -1
        return

    matched = None
    if isinstance(idx, int):
        if 0 <= idx < len(devices) and devices[idx].get("max_input_channels", 0) > 0:
            matched = idx
    elif isinstance(idx, str):
        for i, d in enumerate(devices):
            if idx.lower() in (d.get("name", "") or "").lower() and d.get("max_input_channels", 0) > 0:
                matched = i
                break

    if matched is None:
        logger.warning(
            "[Audio] Configured device_index '{}' is not a valid input device. "
            "Falling back to default input (index {}).",
            idx, default_input,
        )
        config.audio.device_index = -1
    else:
        if matched != idx:
            logger.info("[Audio] Resolved device '{}' → input index {}", idx, matched)
            config.audio.device_index = matched
        logger.info(
            "[Audio] Using input device #{}: {}",
            matched, devices[matched].get("name", "?"),
        )


if __name__ == "__main__":
    main()



















