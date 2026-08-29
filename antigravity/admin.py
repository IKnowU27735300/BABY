"""
antigravity/admin.py — Anti-Gravity Administrator with Multi-Task Dynamic DAG Orchestration.

The central Orchestrator that:
  1. Receives user text from BabyOrchestrator
  2. Calls the Planner LLM to produce a multi-task GoalPlan (DAG format)
  3. Enforces the ConsentGate for risky actions
  4. Schedules and executes tasks in topological stages with dynamic parameter binding
  5. Retries/re-plans on failure until the goal is satisfied
  6. Returns a short, localized summary string back to Baby

This file is the ONLY entry point for Baby → Anti-Gravity.
Call: result = await admin.process(text, context, tts, ui, consent_gate)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from antigravity.goal_tracker import AgentType, GoalPlan, GoalTracker, Task, TaskStatus
from antigravity.task_context import TaskExecutionContext
from antigravity.agents.system_agent  import SystemAgent
from antigravity.agents.browser_agent import BrowserAgent, BROWSER_TOOLS_SCHEMA, BROWSER_TOOL_RISK
from antigravity.agents.vision_agent  import VisionAgent,  VISION_TOOLS_SCHEMA,  VISION_TOOL_RISK
from antigravity.agents.context_agent import ContextAgent, CONTEXT_TOOLS_SCHEMA, CONTEXT_TOOL_RISK, execute_context_tool
from antigravity.agents.learner_agent import LearnerAgent, SkillStore
from tools.file_tools   import FILE_TOOLS_SCHEMA, TOOL_RISK as FILE_TOOL_RISK
from tools.screen_tools import SCREEN_TOOLS_SCHEMA, SCREEN_TOOL_RISK
from tools.system_tools import SYSTEM_TOOLS_SCHEMA
from tools.math_tools   import MATH_TOOLS_SCHEMA, MATH_TOOL_RISK
from tools.code_sandbox import CODE_EXECUTION_TOOL, CODE_EXECUTION_RISK
from tools.home_assistant_tools import HOME_ASSISTANT_TOOLS_SCHEMA, HOME_ASSISTANT_TOOL_RISK
from antigravity.agents.vision_agent import execute_vision_tool

if TYPE_CHECKING:
    from llm.ollama_client import OllamaClient
    from core.consent_gate  import ConsentGate, ActionPlan
    from audio.tts          import TTSEngine


# ─── PLANNER SYSTEM PROMPT ────────────────────────────────────────────────────

def _format_schema_details(schema: list[dict]) -> str:
    formatted = []
    for item in schema:
        func = item.get("function", {})
        name = func.get("name")
        desc = func.get("description", "")
        params = func.get("parameters", {}).get("properties", {})
        req = func.get("parameters", {}).get("required", [])
        param_strs = []
        for p_name, p_info in params.items():
            req_flag = " (required)" if p_name in req else ""
            p_type = p_info.get("type", "string")
            p_desc = p_info.get("description", p_type)
            param_strs.append(f"{p_name}{req_flag}: {p_desc}")
        param_fmt = ", ".join(param_strs) if param_strs else "no args"
        formatted.append(f"  - {name}({param_fmt}): {desc}")
    return "\n".join(formatted)


_FILE_TOOL_SCHEMAS = _format_schema_details(FILE_TOOLS_SCHEMA)
_SCREEN_TOOL_SCHEMAS = _format_schema_details(SCREEN_TOOLS_SCHEMA)
_SYSTEM_TOOL_SCHEMAS = _format_schema_details(SYSTEM_TOOLS_SCHEMA)
_MATH_TOOL_SCHEMAS = _format_schema_details(MATH_TOOLS_SCHEMA)
_BROWSER_TOOL_SCHEMAS = _format_schema_details(BROWSER_TOOLS_SCHEMA)
_VISION_TOOL_SCHEMAS = _format_schema_details(VISION_TOOLS_SCHEMA)
_CONTEXT_TOOL_SCHEMAS = _format_schema_details(CONTEXT_TOOLS_SCHEMA)
_CODE_TOOL_SCHEMAS = _format_schema_details([CODE_EXECUTION_TOOL])
_HA_TOOL_SCHEMAS = _format_schema_details(HOME_ASSISTANT_TOOLS_SCHEMA)


_PLANNER_SYSTEM_PROMPT = f"""\
You are the Anti-Gravity Multi-Task Planner, the strategic brain of the BABY AI assistant.

Analyze the user's request and output ONLY valid JSON.
If the user commands multiple tasks or a multi-step sequence, break it down into a list of structured sub-tasks.
Format your output as valid JSON matching this exact structure:

{{
  "intent": "<overall user goal>",
  "tasks": [
    {{
      "id": "task_1",
      "description": "<what this task accomplishes>",
      "agent_type": "<system|browser|vision|context|conversation|learn>",
      "depends_on": [],
      "requires_consent": <true|false>,
      "risk_level": "<low|medium|high>",
      "tools": [{{"name": "<tool_name>", "args": {{<arguments>}}}}]
    }}
  ]
}}

DEPENDENCY & DATA-FLOW BINDING RULES:
- Use "depends_on": ["task_1"] if a sub-task depends on a previous task's completion.
- To pass output from task_1 into task_2 arguments, use dynamic placeholders like "$task_1.result".

AGENT ROUTING RULES:
- "conversation" → greeting, general knowledge, jokes, chat, mathematical explanations/solving, logical reasoning puzzles (no tools needed)
- "system"       → file operations, app launch, clipboard, system status, weather, volume, settings, camera, Wi-Fi, Bluetooth
- "browser"      → open websites, search, navigate URLs, fetch page content
- "vision"       → take screenshot, read visible text, locate text on screen, point at UI elements
- "vision" uia_locate_element → "where is X?" / "show me where X is" / "point out X": find the element on screen (desktop icons, taskbar, native apps) and circle it with a pointer mark. Requires the user to have shared their screen first (the tool enforces this). Prefer uia_locate_element over vision_locate_text for apps/icons; use vision_locate_text only for plain on-screen text.
- "context"      → store/recall user preferences or facts

SCREEN VISIBILITY & CAPABILITY RULES (read carefully — these override everything else):
- If the user asks "is my screen visible?", "can you see my screen?", "are you watching my
  screen?", "do you have screen access?", "is screen share on/off?", "is screen sharing enabled?",
  or ANY variation asking about whether their screen is visible to you →
  ALWAYS use agent_type "conversation". NEVER use a vision, system, or any other tool agent.
  Just tell the user conversationally whether screen sharing is currently active or not.
- If the user asks you to do something you have NO built-in tool for, use agent_type "conversation"
  to honestly explain what you can and cannot do — do NOT pretend to succeed.
- NEVER return a generic "Done! Task completed." for a task that did not actually execute.

CRITICAL SEARCH-ON-WEBSITE RULE (applies to "search for X on <website>" / "open <site> and search for X"):
- This is ALWAYS a SINGLE agent_type "browser" task that opens the site's DIRECT SEARCH
  URL — NEVER split it into open + vision type_text/key_press (vision typing requires
  the user to share their screen first and will fail otherwise).
- Use browser_open_app with:
    - Amazon:       https://www.amazon.com/s?k=<query>
    - YouTube:      https://www.youtube.com/results?search_query=<query>
    - Google:       https://www.google.com/search?q=<query>
    - DuckDuckGo:   https://duckduckgo.com/?q=<query>
    - Flipkart:     https://www.flipkart.com/search?q=<query>
    - other sites:  https://<site>/search?q=<query> (or the site's known search URL)
- Encode spaces in the query as "+" (e.g. "1TB SSD" → "1TB+SSD").
- Only fall back to browser_search ("<query> on <site>") when you do not know the
  site's search URL pattern.
- Use vision type_text/key_press ONLY for interactions AFTER the search page is open
  (scrolling, clicking a result, adding to cart, etc.) — never for the search itself.

QUICK KNOWLEDGE RULE ("what is X" / "who is X" / "tell me about X" / "latest news on X"):
- When the user asks for factual/current information, use agent_type "browser" with a
  SINGLE task using tool "web_quick_answer" with args {{"question": "<the question>"}}.
  This searches the web, fetches the top result, and returns its text so Baby can
  summarize it aloud — no browser window opens, no screen share needed.
- Do NOT use web_quick_answer when the user wants the website OPENED — that is
  browser_open_app / browser_navigate.
- "learn"        → user wants to automate or do something you have NO built-in tool for

CRITICAL APP-LAUNCH DISAMBIGUATION (read carefully before choosing an agent):
- Opening a DESKTOP APPLICATION is ALWAYS agent_type "system" with tool
  "open_application" and args {{"app_name": "<name>"}}. Examples of desktop apps:
  file explorer, windows explorer, calculator, notepad, paint, command prompt,
  powershell, task manager, settings, camera, photos, calendar, mail, vscode,
  telegram, discord, slack, zoom, skype, brave, spotify, vlc, obs, etc.
- "file explorer" / "windows explorer" / "explorer" means the FILE BROWSER app
  (explorer.exe). It is NOT a web browser. NEVER use browser_open_app or open_url
  for it. Use: {{"name": "open_application", "args": {{"app_name": "file explorer"}}}}.
- Only use the BROWSER agent when the user explicitly wants a WEB BROWSER app
  (chrome, firefox, edge, safari, opera, brave) or a website/URL/web search.
- When unsure whether something is a desktop app, prefer "system" / open_application.

AVAILABLE TOOLS & EXACT SCHEMAS:
[file tools]
{_FILE_TOOL_SCHEMAS}

[screen tools]
{_SCREEN_TOOL_SCHEMAS}

[system tools]
{_SYSTEM_TOOL_SCHEMAS}

[browser tools]
{_BROWSER_TOOL_SCHEMAS}

[vision tools]
{_VISION_TOOL_SCHEMAS}

[context tools]
{_CONTEXT_TOOL_SCHEMAS}

[code execution tools]
{_CODE_TOOL_SCHEMAS}

[home assistant tools]
{_HA_TOOL_SCHEMAS}

- learn: (no tool args — triggers the autonomous research pipeline)

RISK LEVELS:
- low:    read-only (list, screenshot, search, open)
- medium: creates or launches (open app, navigate, web research)
- high:   destroys or modifies (delete, move, overwrite)

FILE EDITING RULES:
- To read a file: system agent, tool "read_file" with args {{"path": "..."}}.
- To create a new file or completely rewrite a file: system agent, tool "write_file" with args {{"path": "...", "content": "..."}}.
- To append text to the end of a file: system agent, tool "append_file" with args {{"path": "...", "content": "..."}}.
- To make a surgical edit (find & replace, insert before/after, delete/replace lines): system agent, tool "edit_file" with args {{"path": "...", "operation": "find_replace|insert_after|insert_before|delete_lines|replace_lines", ...}}.
- write_file / append_file / edit_file / copy_file / move_file / delete_file / create_directory are
  ALWAYS risk "medium" or "high" and MUST have requires_consent=true — the
  user must explicitly approve every file mutation.

MESSAGING RULES:
- To send a WhatsApp message: system agent, tool "send_whatsapp_message" with args {{"recipient": "...", "message": "..."}}.
- To send an Email: system agent, tool "send_email" with args {{"to": "...", "subject": "...", "body": "..."}}.
- To send a Telegram message: system agent, tool "send_telegram_message" with args {{"recipient": "...", "message": "..."}}.
- To send an Instagram DM: system agent, tool "send_instagram_message" with args {{"recipient": "...", "message": "..."}}.

