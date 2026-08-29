"""
tools/system_tools.py — OS-level integration tools.
Clipboard, system status, weather, volume control, and social messaging (WhatsApp / Instagram).
"""

from __future__ import annotations
import os
import json
import re
import urllib.request
import urllib.parse
import subprocess
import sys
import webbrowser
import psutil

from loguru import logger

# ─── Schemas for LLM function-calling ────────────────────────────────────────

SYSTEM_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "clipboard_read",
            "description": "Read the current text from the system clipboard.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_write",
            "description": "Write text to the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to copy to clipboard."}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get current CPU usage, memory usage, and battery status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a specified city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. 'London', 'Tokyo', 'New York'"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_volume",
            "description": "Adjust system volume (up, down, or mute).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["up", "down", "mute"], "description": "What to do with the volume."}
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_settings",
            "description": "Open the system Settings app.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_camera",
            "description": "Open the Camera app.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_wifi",
            "description": "Turn Wi-Fi on, off, or toggle it on the local machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["toggle", "on", "off"],
                        "default": "toggle",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_bluetooth",
            "description": "Turn Bluetooth on, off, or toggle it on the local machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["toggle", "on", "off"],
                        "default": "toggle",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": "Send a WhatsApp message to a phone number or contact name. Opens WhatsApp Desktop/Web with the message pre-filled and auto-sends it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Phone number (e.g. '+919876543210') or contact name (e.g. 'Rahul')"},
                    "message": {"type": "string", "description": "Message text to send"}
                },
                "required": ["recipient", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_instagram_message",
            "description": "Open Instagram Direct Messages to message a contact or username.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Instagram username or contact name, e.g. 'alex_dev', 'Priya'"},
                    "message": {"type": "string", "description": "Message text to send"}
                },
                "required": ["recipient", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Compose and send an email. Opens the user's default email client (Outlook, Gmail, Thunderbird) with all fields pre-filled. User just needs to click Send.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address, e.g. 'john@example.com'"},
                    "subject": {"type": "string", "description": "Email subject line", "default": ""},
                    "body": {"type": "string", "description": "Email body text", "default": ""},
                    "cc": {"type": "string", "description": "CC email address (optional)", "default": ""},
                },
                "required": ["to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": "Send a message on Telegram to a username or phone number. Opens Telegram Desktop with the chat and message pre-filled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Telegram username (e.g. '@username' or 'username') or phone number"},
                    "message": {"type": "string", "description": "Message text to send"},
                },
                "required": ["recipient", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a countdown timer that Baby announces when done. Duration can be '10 seconds', '5 minutes', '1 hour', or 'in half an hour'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "string", "description": "Duration, e.g. '10 minutes', '30 seconds', 'in an hour'"},
                    "label": {"type": "string", "description": "Optional label for the timer, e.g. 'pasta'" }
                },
                "required": ["duration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder Baby announces at the specified time. 'when' can be 'in 20 minutes', 'at 3pm', 'at 8:30 am', 'tomorrow 9am', 'every day at 8am'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to remind the user about, e.g. 'call the dentist', 'meeting at 4'"},
                    "when": {"type": "string", "description": "When to remind, e.g. 'in 20 minutes', 'at 3pm', 'every day at 8am'"}
                },
                "required": ["text", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Set an alarm that Baby announces at a specific clock time. 'time' can be '7am', '7:30 pm', '06:00'. Optional 'repeat' (e.g. 'daily') makes it recurring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "description": "Clock time, e.g. '7am', '7:30 pm'"},
                    "label": {"type": "string", "description": "Optional label, e.g. 'wake up'"},
                    "repeat": {"type": "string", "description": "Optional: 'daily' or 'every day' for a recurring alarm", "default": ""}
                },
                "required": ["time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled",
            "description": "Cancel pending timers, reminders, or alarms. Query can be a word from the label, 'timer', 'reminder', 'alarm', or 'all'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to cancel: label text, kind, or 'all'"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled",
            "description": "List all pending timers, reminders, and alarms.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": "Recall what Baby has learned about the user: their name, preferred language, frequently used apps, preferences, known schedule patterns, and transcription corrections. Use to personalize replies or answer 'what do you know about me'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Optional topic to focus on (name, apps, preferences, schedules). Empty returns everything.", "default": ""}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_play_pause",
            "description": "Play or pause the currently playing media (Spotify, YouTube, etc.) via the media keys.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_next_track",
            "description": "Skip to the next media track.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_previous_track",
            "description": "Go back to the previous media track.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_stop",
            "description": "Stop the currently playing media.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_knowledge_graph",
            "description": "Open the neural network viewer to visualize Baby's knowledge graph — her memory, learned concepts, relationships, and capabilities. Use when user asks 'show me your brain', 'show me your memory', 'how do you work', 'what can you do', 'show me your neural network', 'visualize your knowledge'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

