"""
tools/screen_tools.py — Screen capture and PyAutoGUI input control.
"""

from __future__ import annotations
import sys
import threading
from pathlib import Path
from datetime import datetime

from loguru import logger

from tools.system_tools import clipboard_read, clipboard_write


SCREENSHOT_DIR = Path("data/screenshots")

_POINTER_OVERLAY = None
_SCREEN_SHARE_ENABLED = False
_SCREEN_SHARE_SELECTION: list[int] = []


def _get_pyautogui():
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


def set_pointer_overlay(pointer):
    """Register the shared pointer overlay so screen tools can point at things."""
    global _POINTER_OVERLAY
    _POINTER_OVERLAY = pointer


def set_screen_share_selection(indices: list[int] | None):
    """Store the screens the user explicitly selected for assistant access."""
    global _SCREEN_SHARE_ENABLED, _SCREEN_SHARE_SELECTION
    clean: list[int] = []
    for idx in indices or []:
        if isinstance(idx, int) and idx >= 1 and idx not in clean:
            clean.append(idx)
    _SCREEN_SHARE_SELECTION = clean
    _SCREEN_SHARE_ENABLED = bool(clean)
    logger.info("[ScreenShare] Selection updated: {}", _SCREEN_SHARE_SELECTION)


def set_screen_share_enabled(enabled: bool):
    """Enable or revoke screen sharing access."""
    global _SCREEN_SHARE_ENABLED
    _SCREEN_SHARE_ENABLED = enabled and bool(_SCREEN_SHARE_SELECTION)


def is_screen_share_enabled() -> bool:
    return _SCREEN_SHARE_ENABLED and bool(_SCREEN_SHARE_SELECTION)


def _require_screen_share() -> str | None:
    """Return an error message if screen share permission is missing.

    EVERY tool that shows the pointer or interacts with the user's screen
    (pointing, clicking, typing, scrolling) requires the user to have
    explicitly shared their screen first — pointing at things the user can't
    see makes no sense, and the user must opt in for the assistant to see
    their screen.
    """
    if is_screen_share_enabled():
        return None
    return (
        "Screen share permission is not enabled. The assistant can only point "
        "at or interact with the screen after the user shares their screen: "
        "click the Screen Share button in the Dynamic Island and choose one or "
        "more displays."
    )


def get_screen_share_selection() -> list[int]:
    return list(_SCREEN_SHARE_SELECTION)


def _capture_monitors() -> tuple["object", list[int]]:
    """Return a PIL image of the selected screens and the monitor indices used."""
    from PIL import Image

    if not is_screen_share_enabled():
        raise PermissionError(
            "Screen share permission is not enabled. "
            "Click Screen Share and choose one or more displays first."
        )

    selected = get_screen_share_selection()
    try:
        with __import__("mss").mss() as sct:
            available = len(sct.monitors) - 1
            monitors = [sct.monitors[i] for i in selected if 1 <= i <= available]
            if not monitors:
                raise ValueError("No valid selected screens are currently available.")

            if len(monitors) == 1:
                shot = sct.grab(monitors[0])
                return Image.frombytes("RGB", shot.size, shot.rgb), selected

            left = min(m["left"] for m in monitors)
            top = min(m["top"] for m in monitors)
            right = max(m["left"] + m["width"] for m in monitors)
            bottom = max(m["top"] + m["height"] for m in monitors)
            canvas = Image.new("RGB", (right - left, bottom - top))

            for monitor in monitors:
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.rgb)
                canvas.paste(img, (monitor["left"] - left, monitor["top"] - top))

            return canvas, selected
    except Exception as err:
        logger.warning("[ScreenTools] mss capture failed ({}), falling back to Qt QGuiApplication grab...", err)
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QGuiApplication, QImage
        import numpy as np

        qapp = QApplication.instance()
        if not qapp:
            qapp = QApplication([])

        screens = QGuiApplication.screens()
        if not screens:
            raise RuntimeError(f"Could not grab screen via Qt or MSS: {err}")

        selected = get_screen_share_selection()
        target_screens = []
        for idx in selected:
            if 1 <= idx <= len(screens):
                target_screens.append(screens[idx - 1])
        if not target_screens:
            target_screens = [screens[0]]

        if len(target_screens) == 1:
            pm = target_screens[0].grabWindow(0)
            qimg = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            width, height = qimg.width(), qimg.height()
            ptr = qimg.bits()
            arr = np.array(ptr).reshape((height, width, 4))
            img = Image.fromarray(arr, "RGBA").convert("RGB")
            return img, selected

        geom = [s.geometry() for s in target_screens]
        left = min(g.x() for g in geom)
        top = min(g.y() for g in geom)
        right = max(g.x() + g.width() for g in geom)
        bottom = max(g.y() + g.height() for g in geom)
        canvas = Image.new("RGB", (right - left, bottom - top))

        for scr, g in zip(target_screens, geom):
            pm = scr.grabWindow(0)
            qimg = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = qimg.width(), qimg.height()
            ptr = qimg.bits()
            arr = np.array(ptr).reshape((h, w, 4))
            tile = Image.fromarray(arr, "RGBA").convert("RGB")
            canvas.paste(tile, (g.x() - left, g.y() - top))

        return canvas, selected

