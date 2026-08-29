"""
antigravity/agents/vision_agent.py — Vision & Screen Sub-Agent.

Handles: taking screenshots, reading on-screen text (OCR via pytesseract),
         locating UI elements, and providing screen coordinates.

All operations are read-only — no consent required.
"""

from __future__ import annotations
from difflib import SequenceMatcher
import os
import re
import shutil
import time
from pathlib import Path
from datetime import datetime

from loguru import logger

from antigravity.base_agent import BaseAgent
from antigravity.goal_tracker import Task, TaskStatus
from tools.screen_tools import (
    point_at as screen_point_at,
    highlight_region as screen_highlight_region,
    click_at as screen_click_at,
    type_text as screen_type_text,
    press_key as screen_key_press,
    scroll_at as screen_scroll_at,
    drag as screen_drag,
    take_screenshot as shared_take_screenshot,
    is_screen_share_enabled,
)

# Global reference to the UI controller (set during initialization)
_UI_CONTROLLER = None

def set_ui_controller(controller):
    """Set the reference to the QML UI controller for permission checking."""
    global _UI_CONTROLLER
    _UI_CONTROLLER = controller

def is_camera_access_granted() -> bool:
    """Check if the user has granted camera access through the UI."""
    global _UI_CONTROLLER
    if _UI_CONTROLLER is None:
        return False
    try:
        return getattr(_UI_CONTROLLER, "cameraAccessGranted", False)
    except Exception:
        return False

# ─── Tool registry ────────────────────────────────────────────────────────────

VISION_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "vision_screenshot",
            "description": "Take a full-screen screenshot and return the saved file path.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vision_read_screen",
            "description": "Take a screenshot and extract all visible text from the screen using OCR.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vision_describe_screen",
            "description": "Describe what is currently visible on the screen.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vision_locate_text",
            "description": "Find matching text on the current screen and return approximate coordinates. Optionally highlight the match.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to look for on the screen."},
                    "highlight": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_at",
            "description": "Click at specific screen coordinates (x, y). Works on any application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Screen X coordinate"},
                    "y": {"type": "integer", "description": "Screen Y coordinate"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "clicks": {"type": "integer", "default": 1, "description": "Number of clicks (1=single, 2=double)"}
                },
                "required": ["x", "y"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text at the current cursor position. Optionally click at coordinates first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "x": {"type": "integer", "description": "Optional: click at X coordinate before typing"},
                    "y": {"type": "integer", "description": "Optional: click at Y coordinate before typing"},
                    "delay": {"type": "number", "default": 0.05, "description": "Delay between keystrokes in seconds"}
                },
                "required": ["text"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "key_press",
            "description": "Press a keyboard key (e.g., enter, tab, escape, backspace, arrow keys).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key to press (enter, tab, escape, backspace, delete, up, down, left, right, home, end, pageup, pagedown, f1-f12, ctrl+a, ctrl+c, ctrl+v, ctrl+z, alt+f4, win, etc.)"},
                    "modifiers": {"type": "array", "items": {"type": "string", "enum": ["ctrl", "alt", "shift", "win"]}, "default": []}
                },
                "required": ["key"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the screen at specific coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Screen X coordinate to scroll at"},
                    "y": {"type": "integer", "description": "Screen Y coordinate to scroll at"},
                    "amount": {"type": "integer", "default": -3, "description": "Scroll amount (negative=down, positive=up). Typical: -3 to -10 for down."}
                },
                "required": ["x", "y"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag",
            "description": "Drag from one screen coordinate to another.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer", "description": "Starting X coordinate"},
                    "start_y": {"type": "integer", "description": "Starting Y coordinate"},
                    "end_x": {"type": "integer", "description": "Ending X coordinate"},
                    "end_y": {"type": "integer", "description": "Ending Y coordinate"},
                    "duration": {"type": "number", "default": 0.5, "description": "Drag duration in seconds"}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "camera_frame",
            "description": "Capture a frame from the user's camera (requires camera permission granted in Dynamic Island).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uia_click_element",
            "description": "Click a Windows UI element by name, AutomationId, or ClassName using UI Automation. Works on native Windows apps (Explorer, Settings, Calculator, Notepad, etc.). More reliable than coordinate clicks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Element name (partial match, case-insensitive)"},
                    "automation_id": {"type": "string", "description": "Element AutomationId (partial match, case-insensitive)"},
                    "class_name": {"type": "string", "description": "Element ClassName (partial match, case-insensitive)"},
                    "timeout": {"type": "number", "default": 5.0, "description": "Search timeout in seconds"}
                },
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uia_locate_element",
            "description": "Find a Windows UI element by name (or AutomationId/ClassName) using UI Automation and return its screen coordinates and bounding box, highlighting it with a pointer mark. USE THIS to answer 'where is ...' questions: works for desktop icons, taskbar apps, Start menu, Explorer, Settings, Calculator, Notepad and other native apps. For non-native/web apps fall back to vision_locate_text (OCR).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Element name to look for (partial match, case-insensitive), e.g. 'This PC', 'Chrome', 'Settings'"},
                    "automation_id": {"type": "string", "description": "Element AutomationId (partial match, case-insensitive)"},
                    "class_name": {"type": "string", "description": "Element ClassName (partial match, case-insensitive)"},
                    "highlight": {"type": "boolean", "default": True, "description": "Draw a circle mark around the found element"},
                    "timeout": {"type": "number", "default": 5.0, "description": "Search timeout in seconds"}
                },
                "required": []
            },
        },
    },
]

