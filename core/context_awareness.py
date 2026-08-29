"""
core/context_awareness.py — JARVIS-level Context Awareness System.

Provides the assistant with real-time system context:
- Current time, date, day of week
- Running processes and active windows
- Recent files and documents
- System resource usage (CPU, RAM, battery)
- User's recent activity patterns

This context is injected into every LLM call so the assistant can make
intelligent, context-aware suggestions and proactive recommendations.
"""

from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ContextAwareness:
    """Gathers and provides real-time system context for JARVIS-level intelligence."""

    def __init__(self):
        self._cached_context: dict[str, Any] = {}
        self._last_update: float = 0
        self._cache_ttl: float = 30  # Refresh every 30 seconds

    def get_context_block(self) -> str:
        """Return a formatted string of current system context for LLM injection."""
        import time
        now = time.time()
        if now - self._last_update < self._cache_ttl and self._cached_context:
            return self._format_context(self._cached_context)

        context = self._gather_context()
        self._cached_context = context
        self._last_update = now
        return self._format_context(context)

    def _gather_context(self) -> dict[str, Any]:
        """Gather comprehensive system context."""
        context: dict[str, Any] = {}

        # Time & Date
        now = datetime.now()
        context["time"] = now.strftime("%I:%M %p")
        context["date"] = now.strftime("%A, %B %d, %Y")
        context["hour"] = now.hour
        context["is_late_night"] = now.hour >= 0 and now.hour < 6
        context["is_work_hours"] = now.hour >= 9 and now.hour <= 17
        context["is_weekend"] = now.weekday() >= 5

        # System info
        context["platform"] = platform.system()
        context["hostname"] = platform.node()

        # Running processes (top relevant ones)
        context["running_apps"] = self._get_running_apps()

        # Recent files
        context["recent_files"] = self._get_recent_files()

        # System resources
        context["system_resources"] = self._get_system_resources()

        # User patterns
        context["user_patterns"] = self._get_user_patterns()

        return context

    def _get_running_apps(self) -> list[str]:
        """Get list of currently running applications."""
        apps = []
        try:
            if platform.system() == "Windows":
                # Use tasklist to get running processes
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    seen = set()
                    for line in lines[:50]:  # Limit to first 50
                        parts = line.split(",")
                        if parts:
                            name = parts[0].strip('"').lower()
                            # Filter out system processes and duplicates
                            if (name not in seen and
                                not name.startswith("system") and
                                not name.startswith("svchost") and
                                not name.startswith("csrss") and
                                not name.startswith("lsass") and
                                not name.startswith("services") and
                                not name.startswith("winlogon") and
                                name.endswith(".exe")):
                                seen.add(name)
                                apps.append(name.replace(".exe", ""))
            elif platform.system() == "Linux":
                result = subprocess.run(
                    ["ps", "aux", "--sort=-pcpu"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    seen = set()
                    for line in lines[1:20]:  # Skip header, limit to 20
                        parts = line.split()
                        if len(parts) >= 11:
                            cmd = parts[10]
                            if "/" in cmd:
                                cmd = cmd.split("/")[-1]
                            if cmd not in seen:
                                apps.append(cmd)
            elif platform.system() == "Darwin":
                result = subprocess.run(
                    ["ps", "aux", "--sort=-pcpu"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    seen = set()
                    for line in lines[1:20]:
                        parts = line.split()
                        if len(parts) >= 11:
                            cmd = parts[10]
                            if "/" in cmd:
                                cmd = cmd.split("/")[-1]
                            if cmd not in seen:
                                seen.add(cmd)
                                apps.append(cmd)
        except Exception as e:
            logger.debug("[Context] Failed to get running apps: {}", e)
        return apps[:15]  # Return top 15

    def _get_recent_files(self) -> list[str]:
        """Get recently accessed files."""
        recent = []
        try:
            if platform.system() == "Windows":
                # Check common recent file locations
                user_profile = os.environ.get("USERPROFILE", "")
                recent_dirs = [
                    Path(user_profile) / "Downloads",
                    Path(user_profile) / "Documents",
                    Path(user_profile) / "Desktop",
                ]
                for dir_path in recent_dirs:
                    if dir_path.exists():
                        try:
                            files = sorted(
                                dir_path.glob("*"),
                                key=lambda f: f.stat().st_mtime if f.exists() else 0,
                                reverse=True
                            )
                            for f in files[:3]:  # Top 3 from each
                                if f.is_file() and not f.name.startswith("."):
                                    recent.append(f.name)
                        except (PermissionError, OSError):
                            continue
        except Exception as e:
            logger.debug("[Context] Failed to get recent files: {}", e)
        return recent[:10]  # Return top 10

    def _get_system_resources(self) -> dict[str, Any]:
        """Get system resource usage."""
        resources = {}
        try:
            import psutil
            resources["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            resources["ram_percent"] = mem.percent
            resources["ram_available_gb"] = round(mem.available / (1024**3), 1)

            # Battery (if available)
            battery = psutil.sensors_battery()
            if battery:
                resources["battery_percent"] = battery.percent
                resources["battery_plugged"] = battery.power_plugged
        except ImportError:
            # psutil not available, try basic info
            resources["platform"] = platform.system()
        except Exception as e:
            logger.debug("[Context] Failed to get system resources: {}", e)
        return resources

    def _get_user_patterns(self) -> dict[str, Any]:
        """Infer user patterns from time and history."""
        patterns = {}
        now = datetime.now()

        # Time-based patterns
        if now.hour >= 0 and now.hour < 6:
            patterns["activity"] = "late_night"
            patterns["suggestion"] = "Consider taking a break or enabling night mode"
        elif now.hour >= 6 and now.hour < 9:
            patterns["activity"] = "morning"
            patterns["suggestion"] = "Good morning! Ready to start the day?"
        elif now.hour >= 9 and now.hour < 12:
            patterns["activity"] = "work_morning"
            patterns["suggestion"] = "Peak productivity hours. Shall I help with focused work?"
        elif now.hour >= 12 and now.hour < 14:
            patterns["activity"] = "lunch"
            patterns["suggestion"] = "Lunch break? I can set a reminder for after."
        elif now.hour >= 14 and now.hour < 17:
            patterns["activity"] = "work_afternoon"
            patterns["suggestion"] = "Afternoon session. Need any task management?"
        elif now.hour >= 17 and now.hour < 21:
            patterns["activity"] = "evening"
            patterns["suggestion"] = "Evening time. Winding down or still working?"
        else:
            patterns["activity"] = "night"
            patterns["suggestion"] = "Late evening. Need anything before you wrap up?"

        if now.weekday() >= 5:
            patterns["day_type"] = "weekend"
        else:
            patterns["day_type"] = "weekday"

        return patterns

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format context into a readable string for LLM injection."""
        lines = ["SYSTEM CONTEXT (real-time):"]

        # Time
        lines.append(f"  Time: {context.get('time', 'Unknown')} on {context.get('date', 'Unknown')}")

        # Activity pattern
        patterns = context.get("user_patterns", {})
        if patterns.get("activity"):
            lines.append(f"  Activity period: {patterns['activity'].replace('_', ' ').title()}")

        # Running apps (summarized)
        apps = context.get("running_apps", [])
        if apps:
            # Group common apps
            dev_apps = [a for a in apps if any(d in a.lower() for d in ("code", "pycharm", "intellij", "atom", "sublime", "git"))]
            browser_apps = [a for a in apps if any(b in a.lower() for b in ("chrome", "firefox", "edge", "opera", "brave"))]
            media_apps = [a for a in apps if any(m in a.lower() for m in ("spotify", "vlc", "itunes", "media"))]
            office_apps = [a for a in apps if any(o in a.lower() for o in ("word", "excel", "powerpoint", "outlook", "teams"))]

            app_summary = []
            if dev_apps:
                app_summary.append(f"Development: {', '.join(dev_apps[:3])}")
            if browser_apps:
                app_summary.append(f"Browsers: {', '.join(browser_apps[:2])}")
            if media_apps:
                app_summary.append(f"Media: {', '.join(media_apps[:2])}")
            if office_apps:
                app_summary.append(f"Office: {', '.join(office_apps[:2])}")
            if not app_summary:
                app_summary.append(f"Running: {', '.join(apps[:5])}")

            lines.append(f"  Active applications: {'; '.join(app_summary)}")

        # Recent files
        files = context.get("recent_files", [])
        if files:
            lines.append(f"  Recent files: {', '.join(files[:5])}")

        # System resources
        resources = context.get("system_resources", {})
        if resources:
            res_parts = []
            if "cpu_percent" in resources:
                res_parts.append(f"CPU: {resources['cpu_percent']}%")
            if "ram_percent" in resources:
                res_parts.append(f"RAM: {resources['ram_percent']}%")
            if "battery_percent" in resources:
                battery_status = "charging" if resources.get("battery_plugged") else "on battery"
                res_parts.append(f"Battery: {resources['battery_percent']}% ({battery_status})")
            if res_parts:
                lines.append(f"  System resources: {', '.join(res_parts)}")

        return "\n".join(lines)

    def get_proactive_suggestions(self) -> list[str]:
        """Generate proactive suggestions based on current context."""
        suggestions = []
        context = self._gather_context()
        patterns = context.get("user_patterns", {})
        resources = context.get("system_resources", {})
        hour = context.get("hour", 12)

        # Time-based suggestions
        if patterns.get("activity") == "late_night":
            suggestions.append("It's late night. Consider enabling night mode or taking a break.")
        elif patterns.get("activity") == "morning":
            suggestions.append("Good morning! Shall I check your schedule for today?")
        elif patterns.get("activity") == "lunch":
            suggestions.append("Lunch time! Need me to set a reminder for after lunch?")

        # Resource-based suggestions
        if resources.get("cpu_percent", 0) > 80:
            suggestions.append("CPU usage is high. Would you like me to check what's consuming resources?")
        if resources.get("ram_percent", 0) > 85:
            suggestions.append("Memory usage is high. Consider closing unused applications.")
        if resources.get("battery_percent", 100) < 20 and not resources.get("battery_plugged"):
            suggestions.append("Battery is low! Consider plugging in your charger.")

        # Weekend suggestions
        if patterns.get("day_type") == "weekend":
            suggestions.append("It's the weekend! Need help with personal tasks or relaxation?")

        return suggestions[:3]  # Return top 3 suggestions


# Singleton
_instance: ContextAwareness | None = None


def get_context_awareness() -> ContextAwareness:
    """Return the global ContextAwareness singleton."""
    global _instance
    if _instance is None:
        _instance = ContextAwareness()
    return _instance



















