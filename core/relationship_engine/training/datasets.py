"""
core/relationship_engine/training/datasets.py — Synthetic training data and vocabulary for each type.
"""

from __future__ import annotations
from typing import Dict, List, Tuple


# Synthetic training pairs: (action_a, action_b, expected_type, confidence)
SYNTHETIC_DATASET: List[Tuple[str, str, str, float]] = [
    # SEQUENTIAL
    ("open the file", "read the contents", "SEQUENTIAL", 0.9),
    ("save the document", "close the editor", "SEQUENTIAL", 0.85),
    ("take a screenshot", "annotate the image", "SEQUENTIAL", 0.8),
    ("download the file", "extract the archive", "SEQUENTIAL", 0.85),
    ("compile the code", "run the tests", "SEQUENTIAL", 0.9),
    ("install dependencies", "start the server", "SEQUENTIAL", 0.9),
    ("create the directory", "move the files", "SEQUENTIAL", 0.85),
    ("first clean up", "then deploy", "SEQUENTIAL", 0.95),

    # CAUSAL
    ("click the submit button", "the form gets submitted", "CAUSAL", 0.9),
    ("delete the cache", "the app reloads data", "CAUSAL", 0.85),
    ("change the temperature", "the heater turns on", "CAUSAL", 0.8),
    ("turn off the lights", "the room goes dark", "CAUSAL", 0.9),
    ("run the migration", "the database schema updates", "CAUSAL", 0.85),
    ("press the emergency button", "the alarm sounds", "CAUSAL", 0.9),

    # CONDITIONAL
    ("check if the file exists", "then read it", "CONDITIONAL", 0.9),
    ("verify the password", "grant access", "CONDITIONAL", 0.85),
    ("test the connection", "send the data", "CONDITIONAL", 0.8),
    ("check available space", "download the update", "CONDITIONAL", 0.85),
    ("validate the input", "process the request", "CONDITIONAL", 0.9),
    ("if the server is up", "deploy the changes", "CONDITIONAL", 0.95),

    # PARALLEL
    ("open the browser", "start the music player", "PARALLEL", 0.9),
    ("take a screenshot", "record the audio", "PARALLEL", 0.85),
    ("scan for viruses", "defragment the disk", "PARALLEL", 0.8),
    ("upload the files", "sync the database", "PARALLEL", 0.85),
    ("check email", "check calendar", "PARALLEL", 0.9),
    ("simultaneously open both apps", "run them together", "PARALLEL", 0.95),

    # CONTEXTUAL
    ("find the project file", "open the related document", "CONTEXTUAL", 0.8),
    ("search for the email", "reply to it", "CONTEXTUAL", 0.85),
    ("locate the meeting notes", "share them with the team", "CONTEXTUAL", 0.8),
    ("look up the API docs", "implement the endpoint", "CONTEXTUAL", 0.85),
    ("about the project timeline", "show the milestones", "CONTEXTUAL", 0.9),

    # CONTRADICTORY
    ("save the file", "delete the file", "CONTRADICTORY", 0.9),
    ("enable the feature", "disable the feature", "CONTRADICTORY", 0.9),
    ("start the server", "stop the server", "CONTRADICTORY", 0.85),
    ("lock the door", "unlock the door", "CONTRADICTORY", 0.9),
    ("connect to wifi", "disconnect from wifi", "CONTRADICTORY", 0.85),
    ("turn on the light", "turn off the light", "CONTRADICTORY", 0.95),

    # INDEPENDENT
    ("check the weather", "open the calculator", "INDEPENDENT", 0.9),
    ("take a screenshot", "play some music", "INDEPENDENT", 0.85),
    ("read the news", "count the files", "INDEPENDENT", 0.8),
    ("open the settings", "check the battery", "INDEPENDENT", 0.85),
    ("look at the clock", "open the terminal", "INDEPENDENT", 0.9),
]

# Full vocabulary for tokenization (5000 base + these relationship terms)
VOCABULARY: List[str] = [
    # Core relationship keywords
    "then", "after", "before", "first", "second", "third", "next", "finally",
    "because", "caused", "leads", "results", "therefore", "thus", "hence",
    "if", "unless", "provided", "assuming", "when", "whenever", "case",
    "simultaneously", "concurrent", "parallel", "together", "while", "meanwhile",
    "regarding", "context", "related", "concerning", "about", "respect",
    "but", "however", "instead", "contrary", "opposite", "conflicts", "overrides",
    "separate", "unrelated", "independent", "standalone", "distinct",
    # Action verbs
    "open", "close", "read", "write", "save", "delete", "copy", "move",
    "click", "type", "scroll", "drag", "press", "enter", "submit",
    "search", "find", "locate", "scan", "check", "verify", "validate",
    "run", "execute", "start", "stop", "enable", "disable", "toggle",
    "upload", "download", "install", "uninstall", "update", "upgrade",
    "create", "remove", "add", "edit", "modify", "change", "set",
    "send", "receive", "share", "export", "import", "sync", "backup",
    "connect", "disconnect", "connect", "reconnect", "login", "logout",
    "lock", "unlock", "encrypt", "decrypt", "compress", "extract",
    "play", "pause", "stop", "resume", "skip", "repeat", "shuffle",
    "take", "capture", "record", "snapshot", "screenshot", "capture",
    "list", "show", "display", "hide", "expand", "collapse", "minimize",
    "maximize", "resize", "move", "position", "align", "arrange",
    # Nouns
    "file", "folder", "directory", "document", "image", "video", "audio",
    "application", "program", "window", "tab", "page", "screen", "display",
    "server", "database", "network", "connection", "website", "browser",
    "settings", "configuration", "preference", "option", "parameter",
    "email", "message", "notification", "alert", "reminder", "calendar",
    "project", "task", "todo", "note", "document", "report", "summary",
    "user", "admin", "guest", "account", "profile", "permission",
    "password", "key", "token", "certificate", "credential",
    "system", "process", "service", "daemon", "thread", "task",
    "memory", "storage", "disk", "cpu", "gpu", "network", "bandwidth",
    "weather", "time", "date", "clock", "timer", "alarm",
    "music", "song", "playlist", "album", "artist", "genre",
    "photo", "picture", "camera", "video", "recording", "screenshot",
    "code", "script", "function", "class", "module", "package",
    "test", "debug", "log", "error", "warning", "info",
    "build", "compile", "deploy", "release", "version", "update",
    "cache", "buffer", "queue", "stack", "pool", "registry",
    "button", "menu", "dialog", "panel", "toolbar", "statusbar",
    "text", "input", "output", "result", "response", "request",
    "status", "state", "mode", "level", "phase", "stage",
    "data", "content", "information", "resource", "asset",
    "device", "hardware", "sensor", "peripheral", "driver",
    "light", "temperature", "humidity", "motion", "sound",
    "wifi", "bluetooth", "ethernet", "usb", "serial",
]



