VISION_TOOL_RISK = {t["function"]["name"]: "low" for t in VISION_TOOLS_SCHEMA if isinstance(t, dict) and isinstance(t.get("function"), dict)}

SCREENSHOT_DIR = Path("data/screenshots")


def _take_screenshot() -> dict:
    try:
        if not is_screen_share_enabled():
            return {
                "success": False,
                "error": (
                    "Screen share permission is not enabled. "
                    "Click Screen Share and choose one or more screens first."
                ),
            }

        result = shared_take_screenshot()
        if result.get("success"):
            result["message"] = f"Screenshot saved: {Path(result['path']).name}"
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def _ensure_tesseract_configured() -> bool:
    """Auto-detect Tesseract OCR executable on Windows if not already in PATH."""
    try:
        import pytesseract
    except ImportError:
        return False

    if shutil.which("tesseract"):
        return True

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    candidates = [
        Path(program_files) / "Tesseract-OCR" / "tesseract.exe",
        Path(program_files_x86) / "Tesseract-OCR" / "tesseract.exe",
        Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe" if local_app_data else None,
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]

    for candidate in candidates:
        if candidate and candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            ocr_dir = str(candidate.parent)
            if ocr_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = ocr_dir + os.pathsep + os.environ.get("PATH", "")
            return True

    return False


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s\u0900-\u097F\u0C80-\u0CFF]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _extract_ocr_lines(image_path: str) -> list[dict]:
    import pytesseract
    from pytesseract import Output
    from PIL import Image

    _ensure_tesseract_configured()
    img = Image.open(image_path)
    data = pytesseract.image_to_data(img, output_type=Output.DICT)

    grouped: dict[tuple[int, int, int], dict] = {}
    total = len(data.get("text", []))

    for idx in range(total):
        raw_text = str(data["text"][idx]).strip()
        if not raw_text:
            continue

        try:
            confidence = float(data.get("conf", ["-1"])[idx])
        except Exception:
            confidence = -1.0
        if confidence < 0:
            continue

        key = (
            int(data.get("block_num", [0])[idx]),
            int(data.get("par_num", [0])[idx]),
            int(data.get("line_num", [0])[idx]),
        )
        bucket = grouped.setdefault(
            key,
            {"words": [], "left": [], "top": [], "right": [], "bottom": [], "confidence": []},
        )
        left = int(data["left"][idx])
        top = int(data["top"][idx])
        width = int(data["width"][idx])
        height = int(data["height"][idx])
        bucket["words"].append(raw_text)
        bucket["left"].append(left)
        bucket["top"].append(top)
        bucket["right"].append(left + width)
        bucket["bottom"].append(top + height)
        bucket["confidence"].append(confidence)

    lines: list[dict] = []
    for bucket in grouped.values():
        text = " ".join(bucket["words"]).strip()
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "left": min(bucket["left"]),
                "top": min(bucket["top"]),
                "right": max(bucket["right"]),
                "bottom": max(bucket["bottom"]),
                "confidence": round(sum(bucket["confidence"]) / max(len(bucket["confidence"]), 1), 2),
            }
        )

    return lines