SCREEN_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture the current screen and return the image path.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_at",
            "description": "Click at a screen coordinate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type a string of text using the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval": {"type": "number", "default": 0.02,
                                 "description": "Seconds between keystrokes."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a keyboard key (e.g. 'enter', 'escape', 'ctrl+c').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_at",
            "description": "Scroll the mouse wheel at a position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x":      {"type": "integer"},
                    "y":      {"type": "integer"},
                    "clicks": {"type": "integer",
                               "description": "Positive = up, negative = down."},
                },
                "required": ["x", "y", "clicks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Type a message into the currently focused app and optionally press Enter to send it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "submit": {"type": "boolean", "default": True},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "point_at",
            "description": "Show the overlay pointer pointing towards a specific coordinate (x, y) with a custom label to direct the user's attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "label": {"type": "string", "default": "Point", "description": "Short label indicating what is shown, e.g. 'Look Here'."}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "highlight_region",
            "description": "Draw a glowing circle mark around a screen region (x, y, width, height) with a label — use it to point at an app icon, a window, a button or any area, e.g. after locating an element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Region left coordinate"},
                    "y": {"type": "integer", "description": "Region top coordinate"},
                    "width": {"type": "integer", "description": "Region width in pixels"},
                    "height": {"type": "integer", "description": "Region height in pixels"},
                    "label": {"type": "string", "default": "Look Here", "description": "Short label shown above the mark"}
                },
                "required": ["x", "y", "width", "height"]
            }
        }
    },
]

SCREEN_TOOL_RISK: dict[str, str] = {
    "take_screenshot": "low",
    "click_at":        "medium",
    "type_text":       "medium",
    "press_key":       "medium",
    "scroll_at":       "low",
    "send_message":    "high",
    "point_at":        "low",
    "highlight_region": "low",
}


def take_screenshot() -> dict:
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOT_DIR / f"screen_{ts}.png"
        image, screens = _capture_monitors()
        image.save(path)
        logger.debug("[Screenshot] Saved to {} (screens={})", path, screens)
        return {"success": True, "path": str(path), "screens": screens}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def click_at(x: int, y: int, button: str = "left") -> dict:
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        pag = _get_pyautogui()
        pag.click(x, y, button=button)
        return {"success": True, "clicked": (x, y), "button": button}
    except Exception as e:
        return {"error": str(e)}


def type_text(text: str, interval: float = 0.02) -> dict:
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        pag = _get_pyautogui()
        pag.write(text, interval=interval)
        return {"success": True, "typed": len(text)}
    except Exception as e:
        return {"error": str(e)}


def press_key(key: str) -> dict:
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        import pyautogui
        # Support combos like "ctrl+c"
        keys = [k.strip() for k in key.split("+")]
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return {"success": True, "key": key}
    except Exception as e:
        return {"error": str(e)}


def scroll_at(x: int, y: int, clicks: int) -> dict:
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        import pyautogui
        pyautogui.scroll(clicks, x=x, y=y)
        return {"success": True, "scrolled": clicks}
    except Exception as e:
        return {"error": str(e)}