SYSTEM_TOOL_RISK: dict[str, str] = {
    "clipboard_read":         "low",
    "clipboard_write":        "medium",
    "get_system_status":      "low",
    "get_weather":            "low",
    "adjust_volume":          "medium",
    "open_settings":          "low",
    "open_camera":            "low",
    "toggle_wifi":            "high",
    "toggle_bluetooth":       "high",
    "send_whatsapp_message":  "medium",
    "send_instagram_message": "medium",
    "send_email":             "medium",
    "send_telegram_message":  "medium",
    "set_timer":              "low",
    "set_reminder":           "low",
    "set_alarm":              "low",
    "cancel_scheduled":       "medium",
    "list_scheduled":         "low",
    "memory_recall":          "low",
    "media_play_pause":       "low",
    "media_next_track":       "low",
    "media_previous_track":   "low",
    "media_stop":             "low",
}

# ─── Implementations ──────────────────────────────────────────────────────────

def clipboard_read() -> dict:
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Clipboard"],
                text=True, encoding="utf-8", stderr=subprocess.DEVNULL
            ).strip()
            return {"success": True, "text": output}
        else:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            return {"success": True, "text": text}
    except Exception as e:
        return {"success": False, "error": f"Failed to read clipboard: {e}"}


def clipboard_write(text: str) -> dict:
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; $input | Set-Clipboard"],
                stdin=subprocess.PIPE, text=True, encoding="utf-8"
            )
            process.communicate(input=text)
            return {"success": True, "message": "Copied text to clipboard."}
        else:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return {"success": True, "message": "Copied text to clipboard."}
    except Exception as e:
        return {"success": False, "error": f"Failed to write clipboard: {e}"}


def get_system_status() -> dict:
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        bat_info = "N/A"
        if battery:
            plugged = "Plugged in" if battery.power_plugged else "On battery"
            bat_info = f"{battery.percent}% ({plugged})"

        return {
            "success": True,
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 1),
            "ram_total_gb": round(ram.total / (1024**3), 1),
            "battery": bat_info,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_weather(city: str) -> dict:
    try:
        clean_city = city.strip()
        url = f"https://wttr.in/{urllib.parse.quote(clean_city)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "BABY/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            current = data["current_condition"][0]
            temp_c = current["temp_C"]
            temp_f = current["temp_F"]
            desc = current["weatherDesc"][0]["value"]
            humidity = current["humidity"]

            return {
                "success": True,
                "city": clean_city,
                "condition": desc,
                "temp_c": f"{temp_c}°C",
                "temp_f": f"{temp_f}°F",
                "humidity": f"{humidity}%",
            }
    except Exception as e:
        return {"success": False, "error": f"Failed to fetch weather: {e}"}


