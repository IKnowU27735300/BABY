"""
llm/airllm_client.py — AirLLM Client wrapper for low-VRAM layer-by-layer LLM inference.
Enables running 7B/8B/70B models on GPUs with <= 4GB VRAM (e.g. RTX 3050 4GB).
"""

from __future__ import annotations
import asyncio
import json
import re
from typing import Any, Callable, Optional
from loguru import logger

from core.config import LLMConfig

# Sentence-boundary pattern for streaming TTS
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class AirLLMClient:
    """
    LLM Client powered by AirLLM (https://github.com/lyogavin/airllm).
    Executes transformer models block-by-block to keep GPU VRAM footprint below 4GB.
    """

    def __init__(self, config: LLMConfig):
        self._cfg = config
        self._model = None
        self._tokenizer = None
        self._lock = asyncio.Lock()

    # ─── Warm-up / Model Loading ──────────────────────────────────────────────

    def _load_model_sync(self):
        """Synchronous loader executed in worker thread."""
        try:
            from airllm import AutoModel
        except ImportError:
            raise ImportError(
                "airllm is not installed. Please install it via `pip install airllm`."
            )

        model_name = getattr(self._cfg, "airllm_model", "meta-llama/Meta-Llama-3.1-8B-Instruct")
        compression = getattr(self._cfg, "airllm_compression", "4bit")
        max_length = getattr(self._cfg, "airllm_max_length", 2048)

        logger.info(
            "[AirLLM] Loading model '{}' with compression='{}'...",
            model_name, compression
        )

        kwargs = {"max_length": max_length}
        if compression in ("4bit", "8bit"):
            kwargs["compression"] = compression

        # Initialize AirLLM AutoModel
        self._model = AutoModel.from_pretrained(model_name, **kwargs)
        self._tokenizer = self._model.tokenizer
        logger.success("[AirLLM] Model '{}' loaded successfully ✓", model_name)

    async def warm_up(self):
        """Pre-load the model layers into memory asynchronously."""
        if self._cfg.test_mode:
            logger.info("[AirLLM] Test mode active. Warming up test AirLLM...")
            await asyncio.sleep(0.5)
            logger.success("[AirLLM] Test AirLLM warm ✓")
            return

        async with self._lock:
            if self._model is None:
                await asyncio.to_thread(self._load_model_sync)

    # ─── Format Chat Prompt ───────────────────────────────────────────────────

    def _format_messages_prompt(self, messages: list[dict]) -> str:
        """Formats conversation messages into standard instruction chat format."""
        if self._tokenizer and hasattr(self._tokenizer, "apply_chat_template"):
            try:
                formatted = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                if isinstance(formatted, str):
                    return formatted
            except Exception as e:
                logger.warning("[AirLLM] Failed to apply tokenizer chat template: {}", e)

        # Fallback instruction template
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            prompt_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        prompt_parts.append("<|im_start|>ASSISTANT\n")
        return "\n".join(prompt_parts)

    # ─── Synchronous Generation Helper ────────────────────────────────────────

    def _generate_sync(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        on_token_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Run AirLLM generation in worker thread."""
        if self._model is None or self._tokenizer is None:
            self._load_model_sync()
        if self._model is None or self._tokenizer is None:
            return ""

        import torch

        input_tokens = self._tokenizer(
            [prompt],
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=getattr(self._cfg, "airllm_max_length", 2048),
        )

        device = "cuda" if torch.cuda.is_available() else "cpu"
        input_ids = input_tokens["input_ids"].to(device)

        # Execute generation via AirLLM block-by-block
        with torch.no_grad():
            output_ids = self._model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                use_cache=True,
            )

        # Decode output tokens (extract new tokens only)
        new_ids = output_ids[0][input_ids.shape[1]:]
        generated_text = self._tokenizer.decode(new_ids, skip_special_tokens=True)

        if on_token_cb:
            on_token_cb(generated_text)

        return generated_text

    # ─── Single-shot Chat ─────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        """Non-streaming single response. Used for planning & tool call evaluation."""
        if self._cfg.test_mode:
            return "This is a test mode AirLLM response."

        async with self._lock:
            prompt = self._format_messages_prompt(messages)
            max_new = max_tokens or 512
            response_text = await asyncio.to_thread(self._generate_sync, prompt, max_new)

            if json_mode:
                # Extract JSON object from output if extra tokens were produced
                match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if match:
                    return match.group(0)

            return response_text.strip()

    # ─── Streaming Chat → TTS ─────────────────────────────────────────────────

    async def stream_to_tts(
        self,
        messages: list[dict],
        tts,
        barge_in_event: asyncio.Event,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        min_chunk_chars: int = 36,
        max_chunk_chars: int = 140,
        max_chunk_delay: float = 0.55,
    ) -> str:
        """
        Stream LLM tokens generated via AirLLM, flush in natural chunks, feed to TTS.
        """
        if self._cfg.test_mode:
            sentences = [
                "I am BABY, your local AI assistant running with AirLLM.",
                "I am currently using layer-wise inference to keep memory low on your 4GB GPU.",
                "Let me know what tasks you would like me to assist you with."
            ]
            full_text = ""
            for s in sentences:
                if barge_in_event.is_set():
                    break
                full_text = f"{full_text} {s}".strip()
                if on_token:
                    on_token(full_text)
                await tts.speak(s)
                await asyncio.sleep(0.2)
            return full_text

        async with self._lock:
            prompt = self._format_messages_prompt(messages)
            
            # Execute generation
            generated_text = await asyncio.to_thread(
                self._generate_sync, prompt, 512
            )

        if barge_in_event.is_set():
            logger.info("[AirLLM] Barge-in event set before speech.")
            return generated_text

        # Sentence-boundary splitting for smooth TTS streaming
        sentences = _SENTENCE_RE.split(generated_text.strip())
        if not sentences:
            sentences = [generated_text]

        tts_tasks = []
        accumulated = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if barge_in_event.is_set():
                logger.info("[AirLLM] Barge-in event triggered — stopping speech synthesis.")
                tts.stop()
                for t in tts_tasks:
                    t.cancel()
                break

            accumulated = f"{accumulated} {sentence}".strip()
            if on_token:
                on_token(accumulated)

            tts_tasks.append(asyncio.create_task(tts.speak(sentence)))
            await asyncio.sleep(0.05)

        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        return generated_text

    # ─── ReAct Action Plan ────────────────────────────────────────────────────

    async def get_action_plan(self, messages: list[dict]) -> dict:
        """
        Ask AirLLM if an action is needed and get a structured ReAct plan.
        Returns dict: {requires_action, description, risk_level, tools, thought}
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
            return {
                "requires_action": False,
                "description": "",
                "risk_level": "low",
                "tools": [],
                "thought": "No action needed."
            }

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
                "You must analyze the user's request and decide if a system tool is needed.\n"
                f"Available tools:\n{json.dumps(available_tools, indent=2)}\n\n"
                "Follow the ReAct process and output in this exact format:\n"
                "<thought>\n"
                "Reasoning process in English.\n"
                "</thought>\n"
                "[TOOL_CALL]\n"
                "{\n"
                '  "requires_action": <bool>,\n'
                '  "description": "<description in English>",\n'
                '  "risk_level": "low" | "medium" | "high",\n'
                '  "tools": [{"name": "<tool_name>", "args": {}}]\n'
                "}\n"
            ),
        }

        planning_messages = [plan_prompt] + [
            m for m in messages if m.get("role") != "system"
        ]

        result = await self.chat(planning_messages, json_mode=False)

        # Parse thought block
        thought_text = ""
        thought_match = re.search(r"<thought>(.*?)</thought>", result, re.DOTALL)
        if thought_match:
            thought_text = thought_match.group(1).strip()

        # Parse JSON block
        json_str = result
        if "[TOOL_CALL]" in result:
            json_str = result.split("[TOOL_CALL]")[-1].strip()

        json_match = re.search(r"\{.*\}", json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)

        try:
            plan = json.loads(json_str)
            plan["thought"] = thought_text
            if "tools" in plan and isinstance(plan["tools"], list):
                if len(plan["tools"]) > 0:
                    plan["requires_action"] = True
            return plan
        except json.JSONDecodeError:
            logger.warning("[AirLLM] Could not parse action plan JSON: {}", result)
            return {
                "requires_action": False,
                "description": "",
                "risk_level": "low",
                "tools": [],
                "thought": thought_text
            }



















