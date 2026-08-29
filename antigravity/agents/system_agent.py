"""
antigravity/agents/system_agent.py — System & File Sub-Agent.

Handles: file listing/copy/move/delete, opening applications,
         minimizing/closing windows, running system commands.

Wraps the existing tools/file_tools.py and tools/screen_tools.py executors
so no duplicate code is needed.
"""

from __future__ import annotations
from loguru import logger

from antigravity.base_agent import BaseAgent
from antigravity.goal_tracker import Task, TaskStatus
from tools.file_tools  import execute_tool,        TOOL_RISK
from tools.screen_tools import execute_screen_tool, SCREEN_TOOL_RISK
from tools.system_tools import execute_system_tool, SYSTEM_TOOL_RISK
from tools.math_tools   import execute_math_tool,   MATH_TOOL_RISK
from tools.code_sandbox import execute_python_code, CODE_EXECUTION_RISK
from tools.home_assistant_tools import execute_ha_tool, HOME_ASSISTANT_TOOL_RISK


class SystemAgent(BaseAgent):
    name        = "system"
    description = "Handles file operations, application control, and OS interactions."

    async def run(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        results = []

        try:
            for tool_call in task.tools:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})

                logger.info("[SystemAgent] Executing tool='{}' args={}", tool_name, tool_args)

                if tool_name in TOOL_RISK:
                    result = execute_tool(tool_name, tool_args)
                elif tool_name in SCREEN_TOOL_RISK:
                    result = execute_screen_tool(tool_name, tool_args)
                elif tool_name in SYSTEM_TOOL_RISK:
                    result = execute_system_tool(tool_name, tool_args)
                elif tool_name in MATH_TOOL_RISK:
                    result = execute_math_tool(tool_name, tool_args)
                elif tool_name in CODE_EXECUTION_RISK:
                    result = execute_python_code(tool_args.get("code", ""))
                elif tool_name in HOME_ASSISTANT_TOOL_RISK:
                    result = execute_ha_tool(tool_name, tool_args)
                else:
                    # Fuzzy fallback: the LLM sometimes names the *app* instead of the tool
                    # e.g. "file explorer", "calculator", "notepad" → open_application
                    _APP_ALIASES = {
                        "file explorer", "explorer", "calculator", "calc", "notepad",
                        "paint", "mspaint", "cmd", "command prompt", "powershell",
                        "camera", "settings", "photos", "store", "weather", "maps",
                        "clock", "calendar", "mail", "chrome", "firefox", "edge",
                        "spotify", "vlc", "word", "excel", "powerpoint", "vscode",
                        "task manager", "terminal",
                        # newly supported apps
                        "telegram", "discord", "slack", "zoom", "skype", "signal",
                        "whatsapp", "brave", "opera", "vivaldi", "obs", "obs studio",
                        "steam", "epic", "epic games", "gimp", "audacity", "vlc media player",
                        "notepad++", "notepad plus plus", "sublime text", "android studio",
                        "pycharm", "intellij", "vs code", "visual studio code", "visual studio",
                        "7zip", "7-zip", "winrar", "filezilla", "putty", "postman",
                        "docker", "docker desktop", "virtualbox", "vmware",
                        "itunes", "windows media player", "media player", "snipping tool",
                        "snip", "regedit", "registry editor", "wordpad", "pwsh",
                        "taskmgr", "task manager", "ubisoft connect", "uplay",
                        "battle.net", "battlenet", "gog galaxy",
                    }
                    if tool_name.lower() in _APP_ALIASES:
                        resolved_args = dict(tool_args) if tool_args else {"app_name": tool_name}
                        if "app_name" not in resolved_args:
                            resolved_args["app_name"] = tool_name
                        logger.info("[SystemAgent] Fuzzy-resolved '{}' → open_application({})", tool_name, resolved_args)
                        result = execute_tool("open_application", resolved_args)
                    else:
                        result = {"success": False, "error": f"Unknown tool: {tool_name}"}


                logger.info("[SystemAgent] Result: {}", result)
                results.append(result)

            # Check if any tool returned an error
            has_error = any(
                (isinstance(r, dict) and r.get("error")) or
                ("error" in str(r).lower())
                for r in results
            )

            if has_error:
                task.status = TaskStatus.FAILED
                task.error  = self._format_result(results)
            else:
                task.status = TaskStatus.DONE
                task.raw_results = results
                task.result = self._format_result(results)

        except Exception as e:
            logger.error("[SystemAgent] Unexpected error: {}", e)
            task.status = TaskStatus.FAILED
            task.error  = str(e)

        return task



