def adjust_volume(action: str) -> dict:
    try:
        if sys.platform == "win32":
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            speakers = AudioUtilities.GetSpeakers()
            if not speakers:
                return {"success": False, "error": "No speaker device available."}

            # pycaw >= 20251023 returns a high-level AudioDevice wrapper;
            # older versions return the raw IMMDevice with .Activate().
            if hasattr(speakers, "EndpointVolume"):
                volume = speakers.EndpointVolume
            else:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))

            if action == "mute":
                is_muted = volume.GetMute()
                volume.SetMute(not is_muted, None)
                return {"success": True, "message": "Muted" if not is_muted else "Unmuted"}
            elif action == "up":
                cur = volume.GetMasterVolumeLevelScalar()
                new_vol = min(1.0, cur + 0.1)
                volume.SetMasterVolumeLevelScalar(new_vol, None)
                return {"success": True, "message": f"Volume increased to {int(new_vol * 100)}%"}
            elif action == "down":
                cur = volume.GetMasterVolumeLevelScalar()
                new_vol = max(0.0, cur - 0.1)
                volume.SetMasterVolumeLevelScalar(new_vol, None)
                return {"success": True, "message": f"Volume decreased to {int(new_vol * 100)}%"}
        return {"success": False, "error": "Volume control is Windows-only currently."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_settings() -> dict:
    try:
        if sys.platform == "win32":
            subprocess.Popen(["start", "ms-settings:"], shell=True)
            return {"success": True, "message": "Opened Windows Settings."}
        return {"success": False, "error": "Settings app launch is Windows-only."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_camera() -> dict:
    try:
        if sys.platform == "win32":
            subprocess.Popen(["start", "microsoft.windows.camera:"], shell=True)
            return {"success": True, "message": "Opened Camera app."}
        return {"success": False, "error": "Camera app launch is Windows-only."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=12
    )


def toggle_wifi(action: str = "toggle") -> dict:
    mode = (action or "toggle").lower().strip()
    if mode not in ("toggle", "on", "off"):
        return {"error": f"Invalid action '{action}'. Use 'toggle', 'on' or 'off'."}
    if sys.platform != "win32":
        return {"error": "Wi-Fi toggle is supported on Windows host environments."}

    try:
        script = f"""
$adapters = Get-NetAdapter -Physical | Where-Object {{ $_.Name -like '*Wi-Fi*' -or $_.InterfaceDescription -like '*Wireless*' -or $_.InterfaceDescription -like '*802.11*' }}
if (-not $adapters) {{
    Write-Error "No Wi-Fi adapter found on this system."
    exit 1
}}
$adapter = $adapters[0]
if ('{mode}' -eq 'toggle') {{
    if ($adapter.Status -eq 'Up') {{
        Disable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
        $state = 'off'
    }} else {{
        Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
        $state = 'on'
    }}
}} elseif ('{mode}' -eq 'off') {{
    Disable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
    $state = 'off'
}} else {{
    Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
    $state = 'on'
}}
Write-Output $state
"""
        result = _run_powershell(script)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Failed to toggle Wi-Fi adapter."
            if "access is denied" in message.lower() or "requires elevation" in message.lower() or "permission" in message.lower():
                message = "Administrator privileges required to toggle Wi-Fi adapter. Please restart BABY as Administrator."
            return {"error": message}

        state = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else mode
        return {"success": True, "message": f"Wi-Fi turned {state}.", "state": state}
    except Exception as e:
        return {"error": str(e)}


def toggle_bluetooth(action: str = "toggle") -> dict:
    mode = (action or "toggle").lower().strip()
    if mode not in ("toggle", "on", "off"):
        return {"error": f"Invalid action '{action}'. Use 'toggle', 'on' or 'off'."}
    if sys.platform != "win32":
        return {"error": "Bluetooth toggle is supported on Windows host environments."}

    try:
        script = f"""
$devices = Get-PnpDevice -Class 'Bluetooth' -ErrorAction SilentlyContinue | Where-Object {{ $_.FriendlyName -like '*Bluetooth Radio*' -or $_.FriendlyName -like '*Bluetooth Adapter*' -or $_.Service -like '*Bth*' }}
if (-not $devices) {{
    $devices = Get-PnpDevice -Class 'Bluetooth' -ErrorAction SilentlyContinue | Where-Object {{ $_.Status -eq 'OK' -or $_.Status -eq 'Disabled' }}
}}
if (-not $devices) {{
    Write-Error "No Bluetooth adapter hardware found on this system."
    exit 1
}}
$device = $devices[0]
if ('{mode}' -eq 'toggle') {{
    if ($device.Status -eq 'OK') {{
        Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction Stop
        $state = 'off'
    }} else {{
        Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction Stop
        $state = 'on'
    }}
}} elseif ('{mode}' -eq 'off') {{
    Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction Stop
    $state = 'off'
}} else {{
    Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction Stop
    $state = 'on'
}}
Write-Output $state
"""
        result = _run_powershell(script)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Failed to toggle Bluetooth."
            if "access is denied" in message.lower() or "requires elevation" in message.lower() or "permission" in message.lower():
                message = "Administrator privileges required to toggle Bluetooth device. Please restart BABY as Administrator."
            return {"error": message}

        state = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else mode
        return {"success": True, "message": f"Bluetooth turned {state}.", "state": state}
    except Exception as e:
        return {"error": str(e)}


def send_whatsapp_message(recipient: str = "", message: str = "") -> dict:
    """Send a WhatsApp message using the wa.me deep-link, with auto-send via pyautogui."""
    try:
        clean_recipient = (recipient or "").strip()
        clean_msg = (message or "").strip()
        encoded_msg = urllib.parse.quote(clean_msg) if clean_msg else ""

        # Detect phone number (7+ digits, optionally with +/spaces/dashes)
        phone_digits = re.sub(r"[^\d]", "", clean_recipient)
        is_phone = len(phone_digits) >= 7

        if is_phone:
            # wa.me deep-link opens WhatsApp Desktop (if installed) or WhatsApp Web
            # with the number and message pre-populated.
            url = f"https://wa.me/{phone_digits}" + (f"?text={encoded_msg}" if encoded_msg else "")
            webbrowser.open(url)

            # Try to auto-send using pyautogui after giving WhatsApp time to load
            auto_sent = False
            try:
                import pyautogui
                import time as _time
                _time.sleep(4)          # wait for WhatsApp to open and render
                pyautogui.hotkey("enter")  # press Enter to send the pre-filled message
                auto_sent = True
            except ImportError:
                # pyautogui not installed — fall back to clipboard so user can paste
                clipboard_write(clean_msg)
            except Exception as _e:
                logger.warning("[SystemTools] pyautogui auto-send failed: {}", _e)
                clipboard_write(clean_msg)

            return {
                "success": True,
                "message": (
                    f"WhatsApp message sent to +{phone_digits}!" if auto_sent
                    else f"WhatsApp opened for +{phone_digits}. Message copied to clipboard — paste it and press Enter to send."
                ),
                "auto_sent": auto_sent,
                "url": url,
            }
        else:
            # Contact name — WhatsApp has no deep-link by name;
            # open WhatsApp Web and copy message to clipboard.
            url = "https://web.whatsapp.com/"
            webbrowser.open(url)
            if clean_msg:
                clipboard_write(clean_msg)
            return {
                "success": True,
                "message": (
                    f"WhatsApp opened for '{clean_recipient}'. "
                    + (f"Your message is copied to clipboard — find the contact, paste (Ctrl+V) and press Enter to send." if clean_msg else "")
                ),
                "note": "WhatsApp doesn't support deep-linking by contact name — manual contact selection required.",
                "recipient": clean_recipient,
            }
    except Exception as e:
        logger.error("[SystemTools] Failed to send WhatsApp message: {}", e)
        return {"error": str(e)}


def send_instagram_message(recipient: str = "", message: str = "") -> dict:
    """Open Instagram Direct Messages for a user."""
    try:
        clean_recipient = (recipient or "").strip().lstrip("@")
        clean_msg = (message or "").strip()

        url = "https://www.instagram.com/direct/inbox/"
        if clean_recipient:
            url = f"https://www.instagram.com/direct/t/{clean_recipient}/"

        webbrowser.open(url)
        if clean_msg:
            clipboard_write(clean_msg)

        return {
            "success": True,
            "message": f"Opened Instagram Direct Messages for '{clean_recipient}'." + (f" Message copied to clipboard — paste (Ctrl+V) and press Enter to send: '{clean_msg}'" if clean_msg else ""),
            "recipient": clean_recipient,
        }
    except Exception as e:
        logger.error("[SystemTools] Failed to send Instagram message: {}", e)
        return {"error": str(e)}


# ─── Email ────────────────────────────────────────────────────────────────────

def send_email(to: str = "", subject: str = "", body: str = "", cc: str = "") -> dict:
    """Compose an email using the system default email client via mailto: URI.

    Opens Outlook / Gmail / Thunderbird (whichever is the default) with all
    fields pre-filled. The user reviews and clicks Send.
    """
    try:
        clean_to = (to or "").strip()
        clean_subject = (subject or "").strip()
        clean_body = (body or "").strip()
        clean_cc = (cc or "").strip()

        if not clean_to:
            return {"error": "Recipient email address ('to') is required."}

        # Build the mailto: URI
        params: list[str] = []
        if clean_subject:
            params.append(f"subject={urllib.parse.quote(clean_subject)}")
        if clean_body:
            params.append(f"body={urllib.parse.quote(clean_body)}")
        if clean_cc:
            params.append(f"cc={urllib.parse.quote(clean_cc)}")

        mailto_url = (
            f"mailto:{urllib.parse.quote(clean_to)}"
            + ("?" + "&".join(params) if params else "")
        )

        # Gmail web compose URL as fallback
        gmail_url = (
            "https://mail.google.com/mail/?view=cm"
            f"&to={urllib.parse.quote(clean_to)}"
            + (f"&su={urllib.parse.quote(clean_subject)}" if clean_subject else "")
            + (f"&body={urllib.parse.quote(clean_body)}" if clean_body else "")
            + (f"&cc={urllib.parse.quote(clean_cc)}" if clean_cc else "")
        )

        # Try the mailto: scheme first (opens native desktop client)
        try:
            webbrowser.open(mailto_url)
        except Exception:
            webbrowser.open(gmail_url)

        return {
            "success": True,
            "message": (
                f"Email compose window opened for {clean_to}."
                + (f" Subject: '{clean_subject}'." if clean_subject else "")
                + " Review and click Send when ready."
            ),
            "to": clean_to,
            "subject": clean_subject,
            "mailto": mailto_url,
            "gmail_fallback": gmail_url,
        }
    except Exception as e:
        logger.error("[SystemTools] Failed to compose email: {}", e)
        return {"error": str(e)}


# ─── Telegram ─────────────────────────────────────────────────────────────────

def send_telegram_message(recipient: str = "", message: str = "") -> dict:
    """Send a Telegram message via the tg:// deep-link (opens Telegram Desktop)."""
    try:
        clean_recipient = (recipient or "").strip().lstrip("@")
        clean_msg = (message or "").strip()
        encoded_msg = urllib.parse.quote(clean_msg) if clean_msg else ""

        if not clean_recipient:
            return {"error": "Recipient (Telegram username or phone) is required."}

        # Detect if it looks like a phone number
        phone_digits = re.sub(r"[^\d]", "", clean_recipient)
        is_phone = len(phone_digits) >= 7 and not re.search(r"[a-zA-Z]", clean_recipient)

        if is_phone:
            tg_url = (
                f"tg://resolve?phone={phone_digits}"
                + (f"&text={encoded_msg}" if encoded_msg else "")
            )
            fallback_url = f"https://t.me/+{phone_digits}"
        else:
            tg_url = (
                f"tg://resolve?domain={urllib.parse.quote(clean_recipient)}"
                + (f"&text={encoded_msg}" if encoded_msg else "")
            )
            fallback_url = f"https://t.me/{urllib.parse.quote(clean_recipient)}"

        # Try Telegram Desktop deep-link first (Windows startfile understands tg://)
        opened_desktop = False
        if sys.platform == "win32":
            try:
                import os as _os
                _os.startfile(tg_url)
                opened_desktop = True
            except Exception:
                pass

        if not opened_desktop:
            webbrowser.open(tg_url)

        # Copy message to clipboard so user can paste if deep-link doesn't pre-fill
        if clean_msg:
            clipboard_write(clean_msg)

        # Try to auto-send after a short delay
        auto_sent = False
        if opened_desktop and clean_msg:
            try:
                import pyautogui
                import time as _time
                _time.sleep(3)
                pyautogui.hotkey("enter")
                auto_sent = True
            except ImportError:
                pass
            except Exception as _e:
                logger.warning("[SystemTools] Telegram auto-send failed: {}", _e)

        return {
            "success": True,
            "message": (
                f"Telegram message sent to @{clean_recipient}!" if auto_sent
                else (
                    f"Telegram opened for @{clean_recipient}."
                    + (f" Message copied to clipboard — paste (Ctrl+V) and press Enter to send." if clean_msg else "")
                )
            ),
            "auto_sent": auto_sent,
            "recipient": clean_recipient,
        }
    except Exception as e:
        logger.error("[SystemTools] Failed to send Telegram message: {}", e)
        return {"error": str(e)}


# ─── Reminders / timers / alarms ─────────────────────────────────────────────

def _reminder_svc():
    from core.reminders import get_reminder_service
    svc = get_reminder_service()
    if svc is None:
        return None, {"error": "Reminder service is not initialized."}
    return svc, None


def set_timer(duration: str = "", label: str = "") -> dict:
    svc, err = _reminder_svc()
    if err or svc is None:
        return err or {"error": "Reminder service is not initialized."}
    if not duration:
        return {"error": "Please provide a duration, e.g. '10 minutes'."}
    try:
        entry = svc.schedule_from_when("timer", label or "Timer", duration)
        import datetime as _dt
        when = _dt.datetime.fromtimestamp(entry.due_at).strftime("%H:%M:%S")
        return {"success": True, "message": f"Timer set for {duration}. It will go off at {when}."}
    except ValueError as e:
        return {"error": str(e)}


def set_reminder(text: str = "", when: str = "") -> dict:
    svc, err = _reminder_svc()
    if err or svc is None:
        return err or {"error": "Reminder service is not initialized."}
    if not text:
        return {"error": "Please tell me what to remind you about."}
    if not when:
        return {"error": "Please tell me when, e.g. 'in 20 minutes' or 'at 3pm'."}
    try:
        entry = svc.schedule_from_when("reminder", text, when)
        return {"success": True, "message": svc.describe(entry) + " set. I will remind you."}
    except ValueError as e:
        return {"error": str(e)}


def set_alarm(time: str = "", label: str = "", repeat: str = "") -> dict:
    svc, err = _reminder_svc()
    if err or svc is None:
        return err or {"error": "Reminder service is not initialized."}
    if not time:
        return {"error": "Please provide an alarm time, e.g. '7am'."}
    when = time
    if repeat and repeat.strip().lower() not in ("", "no", "none", "false"):
        when = f"{time} {repeat}"
    try:
        entry = svc.schedule_from_when("alarm", label or "Alarm", when)
        return {"success": True, "message": svc.describe(entry) + " set."}
    except ValueError as e:
        return {"error": str(e)}


def cancel_scheduled(query: str = "") -> dict:
    svc, err = _reminder_svc()
    if err or svc is None:
        return err or {"error": "Reminder service is not initialized."}
    removed = svc.cancel(query or "all")
    if not removed:
        return {"success": True, "message": "Nothing matching was scheduled."}
    labels = ", ".join(r.text for r in removed[:5])
    more = f" and {len(removed) - 5} more" if len(removed) > 5 else ""
    return {"success": True, "message": f"Cancelled {len(removed)} scheduled item(s): {labels}{more}"}


def list_scheduled() -> dict:
    svc, err = _reminder_svc()
    if err or svc is None:
        return err or {"error": "Reminder service is not initialized."}
    items = svc.list()
    if not items:
        return {"success": True, "message": "No pending timers, reminders, or alarms."}
    lines = []
    import datetime as _dt
    for r in items:
        t = _dt.datetime.fromtimestamp(r.due_at).strftime("%H:%M")
        rep = f" (repeats {r.repeat})" if r.repeat else ""
        lines.append(f"- {r.kind}: {r.text} at {t}{rep}")
    return {"success": True, "message": "Scheduled items:\n" + "\n".join(lines)}


def memory_recall(topic: str = "") -> dict:
    try:
        from core.memory_engine import get_memory
        mem = get_memory()

        # Use the new query-based recall if a topic is provided
        if topic and topic.strip():
            result = mem.memory_recall(topic)
            if result:
                return {"success": True, "message": result}

        # Fall back to full profile block
        block = mem.get_profile_system_block() or "Baby has not learned anything about the user yet."
        stats = mem.stats()
        info = block
        if stats:
            info += f"\nSession stats: {json.dumps(stats)}"
        return {"success": True, "message": info}
    except Exception as e:
        logger.error("[SystemTools] memory_recall failed: {}", e)
        return {"error": f"Memory recall failed: {e}"}


def show_knowledge_graph() -> dict:
    """Open the neural network viewer to visualize Baby's knowledge graph."""
    from core.knowledge_graph import knowledge_graph
    stats = knowledge_graph.get_stats()
    return {
        "success": True,
        "message": "Opening neural network viewer...",
        "stats": stats
    }


# ─── Media control (system media keys) ───────────────────────────────────────

def _media_key(vk: int) -> dict:
    """Send a media key press via SendInput (works with Spotify, YouTube, etc.)."""
    try:
        import ctypes
        from ctypes import wintypes

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _I)]

        def press(vk_code: int, keyup: bool = False) -> None:
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.ki.wVk = vk_code
            inp.ki.dwFlags = KEYEVENTF_KEYUP if keyup else 0
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        press(vk)
        press(vk, keyup=True)
        return {"success": True}
    except Exception as e:
        logger.error("[SystemTools] Media key {:#x} failed: {}", vk, e)
        return {"error": f"Failed to send media key: {e}"}