def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> dict:
    """Drag from one coordinate to another."""
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        import pyautogui
        pyautogui.moveTo(start_x, start_y, duration=0.1)
        pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
        return {"success": True, "message": f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"}
    except Exception as e:
        return {"error": str(e)}


def send_message(text: str, submit: bool = True) -> dict:
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        import pyautogui
        import time

        # Clipboard paste is more reliable for multilingual text than keystrokes.
        previous_clipboard = None
        try:
            previous_result = clipboard_read()
            if previous_result.get("success"):
                previous_clipboard = previous_result.get("text", "")
        except Exception:
            previous_clipboard = None

        if clipboard_write(text).get("error"):
            pyautogui.write(text)
        else:
            time.sleep(0.05)
            if sys.platform == "darwin":
                pyautogui.hotkey("command", "v")
            else:
                pyautogui.hotkey("ctrl", "v")

        if submit:
            pyautogui.press("enter")

        if previous_clipboard is not None:
            clipboard_write(previous_clipboard)

        return {"success": True, "sent": len(text), "submitted": submit}
    except Exception as e:
        return {"error": str(e)}


def _flash_pointer(x: int, y: int, label: str = "Point", duration: float = 4.0) -> bool:
    if _POINTER_OVERLAY is None:
        return False

    try:
        _POINTER_OVERLAY.move_to(x, y, label)

        def _hide():
            try:
                if _POINTER_OVERLAY is not None:
                    _POINTER_OVERLAY.hide_pointer()
            except Exception:
                pass

        timer = threading.Timer(duration, _hide)
        timer.daemon = True
        timer.start()
        return True
    except Exception as e:
        logger.debug("[Pointer] Failed to flash overlay: {}", e)
        return False


def point_at(x: int, y: int, label: str = "Point") -> dict:
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    try:
        shown = _flash_pointer(x, y, label)
        return {"success": True, "pointed_at": (x, y), "label": label, "overlay": shown}
    except Exception as e:
        return {"error": str(e)}


def highlight_region(x: int, y: int, width: int, height: int, label: str = "Look Here") -> dict:
    """Draw a glowing circle/rounded-rect mark around a screen region."""
    denied = _require_screen_share()
    if denied:
        return {"error": denied}
    if _POINTER_OVERLAY is None:
        return {"error": "Pointer overlay not available (UI not running)."}
    try:
        _POINTER_OVERLAY.highlight_region(x, y, width, height, label)

        def _hide():
            try:
                if _POINTER_OVERLAY is not None:
                    _POINTER_OVERLAY.hide_pointer()
            except Exception:
                pass

        timer = threading.Timer(6.0, _hide)
        timer.daemon = True
        timer.start()
        return {
            "success": True,
            "region": (x, y, width, height),
            "label": label,
            "overlay": True,
            "message": f"Highlighted region at ({x}, {y}) size {width}x{height}.",
        }
    except Exception as e:
        return {"error": str(e)}


_REGISTRY = {
    "take_screenshot": take_screenshot,
    "click_at":        click_at,
    "type_text":       type_text,
    "press_key":       press_key,
    "scroll_at":       scroll_at,
    "drag":            drag,
    "send_message":    send_message,
    "point_at":        point_at,
    "highlight_region": highlight_region,
}


def execute_screen_tool(name: str, args: dict) -> dict:
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown screen tool: '{name}'"}
    
    normalized_args = dict(args) if isinstance(args, dict) else {}
    if name in ("click_at", "point_at"):
        if "x" in normalized_args:
            try:
                normalized_args["x"] = int(normalized_args["x"])
            except Exception:
                pass
        if "y" in normalized_args:
            try:
                normalized_args["y"] = int(normalized_args["y"])
            except Exception:
                pass
    elif name == "type_text":
        if "text" not in normalized_args:
            for k in ("content", "string", "input", "message"):
                if k in normalized_args:
                    normalized_args["text"] = normalized_args.pop(k)
                    break
    elif name == "press_key":
        if "key" not in normalized_args:
            for k in ("k", "button", "keys"):
                if k in normalized_args:
                    normalized_args["key"] = normalized_args.pop(k)
                    break

    try:
        logger.debug("[ScreenTool] {}({})", name, normalized_args)
        result = fn(**normalized_args)
        logger.debug("[ScreenTool] {} → {}", name, result)
        return result
    except TypeError as e:
        return {"error": f"Invalid arguments for '{name}': {e}"}
    except Exception as e:
        return {"error": str(e)}



