PDF READING & SUMMARIZATION RULES:
- To read, scan, or summarize a PDF file by path: system agent, tool "read_pdf" with args {{"path": "..."}}.
- To scan or summarize an opened PDF on screen: vision agent, tool "vision_read_screen" or "vision_screenshot".
- For PDF summarization, use the structured content from read_pdf (includes metadata, page numbers, tables).

MATH COMPUTATION RULES:
- For ANY calculation, equation, or math problem: use math tools, NOT the LLM's arithmetic.
- To evaluate an expression: system agent, tool "evaluate_expression" with args {{"expression": "2+2"}}.
- To solve an equation: system agent, tool "solve_equation" with args {{"equations": ["x**2 - 4 == 0"], "variables": ["x"]}}.
- To compute a derivative: system agent, tool "differentiate" with args {{"expression": "x**2", "variable": "x"}}.
- To compute an integral: system agent, tool "integrate" with args {{"expression": "x**2"}}.
- To simplify an expression: system agent, tool "simplify_expression" with args {{"expression": "x**2 + 2*x + 1"}}.
- To factor a polynomial: system agent, tool "factorize" with args {{"expression": "x**2 - 4"}}.
- To expand an expression: system agent, tool "expand_expression" with args {{"expression": "(x+1)*(x-1)"}}.
- To calculate statistics: system agent, tool "calculate_statistics" with args {{"numbers": [1,2,3,4,5]}}.
- To convert units: system agent, tool "convert_units" with args {{"value": 100, "from_unit": "km", "to_unit": "miles"}}.
- Math tools are risk "low" and auto-approved — no consent needed.



requires_consent = true for risk_level "medium" or "high".
requires_consent = false for risk_level "low".

PRIVACY MANDATE (non-negotiable):
- You NEVER include real user names, phone numbers, file paths, or IDs in tool args.
- If the user shares sensitive data (passwords, bank details), acknowledge it warmly
  but do NOT pass it to any tool argument verbatim.
- All web search queries you generate must be generic and anonymized.

AUTONOMOUS LEARNING PROTOCOL:
- Use agent_type "learn" ONLY when you have NO existing tool that can accomplish the task.
- When a pre-searched workflow is injected into your context, USE IT to plan a system/browser task.
- Tag the learning intent clearly so Baby can ask consent before any web access.