_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_MEDIA_NEXT_TRACK = 0xB0
_VK_MEDIA_PREV_TRACK = 0xB1
_VK_MEDIA_STOP = 0xB2


def media_play_pause() -> dict:
    return _media_key(_VK_MEDIA_PLAY_PAUSE)


def media_next_track() -> dict:
    return _media_key(_VK_MEDIA_NEXT_TRACK)


def media_previous_track() -> dict:
    return _media_key(_VK_MEDIA_PREV_TRACK)


def media_stop() -> dict:
    return _media_key(_VK_MEDIA_STOP)


# ─── Dispatcher ───────────────────────────────────────────────────────────────

_REGISTRY = {
    "clipboard_read":         clipboard_read,
    "clipboard_write":        clipboard_write,
    "get_system_status":      get_system_status,
    "get_weather":            get_weather,
    "adjust_volume":          adjust_volume,
    "open_settings":          open_settings,
    "open_camera":            open_camera,
    "toggle_wifi":            toggle_wifi,
    "toggle_bluetooth":       toggle_bluetooth,
    "send_whatsapp_message":  send_whatsapp_message,
    "send_instagram_message": send_instagram_message,
    "send_email":             send_email,
    "send_telegram_message":  send_telegram_message,
    "set_timer":              set_timer,
    "set_reminder":           set_reminder,
    "set_alarm":              set_alarm,
    "cancel_scheduled":       cancel_scheduled,
    "list_scheduled":         list_scheduled,
    "memory_recall":          memory_recall,
    "media_play_pause":       media_play_pause,
    "media_next_track":       media_next_track,
    "media_previous_track":   media_previous_track,
    "media_stop":             media_stop,
    "show_knowledge_graph":   show_knowledge_graph,
}