def _locate_text(query: str, highlight: bool = True) -> dict:
    shot = _take_screenshot()
    if not shot.get("success"):
        return shot

    try:
        lines = _extract_ocr_lines(shot["path"])
    except ImportError:
        return {
            "success": False,
            "error": "OCR unavailable. Install pytesseract and the Tesseract app to use screen text locating.",
            "path": shot.get("path"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "path": shot.get("path")}

    query_norm = _normalize_text(query)
    if not query_norm:
        return {"success": False, "error": "Query text cannot be empty.", "path": shot.get("path")}

    scored: list[tuple[float, dict]] = []
    for line in lines:
        line_norm = _normalize_text(line["text"])
        if not line_norm:
            continue

        if query_norm in line_norm or line_norm in query_norm:
            score = 1.0
        else:
            score = SequenceMatcher(None, query_norm, line_norm).ratio()

        if score >= 0.35:
            scored.append((score, line))

    if not scored:
        return {
            "success": False,
            "error": f"Could not find text matching '{query}'.",
            "path": shot.get("path"),
            "found": [],
        }

    scored.sort(key=lambda item: (item[0], item[1]["confidence"]), reverse=True)
    best_score, best = scored[0]
    x = int((best["left"] + best["right"]) / 2)
    y = int((best["top"] + best["bottom"]) / 2)

    highlighted = False
    if highlight:
        try:
            highlighted = bool(screen_point_at(x, y, best["text"][:18]).get("success"))
        except Exception:
            highlighted = False

    return {
        "success": True,
        "query": query,
        "matched_text": best["text"],
        "x": x,
        "y": y,
        "confidence": round(best_score, 2),
        "highlighted": highlighted,
        "path": shot.get("path"),
    }


# ─── UI Interaction Tools ─────────────────────────────────────────────────────
# These work on ANY application (web or desktop) via screen coordinates.
# Require screen share permission enabled.

def _screen_click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
    """Click at screen coordinates using the shared pointer module."""
    try:
        if button not in ("left", "right", "middle"):
            button = "left"
        if clicks < 1:
            clicks = 1
        # Use the shared screen_click_at which handles the click
        result = screen_click_at(x, y, button)
        if not result.get("success"):
            return result
        if clicks > 1:
            for _ in range(clicks - 1):
                time.sleep(0.1)
                sub_res = screen_click_at(x, y, button)
                if not sub_res.get("success"):
                    return sub_res
        return {"success": True, "message": f"Clicked {button} at ({x}, {y}) {clicks}x"}
    except Exception as e:
        return {"success": False, "error": f"Click failed: {e}"}


def _screen_type(text: str, x: int | None = None, y: int | None = None, delay: float = 0.05) -> dict:
    """Type text, optionally clicking at coordinates first."""
    try:
        if x is not None and y is not None:
            click_result = screen_click_at(x, y, "left")
            if not click_result.get("success"):
                return {"success": False, "error": f"Could not focus at ({x}, {y}): {click_result.get('error')}"}
            time.sleep(0.1)
        # Type the text using the shared module (delay maps to interval)
        result = screen_type_text(text, interval=delay)
        if not result.get("success"):
            return result
        return {"success": True, "message": f"Typed {len(text)} characters"}
    except Exception as e:
        return {"success": False, "error": f"Type failed: {e}"}


def _screen_key(key: str, modifiers: list[str] | None = None) -> dict:
    """Press a keyboard key with optional modifiers.
    Combines modifiers + key into a single hotkey string (e.g., ['ctrl', 'shift'] + 'c' -> 'ctrl+shift+c').
    """
    if modifiers is None:
        modifiers = []
    try:
        # Combine modifiers and key into hotkey format
        if modifiers:
            hotkey = "+".join(modifiers + [key])
        else:
            hotkey = key
        result = screen_key_press(hotkey)
        if not result.get("success"):
            return result
        return {"success": True, "message": f"Pressed {hotkey}"}
    except Exception as e:
        return {"success": False, "error": f"Key press failed: {e}"}


def _screen_scroll(x: int, y: int, amount: int = -3) -> dict:
    """Scroll at screen coordinates. Amount maps to clicks (negative=down)."""
    try:
        result = screen_scroll_at(x, y, amount)
        if not result.get("success"):
            return result
        return {"success": True, "message": f"Scrolled {amount} at ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": f"Scroll failed: {e}"}


def _screen_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> dict:
    """Drag from one coordinate to another."""
    try:
        result = screen_drag(start_x, start_y, end_x, end_y, duration)
        if not result.get("success"):
            return result
        return {"success": True, "message": f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"}
    except Exception as e:
        return {"success": False, "error": f"Drag failed: {e}"}


# ─── UI Automation (Windows UIA) ──────────────────────────────────────────────
# Uses Windows UI Automation to click elements by name/automationId — more
# reliable than coordinate-based clicks for standard Windows apps.

def _uia_click_element(name: str = "", automation_id: str = "", class_name: str = "", timeout: float = 5.0) -> dict:
    """Click a Windows UI element using UI Automation (name, automationId, or className).
    Works on native Windows apps (Explorer, Settings, Calculator, Notepad, etc.).
    """
    try:
        import uiautomation as auto
    except ImportError:
        return {"success": False, "error": "uiautomation not installed. pip install uiautomation"}

    try:
        # Search for element with given properties
        root = auto.GetRootControl()
        ctrl = auto.FindControl(
            root,
            lambda c, d: (not name or name.lower() in (c.Name or "").lower()) and
                         (not automation_id or automation_id.lower() in (c.AutomationId or "").lower()) and
                         (not class_name or class_name.lower() in (c.ClassName or "").lower()),
            maxDepth=8,
        )
        if ctrl is None:
            return {"success": False, "error": f"Element not found (name={name}, automationId={automation_id}, className={class_name})"}

        # Bring to front and click
        ctrl.SetFocus()
        time.sleep(0.1)
        ctrl.Click()
        return {"success": True, "message": f"Clicked UIA element: {ctrl.Name} (AutoId: {ctrl.AutomationId}, Class: {ctrl.ClassName})"}
    except Exception as e:
        return {"success": False, "error": f"UIA click failed: {e}"}


def _uia_locate_element(name: str = "", automation_id: str = "",
                        class_name: str = "", highlight: bool = True,
                        timeout: float = 5.0) -> dict:
    """Find a UI element by name/AutomationId/ClassName and point at it.

    Uses Windows UI Automation so Baby can answer 'where is ...' for desktop
    icons, taskbar apps, Start menu, Explorer, Settings, Calculator, Notepad,
    etc. — things OCR alone cannot identify.
    """
    if not is_screen_share_enabled():
        return {
            "success": False,
            "error": (
                "Screen share permission is not enabled. Share your screen "
                "first so the assistant can see and point at elements."
            ),
        }
    if not (name or automation_id or class_name):
        return {"success": False, "error": "Provide name, automation_id, or class_name."}
    try:
        import uiautomation as auto
    except ImportError:
        return {"success": False, "error": "uiautomation not installed. pip install uiautomation"}

    try:
        root = auto.GetRootControl()
        ctrl = auto.FindControl(
            root,
            lambda c, d: (not name or name.lower() in (c.Name or "").lower()) and
                         (not automation_id or automation_id.lower() in (c.AutomationId or "").lower()) and
                         (not class_name or class_name.lower() in (c.ClassName or "").lower()),
            maxDepth=8,
        )
        if ctrl is None:
            return {
                "success": False,
                "error": f"Element not found (name={name}, automationId={automation_id}, className={class_name}). "
                         f"The app may be closed or the element may not be a native Windows element.",
            }

        try:
            ctrl.SetFocus()
        except Exception:
            pass

        rect = ctrl.BoundingRectangle
        cx = rect.xcenter()
        cy = rect.ycenter()

        shown = False
        if highlight and rect.width() > 0 and rect.height() > 0:
            try:
                result = screen_highlight_region(
                    rect.left, rect.top,
                    max(rect.width(), 48), max(rect.height(), 40),
                    label=(name or ctrl.Name or "Here")[:18],
                )
                shown = bool(result.get("success"))
            except Exception:
                shown = False

        return {
            "success": True,
            "name": ctrl.Name,
            "automation_id": ctrl.AutomationId,
            "class_name": ctrl.ClassName,
            "x": cx,
            "y": cy,
            "left": rect.left,
            "top": rect.top,
            "width": rect.width(),
            "height": rect.height(),
            "highlighted": shown,
            "message": f"Found '{ctrl.Name}' centered at ({cx}, {cy}).",
        }
    except Exception as e:
        return {"success": False, "error": f"UIA locate failed: {e}"}


def _read_screen_text() -> dict:
    shot = _take_screenshot()
    if not shot.get("success"):
        return shot
    try:
        import pytesseract
        from PIL import Image
        _ensure_tesseract_configured()
        img  = Image.open(shot["path"])
        text = pytesseract.image_to_string(img)
        return {"success": True, "text": text.strip(), "message": "Screen text extracted."}
    except ImportError:
        return {
            "success": True,
            "text": "(OCR not available — pytesseract not installed)",
            "message": "Screenshot taken but OCR unavailable.",
            "path": shot.get("path"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _capture_camera_frame() -> dict:
    """Capture a frame from the user's webcam (requires camera permission)."""
    if not is_camera_access_granted():
        return {
            "success": False,
            "error": (
                "Camera access permission is not enabled. "
                "Click Camera in the Dynamic Island to grant permission."
            ),
        }

    try:
        import cv2
        from PIL import Image

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return {
                "success": False,
                "error": "Could not open camera device. Check that the camera is available and not in use.",
            }

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return {"success": False, "error": "Failed to capture frame from camera."}

        # Save the frame
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOT_DIR / f"camera_{ts}.png"
        
        # Convert BGR to RGB for saving
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img.save(path)

        logger.debug("[Camera] Frame captured and saved to {}", path)
        return {
            "success": True,
            "path": str(path),
            "message": f"Camera frame captured: {path.name}",
        }
    except ImportError:
        return {
            "success": False,
            "error": "OpenCV (cv2) is not installed. Install it with: pip install opencv-python",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_vision_tool(name: str, args: dict) -> dict:
    if name in ("vision_screenshot", "take_screenshot"):
        return _take_screenshot()
    elif name == "vision_read_screen":
        return _read_screen_text()
    elif name == "vision_describe_screen":
        # Read screen text and return as description
        r = _read_screen_text()
        if r.get("success") and r.get("text"):
            r["message"] = f"Screen content: {r['text'][:300]}"
        return r
    elif name == "vision_locate_text":
        return _locate_text(
            query=args.get("query", ""),
            highlight=bool(args.get("highlight", True)),
        )
    elif name == "click_at":
        return _screen_click(
            x=args.get("x", 0),
            y=args.get("y", 0),
            button=args.get("button", "left"),
            clicks=args.get("clicks", 1),
        )
    elif name == "type_text":
        return _screen_type(
            text=args.get("text", ""),
            x=args.get("x"),
            y=args.get("y"),
            delay=args.get("delay", 0.05),
        )
    elif name == "key_press":
        return _screen_key(
            key=args.get("key", ""),
            modifiers=args.get("modifiers", []),
        )
    elif name == "scroll":
        return _screen_scroll(
            x=args.get("x", 0),
            y=args.get("y", 0),
            amount=args.get("amount", -3),
        )
    elif name == "drag":
        return _screen_drag(
            start_x=args.get("start_x", 0),
            start_y=args.get("start_y", 0),
            end_x=args.get("end_x", 0),
            end_y=args.get("end_y", 0),
            duration=args.get("duration", 0.5),
        )
    elif name == "uia_click_element":
        return _uia_click_element(
            name=args.get("name", ""),
            automation_id=args.get("automation_id", ""),
            class_name=args.get("class_name", ""),
            timeout=args.get("timeout", 5.0),
        )
    elif name == "uia_locate_element":
        return _uia_locate_element(
            name=args.get("name", ""),
            automation_id=args.get("automation_id", ""),
            class_name=args.get("class_name", ""),
            highlight=bool(args.get("highlight", True)),
            timeout=args.get("timeout", 5.0),
        )
    elif name in ("point_at", "screen_point_at"):
        return screen_point_at(
            x=args.get("x", 0),
            y=args.get("y", 0),
            label=args.get("label", "Point"),
        )
    elif name == "highlight_region":
        return screen_highlight_region(
            x=args.get("x", 0),
            y=args.get("y", 0),
            width=args.get("width", 64),
            height=args.get("height", 64),
            label=args.get("label", "Look Here"),
        )
    elif name == "camera_frame":
        return _capture_camera_frame()
    return {"success": False, "error": f"Unknown vision tool: {name}"}


# ─── Agent class ──────────────────────────────────────────────────────────────

class VisionAgent(BaseAgent):
    name        = "vision"
    description = "Captures and analyzes what is visible on the screen."

    async def run(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        results = []

        try:
            for tool_call in task.tools:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})

                logger.info("[VisionAgent] Executing tool='{}' args={}", tool_name, tool_args)
                result = execute_vision_tool(tool_name, tool_args)
                logger.info("[VisionAgent] Result: {}", result)
                results.append(result)

            has_error = any(isinstance(r, dict) and r.get("error") for r in results)

            if has_error:
                task.status = TaskStatus.FAILED
                task.error  = self._format_result(results)
            else:
                task.status = TaskStatus.DONE
                task.raw_results = results
                task.result = self._format_result(results)

        except Exception as e:
            logger.error("[VisionAgent] Unexpected error: {}", e)
            task.status = TaskStatus.FAILED
            task.error  = str(e)

        return task



















