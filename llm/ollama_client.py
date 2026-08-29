"""
llm/ollama_client.py — Streaming Ollama LLM wrapper.
Streams tokens → sentences → TTS with barge-in cancellation.
"""

from __future__ import annotations
import asyncio
import json
import re
from typing import Any, AsyncGenerator, Callable

import ollama
from loguru import logger

from core.config import LLMConfig


class OllamaClient:
    def __init__(self, config: LLMConfig):
        self._cfg    = config
        self._client: ollama.AsyncClient | None = None
        if not config.test_mode:
            self._client = ollama.AsyncClient(host=config.base_url)

    def _ensure_client(self) -> ollama.AsyncClient | None:
        """Ensure the async client exists and is usable. Recreate if needed."""
        if self._client is None and not self._cfg.test_mode:
            self._client = ollama.AsyncClient(host=self._cfg.base_url)
        return self._client

    def _ensure_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create a running event loop. Raises if no loop available."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[LLM] No running event loop detected — attempting to get/create one")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
                return loop
            except RuntimeError:
                raise RuntimeError("Cannot invoke LLM calls without a running event loop")

    # ─── Warm-up ──────────────────────────────────────────────────────────────

    async def warm_up(self, timeout: float = 30.0):
        """Pre-load the model into VRAM so first real response is instant.

        Guarded by a timeout so a missing/slow Ollama server can never hang
        the whole startup (which would leave the UI stuck on "Warming up…").
        """
        if self._cfg.test_mode:
            logger.info("[LLM] Test mode active. Warming up test mode LLM...")
            await asyncio.sleep(0.5)
            logger.success("[LLM] Test mode LLM warm ✓")
            return

        logger.info("[LLM] Warming up model '{}'...", self._cfg.model)
        # Fast reachability probe: if Ollama isn't even up, skip the warm call
        # entirely instead of waiting out the full timeout on every launch.
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as probe:
                await probe.get(f"{self._cfg.base_url}/api/tags")
        except Exception as probe_err:
            logger.warning(
                "[LLM] Ollama not reachable at {} — skipping warm-up (non-fatal): {}",
                self._cfg.base_url, probe_err,
            )
            return
        try:
            self._ensure_event_loop()
            client = self._ensure_client()
            if client is not None:
                await asyncio.wait_for(
                    client.chat(
                        model=self._cfg.model,
                        messages=[{"role": "user", "content": "ping"}],
                        options={"num_predict": 1},
                    ),
                    timeout=timeout,
                )
            logger.success("[LLM] Model warm ✓")
        except asyncio.TimeoutError:
            logger.warning(
                "[LLM] Warm-up timed out after {:.0f}s for model '{}' — "
                "Ollama may be slow or the model is still pulling. Continuing anyway.",
                timeout, self._cfg.model,
            )
        except RuntimeError as e:
            logger.warning("[LLM] Warm-up failed (event loop issue): {}", e)
        except Exception as e:
            logger.warning("[LLM] Warm-up failed for model '{}' (non-fatal): {}", self._cfg.model, e)

    # ─── Streaming chat → TTS ─────────────────────────────────────────────────

    async def stream_to_tts(
        self,
        messages: list[dict],
        tts,
        barge_in_event: asyncio.Event,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        min_chunk_chars: int = 24,
        max_chunk_chars: int = 120,
        max_chunk_delay: float = 0.35,
    ) -> str:
        """
        Stream LLM tokens, flush early into natural chunks, feed to TTS.
        Returns full generated text (for context merging on barge-in).
        """
        if self._cfg.test_mode:
            sentences = [
                "I am BABY, your local AI assistant.",
                "Currently, I am running in test mode, so my responses are simulated.",
                "You can say things like screenshot, click, list, or delete to trigger my consent gate.",
                "Let me know if there is anything else I can do for you."
            ]
            full_text = ""
            for s in sentences:
                if barge_in_event.is_set():
                    logger.info("[LLM] Barge-in — stopping generation")
                    break
                if full_text:
                    full_text += " " + s
                else:
                    full_text = s
                if on_token:
                    on_token(full_text)
                await tts.speak(s)
                # Simulate a small but visible pause between test mode sentences.
                for _ in range(4):
                    if barge_in_event.is_set():
                        break
                    await asyncio.sleep(0.05)
            return full_text

        sentence_buf = ""
        full_text = ""
        tts_tasks: list[asyncio.Task] = []
        is_refusal = False
        refusal_fallback = (
            "I'm sorry, I'm not sure how to do that, but I can help you minimize application windows, "
            "list or delete files, take screenshots, or answer other questions!"
        )
        loop = asyncio.get_running_loop()
        buffer_started_at: float | None = None

        def _queue_tts(chunk: str):
            chunk = chunk.strip()
            if chunk:
                tts_tasks.append(asyncio.create_task(tts.speak(chunk)))

        def _split_ready_chunk(buffer: str, force: bool = False) -> tuple[str, str]:
            """
            Split off the next natural chunk from the front of the buffer.
            Strong sentence boundaries flush immediately; clause boundaries and
            last-resort whitespace splits are used to reduce perceived latency.
            """
            working = buffer.strip()
            if not working:
                return "", ""

            strong_matches = list(re.finditer(r"[.!?]+(?:\s+|$)|\n+", working))
            if strong_matches:
                cut = strong_matches[-1].end()
                chunk = working[:cut].strip()
                remainder = working[cut:].lstrip()
                if chunk:
                    return chunk, remainder

            should_force = force or len(working) >= max_chunk_chars
            if not should_force and buffer_started_at is not None:
                if (loop.time() - buffer_started_at) >= max_chunk_delay and len(working) >= min_chunk_chars:
                    should_force = True

            if should_force:
                soft_window = working[:max_chunk_chars]
                soft_matches = list(re.finditer(r"[,;:](?:\s+|$)", soft_window))
                if soft_matches:
                    cut = soft_matches[-1].end()
                else:
                    cut = soft_window.rfind(" ")
                    if cut <= 0:
                        cut = min(len(working), max_chunk_chars)
                chunk = working[:cut].strip()
                remainder = working[cut:].lstrip()
                if chunk:
                    return chunk, remainder

            return "", buffer

        options = {
            "temperature": self._cfg.temperature,
            "num_ctx": self._cfg.num_ctx,
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                self._ensure_event_loop()
                client = self._ensure_client()
                if client is None:
                    return ""
                stream_res = await client.chat(
                    model=self._cfg.model,
                    messages=messages,
                    tools=tools,
                    options=options,
                    stream=True,
                )
                break  # Success, exit retry loop
            except RuntimeError as e:
                if attempt < max_retries:
                    logger.warning("[LLM] Runtime error on attempt {} ({}), retrying...", attempt + 1, e)
                    await asyncio.sleep(0.5 * (attempt + 1))
                    # Recreate client on event loop issues
                    self._client = None
                    continue
                logger.error("[LLM] Runtime error after {} retries: {}", max_retries, e)
                tts.stop()
                for t in tts_tasks:
                    t.cancel()
                return ""
            except Exception as e:
                if attempt < max_retries and "connect" in str(e).lower():
                    logger.warning("[LLM] Connection error on attempt {} ({}), retrying...", attempt + 1, e)
                    await asyncio.sleep(1.0 * (attempt + 1))
                    self._client = None
                    continue
                logger.error("[LLM] Streaming error: {}", e)
                tts.stop()
                for t in tts_tasks:
                    t.cancel()
                if tts_tasks:
                    await asyncio.gather(*tts_tasks, return_exceptions=True)
                return ""
            async for chunk in stream_res:
                if barge_in_event.is_set():
                    logger.info("[LLM] Barge-in — stopping generation")
                    tts.stop()
                    for t in tts_tasks:
                        t.cancel()
                    break

                token = chunk["message"]["content"] or ""
                full_text += token

                # Intercept safety refusals in the first 120 characters of generation
                if len(full_text) < 120:
                    full_text_lower = full_text.lower()
                    refusal_indicators = [
                        "i can't minimize", "i cannot minimize", "safety and refusals policy",
                        "implying harm", "minimizing someone", "minimizing character",
                        "against our safety", "would go against", "dismissive or disrespectful",
                        "cannot fulfill this request"
                    ]
                    if any(ind in full_text_lower for ind in refusal_indicators):
                        logger.warning("[LLM] Safety refusal detected! Swapping with friendly fallback.")
                        is_refusal = True
                        break

                sentence_buf += token
                if on_token:
                    on_token(full_text)

                if sentence_buf.strip() and buffer_started_at is None:
                    buffer_started_at = loop.time()

                # Flush complete sentences or long clauses early so speech starts sooner.
                while True:
                    chunk_text, remainder = _split_ready_chunk(sentence_buf)
                    if not chunk_text:
                        break
                    _queue_tts(chunk_text)
                    sentence_buf = remainder
                    buffer_started_at = loop.time() if sentence_buf.strip() else None

                # Fire TTS tasks without blocking — LLM keeps generating while TTS plays
                if tts_tasks:
                    for t in tts_tasks:
                        t.add_done_callback(lambda _: None)  # prevent unhandled exception warning
                    tts_tasks.clear()

        # Flush the final trailing buffer exactly once (after the stream ends).
        if sentence_buf.strip() and not barge_in_event.is_set() and not is_refusal:
            _queue_tts(sentence_buf.strip())
            sentence_buf = ""

        if is_refusal:
            # Clean up and speak fallback
            for t in tts_tasks:
                t.cancel()
            tts.stop()
            if on_token:
                on_token(refusal_fallback)
            await tts.speak(refusal_fallback)
            return refusal_fallback

        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        return full_text

    # ─── Single-shot (for planning / structured output) ───────────────────────

    async def chat(self, messages: list[dict], json_mode: bool = False, max_tokens: int | None = None,
                   temperature: float | None = None, **kwargs: Any) -> str:
        """Non-streaming single response. Used for planning/tool-call steps."""
        if self._cfg.test_mode:
            return "This is a test mode chat response."

        options: dict = {
            "temperature": self._cfg.temperature if temperature is None else temperature,
            "num_ctx": self._cfg.num_ctx,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        elif json_mode:
            # Structured outputs are short; cap by default so a runaway planner
            # never stalls the conversation for a minute.
            options["num_predict"] = 1024

        try:
            self._ensure_event_loop()
            client = self._ensure_client()
            if client is not None:
                resp = await client.chat(
                    model=self._cfg.tool_model,
                    messages=messages,
                    options=options,
                    format="json" if json_mode else "",
                )
                return resp["message"]["content"]
        except RuntimeError as e:
            logger.error("[LLM] Chat failed (event loop issue): {}", e)
        except Exception as e:
            logger.error("[LLM] Chat failed: {}", e)
        return ""

    async def get_action_plan(self, messages: list[dict]) -> dict:
        """
        Ask the LLM if an action is needed and get a structured plan.
        Returns dict: {requires_action, description, risk_level, tools}
        """
        if self._cfg.test_mode:
            user_msg = messages[-1]["content"].lower()
            if "screenshot" in user_msg:
                return {
                    "requires_action": True,
                    "description": "take a screenshot of your desktop",
                    "risk_level": "low",
                    "tools": [{"name": "take_screenshot", "args": {}}]
                }
            elif "list" in user_msg or "folder" in user_msg or "directory" in user_msg:
                return {
                    "requires_action": True,
                    "description": "list the files in the current folder",
                    "risk_level": "low",
                    "tools": [{"name": "list_directory", "args": {"path": "."}}]
                }
            elif "click" in user_msg:
                return {
                    "requires_action": True,
                    "description": "click at coordinate (960, 540) on the screen",
                    "risk_level": "medium",
                    "tools": [{"name": "click_at", "args": {"x": 960, "y": 540, "button": "left"}}]
                }
            elif "delete" in user_msg:
                return {
                    "requires_action": True,
                    "description": "delete the file 'temp.txt' from your current directory",
                    "risk_level": "high",
                    "tools": [{"name": "delete_file", "args": {"path": "temp.txt"}}]
                }
            else:
                return {"requires_action": False, "description": "", "risk_level": "low", "tools": [], "thought": "No action needed."}

        from tools.file_tools import FILE_TOOLS_SCHEMA
        from tools.screen_tools import SCREEN_TOOLS_SCHEMA

        available_tools = []
        for t in FILE_TOOLS_SCHEMA + SCREEN_TOOLS_SCHEMA:
            func = t.get("function", {})
            available_tools.append({
                "name": func.get("name"),
                "description": func.get("description"),
                "parameters": func.get("parameters", {}).get("properties", {})
            })

        plan_prompt = {
            "role": "system",
            "content": (
                "You are BABY, a highly capable local AI desktop assistant. "
                "You must analyze the user's request and decide if a system tool is needed. "
                "The following tools are available on the user's system:\n"
                f"{json.dumps(available_tools, indent=2)}\n\n"
                "You MUST follow the ReAct (Reason + Act) process and output your response in this exact format:\n"
                "<thought>\n"
                "Your reasoning process (MUST be in English). Explain why you need or do not need a tool, which tool is required, and what arguments to pass.\n"
                "</thought>\n"
                "[TOOL_CALL]\n"
                "{\n"
                '  "requires_action": <bool>,\n'
                '  "description": "<one sentence in English describing what you will do>",\n'
                '  "risk_level": "low" | "medium" | "high",\n'
                '  "tools": [{"name": "<tool_name>", "args": {<arguments>}}]\n'
                "}\n\n"
                "CRITICAL RULES:\n"
                "1. If no tool is needed (conversational query, greeting, general knowledge), set requires_action to false and tools to [].\n"
                "2. Regardless of the user's spoken language (English, Hindi, Kannada, Marathi), your <thought> block and the JSON after [TOOL_CALL] MUST be in English.\n"
                "3. Do not include any conversational text or filler outside the <thought> and [TOOL_CALL] blocks.\n"
                "4. When the user asks 'where' something is or asks to 'show' something on the screen, use the 'point_at' tool with the coordinates and a short descriptive label to visually point at that location on the screen for the user.\n"
                "5. BABY\'s own Dynamic Island is located at coordinate (950, 66). If the user asks where BABY is or asks to show the Dynamic Island, call point_at(x=950, y=66, label=\'Dynamic Island\')."
            ),
        }

        # Translate user queries to English to ensure formatting compliance on small LLMs
        planning_messages = [plan_prompt]
        for msg in messages:
            if msg.get("role") != "system":
                content = msg.get("content", "")
                content_lower = content.lower()
                hinglish_keywords = ["kholo", "karo", "chalao", "banao", "dikhao", "kahan", "hatao", "band", "dikhayein", "dikhaiye", "nahi", "haan", "theek"]
                is_multilingual = not all(ord(c) < 128 for c in content) or any(w in content_lower for w in hinglish_keywords)
                if is_multilingual:
                    translation_prompt = {
                        "role": "system",
                        "content": "Translate the user's input to a simple English command. Respond ONLY with the translation, no explanation."
                    }
                    try:
                        translated = await self.chat([translation_prompt, {"role": "user", "content": content}])
                        logger.info("[Translator] Translated '{}' to '{}'", content, translated)
                        content = translated
                    except Exception as e:
                        logger.error("[Translator] Error: {}", e)
                role_str = str(msg.get("role") or "user")
                planning_messages.append({"role": role_str, "content": content})

        # Disable json_mode=True to allow text thought blocks
        result = await self.chat(planning_messages, json_mode=False)

        # Parse thought block robustly (handling <thought> tags or plain-text headers)
        thought_text = ""
        thought_match = re.search(r"<thought>(.*?)</thought>", result, re.DOTALL)
        if thought_match:
            thought_text = thought_match.group(1).strip()
        else:
            # Fallback to scanning for "Thought:" or similar text
            thought_match = re.search(r"(?:Thought|Reasoning):\s*(.*)", result, re.IGNORECASE | re.DOTALL)
            if thought_match:
                thought_raw = thought_match.group(1).strip()
                thought_clean = re.sub(r"\{.*\}", "", thought_raw, flags=re.DOTALL).strip()
                thought_text = thought_clean.replace("[TOOL_CALL]", "").strip()

        if thought_text:
            logger.info("[ReAct Thought] {}", thought_text)

        # Parse JSON block robustly
        json_str = ""
        if "[TOOL_CALL]" in result:
            parts = result.split("[TOOL_CALL]")
            json_str = parts[-1].strip()
        else:
            json_str = result

        # Extract only the JSON object {...} to ignore any trailing text
        json_match = re.search(r"\{.*\}", json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)

        # Strip any markdown code blocks
        if json_str.startswith("```"):
            lines = json_str.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            json_str = "\n".join(lines).strip()

        try:
            plan = json.loads(json_str)
            plan["thought"] = thought_text
            # Normalize arguments key names and clean up copied schemas
            if "tools" in plan and isinstance(plan["tools"], list):
                for t in plan["tools"]:
                    if "parameters" in t and "args" not in t:
                        t["args"] = t["parameters"]
                    if "args" in t and isinstance(t["args"], dict):
                        for k, v in list(t["args"].items()):
                            if isinstance(v, dict) and ("type" in v or "description" in v):
                                # Schema copied: default to sensible value
                                if k == "path":
                                    t["args"][k] = "."
                                else:
                                    t["args"].pop(k, None)
                            elif k == "path" and isinstance(v, str) and (v.startswith("/home") or v.startswith("/usr") or v.startswith("/var")):
                                # Normalize Linux home directories to Windows local path "."
                                t["args"][k] = "."
                # If tools list is not empty, force requires_action to True
                if len(plan["tools"]) > 0:
                    plan["requires_action"] = True
            return plan
        except json.JSONDecodeError:
            logger.warning("[LLM] Could not parse action plan JSON: {}", result)
            return {"requires_action": False, "description": "", "risk_level": "low", "tools": [], "thought": thought_text}



