def execute_system_tool(name: str, args: dict) -> dict:
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown system tool: '{name}'"}

    normalized_args = dict(args) if isinstance(args, dict) else {}
    if name == "adjust_volume":
        if "action" not in normalized_args:
            for k in ("mode", "volume", "direction", "type"):
                if k in normalized_args:
                    val = str(normalized_args.pop(k)).lower()
                    if "up" in val or "increase" in val or "louder" in val:
                        normalized_args["action"] = "up"
                    elif "down" in val or "decrease" in val or "quieter" in val:
                        normalized_args["action"] = "down"
                    elif "mute" in val or "silence" in val:
                        normalized_args["action"] = "mute"
                    break
            if "action" not in normalized_args:
                normalized_args["action"] = "up"
    elif name == "get_weather":
        if "city" not in normalized_args:
            for k in ("location", "place", "city_name", "target"):
                if k in normalized_args:
                    normalized_args["city"] = normalized_args.pop(k)
                    break
    elif name in ("toggle_wifi", "toggle_bluetooth"):
        if "action" not in normalized_args:
            for k in ("mode", "state", "status"):
                if k in normalized_args:
                    normalized_args["action"] = normalized_args.pop(k)
                    break
    elif name == "clipboard_write":
        if "text" not in normalized_args:
            for k in ("content", "string", "data", "value"):
                if k in normalized_args:
                    normalized_args["text"] = normalized_args.pop(k)
                    break
    elif name in ("send_whatsapp_message", "send_instagram_message", "send_telegram_message"):
        if "recipient" not in normalized_args:
            for k in ("contact", "user", "username", "to", "person", "number", "target"):
                if k in normalized_args:
                    normalized_args["recipient"] = str(normalized_args.pop(k))
                    break
        if "message" not in normalized_args:
            for k in ("text", "msg", "body", "content", "saying"):
                if k in normalized_args:
                    normalized_args["message"] = str(normalized_args.pop(k))
                    break
    elif name == "send_email":
        if "to" not in normalized_args:
            for k in ("recipient", "email", "address", "contact", "target"):
                if k in normalized_args:
                    normalized_args["to"] = str(normalized_args.pop(k))
                    break
        if "subject" not in normalized_args:
            for k in ("title", "re", "about"):
                if k in normalized_args:
                    normalized_args["subject"] = str(normalized_args.pop(k))
                    break
        if "body" not in normalized_args:
            for k in ("message", "content", "text", "msg"):
                if k in normalized_args:
                    normalized_args["body"] = str(normalized_args.pop(k))
                    break
    elif name == "set_timer":
        if "duration" not in normalized_args:
            for k in ("time", "when", "amount", "for"):
                if k in normalized_args:
                    normalized_args["duration"] = str(normalized_args.pop(k))
                    break
        if "label" not in normalized_args and "text" in normalized_args:
            normalized_args["label"] = normalized_args.pop("text")
    elif name == "set_reminder":
        if "when" not in normalized_args:
            for k in ("time", "at", "in"):
                if k in normalized_args:
                    normalized_args["when"] = str(normalized_args.pop(k))
                    break
        if "text" not in normalized_args:
            for k in ("message", "about", "label", "what"):
                if k in normalized_args:
                    normalized_args["text"] = str(normalized_args.pop(k))
                    break
    elif name == "set_alarm":
        if "time" not in normalized_args:
            for k in ("when", "at"):
                if k in normalized_args:
                    normalized_args["time"] = str(normalized_args.pop(k))
                    break
    elif name == "cancel_scheduled":
        if "query" not in normalized_args:
            for k in ("what", "name", "kind", "all", "everything"):
                if k in normalized_args:
                    normalized_args["query"] = str(normalized_args.pop(k))
                    break

    try:
        logger.debug("[SystemTool] {}({})", name, normalized_args)
        result = fn(**normalized_args)
        logger.debug("[SystemTool] {} → {}", name, result)
        return result
    except TypeError as e:
        return {"error": f"Invalid arguments for '{name}': {e}"}
    except Exception as e:
        return {"error": str(e)}



















