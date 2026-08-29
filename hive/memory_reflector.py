"""
Memory Reflector — Auto-condense oversized memory.md files with safety gates.

Monitors agent memory files and condenses them into the 3-region structure
(pinned / condensed / recent) when they exceed size thresholds.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from hive.hive_manager import get_hive

logger = logging.getLogger("Baby.hive.memory")

# Default thresholds
BYTE_TRIGGER_PCT = 80        # Trigger when memory > 80% of 128KB budget
SECTION_TRIGGER = 10         # Or when > 10 sections and file > minBytes
MIN_BYTES = 4096
MAX_MEMORY_BYTES = 131072    # 128KB budget
RECENT_KEEP = 3              # Keep last N recent sections


class MemoryReflector:
    """Condenses agent memory.md files into bounded 3-region structure."""

    def __init__(self, byte_trigger_pct: int = BYTE_TRIGGER_PCT,
                 section_trigger: int = SECTION_TRIGGER,
                 min_bytes: int = MIN_BYTES, recent_keep: int = RECENT_KEEP):
        self.byte_trigger_pct = byte_trigger_pct
        self.section_trigger = section_trigger
        self.min_bytes = min_bytes
        self.recent_keep = recent_keep
        self._hive = get_hive()

    def should_condense(self, agent_id: str) -> bool:
        """Check if an agent's memory needs condensing."""
        mem_path = self._hive.agents_dir / agent_id / "memory.md"
        if not mem_path.exists():
            return False
        content = mem_path.read_text(encoding="utf-8")
        size = len(content.encode("utf-8"))
        threshold = int(MAX_MEMORY_BYTES * self.byte_trigger_pct / 100)
        if size > threshold:
            return True
        sections = len(re.findall(r"^## ", content, re.MULTILINE))
        if sections > self.section_trigger and size > self.min_bytes:
            return True
        return False

    def parse_regions(self, content: str) -> dict:
        """Parse memory.md into 3 regions."""
        regions = {"pinned": "", "condensed": "", "recent": "", "header": ""}
        lines = content.split("\n")
        current_region = "header"
        region_lines = []

        for line in lines:
            stripped = line.strip()
            if re.match(r"^## .*(Pinned|📌)", stripped, re.IGNORECASE):
                if region_lines:
                    regions[current_region] = "\n".join(region_lines).strip()
                current_region = "pinned"
                region_lines = []
            elif re.match(r"^## .*(Condensed|🗜)", stripped, re.IGNORECASE):
                if region_lines:
                    regions[current_region] = "\n".join(region_lines).strip()
                current_region = "condensed"
                region_lines = []
            elif re.match(r"^## .*(Recent)", stripped, re.IGNORECASE):
                if region_lines:
                    regions[current_region] = "\n".join(region_lines).strip()
                current_region = "recent"
                region_lines = []
            elif re.match(r"^## ", stripped) and current_region == "recent":
                region_lines.append(line)
            else:
                region_lines.append(line)

        if region_lines:
            regions[current_region] = "\n".join(region_lines).strip()

        return regions

    def condense(self, agent_id: str, llm_summarizer=None) -> bool:
        """Condense an agent's memory.md. Returns True if condensed."""
        mem_path = self._hive.agents_dir / agent_id / "memory.md"
        if not mem_path.exists():
            return False

        content = mem_path.read_text(encoding="utf-8")
        regions = self.parse_regions(content)

        # Backup first
        self._hive.backup_agent_memory(agent_id)

        # Extract recent sections (last N ## headings)
        recent_content = regions.get("recent", "")
        sections = re.split(r"(?=^## )", recent_content, flags=re.MULTILINE)
        sections = [s for s in sections if s.strip()]
        kept = sections[-self.recent_keep:] if len(sections) > self.recent_keep else sections
        evicted = sections[:-self.recent_keep] if len(sections) > self.recent_keep else []

        # Summarize evicted sections
        if evicted and llm_summarizer:
            evicted_text = "\n".join(evicted)
            summary = llm_summarizer(
                pinned=regions.get("pinned", ""),
                evicted=evicted_text,
                condensed=regions.get("condensed", ""),
            )
        elif evicted:
            # Simple truncation summary if no LLM available
            summary = f"_Condensed {len(evicted)} sections at {time.strftime('%Y-%m-%d %H:%M')}_"
            for s in evicted:
                # Extract first line of each section as summary
                first_line = s.strip().split("\n")[0][:100]
                summary += f"\n- {first_line}"
        else:
            summary = regions.get("condensed", "")

        # Reassemble
        header = regions.get("header", "# Memory\n")
        pinned = regions.get("pinned", "")
        new_content = (
            f"{header}\n\n"
            f"## Pinned facts\n{pinned}\n\n"
            f"## Condensed history\n{summary}\n\n"
            f"## Recent\n"
        )
        for s in kept:
            new_content += s + "\n"

        # Verify gate: new file must be smaller
        old_size = len(content.encode("utf-8"))
        new_size = len(new_content.encode("utf-8"))
        if new_size >= old_size * 0.95 and evicted:
            logger.warning("[MemoryReflector] Condense would not reduce size for {}, skipping", agent_id)
            return False

        # Atomic write
        tmp_path = mem_path.with_suffix(".tmp")
        tmp_path.write_text(new_content, encoding="utf-8")
        tmp_path.replace(mem_path)

        logger.info("[MemoryReflector] Condensed memory for {}: {} -> {} bytes", agent_id, old_size, new_size)
        return True

    def condense_all(self, llm_summarizer=None) -> dict[str, bool]:
        """Condense all agents that need it."""
        results = {}
        for agent in self._hive.list_agents():
            agent_id = agent["id"]
            if self.should_condense(agent_id):
                results[agent_id] = self.condense(agent_id, llm_summarizer)
            else:
                results[agent_id] = False
        return results



