CRITICAL: Output ONLY valid JSON. No markdown, no explanation, no code blocks.
CRITICAL: If agent_type is "conversation" or "learn", set tools to [] always.
"""

_FEW_SHOT_EXAMPLES = [
    {
        "user": "send hello to John on WhatsApp",
        "plan": {
            "intent": "send hello to John on WhatsApp",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Send WhatsApp message to John",
                    "agent_type": "system",
                    "depends_on": [],
                    "requires_consent": True,
                    "risk_level": "medium",
                    "tools": [{"name": "send_whatsapp_message", "args": {"recipient": "John", "message": "hello"}}]
                }
            ]
        }
    },
    {
        "user": "open file explorer and find budget.xlsx",
        "plan": {
            "intent": "open file explorer and search for budget.xlsx",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Open File Explorer app",
                    "agent_type": "system",
                    "depends_on": [],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "open_application", "args": {"app_name": "file explorer"}}]
                },
                {
                    "id": "task_2",
                    "description": "Search for file budget.xlsx",
                    "agent_type": "system",
                    "depends_on": ["task_1"],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "search_files", "args": {"query": "budget.xlsx"}}]
                }
            ]
        }
    },
    {
        "user": "take screenshot and read text",
        "plan": {
            "intent": "capture screen and extract text",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Take screenshot",
                    "agent_type": "vision",
                    "depends_on": [],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "vision_screenshot", "args": {}}]
                },
                {
                    "id": "task_2",
                    "description": "Extract text from screenshot",
                    "agent_type": "vision",
                    "depends_on": ["task_1"],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "vision_read_screen", "args": {}}]
                }
            ]
        }
    },
    {
        "user": "what is 25 times 4",
        "plan": {
            "intent": "calculate 25 * 4",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Evaluate 25 * 4",
                    "agent_type": "system",
                    "depends_on": [],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "evaluate_expression", "args": {"expression": "25 * 4"}}]
                }
            ]
        }
    },
    {
        "user": "summarize this pdf C:\\Documents\\report.pdf",
        "plan": {
            "intent": "read and summarize PDF report",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Read PDF content with metadata",
                    "agent_type": "system",
                    "depends_on": [],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "read_pdf", "args": {"path": "C:\\Documents\\report.pdf"}}]
                }
            ]
        }
    },
    {
        "user": "convert 100 km to miles",
        "plan": {
            "intent": "convert 100 kilometers to miles",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Convert 100 km to miles",
                    "agent_type": "system",
                    "depends_on": [],
                    "requires_consent": False,
                    "risk_level": "low",
                    "tools": [{"name": "convert_units", "args": {"value": 100, "from_unit": "km", "to_unit": "miles"}}]
                }
            ]
        }
    },
]
# ─── DETERMINISTIC APP-RESOLUTION GUARD ───────────────────────────────────────

_DESKTOP_APP_ALIASES = {
    # File Explorer & OS
    "file explorer": "file explorer",
    "file manager": "file explorer",
    "explorer": "file explorer",
    "windows explorer": "file explorer",
    "my computer": "file explorer",
    "this pc": "file explorer",
    "calculator": "calculator",
    "calc": "calculator",
    "notepad": "notepad",
    "paint": "paint",
    "mspaint": "paint",
    "command prompt": "command prompt",
    "cmd": "command prompt",
    "terminal": "command prompt",
    "powershell": "powershell",
    "pwsh": "powershell",
    "task manager": "task manager",
    "taskmgr": "task manager",
    "settings": "settings",
    "control panel": "settings",
    "camera": "camera",
    "photos": "photos",
    "store": "store",
    "microsoft store": "store",
    "weather": "weather",
    "maps": "maps",
    "clock": "clock",
    "calendar": "calendar",
    "mail": "mail",
    "snipping tool": "snipping tool",
    "snip": "snipping tool",
    "wordpad": "wordpad",
    "registry editor": "registry editor",
    "regedit": "registry editor",
    # Browsers
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
    "edge": "edge",
    "microsoft edge": "edge",
    "brave": "brave",
    "brave browser": "brave",
    "opera": "opera",
    "opera gx": "opera",
    "vivaldi": "vivaldi",
    "tor": "tor",
    "arc": "arc",
    # Messaging & Social
    "whatsapp": "whatsapp",
    "whatsapp desktop": "whatsapp",
    "telegram": "telegram",
    "discord": "discord",
    "slack": "slack",
    "teams": "teams",
    "microsoft teams": "teams",
    "zoom": "zoom",
    "skype": "skype",
    "signal": "signal",
    "instagram": "instagram",
    "insta": "instagram",
    # Media & Audio
    "spotify": "spotify",
    "vlc": "vlc",
    "vlc media player": "vlc",
    "itunes": "itunes",
    "media player": "media player",
    "windows media player": "media player",
    "audacity": "audacity",
    "obs": "obs",
    "obs studio": "obs",
    # Office & Productivity
    "word": "word",
    "microsoft word": "word",
    "excel": "excel",
    "microsoft excel": "excel",
    "powerpoint": "powerpoint",
    "microsoft powerpoint": "powerpoint",
    "outlook": "outlook",
    "microsoft outlook": "outlook",
    "onenote": "onenote",
    "microsoft onenote": "onenote",
    "libreoffice": "libreoffice",
    "notion": "notion",
    "figma": "figma",
    "canva": "canva",
    # Development & Tools
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "visual studio": "visual studio",
    "code": "vscode",
    "pycharm": "pycharm",
    "intellij": "intellij",
    "android studio": "android studio",
    "sublime text": "sublime text",
    "sublime": "sublime text",
    "notepad++": "notepad++",
    "notepad plus plus": "notepad++",
    "postman": "postman",
    "docker": "docker",
    "docker desktop": "docker",
    "virtualbox": "virtualbox",
    "vmware": "vmware",
    "git bash": "git bash",
# Gaming
    "steam": "steam",
    "epic games": "epic games",
    "epic": "epic games",
    "battle.net": "battle.net",
    "battlenet": "battle.net",
    "ubisoft connect": "ubisoft connect",
    "uplay": "ubisoft connect",
    "gog galaxy": "gog galaxy",
    "gta 5": "gta 5",
    "gta v": "gta 5",
    "grand theft auto 5": "gta 5",
    "grand theft auto v": "gta 5",
    # VPN
    "planet vpn": "planet vpn",
    "vpn": "planet vpn",
    # AI & Development Tools
    "antigravity": "antigravity",
    "opencode": "opencode",
    "qwen": "qwen",
    "aratti": "aratti",
    "trae": "trae",
    "tldraw": "tldraw",
    "kiro": "kiro",
    "lm studio": "lm studio",
    "lmstudio": "lm studio",
    # Video Editing
    "capcut": "capcut",
    "cap cut": "capcut",
    # Design & Graphics
    "photoshop": "photoshop",
    "illustrator": "illustrator",
    "premiere": "premiere",
    "after effects": "after effects",
    "lightroom": "lightroom",
    "blender": "blender",
    "gimp": "gimp",
}

_BROWSER_KEYWORDS = ("chrome", "google chrome", "firefox", "mozilla", "edge",
                     "microsoft edge", "safari", "opera", "brave")
_WHERE_PREFIX = re.compile(r"\b(?:where (?:is|are|do i find)|where's|show me where|point (?:out|to)|highlight (?:the|where))\b", re.IGNORECASE)
_FAST_PATH_PATH_HINT = re.compile(
    r"(?:[A-Za-z]:[\\/]|[\\/]{1,2}|\.(?:txt|md|docx?|xlsx?|pptx?|py|js|json|csv|png|jpg|jpeg|log|sh|bat|ps1|ini|cfg|yaml|yml|toml|html?|pdf)\b"
    r"|desktop|documents|downloads|pictures|music|videos|folder|directory|my documents)"
)





def _complete_browser_urls(plan: GoalPlan, user_text: str) -> GoalPlan:
    """Fill missing URLs on browser tasks using the user's original wording.

    The planner LLM frequently emits browser_open_app({"browser": "chrome"})
    without a url for "open amazon in chrome", or stuffs the site name into
    the browser slot. This guard recovers the intended URL before execution
    so the browser never opens to just its home page.
    """
    from antigravity.agents.browser_agent import _BROWSER_EXECUTABLES, _normalize_url, _resolve_site_name

    for task in plan.tasks:
        if task.agent_type == AgentType.BROWSER:
            # BROWSER tasks must only carry browser tools. The planner
            # sometimes emits the system "open_application" tool here
            # ("open amazon" → open_application(app_name=chrome)), which
            # BrowserAgent cannot execute. Rewrite it into a browser tool.
            for tool in task.tools:
                if tool.get("name") != "open_application":
                    continue
                args = dict(tool.get("args", {}) or {})
                app  = (args.get("app_name") or "").strip().lower()
                site = _extract_site_from_text(user_text)
                if site:
                    tool["name"] = "browser_open_app"
                    tool["args"] = {"browser": "default", "url": site}
                elif app in _BROWSER_EXECUTABLES:
                    tool["name"] = "browser_open_app"
                    tool["args"] = {"browser": app, "url": ""}
                elif app:
                    tool["name"] = "browser_open_app"
                    tool["args"] = {"browser": "default", "url": _resolve_site_name(app) or ""}
                logger.info(
                    "[AntiGravity] Browser guard: rewrote 'open_application' → '{}' for task '{}'",
                    tool["name"], task.id
                )
        elif task.agent_type == AgentType.SYSTEM:
            # Mirror misroute: system tasks carrying browser tools → BROWSER.
            if any(tool.get("name") in ("browser_open_app", "browser_navigate",
                                        "open_url", "navigate_url", "open_website", "goto_url",
                                        "chrome_browser", "google_chrome_browser")
                   for tool in task.tools):
                task.agent_type = AgentType.BROWSER
                logger.warning(
                    "[AntiGravity] Browser guard: re-routed system task '{}' to BROWSER agent",
                    task.id
                )

        if task.agent_type != AgentType.BROWSER:
            continue
        for tool in task.tools:
            name = tool.get("name", "")
            if name not in ("browser_open_app", "browser_navigate", "open_url",
                            "navigate_url", "open_website", "goto_url",
                            "chrome_browser", "google_chrome_browser"):
                continue
            args = dict(tool.get("args", {}) or {})
            browser = (args.get("browser") or "").strip().lower()
            url     = (args.get("url") or "").strip()

            if url:
                args["url"] = _normalize_url(url)
                tool["args"] = args
                continue

            # No URL given — recover it. A non-browser value in the "browser"
            # slot is actually the site ("browser": "amazon").
            if browser and browser not in _BROWSER_EXECUTABLES:
                args["url"]     = _resolve_site_name(browser) or ""
                args["browser"] = "default"
            else:
                args["url"] = _extract_site_from_text(user_text)

            tool["args"] = args
            if args.get("url"):
                logger.info(
                    "[AntiGravity] Browser guard: recovered URL '{}' for task '{}' ('{}')",
                    args["url"], task.id, task.description
                )
    return plan

_BROWSER_KEYWORDS = ("chrome", "google chrome", "firefox", "mozilla", "edge",
                     "microsoft edge", "safari", "opera", "brave")

_BROWSER_NAME_WORDS = _BROWSER_KEYWORDS

_SITE_EXTRACTION_FILLER = (
    "open", "launch", "start", "run", "please", "could", "can", "you", "would",
    "me", "the", "a", "an", "in", "on", "for", "my", "and", "with", "using",
    "use", "to", "of", "at", "tab", "window", "web", "website", "site", "app",
    "application", "browser", "up", "it", "its", "that",
)


def _extract_site_from_text(user_text: str) -> str:
    """Best-effort recovery of a website URL if the user requested a known site, domain, or website."""
    from antigravity.agents.browser_agent import _KNOWN_SITES, _normalize_url

    text = user_text.lower()
    text_clean = re.sub(r"[^a-z0-9.\s]", " ", text)

    for key in sorted(_KNOWN_SITES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"\b", text_clean):
            return _KNOWN_SITES[key]

    has_domain = bool(re.search(r"https?://|www\.|(?:\.com|\.org|\.net|\.io|\.dev|\.ai|\.gov|\.edu|\.co\.in)\b", text))
    has_web_word = any(w in text for w in ("website", "web site", "webpage", "online"))

    if not (has_domain or has_web_word):
        return ""

    words = [w for w in text_clean.split() if w not in _SITE_EXTRACTION_FILLER]
    for w in words:
        if "." in w and w not in _BROWSER_NAME_WORDS:
            return _normalize_url(w)
    return ""


_APP_VERBS = (
    "open", "launch", "start", "run", "show me", "show", "turn on", "bring up", "exec", "execute",
    "kholo", "chalao", "dikhao", "banao", "chalu karo", "open karo", "start karo", "khol do"
)

_APP_SEARCH_PATHS = [
    Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
    Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]


def _find_installed_app(app_name: str) -> str | None:
    """Search common Windows locations for an installed app matching the name."""
    app_lower = app_name.lower().strip()
    app_stripped = re.sub(r"\s*(app|application|program|software)$", "", app_lower).strip()

    for search_path in _APP_SEARCH_PATHS:
        if not search_path.exists():
            continue
        try:
            for exe in search_path.rglob("*.exe"):
                exe_name = exe.stem.lower()
                if exe_name == app_stripped or exe_name.replace(" ", "") == app_stripped.replace(" ", ""):
                    return app_name
                if len(app_stripped) >= 3 and app_stripped in exe_name:
                    return app_name
        except (PermissionError, OSError):
            continue
    return None


def _detect_desktop_app(user_text: str) -> str | None:
    """Return a canonical app_name if the user asked to open an application."""
    text = user_text.lower().strip()

    if re.search(r"https?://|www\.|(?:\.com|\.org|\.net|\.io|\.dev|\.ai|\.gov|\.edu|\.co\.in)\b", text):
        return None
    if any(w in text for w in ("website", "web site", "webpage")):
        return None
    if _extract_site_from_text(user_text):
        return None

    _INTERNAL_COMMANDS = {
        "anti gravity", "antigravity", "anti-gravity",
    }
    if any(cmd in text for cmd in _INTERNAL_COMMANDS):
        return None

    has_verb = any(v in text for v in _APP_VERBS)

    if any(b in text for b in _BROWSER_KEYWORDS):
        return None

    for alias, canonical in _DESKTOP_APP_ALIASES.items():
        if alias in _BROWSER_KEYWORDS:
            continue
        if re.search(r"\b" + re.escape(alias) + r"\b", text):
            if has_verb or text == alias or text == f"my {alias}" or text == f"the {alias}":
                return canonical

    if has_verb:
        clean_text = text
        for v in sorted(_APP_VERBS, key=len, reverse=True):
            if v in clean_text:
                clean_text = clean_text.replace(v, " ", 1)
                break
        words = [w for w in clean_text.split() if w not in _SITE_EXTRACTION_FILLER]
        if 1 <= len(words) <= 3:
            candidate = " ".join(words).strip()
            if candidate not in _BROWSER_KEYWORDS and not _FAST_PATH_SEARCH_VERBS.search(text) and not _FAST_PATH_PATH_HINT.search(text):
                found = _find_installed_app(candidate)
                if found:
                    return found

    return None

_FAST_PATH_OPEN_VERBS = re.compile(r"\b(?:open|launch|start|go to|navigate to|open up)\b", re.IGNORECASE)
_FAST_PATH_SEARCH_VERBS = re.compile(r"\b(?:search(?: for)?|google|look up|research|find out about)\b", re.IGNORECASE)
_WHERE_PREFIX = re.compile(r"\b(?:where (?:is|are|do i find)|where's|show me where|point (?:out|to)|highlight (?:the|where))\b", re.IGNORECASE)
_FAST_PATH_PATH_HINT = re.compile(
    r"(?:[A-Za-z]:[\\/]|[\\/]{1,2}|\.(?:txt|md|docx?|xlsx?|pptx?|py|js|json|csv|png|jpg|jpeg|log|sh|bat|ps1|ini|cfg|yaml|yml|toml|html?|pdf)\b"
    r"|desktop|documents|downloads|pictures|music|videos|folder|directory|my documents)"
)


def _extract_browser_name(user_text: str) -> str:
    """Return which browser the user named ('' if none)."""
    text = user_text.lower()
    for kw in _BROWSER_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            return kw
    return ""


def _force_app_intent(plan: GoalPlan, user_text: str) -> GoalPlan:
    """Override misrouted app-open tasks to the correct SYSTEM open_application call."""
    canonical = _detect_desktop_app(user_text)
    if canonical is None:
        return plan

    text_low = user_text.lower()
    explicit_user_url = bool(
        re.search(r"https?://|www\.|(?:\.com|\.org|\.net|\.io|\.dev|\.ai|\.gov|\.edu|\.co\.in)\b", text_low)
        or any(w in text_low for w in ("website", "web site", "webpage", "online"))
        or _extract_site_from_text(user_text)
    )

    for idx, task in enumerate(plan.tasks):
        if (task.agent_type == AgentType.BROWSER or not task.tools) and not explicit_user_url:
            corrected = Task(
                id               = task.id,
                description      = f"Open {canonical.title() if canonical != 'file explorer' else 'File Explorer'}",
                agent_type       = AgentType.SYSTEM,
                tools            = [{"name": "open_application", "args": {"app_name": canonical}}],
                risk_level       = "low",
                requires_consent = False,
                depends_on       = task.depends_on,
            )
            logger.warning(
                "[AntiGravity] Guard corrected '{}' → SYSTEM open_application({}) (was agent={})",
                user_text, canonical, task.agent_type.value
            )
            plan.tasks[idx] = corrected
    return plan


# ─── LOCALIZED RESPONSES ─────────────────────────────────────────────────────

_SUCCESS_RESPONSES = {
    "en": "Done! The task has been completed.",
    "hi": "हो गया! आपका काम पूरा हो गया।",
    "kn": "ಆಯ್ತು! ನಿಮ್ಮ ಕೆಲಸ ಮುಗಿಯಿತು.",
    "mr": "झालं! तुमचं काम पूर्ण झालं.",
    "ta": "முடிந்தது! உங்கள் வேலை முடிந்துவிட்டது.",
    "te": "అయిపోయింది! మీ పని పూర్తయింది.",
}


def _build_success_message(plan: "GoalPlan", user_lang: str) -> str:
    """Build a specific, meaningful success message from the plan's results.

    Priority:
      1. If a completed task carried a tool result with a 'message' key, use it.
      2. If the plan intent is descriptive, echo it back.
      3. Fall back to the generic _SUCCESS_RESPONSES string.
    """
    # Collect meaningful tool-level messages from done tasks
    tool_messages: list[str] = []
    for t in plan.tasks:
        if t.status and t.status.value == "done" and t.raw_results:
            for res in t.raw_results:
                if isinstance(res, dict):
                    msg = res.get("message") or res.get("launched")
                    if msg and isinstance(msg, str):
                        # Exclude generic protocol strings like "ms-settings:"
                        if not msg.endswith(":") and len(msg) > 8:
                            tool_messages.append(msg)
    if tool_messages:
        # Return the first good tool message, capitalised
        best = tool_messages[0].strip()
        if not best.endswith((".", "!", "?")):
            best += "."
        return best

    # Use intent as a short confirmation
    intent = (plan.intent or "").strip()
    if intent and len(intent) > 4 and intent.lower() not in ("done", "task", "action"):
        intent_cap = intent[0].upper() + intent[1:]
        if not intent_cap.endswith((".", "!", "?")):
            intent_cap += " — done!"
        return intent_cap

    return _SUCCESS_RESPONSES.get(user_lang, _SUCCESS_RESPONSES["en"])


def _auto_dependencies(task: "Task") -> list[str]:
    """Derive implicit DAG dependencies from dynamic bindings.

    If a task's tool args or input_bindings reference "$task_N", it must run
    AFTER that task, even when the LLM omitted an explicit depends_on entry.
    Without this, bound args are resolved before the referenced task's result
    exists and the placeholder is passed through unresolved.
    """
    referenced: set[str] = set()
    pattern = re.compile(r"\$\{?([a-zA-Z0-9_\-]+)\.?[^}\s]*\}?")
    def scan(value) -> None:
        if isinstance(value, str):
            for m in pattern.finditer(value):
                token = m.group(1)
                if token.startswith("task_"):
                    referenced.add(token)
        elif isinstance(value, dict):
            for v in value.values():
                scan(v)
        elif isinstance(value, list):
            for item in value:
                scan(item)
    for tool in task.tools:
        scan(tool)
    scan(task.input_bindings)
    merged = list(dict.fromkeys(list(task.depends_on) + sorted(referenced)))
    if sorted(merged) != sorted(task.depends_on):
        logger.debug("[AntiGravity] Auto-derived dependencies for '{}': {}", task.id, merged)
    return merged


def _clean_urls_from_text(text: str) -> str:
    """Remove raw URLs and web addresses from task summaries for display and speech."""
    text = re.sub(r"\b(?:https?|ftp|file)://[^\s<>\"'\\]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwww\.[^\s<>\"'\\]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _format_task_results(plan: GoalPlan, user_lang: str) -> str:
    """Build a human-readable summary of completed task results."""
    summaries = []
    for t in plan.tasks:
        if t.status == TaskStatus.DONE and t.result:
            # t.result is the formatted string from SystemAgent._format_result
            result_str = _clean_urls_from_text(str(t.result))
            # Truncate overly long results
            if len(result_str) > 300:
                result_str = result_str[:300] + "..."
            if result_str:
                summaries.append(f"• {t.description}: {result_str}")
            else:
                summaries.append(f"• {t.description}: Done.")
    if summaries:
        return "Completed:\n" + "\n".join(summaries)
    return _SUCCESS_RESPONSES.get(user_lang, _SUCCESS_RESPONSES["en"])

_ERROR_RESPONSES = {
    "en": "I ran into a problem. Please try again.",
    "hi": "मुझे एक दिक्कत आई है। कृपया दोबारा कोशिश करें।",
    "kn": "ನನಗೆ ಒಂದು ಸಮಸ್ಯೆ ಆಯಿತು. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.",
    "mr": "मला एक अडचण आली. कृपया पुन्हा प्रयत्न करा.",
    "ta": "எனக்கு ஒரு பிரச்சினை வந்தது. தயவுசெய்து மீண்டும் முயற்சி செய்யுங்கள்.",
    "te": "నాకు ఒక సమస్య వచ్చింది. దయచేసి మళ్లీ ప్రయత్నించండి.",
}

_CLARIFY_RESPONSES = {
    "en": "I didn't quite catch that. Could you say it again?",
    "hi": "मैं ठीक से समझ नहीं पाई। क्या आप एक बार फिर कह सकते हैं?",
    "kn": "ನಾನು ಸರಿಯಾಗಿ ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಹೇಳಬಹುದೇ?",
    "mr": "मला नीट समजलं नाही. कृपया ते पुन्हा सांगाल का?",
    "ta": "எனக்கு சரியாகப் புரியவில்லை. மீண்டும் ஒருமுறை சொல்ல முடியுமா?",
    "te": "నాకు సరిగ్గా అర్థం కాలేదు. దయచేసి మరోసారి చెప్పగలరా?",
}
_DENY_RESPONSES = {
    "en": "Okay, I won't do that.",
    "hi": "ठीक है, मैं ऐसा नहीं करूँगी।",
    "kn": "ಸರಿ, ನಾನು ಅದನ್ನು ಮಾಡುವುದಿಲ್ಲ.",
    "mr": "ठीक आहे, मी ते करणार नाही.",
}


# ─── MAIN ADMIN CLASS ─────────────────────────────────────────────────────────

class AntiGravityAdmin:
    """
    The Anti-Gravity Administrator — Baby's backend brain.
    Supports Multi-Task Dynamic DAG Execution.
    """

    def __init__(self, llm: Any, guard=None, learner_config=None):
        self._llm     = llm
        self._tracker = GoalTracker(max_replan_cycles=2)
        self._guard   = guard
        self._plan_cache: dict[tuple[str, str], tuple[float, "GoalPlan | None"]] = {}

        # Fast-path plan cache with TTL
        self._fast_path_cache: dict[str, tuple[float, GoalPlan]] = {}
        self._fast_path_cache_ttl = 300.0  # 5 minutes

        skill_store_path = (
            learner_config.vector_db_path if learner_config else "data/skill_store"
        )
        min_confidence = (
            learner_config.min_confidence if learner_config else 0.75
        )
        self._skill_store = SkillStore(db_path=skill_store_path, guard=guard)
        self._learner     = LearnerAgent(
            llm=llm,
            skill_store=self._skill_store,
            guard=guard,
            min_confidence=min_confidence,
        )

        self._agents = {
            AgentType.SYSTEM:  SystemAgent(),
            AgentType.BROWSER: BrowserAgent(),
            AgentType.VISION:  VisionAgent(),
            AgentType.CONTEXT: ContextAgent(),
        }

        logger.info("[AntiGravity] Administrator initialized with {} agents.", len(self._agents))

    # ─── Fast-Path Plan Cache ────────────────────────────────────────────────

    def _get_cached_fast_path(self, key: str) -> GoalPlan | None:
        """Retrieve cached fast-path plan if not expired."""
        import time
        cache = getattr(self, "_fast_path_cache", {})
        if key in cache:
            ts, plan = cache[key]
            if time.time() - ts < self._fast_path_cache_ttl:
                logger.debug("[AntiGravity] Fast-path cache hit for: {}", key)
                return plan
            else:
                del cache[key]
        return None

    def _cache_fast_path(self, key: str, plan: GoalPlan):
        """Cache fast-path plan with timestamp."""
        import time
        if not hasattr(self, "_fast_path_cache"):
            self._fast_path_cache = {}
        self._fast_path_cache[key] = (time.time(), plan)

    # ── Public entry point ────────────────────────────────────────────────────

    async def process(
        self,
        user_text:    str,
        user_lang:    str,
        consent_gate: ConsentGate,
        tts:          TTSEngine,
        ui,
        pointer=None,
    ) -> str:
        """
        Main entry point called by BabyOrchestrator for every user command.
        Runs a ReAct feedback loop with Multi-Task DAG orchestration.
        """
        logger.info("[AntiGravity] Processing: '{}' (lang={})", user_text, user_lang)
        asyncio.create_task(
            asyncio.to_thread(self._maybe_store_feedback, user_text)
        )

        recalled_workflow, live_context, recent_feedback = await asyncio.gather(
            asyncio.to_thread(self._learner.lookup, user_text),
            asyncio.to_thread(self._capture_live_screen_context_sync, user_text),
            asyncio.to_thread(self._recall_recent_feedback),
        )

        skill_context = ""
        if recalled_workflow:
            logger.info("[AntiGravity] Found locally stored skill — injecting into context.")
            skill_context = (
                f"\n\n[RECALLED SKILL]\n"
                f"I already know how to do this. Here is the stored workflow:\n"
                f"{recalled_workflow}\n"
                f"Use this workflow to formulate the appropriate tool calls."
            )

        messages = [{"role": "system", "content": _PLANNER_SYSTEM_PROMPT}]
        if recent_feedback:
            messages.append({
                "role": "system",
                "content": (
                    "[RECENT USER FEEDBACK]\n"
                    f"{recent_feedback}\n"
                    "Use this to adapt tone, detail level, and action choices."
                ),
            })
        if live_context:
            messages.append({
                "role": "system",
                "content": (
                    "[LIVE SCREEN CONTEXT]\n"
                    f"{live_context}\n"
                    "Use this current screen information when choosing tools."
                ),
            })
        if skill_context:
            messages.append({"role": "system", "content": skill_context})
        messages.append({"role": "user", "content": user_text})

        max_cycles = 3
        cycle = 0

        while cycle < max_cycles:
            logger.info("[AntiGravity] ReAct Loop: Cycle {}/{}", cycle + 1, max_cycles)
            if cycle == 0:
                # Zero-LLM fast path: common commands (open site/browser, web
                # search, app launch, volume, file ops with explicit paths)
                # are planned deterministically — the LLM planner costs
                # 40-80 s per turn and is only used when needed.
                plan = self._fast_path_plan(user_text, user_lang)
                if plan is not None:
                    logger.info("[AntiGravity] Fast-path plan matched — LLM planner skipped.")
                else:
                    plan = await self._plan(messages, user_lang)
            else:
                plan = await self._plan(messages, user_lang)
            if not plan or not plan.tasks:
                if cycle == 0:
                    # Parse/plan failure: give the planner ONE corrective retry
                    # (its output was malformed) before giving up.
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous output could not be parsed into the required JSON plan format. "
                            "Respond with ONLY valid JSON matching the multi-task plan format, exactly as specified."
                        ),
                    })
                    cycle += 1
                    continue
                logger.warning("[AntiGravity] Planner returned no plan after retry — asking user to clarify.")
                clarification = _CLARIFY_RESPONSES.get(user_lang, _CLARIFY_RESPONSES["en"])
                return f"__CLARIFY__:{clarification}"

            self._tracker.reset()
            self._tracker.start(plan)

            # Step 1 — If purely conversational, stream LLM response
            if all(t.agent_type == AgentType.CONVERSATION for t in plan.tasks):
                logger.info("[AntiGravity] Conversational request planned — handing back to Baby.")
                return ""

            # Step 2 — If any task is "learn", run the autonomous RAG pipeline
            if any(t.agent_type == AgentType.LEARN for t in plan.tasks):
                logger.info("[AntiGravity] LEARN agent_type — triggering autonomous skill research.")
                workflow = await self._learner.research(
                    user_query=user_text,
                    consent_gate=consent_gate,
                    tts=tts,
                    ui=ui,
                )
                return workflow if workflow else _ERROR_RESPONSES.get(user_lang, _ERROR_RESPONSES["en"])

            # Step 3 — Consent gate (if any task requires it)
            if any(t.requires_consent for t in plan.tasks):
                approved = await self._request_consent(
                    plan=plan,
                    consent_gate=consent_gate,
                    user_lang=user_lang,
                )
                if not approved:
                    return _DENY_RESPONSES.get(user_lang, _DENY_RESPONSES["en"])

            # Step 4 — Multi-Task DAG Execution & State Resolution
            await self._execute_plan(plan, pointer, ui)

            # Step 5 — Verification Check (Observation phase)
            failed_tasks = plan.failed_tasks
            if not failed_tasks:
                logger.success("[AntiGravity] Verification Success: All DAG tasks executed and verified.")
                self._remember_successful_workflow(user_text, plan, live_context=live_context)
                self._store_turn_feedback(user_text, plan, live_context, satisfied=True)
                # Build a specific, task-aware success message instead of the generic one
                return _build_success_message(plan, user_lang)

            logger.warning("[AntiGravity] Verification Failed: Tasks failed: {}", failed_tasks)

            planned_tool_json = {
                "intent": plan.intent,
                "tasks": [
                    {
                        "id": t.id,
                        "description": t.description,
                        "agent_type": t.agent_type.value,
                        "requires_consent": t.requires_consent,
                        "risk_level": t.risk_level,
                        "tools": t.tools
                    }
                    for t in plan.tasks
                ]
            }
            messages.append({"role": "assistant", "content": json.dumps(planned_tool_json)})

            errors_content = [f"Task '{t.description}' ({t.id}) failed with error: {t.error}" for t in failed_tasks]
            observation = (
                f"Observation: {'; '.join(errors_content)}. "
                f"The verification step failed. Do NOT pretend the action succeeded. "
                f"Either output a corrected multi-task JSON plan or an agent_type='conversation' message explaining the failure."
            )
            # Retry intelligence: if a vision task (type_text/key_press/click) was
            # blocked by the screen-share permission, steer the replan toward the
            # browser agent with a direct URL — no screen share needed.
            if any(
                t.agent_type == AgentType.VISION
                and t.error
                and ("screen share" in (t.error or "").lower() or "screen-share" in (t.error or "").lower())
                for t in failed_tasks
            ):
                observation += (
                    " The failures were caused by the screen-share permission being disabled."
                    " The user has NOT shared their screen, so vision type_text/key_press/click will NEVER work."
                    " Replan those steps using ONLY agent_type 'browser' with browser_open_app or browser_navigate"
                    " and a direct URL (e.g. https://www.amazon.com/s?k=QUERY) or browser_search."
                    " Do NOT use agent_type 'vision' again in this plan."
                )
            messages.append({"role": "user", "content": observation})

            self._tracker.increment_cycle()
            if not self._tracker.should_replan():
                break
            cycle += 1
            await asyncio.sleep(0.5)

        logger.error("[AntiGravity] ReAct loop completed with permanent failures after {} cycles.", max_cycles)
        self._store_turn_feedback(user_text, plan=None, live_context=live_context, satisfied=False)
        return _ERROR_RESPONSES.get(user_lang, _ERROR_RESPONSES["en"])

    # ── Planner ───────────────────────────────────────────────────────────────

    async def _plan(self, messages: list[dict], user_lang: str) -> GoalPlan | None:
        """Ask the LLM to produce a structured GoalPlan from the message history."""
        # Plan cache: identical recent user intent (within TTL) reuses the last
        # parsed plan — avoids repeat planner calls for retries / re-runs.
        CACHE_TTL_S = 90.0
        user_text = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_text = msg["content"]
                break
        cache_key = (user_text.strip().lower(), user_lang)
        if cache_key in self._plan_cache:
            ts, cached = self._plan_cache[cache_key]
            if time.time() - ts < CACHE_TTL_S:
                logger.info("[AntiGravity] Plan cache hit for '{}'", user_text[:60])
                return cached
            self._plan_cache.pop(cache_key, None)

        if self._llm._cfg.test_mode:
            plan = self._heuristic_plan(user_text, user_lang)
            self._plan_cache[cache_key] = (time.time(), plan)
            return plan

        # Inject few-shot examples as additional system messages (after system prompt, before user)
        few_shot_msgs = []
        for ex in _FEW_SHOT_EXAMPLES:
            few_shot_msgs.append({"role": "user", "content": ex["user"]})
            few_shot_msgs.append({"role": "assistant", "content": json.dumps(ex["plan"], ensure_ascii=False)})

        # Insert few-shot examples after system prompt (index 1), before the actual user message
        augmented = messages[:1] + few_shot_msgs + messages[1:]

        try:
            # 600 tokens is ample for a multi-task DAG (4-6 tasks + args).
            # Reduced from 800 → 600 and temp 0.1 → 0.05 for faster, stricter JSON.
            raw = await self._llm.chat(
                augmented, json_mode=True, max_tokens=600, temperature=0.05,
            )
            plan = self._parse_plan(raw, user_text, user_lang)
            self._plan_cache[cache_key] = (time.time(), plan)
            return plan
        except Exception as e:
            logger.error("[AntiGravity] Planner LLM call failed: {}", e)
            return None

    @staticmethod
    def _repair_json(raw: str) -> dict | None:
        """Parse planner JSON, repairing the common truncation cases:
        1) unclosed brackets/braces (missing trailing ] / }),
        2) a trailing value cut mid-token (string, number, nested args).
        Returns a dict or None if unrecoverable.
        """
        def _try(s: str) -> dict | None:
            try:
                obj = json.loads(s)
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None

        def _close(s: str) -> str:
            """Append missing closing brackets in correct nesting order."""
            stack: list[str] = []
            pairs = {"{": "}", "[": "]"}
            in_string = False
            escaped = False
            for ch in s:
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch in pairs:
                    stack.append(ch)
                elif ch in pairs.values():
                    if stack and pairs[stack[-1]] == ch:
                        stack.pop()
            if not stack:
                return s
            return s.rstrip() + "".join(pairs[op] for op in reversed(stack))

        obj = _try(raw)
        if obj is not None:
            return obj

        # Breadth-first walk backwards across token boundaries (quote, colon,
        # comma, brace, bracket). Each prefix is tried with brackets closed —
        # this recovers truncations that cut mid-string or mid-argument.
        seen: set[str] = set()
        queue = [raw]
        steps = 0
        while queue and steps < 48:
            steps += 1
            prefix = queue.pop()
            positions = [
                p for p in (
                    prefix.rfind('"'), prefix.rfind(":"),
                    prefix.rfind(","), prefix.rfind("{"), prefix.rfind("["),
                ) if p > 0
            ]
            if not positions:
                continue
            cut = max(positions)
            for candidate in (prefix[:cut], prefix[:cut + 1]):
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                obj = _try(_close(candidate))
                if obj is not None and isinstance(obj, dict) and bool(obj.get("tasks")):
                    logger.info("[AntiGravity] Repaired truncated planner JSON.")
                    return obj
                queue.append(candidate)

        return None

    def _parse_plan(self, raw: str, user_text: str, user_lang: str) -> GoalPlan | None:
        """Parse the LLM's JSON response into a GoalPlan (supporting single or multi-task DAG)."""
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)

        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            logger.warning("[AntiGravity] No JSON found in planner response: {}", raw[:200])
            return self._fallback_plan(user_text, user_lang)

        data = self._repair_json(match.group(0))
        if data is None:
            logger.warning("[AntiGravity] JSON unrepairable: {}", raw[:200])
            return self._fallback_plan(user_text, user_lang)

        tasks: list[Task] = []
        raw_tasks = data.get("tasks", [])

        if raw_tasks and isinstance(raw_tasks, list):
            for idx, t_raw in enumerate(raw_tasks, start=1):
                if not isinstance(t_raw, dict):
                    continue
                agent_type_str = t_raw.get("agent_type", "conversation").lower()
                try:
                    agent_type = AgentType(agent_type_str)
                except ValueError:
                    agent_type = AgentType.CONVERSATION

                risk_level = t_raw.get("risk_level", "low")
                requires_consent = t_raw.get("requires_consent", risk_level in ("medium", "high"))
                tools_raw = t_raw.get("tools", [])

                tools = []
                for tool_item in tools_raw:
                    if isinstance(tool_item, dict):
                        tools.append(tool_item)
                    elif isinstance(tool_item, str) and tool_item:
                        tools.append({"name": tool_item, "args": {}})

                task = Task(
                    id               = str(t_raw.get("id", f"task_{idx}")),
                    description      = str(t_raw.get("description") or t_raw.get("action_description") or user_text),
                    agent_type       = agent_type,
                    tools            = tools,
                    risk_level       = risk_level,
                    requires_consent = requires_consent,
                    depends_on       = [str(d) for d in t_raw.get("depends_on", [])],
                    input_bindings   = t_raw.get("input_bindings", {}),
                    fault_policy     = t_raw.get("fault_policy", "CONTINUE"),
                )
                task.depends_on = _auto_dependencies(task)
                tasks.append(task)

        if not tasks:
            # Fallback to legacy single task format
            agent_type_str = data.get("agent_type", "conversation").lower()
            try:
                agent_type = AgentType(agent_type_str)
            except ValueError:
                agent_type = AgentType.CONVERSATION

            risk_level       = data.get("risk_level", "low")
            requires_consent = data.get("requires_consent", risk_level in ("medium", "high"))
            tools_raw        = data.get("tools", [])

            tools = []
            for tool_item in tools_raw:
                if isinstance(tool_item, dict):
                    tools.append(tool_item)
                elif isinstance(tool_item, str) and tool_item:
                    tools.append({"name": tool_item, "args": {}})

            task = Task(
                id               = "task_1",
                description      = data.get("action_description", user_text),
                agent_type       = agent_type,
                tools            = tools,
                risk_level       = risk_level,
                requires_consent = requires_consent,
            )
            tasks.append(task)

        plan = GoalPlan(
            original_request = user_text,
            intent           = data.get("intent", user_text),
            tasks            = tasks,
            user_lang        = user_lang,
        )

        logger.info(
            "[AntiGravity] Multi-Task Plan parsed: {} tasks across intent='{}'",
            len(plan.tasks), plan.intent
        )

        plan = _force_app_intent(plan, user_text)
        plan = _complete_browser_urls(plan, user_text)
        return plan

    def _fallback_plan(self, user_text: str, user_lang: str) -> GoalPlan:
        """Fallback when the planner LLM output is unusable.

        Runs the deterministic heuristic decomposer instead of giving up with a
        conversational response — so multi-part commands like "create a folder
        and move these files" still get executed even when the LLM JSON fails.
        If nothing matches, returns a safe conversational plan.
        """
        plan = self._heuristic_plan(user_text, user_lang)
        logger.info(
            "[AntiGravity] Fallback heuristic plan: {} task(s), first agent={}",
            len(plan.tasks),
            plan.tasks[0].agent_type.value if plan.tasks else "none",
        )
        return plan

    def _heuristic_single_task_plan(self, part_text: str, original_text: str, user_lang: str, task_id: str = "task_1") -> GoalPlan:
        text = part_text.lower().strip()
        full_context = f"{text} {original_text.lower().strip()}"

        # Check for social messaging commands first (using full query context)
        if any(w in full_context for w in ["whatsapp", "instagram", "insta"]) and any(w in text for w in ["text", "message", "saying", "send", "dm"]):
            if "whatsapp" in full_context:
                recipient = ""
                message = ""
                if " saying " in part_text.lower():
                    recipient, message = part_text.lower().split(" saying ", 1)
                elif " msg " in part_text.lower():
                    recipient, message = part_text.lower().split(" msg ", 1)
                elif ":" in part_text:
                    recipient, message = part_text.split(":", 1)
                else:
                    recipient = part_text

                recipient = re.sub(r"^(?:send\s+)?(?:a\s+)?(?:whatsapp|instagram|insta)?\s*(?:message|dm|text)?\s*(?:to\s+)?", "", recipient, flags=re.IGNORECASE).strip()
                recipient = re.sub(r"\s+(?:on|via)\s+(?:whatsapp|instagram|insta)$", "", recipient, flags=re.IGNORECASE).strip()

                task = Task(
                    id=task_id,
                    description=f"Send WhatsApp message to '{recipient or 'contact'}'",
                    agent_type=AgentType.SYSTEM,
                    tools=[{"name": "send_whatsapp_message", "args": {"recipient": recipient or "contact", "message": message.strip()}}],
                    risk_level="medium",
                    requires_consent=True,
                )
                return GoalPlan(original_request=original_text, intent=part_text, tasks=[task], user_lang=user_lang)

            elif "instagram" in full_context or "insta" in full_context:
                recipient = ""
                message = ""
                if " saying " in part_text.lower():
                    recipient, message = part_text.lower().split(" saying ", 1)
                elif " msg " in part_text.lower():
                    recipient, message = part_text.lower().split(" msg ", 1)
                elif ":" in part_text:
                    recipient, message = part_text.split(":", 1)
                else:
                    recipient = part_text

                recipient = re.sub(r"^(?:send\s+)?(?:a\s+)?(?:whatsapp|instagram|insta)?\s*(?:message|dm|text)?\s*(?:to\s+)?", "", recipient, flags=re.IGNORECASE).strip()
                recipient = re.sub(r"\s+(?:on|via)\s+(?:whatsapp|instagram|insta)$", "", recipient, flags=re.IGNORECASE).strip()

                task = Task(
                    id=task_id,
                    description=f"Send Instagram message to '{recipient or 'contact'}'",
                    agent_type=AgentType.SYSTEM,
                    tools=[{"name": "send_instagram_message", "args": {"recipient": recipient or "contact", "message": message.strip()}}],
                    risk_level="medium",
                    requires_consent=True,
                )
                return GoalPlan(original_request=original_text, intent=part_text, tasks=[task], user_lang=user_lang)

        # ── "Where is X?" / "Show me where X is" → locate & point ──────────
        # Compulsory screen share is enforced by the uia_locate_element tool
        # itself; the assistant can only point after the user shares a screen.
        _where_match = None
        for prefix in ("show me where is", "show me where's", "show me where",
                       "where is", "where's", "where are", "where do i find",
                       "point out", "point to", "highlight the", "highlight where"):
            if prefix in part_text.lower():
                _where_match = prefix
                break
        if _where_match and not _FAST_PATH_SEARCH_VERBS.search(text) \
                and not re.search(r"\b(?:file|files|folder|folders|document|documents)\b", text):
            target = part_text.lower().split(_where_match, 1)[-1].strip()
            target = re.sub(r"^(?:the|my|me|on|screen|is|are|it)\s+", "", target)
            target = re.sub(r"\s+(?:is|are|located|situated)\??\s*$", "", target).strip()
            target = target.strip(" .?")
            if target and not _FAST_PATH_PATH_HINT.search(target):
                task = Task(
                    id=task_id,
                    description=f"Locate '{target}' on screen and point at it",
                    agent_type=AgentType.VISION,
                    tools=[{"name": "uia_locate_element",
                            "args": {"name": target, "highlight": True}}],
                    risk_level="low",
                    requires_consent=False,
                )
                return GoalPlan(original_request=original_text, intent=part_text,
                                tasks=[task], user_lang=user_lang)

        canonical_app = _detect_desktop_app(part_text)
        if canonical_app:
            display_name = canonical_app.title() if canonical_app != "file explorer" else "File Explorer"
            task = Task(
                id=task_id,
                description=f"Open {display_name}",
                agent_type=AgentType.SYSTEM,
                tools=[{"name": "open_application", "args": {"app_name": canonical_app}}],
                risk_level="low",
                requires_consent=False,
            )
            return GoalPlan(original_request=original_text, intent=part_text, tasks=[task], user_lang=user_lang)

        if any(w in text for w in ["volume up", "louder", "increase volume"]):
            task = Task(id=task_id, description="Increase volume", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "adjust_volume", "args": {"action": "up"}}], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["volume down", "quieter", "decrease volume"]):
            task = Task(id=task_id, description="Decrease volume", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "adjust_volume", "args": {"action": "down"}}], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["screenshot", "screen shot", "snap"]):
            task = Task(id=task_id, description="Take screenshot", agent_type=AgentType.VISION,
                        tools=[{"name": "take_screenshot", "args": {}}], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["system status", "cpu", "memory usage"]):
            task = Task(id=task_id, description="Get system status", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "get_system_status", "args": {}}], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["search for file", "find file", "locate file", "where is the file", "search my files"]):
            query = part_text
            for prefix in ["search for file", "find file", "locate file", "where is the file", "search my files"]:
                if prefix in query.lower():
                    query = query.split(prefix, 1)[-1].strip()
                    break
            if not query:
                query = part_text.strip().strip(".")
            task = Task(id=task_id, description=f"Search file '{query}'", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "search_files", "args": {"query": query}}], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["create a folder", "create folder", "create a directory", "create directory", "make a folder", "make folder", "make a directory", "make directory", "new folder", "new directory"]):
            folder = ""
            for prefix in ["create a folder", "create folder", "create a directory", "create directory", "make a folder", "make folder", "make a directory", "make directory", "new folder", "new directory"]:
                if prefix in text:
                    folder = part_text.split(prefix, 1)[-1].strip()
                    break
            folder = re.sub(r"^(?:named|called|with the name|by the name)\s+", "", folder.strip())
            if not folder:
                folder = "new folder"
            task = Task(id=task_id, description=f"Create folder '{folder}'", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "create_directory", "args": {"path": folder}}], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["create file", "make a file", "make file", "new file"]):
            filepath = ""
            for prefix in ["create file", "make a file", "make file", "new file"]:
                if prefix in text:
                    filepath = part_text.split(prefix, 1)[-1].strip()
                    break
            filepath = re.sub(r"^(?:named|called|with the name|by the name)\s+", "", filepath.strip())
            if not filepath:
                filepath = "new_file.txt"
            task = Task(id=task_id, description=f"Create file '{filepath}'", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "write_file", "args": {"path": filepath, "content": ""}}], risk_level="medium", requires_consent=True)
        elif (any(w in text for w in ["move ", "move the", "moves", "shift ", "rename "]) or re.search(r"\brename\b", text)) and (_FAST_PATH_PATH_HINT.search(text) or any(k in text for k in ["file", "folder", "directory", "path", "."])):
            match = re.search(r"(?:move|shift|rename)\s+(.+?)\s+(?:to|into)\s+(.+)", text)
            if match:
                source = match.group(1).strip().strip('"')
                destination = match.group(2).strip().strip('"')
                task = Task(id=task_id, description=f"Move '{source}' to '{destination}'", agent_type=AgentType.SYSTEM,
                            tools=[{"name": "move_file", "args": {"source": source, "destination": destination}}],
                            risk_level="medium", requires_consent=True)
            else:
                task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["copy "]) or re.search(r"\bcopy\b.*\bto\b", text):
            match = re.search(r"copy\s+(.+?)\s+to\s+(.+)", text)
            if match:
                source = match.group(1).strip().strip('"')
                destination = match.group(2).strip().strip('"')
                task = Task(id=task_id, description=f"Copy '{source}' to '{destination}'", agent_type=AgentType.SYSTEM,
                            tools=[{"name": "copy_file", "args": {"source": source, "destination": destination}}],
                            risk_level="medium", requires_consent=True)
            else:
                task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["delete ", "delete the", "remove ", "remove the", "delete this", "get rid of"]):
            target = ""
            for prefix in ["delete", "remove", "get rid of"]:
                if prefix in text:
                    target = part_text.split(prefix, 1)[-1].strip()
                    if prefix == "get rid of":
                        target = target.lstrip(" of ").strip()
                    break
            if target and target not in ("the", "this", "it"):
                task = Task(id=task_id, description=f"Delete '{target}'", agent_type=AgentType.SYSTEM,
                            tools=[{"name": "delete_file", "args": {"path": target}}], risk_level="high", requires_consent=True)
            else:
                task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)
        elif any(w in text for w in ["pdf", "summarize pdf", "scan pdf", "read pdf"]):
            if any(w in text for w in ["on screen", "opened", "this pdf", "open pdf", "visible pdf", "currently open"]):
                task = Task(id=task_id, description="Scan and read opened PDF on screen", agent_type=AgentType.VISION,
                            tools=[{"name": "vision_read_screen", "args": {}}], risk_level="low", requires_consent=False)
            else:
                m = re.search(r"([a-zA-Z0-9_\:\\\/\-]+\.pdf)", part_text, re.IGNORECASE)
                pdf_path = m.group(1).strip() if m else ""
                if pdf_path:
                    task = Task(id=task_id, description=f"Read PDF file '{pdf_path}'", agent_type=AgentType.SYSTEM,
                                tools=[{"name": "read_pdf", "args": {"path": pdf_path}}], risk_level="low", requires_consent=False)
                else:
                    task = Task(id=task_id, description="Scan text on screen for PDF contents", agent_type=AgentType.VISION,
                                tools=[{"name": "vision_read_screen", "args": {}}], risk_level="low", requires_consent=False)
        elif re.search(r"\b(?:append|add to)\b", text) and _FAST_PATH_PATH_HINT.search(text):
            m = re.search(r"\b(?:append|add)\s+(.+?)\s+(?:to|into|in)\s+(.+)$", part_text, re.IGNORECASE)
            if m:
                content = m.group(1).strip()
                path = m.group(2).strip().strip('"').strip("'")
                task = Task(id=task_id, description=f"Append to file '{path}'", agent_type=AgentType.SYSTEM,
                            tools=[{"name": "append_file", "args": {"path": path, "content": content}}],
                            risk_level="medium", requires_consent=True)
            else:
                task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)
        elif re.search(r"\b(?:replace|change|swap)\b", text) and " in " in text and _FAST_PATH_PATH_HINT.search(text):
            m = re.search(r"\b(?:replace|change|swap)\s+(.+?)\s+with\s+(.+?)\s+in\s+(.+)$", part_text, re.IGNORECASE)
            if m:
                old_txt = m.group(1).strip().strip('"').strip("'")
                new_txt = m.group(2).strip().strip('"').strip("'")
                path = m.group(3).strip().strip('"').strip("'")
                task = Task(id=task_id, description=f"Replace '{old_txt}' with '{new_txt}' in '{path}'", agent_type=AgentType.SYSTEM,
                            tools=[{"name": "edit_file", "args": {"path": path, "operation": "find_replace", "old_text": old_txt, "new_text": new_txt}}],
                            risk_level="medium", requires_consent=True)
            else:
                task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)
        elif re.search(r"\b(?:write|save|put)\b", text) and _FAST_PATH_PATH_HINT.search(text):
            m = re.search(r"\b(?:write|save|put)\s+(.+?)\s+(?:to|into|in)\s+(.+)$", part_text, re.IGNORECASE)
            if m:
                content = m.group(1).strip()
                path = m.group(2).strip().strip('"').strip("'")
                task = Task(id=task_id, description=f"Write to file '{path}'", agent_type=AgentType.SYSTEM,
                            tools=[{"name": "write_file", "args": {"path": path, "content": content}}],
                            risk_level="medium", requires_consent=True)
            else:
                task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)
        elif re.match(r"^type\s+", text) or any(w in text for w in ["type out", "write down", "enter text"]):
            typed = ""
            for prefix in ["type out", "write down", "enter text"]:
                if prefix in text:
                    typed = part_text.split(prefix, 1)[-1].strip()
                    break
            if not typed:
                typed = re.sub(r"^type\s+", "", text).strip()
            task = Task(id=task_id, description=f"Type text", agent_type=AgentType.SYSTEM,
                        tools=[{"name": "type_text", "args": {"text": typed}}], risk_level="medium", requires_consent=True)
        elif "whatsapp" in text and any(w in text for w in ["text", "message", "saying", "send"]):
            recipient = ""
            message = ""
            if any(w in text for w in ["text ", "message ", "to ", "send"]):
                match = re.search(r"(?:text|message|to|send)\s+([a-zA-Z0-9_\+\s]+?)(?:\s+(?:saying|with|that|msg)|$)", text, re.IGNORECASE)
                if match:
                    recipient = match.group(1).strip()
            if "saying " in text:
                message = part_text.split("saying ", 1)[-1].strip()
            elif "msg " in text:
                message = part_text.split("msg ", 1)[-1].strip()

            task = Task(
                id=task_id,
                description=f"Send WhatsApp message to '{recipient or 'contact'}'",
                agent_type=AgentType.SYSTEM,
                tools=[{"name": "send_whatsapp_message", "args": {"recipient": recipient or "contact", "message": message}}],
                risk_level="medium",
                requires_consent=True,
            )
        elif "telegram" in text or "tg " in text:
            recipient = ""
            message = ""
            match = re.search(r"(?:telegram|tg|to|message)\s+([a-zA-Z0-9_\+\@\s]+?)(?:\s+(?:saying|with|that|msg)|$)", text, re.IGNORECASE)
            if match:
                recipient = match.group(1).strip()
            if "saying " in text:
                message = part_text.split("saying ", 1)[-1].strip()
            elif "msg " in text:
                message = part_text.split("msg ", 1)[-1].strip()

            task = Task(
                id=task_id,
                description=f"Send Telegram message to '{recipient or 'contact'}'",
                agent_type=AgentType.SYSTEM,
                tools=[{"name": "send_telegram_message", "args": {"recipient": recipient or "contact", "message": message}}],
                risk_level="medium",
                requires_consent=True,
            )
        elif "email" in text or "mail " in text:
            to = ""
            subject = ""
            body = ""
            to_match = re.search(r"(?:email|mail|to)\s+([a-zA-Z0-9_\.\+\-]+@[a-zA-Z0-9_\.\-]+\.[a-zA-Z]{2,})", text, re.IGNORECASE)
            if to_match:
                to = to_match.group(1).strip()
            subj_match = re.search(r"(?:subject|about)\s+['\"]?([^'\"]+?)['\"]?(?:\s+(?:body|saying|message)|$)", text, re.IGNORECASE)
            if subj_match:
                subject = subj_match.group(1).strip()
            if "body " in text:
                body = part_text.split("body ", 1)[-1].strip()
            elif "saying " in text:
                body = part_text.split("saying ", 1)[-1].strip()

            task = Task(
                id=task_id,
                description=f"Send email to '{to or 'recipient'}'",
                agent_type=AgentType.SYSTEM,
                tools=[{"name": "send_email", "args": {"to": to or "recipient", "subject": subject, "body": body}}],
                risk_level="medium",
                requires_consent=True,
            )
        elif "instagram" in text or "insta" in text or "dm " in text:
            recipient = ""
            message = ""
            if any(w in text for w in ["text ", "message ", "to ", "dm "]):
                match = re.search(r"(?:text|message|to|dm)\s+([a-zA-Z0-9_\+\@\s]+?)(?:\s+(?:saying|with|that|msg)|$)", text, re.IGNORECASE)
                if match:
                    recipient = match.group(1).strip()
            if "saying " in text:
                message = part_text.split("saying ", 1)[-1].strip()
            elif "msg " in text:
                message = part_text.split("msg ", 1)[-1].strip()

            task = Task(
                id=task_id,
                description=f"Send Instagram message to '{recipient or 'contact'}'",
                agent_type=AgentType.SYSTEM,
                tools=[{"name": "send_instagram_message", "args": {"recipient": recipient or "contact", "message": message}}],
                risk_level="medium",
                requires_consent=True,
            )
        else:
            task = Task(id=task_id, description=part_text, agent_type=AgentType.CONVERSATION, tools=[], risk_level="low", requires_consent=False)

        return GoalPlan(original_request=original_text, intent=part_text, tasks=[task], user_lang=user_lang)

    def _fast_path_plan(self, user_text: str, user_lang: str) -> GoalPlan | None:
            """Deterministic zero-LLM plan for high-confidence intents.

            The planner LLM costs 40-80 s per turn on this machine (5.8 tok/s
            generation), so the most common commands are planned here instantly:
            open a website/browser, web search, desktop app launch, volume,
            screenshot, system status, and file operations that name a real path.
            Returns None for anything ambiguous or conversational so the LLM
            planner still handles it.
            """
            text = user_text.lower().strip()
            if not text:
                return None

            # Check fast-path cache
            cache_key = f"{text}:{user_lang}"
            cached = self._get_cached_fast_path(cache_key)
            if cached:
                return cached

            # Multi-command check: if user_text has conjunctions joining multiple action verbs, let _heuristic_plan handle it
            if re.search(r"\b(?:and|then|also)\b|[;,]", text):
                verbs = ["open", "search", "google", "find", "create", "make", "move", "copy", "delete", "take", "set", "adjust", "close"]
                verb_count = sum(1 for v in verbs if re.search(rf"\b{v}\b", text))
                if verb_count >= 2:
                    return None

            # 0. Screen-share / screen-visibility status question — ALWAYS conversational.
            #    The user is asking whether you can see their screen, not requesting an action.
            _SCREEN_VISIBILITY_PATTERNS = (
                "is my screen visible", "can you see my screen", "are you watching my screen",
                "do you have screen access", "is screen share", "is screen sharing",
                "screen share on", "screen share off", "screen sharing on", "screen sharing off",
                "can you see what i", "can you see what's on", "can you see the screen",
                "are you seeing my screen", "do you see my screen", "you can see my screen",
                "screen visible to you", "screen access enabled", "screen share enabled",
            )
            if any(pat in text for pat in _SCREEN_VISIBILITY_PATTERNS):
                logger.info("[AntiGravity] Fast-path: screen-visibility question → conversation")
                return GoalPlan(
                    original_request=user_text,
                    intent="screen share status question",
                    tasks=[Task(
                        id="task_1",
                        description="Answer whether screen sharing is active",
                        agent_type=AgentType.CONVERSATION,
                        tools=[],
                        risk_level="low",
                        requires_consent=False,
                    )],
                    user_lang=user_lang,
                )

            # Internal commands — answer conversationally instead of launching apps
            _INTERNAL_KEYWORDS = ("anti gravity", "antigravity", "anti-gravity")
            if any(cmd in text for cmd in _INTERNAL_KEYWORDS):
                return GoalPlan(
                    original_request=user_text,
                    intent="internal command explanation",
                    tasks=[Task(
                        id="task_1",
                        description="Explain what AntiGravity is",
                        agent_type=AgentType.CONVERSATION,
                        tools=[],
                        risk_level="low",
                        requires_consent=False,
                    )],
                    user_lang=user_lang,
                )
            # 1. Desktop app launch (curated aliases) — safe even without a path.
            #    Check FIRST before browser routing so "open calculator" never opens Chrome.
            if _detect_desktop_app(user_text):
                plan = self._heuristic_single_task_plan(user_text, user_text, user_lang)
                if plan.tasks and plan.tasks[0].agent_type != AgentType.CONVERSATION:
                    return plan

            # 2. Browser: "open <site> [in <browser>]" / "go to <url>" / "open <browser>"
            #    Only reach here if no known desktop app was detected.
            if _FAST_PATH_OPEN_VERBS.search(text):
                browser = _extract_browser_name(user_text)
                words = [w for w in re.sub(r"[^a-z0-9.\s]", " ", text).split()
                         if w not in _SITE_EXTRACTION_FILLER]
                from antigravity.agents.browser_agent import _KNOWN_SITES
                strong_site = (any("." in w and w not in _BROWSER_NAME_WORDS for w in words)
                               or any(k in words for k in _KNOWN_SITES))
                site = _extract_site_from_text(user_text)

                if browser:
                    args = {"browser": browser, "url": site} if site else {"browser": browser}
                    tool = {"name": "browser_open_app", "args": args}
                elif strong_site and site:
                    tool = {"name": "browser_navigate", "args": {"url": site}}
                else:
                    tool = None  # ambiguous single word (e.g. "open word") -> fall through

                if tool is not None:
                    plan = GoalPlan(
                        original_request=user_text,
                        intent="open website",
                        tasks=[Task(
                            id="task_1",
                            description=f"Open website in browser",
                            agent_type=AgentType.BROWSER,
                            tools=[tool],
                            risk_level="low",
                            requires_consent=False,
                        )],
                        user_lang=user_lang,
                    )
                    plan = _force_app_intent(plan, user_text)
                    result = _complete_browser_urls(plan, user_text)
                    self._cache_fast_path(cache_key, result)
                    return result

            # 3. Web search: "search for <query>" / "google <query>"
            if _FAST_PATH_SEARCH_VERBS.search(text) and not re.search(r"\b(?:file|folder|document)\b", text):
                m = _FAST_PATH_SEARCH_VERBS.search(text)
                query = text[m.end():].strip().strip("?.!, ") if m else ""
                if not query:
                    return None
                plan = GoalPlan(
                    original_request=user_text,
                    intent="web search",
                    tasks=[Task(
                        id="task_1",
                        description=f"Search the web for '{query}'",
                        agent_type=AgentType.BROWSER,
                        tools=[{"name": "browser_search_text", "args": {"query": query}}],
                        risk_level="low",
                        requires_consent=False,
                    )],
                    user_lang=user_lang,
                )
                result = _complete_browser_urls(plan, user_text)
                self._cache_fast_path(cache_key, result)
                return result

            # 4. "Where is X?" / "show me where X is" -> locate & point.
            #    File-related where-phrases fall through to the file branch
            #    below (search_files). Compulsory screen share is enforced
            #    inside uia_locate_element itself.
            if _WHERE_PREFIX.search(text):
                plan = self._heuristic_single_task_plan(user_text, user_text, user_lang)
                if plan.tasks and plan.tasks[0].agent_type != AgentType.CONVERSATION:
                    self._cache_fast_path(cache_key, plan)
                    return plan

            # 5. Safe device/system commands (volume, screenshot, status).
            if any(w in text for w in ["volume up", "louder", "increase volume",
                                       "volume down", "quieter", "decrease volume",
                                       "screenshot", "screen shot", "snap",
                                       "system status", "cpu", "memory usage"]):
                plan = self._heuristic_single_task_plan(user_text, user_text, user_lang)
                if plan.tasks and plan.tasks[0].agent_type != AgentType.CONVERSATION:
                    self._cache_fast_path(cache_key, plan)
                    return plan

            # 6. Messaging (platform word + message verb is unambiguous).
            if any(w in text for w in ["whatsapp", "instagram", "insta"]) and \
               any(w in text for w in ["text", "message", "saying", "send", "dm"]):
                plan = self._heuristic_single_task_plan(user_text, user_text, user_lang)
                if plan.tasks and plan.tasks[0].agent_type != AgentType.CONVERSATION:
                    self._cache_fast_path(cache_key, plan)
                    return plan

            # 7. File operations — ONLY when the text names a real path/folder,
            #    so conversational phrasing ("move the discussion to another
            #    topic", "delete that thought") never touches the filesystem.
            if _FAST_PATH_PATH_HINT.search(text) and re.search(
                    r"\b(?:write|save|append|put|add|move|rename|shift|copy|delete|remove|create|make|new|find|search|locate)\b", text):
                plan = self._heuristic_single_task_plan(user_text, user_text, user_lang)
                if plan.tasks and plan.tasks[0].agent_type != AgentType.CONVERSATION:
                    self._cache_fast_path(cache_key, plan)
                    return plan

            return None

    def _heuristic_plan(self, user_text: str, user_lang: str) -> GoalPlan:
        """Deterministic plan builder supporting multi-command decomposition.

        Used when the planner LLM is in test mode AND as the safety-net fallback
        when its JSON output cannot be parsed.
        """
        delimiters = [" and ", " then ", " & ", ", "]
        parts = [user_text]
        for delim in delimiters:
            new_parts = []
            for p in parts:
                new_parts.extend(p.split(delim))
            parts = [p.strip() for p in new_parts if p.strip()]

        if len(parts) > 1 and not any(kw in user_text.lower() for kw in ["google", "web search"]):
            tasks = []
            for idx, part in enumerate(parts, start=1):
                sub_plan = self._heuristic_single_task_plan(part, user_text, user_lang, task_id=f"task_{idx}")
                tasks.extend(sub_plan.tasks)
            if tasks:
                return GoalPlan(original_request=user_text, intent=f"Multi-task execution: {user_text}", tasks=tasks, user_lang=user_lang)

        return self._heuristic_single_task_plan(user_text, user_text, user_lang, task_id="task_1")

    def _mock_plan(self, user_text: str, user_lang: str) -> GoalPlan:
        """Backwards-compatible alias (scratch tests) for _heuristic_plan."""
        return self._heuristic_plan(user_text, user_lang)

    # ── Feedback & Context ────────────────────────────────────────────────────

    def _remember_successful_workflow(self, user_text: str, plan: GoalPlan, live_context: str = ""):
        """Store a compact success trace so the assistant can reuse it later."""
        if not plan or not plan.tasks:
            return

        primary = plan.tasks[0].agent_type
        if primary in (AgentType.CONVERSATION, AgentType.LEARN):
            return

        try:
            skill_label = f"Workflow: {plan.intent or user_text[:80]}"
            workflow_data = {
                "intent": plan.intent or user_text,
                "agent_type": primary.value,
                "tasks": [
                    {
                        "id": t.id,
                        "description": t.description,
                        "agent_type": t.agent_type.value,
                        "depends_on": t.depends_on,
                        "tools": t.tools,
                    }
                    for t in plan.tasks
                ],
                "result": "success",
            }
            workflow_json = json.dumps(workflow_data, ensure_ascii=False, indent=2)
            self._learner._store.save(skill_label, workflow_json, search_text=f"{user_text}\n{plan.intent}")
            logger.success("[AntiGravity] Stored successful multi-task workflow: '{}'", skill_label)
        except Exception as e:
            logger.warning("[AntiGravity] Failed to store workflow: {}", e)

    def _should_capture_live_context(self, user_text: str) -> bool:
        text = user_text.lower()
        return any(
            phrase in text
            for phrase in (
                "screen", "page", "window", "current app", "current screen",
                "live", "locate", "find", "point", "click", "open settings",
                "open camera", "settings", "camera", "wifi", "bluetooth",
                "message", "send message", "what is on", "what's on", "visible",
            )
        )

    def _capture_live_screen_context_sync(self, user_text: str) -> str:
        if not self._should_capture_live_context(user_text):
            return ""

        try:
            from tools.screen_tools import is_screen_share_enabled
            if not is_screen_share_enabled():
                return ""
        except Exception:
            return ""

        try:
            result = execute_vision_tool("vision_read_screen", {})
            if not result.get("success"):
                return ""

            text = str(result.get("text", "")).strip()
            if not text or text.startswith("(OCR not available"):
                return ""

            if self._guard:
                text, _ = self._guard.scrub(text)

            text = re.sub(r"\s+", " ", text).strip()
            return text[:1200]
        except Exception as e:
            logger.debug("[AntiGravity] Live screen capture failed: {}", e)
            return ""

    def _recall_recent_feedback(self) -> str:
        try:
            result = execute_context_tool("memory_list", {"category": "feedback", "limit": 3})
            memories = result.get("memories", []) if result.get("success") else []
            if not memories:
                return ""

            lines = []
            for memory in memories[-3:]:
                key = memory.get("key", "")
                value = str(memory.get("value", "")).strip()
                if value:
                    lines.append(f"- {key}: {value[:240]}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("[AntiGravity] Feedback recall failed: {}", e)
            return ""

    def _maybe_store_feedback(self, user_text: str):
        text = user_text.lower().strip()
        positive_markers = (
            "thanks", "thank you", "perfect", "great", "nice", "good job",
            "works", "that works", "correct", "exactly", "awesome",
        )
        negative_markers = (
            "not that", "wrong", "instead", "actually", "fix it", "change it",
            "that's not", "that is not", "not right", "correction", "redo",
        )

        category = ""
        key = ""
        if any(marker in text for marker in positive_markers):
            category = "feedback"
            key = "positive_feedback"
        elif any(marker in text for marker in negative_markers):
            category = "feedback"
            key = "correction_feedback"

        if not category:
            return

        try:
            execute_context_tool(
                "memory_store",
                {
                    "key": key,
                    "value": user_text,
                    "category": category,
                },
            )
        except Exception as e:
            logger.debug("[AntiGravity] Feedback store failed: {}", e)

    def _store_turn_feedback(self, user_text: str, plan: GoalPlan | None, live_context: str, satisfied: bool):
        try:
            payload: dict[str, Any] = {
                "user_text": user_text,
                "live_context": live_context,
                "satisfied": satisfied,
            }
            if plan is not None and plan.tasks:
                payload["intent"] = plan.intent
                payload["task_count"] = len(plan.tasks)

            execute_context_tool(
                "memory_store",
                {
                    "key": "turn_feedback",
                    "value": json.dumps(payload, ensure_ascii=False),
                    "category": "feedback",
                },
            )
        except Exception as e:
            logger.debug("[AntiGravity] Turn feedback store failed: {}", e)

    # ── Consent ───────────────────────────────────────────────────────────────

    async def _request_consent(
        self,
        plan:         GoalPlan,
        consent_gate: ConsentGate,
        user_lang:    str,
    ) -> bool:
        from core.consent_gate import ActionPlan

        risky_tasks = [t for t in plan.tasks if t.requires_consent]
        if not risky_tasks:
            return True

        descriptions = [t.description for t in risky_tasks]
        combined_tools = []
        for t in risky_tasks:
            combined_tools.extend(t.tools)

        highest_risk = "high" if any(t.risk_level == "high" for t in risky_tasks) else "medium"

        action_plan = ActionPlan(
            description = " & ".join(descriptions),
            risk_level  = highest_risk,
            tools       = combined_tools,
        )

        approved = await consent_gate.request_consent(action_plan)
        logger.info("[AntiGravity] Consent result for multi-task plan: {}", approved)
        return approved

    # ── Multi-Task DAG Execution Engine ───────────────────────────────────────

    @staticmethod
    def _is_permanent_failure(error: str | None) -> bool:
        """Return True for errors that retrying will not fix."""
        if not error:
            return False
        lowered = error.lower()
        markers = (
            "permission", "not enabled", "not installed", "no module",
            "unknown tool", "unknown", "not found", "could not find",
            "unavailable", "denied", "cannot", "invalid",
        )
        return any(m in lowered for m in markers)

    async def _execute_plan(self, plan: GoalPlan, pointer=None, ui=None):
        """Run tasks level-by-level using Topological Stage Scheduling. Execute independent tasks concurrently."""
        ctx = TaskExecutionContext()
        stages = plan.get_execution_stages()

        for stage_idx, stage in enumerate(stages):
            logger.info("[AntiGravity] Executing Stage {}/{} with {} task(s)", stage_idx + 1, len(stages), len(stage))

            async def run_single_task(task: Task) -> Task:
                if task.status in (TaskStatus.DONE, TaskStatus.SKIPPED):
                    return task

                if plan.should_skip_due_to_dependency_failure(task):
                    logger.warning("[AntiGravity] Skipping task '{}' ({}) due to upstream dependency failure.", task.description, task.id)
                    task.status = TaskStatus.SKIPPED
                    task.error = "Upstream dependency failed"
                    return task

                agent = self._agents.get(task.agent_type)
                if agent is None:
                    logger.warning("[AntiGravity] No agent for type={}", task.agent_type)
                    task.status = TaskStatus.SKIPPED
                    return task

                resolved_tools = []
                for tool in task.tools:
                    resolved_tool = {
                        "name": tool.get("name"),
                        "args": ctx.resolve_value(tool.get("args", {}))
                    }
                    resolved_tools.append(resolved_tool)
                task.tools = resolved_tools

                await self._maybe_move_pointer(task, pointer)

                is_vision = task.agent_type == AgentType.VISION
                if is_vision and ui:
                    try:
                        ui.set_cam_active(True)
                        logger.info("[AntiGravity] Camera/Screen sensor activated — UI indicator ON")
                    except Exception:
                        pass

                while task.retries <= task.max_retries:
                    logger.info(
                        "[AntiGravity] Executing task '{}' ({}) via {} (attempt {})",
                        task.description, task.id, agent.name, task.retries + 1
                    )
                    task = await agent.run(task)

                    if task.status == TaskStatus.DONE:
                        logger.success("[AntiGravity] Task done: {}", task.result)
                        ctx.store_result(task.id, task.result, getattr(task, "raw_results", None))
                        break

                    if self._is_permanent_failure(task.error):
                        logger.error("[AntiGravity] Task permanently failed (non-retryable): {}", task.error)
                        task.status = TaskStatus.FAILED
                        break

                    task.retries += 1
                    if task.retries <= task.max_retries:
                        logger.warning("[AntiGravity] Task failed ({}), retrying...", task.error)
                        await asyncio.sleep(0.3)
                    else:
                        logger.error("[AntiGravity] Task permanently failed: {}", task.error)
                        task.status = TaskStatus.FAILED

                if is_vision and ui:
                    try:
                        ui.set_cam_active(False)
                        logger.info("[AntiGravity] Camera/Screen sensor deactivated — UI indicator OFF")
                    except Exception:
                        pass

                if pointer:
                    try:
                        pointer.hide_pointer()
                    except Exception:
                        pass

                return task

            await asyncio.gather(*(run_single_task(t) for t in stage))

            if any(t.status == TaskStatus.FAILED and t.fault_policy == "ABORT_ALL" for t in stage):
                logger.error("[AntiGravity] Stage task failed under ABORT_ALL fault policy. Aborting remaining stages.")
                break

    async def _maybe_move_pointer(self, task: Task, pointer):
        """If the task includes screen coordinates, move the AI pointer there first."""
        if pointer is None:
            return
        for tool_call in task.tools:
            args = tool_call.get("args", {})
            if "x" in args and "y" in args:
                try:
                    label = "Click" if "click" in tool_call.get("name", "") else "Point"
                    await pointer.async_move_to(args["x"], args["y"], label)
                    await asyncio.sleep(0.6)
                except Exception as e:
                    logger.warning("[AntiGravity] Pointer move failed: {}", e)
                break




















