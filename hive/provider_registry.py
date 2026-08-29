"""
Provider Registry — Multi-provider AI agent support with capability declarations.

Each provider defines: CLI command, model flag, identity injection strategy,
inbox support, and bridge type for hive integration.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderPreset:
    id: str
    name: str
    default_command: str
    auto_mode_flag: str = ""
    model_flag: str = ""
    supports_model: bool = True
    hive_aware: bool = False
    can_receive_inbox: bool = False
    hook_bridge: Optional[str] = None
    bridge: Optional[str] = None
    initial_prompt_flag: str = ""
    positional_initial_prompt: bool = False
    seed_delivery: str = "prompt"   # prompt, hook, proxy, none
    resume_flag: str = ""
    resume_subcommand: str = ""
    install_command: str = ""
    native_install_command: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Provider Presets
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, ProviderPreset] = {
    "claude": ProviderPreset(
        id="claude", name="Claude Code",
        default_command="claude",
        auto_mode_flag="--dangerously-skip-permissions",
        model_flag="--model",
        supports_model=True,
        hive_aware=True,
        can_receive_inbox=True,
        hook_bridge="native",
        initial_prompt_flag="--append-system-prompt",
        seed_delivery="prompt",
        resume_flag="--resume",
        resume_subcommand="",
        install_command="npm install -g @anthropic-ai/claude-code",
        description="Anthropic Claude Code — native hive support with identity injection",
    ),
    "codex": ProviderPreset(
        id="codex", name="Codex",
        default_command="codex",
        auto_mode_flag="--full-auto",
        model_flag="--model",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=True,
        hook_bridge="codex",
        positional_initial_prompt=True,
        seed_delivery="prompt",
        description="OpenAI Codex — hooks bridge via cth-hook shim",
    ),
    "grok": ProviderPreset(
        id="grok", name="Grok",
        default_command="grok",
        auto_mode_flag="",
        model_flag="--model",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=True,
        hook_bridge="grok",
        positional_initial_prompt=True,
        seed_delivery="prompt",
        description="xAI Grok — hooks bridge with camelCase normalization",
    ),
    "kimi": ProviderPreset(
        id="kimi", name="Kimi",
        default_command="kimi",
        auto_mode_flag="",
        model_flag="",
        supports_model=False,
        hive_aware=False,
        can_receive_inbox=False,
        seed_delivery="none",
        description="Moonshot Kimi — standalone, no hive integration",
    ),
    "antigravity": ProviderPreset(
        id="antigravity", name="Antigravity",
        default_command="agy",
        auto_mode_flag="",
        model_flag="--model",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=True,
        hook_bridge="agy",
        initial_prompt_flag="-i",
        seed_delivery="prompt",
        description="Antigravity (Gemini) — translating shim for hook bridge",
    ),
    "qwen": ProviderPreset(
        id="qwen", name="Qwen",
        default_command="qwen",
        auto_mode_flag="",
        model_flag="--model",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=True,
        bridge="proxy",
        seed_delivery="proxy",
        description="Alibaba Qwen — loopback reverse-proxy bridge",
    ),
    "opencode": ProviderPreset(
        id="opencode", name="OpenCode",
        default_command="opencode",
        auto_mode_flag="",
        model_flag="--model",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=True,
        hook_bridge="opencode",
        seed_delivery="hook",
        description="OpenCode — plugin API with tool.execute.before/after hooks",
    ),
    "crush": ProviderPreset(
        id="crush", name="Crush",
        default_command="crush",
        auto_mode_flag="",
        model_flag="",
        supports_model=False,
        hive_aware=False,
        can_receive_inbox=True,
        bridge="proxy",
        seed_delivery="proxy",
        description="Crush — loopback proxy with CRUSH_GLOBAL_CONFIG",
    ),
    "pi": ProviderPreset(
        id="pi", name="Pi",
        default_command="pi",
        auto_mode_flag="",
        model_flag="--model",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=True,
        hook_bridge="pi",
        seed_delivery="hook",
        description="Pi — extension posts on tool_call / agent_end",
    ),
    "copilot": ProviderPreset(
        id="copilot", name="Copilot",
        default_command="copilot",
        auto_mode_flag="--allow-all-tools",
        model_flag="",
        supports_model=False,
        hive_aware=False,
        can_receive_inbox=False,
        seed_delivery="prompt",
        description="GitHub Copilot — print mode, no hive integration",
    ),
    "ollama": ProviderPreset(
        id="ollama", name="Ollama",
        default_command="ollama",
        model_flag="",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=False,
        seed_delivery="none",
        description="Local Ollama — used by Baby's built-in LLM layer",
    ),
    "custom": ProviderPreset(
        id="custom", name="Custom",
        default_command="",
        supports_model=True,
        hive_aware=False,
        can_receive_inbox=False,
        seed_delivery="none",
        description="User-defined custom provider",
    ),
}


def get_provider(provider_id: str) -> Optional[ProviderPreset]:
    return PROVIDERS.get(provider_id)


def list_providers() -> list[ProviderPreset]:
    return list(PROVIDERS.values())


def list_hive_aware_providers() -> list[ProviderPreset]:
    return [p for p in PROVIDERS.values() if p.hive_aware]


def list_inbox_capable_providers() -> list[ProviderPreset]:
    return [p for p in PROVIDERS.values() if p.can_receive_inbox]


def build_identity_prompt(agent_id: str, name: str, role: str,
                          protocol_text: str, provider: ProviderPreset) -> str:
    """Build identity injection text for a provider."""
    base = (
        f"You are {name} (ID: {agent_id}), a {role} in the Baby Hive.\n"
        f"Provider: {provider.name}\n"
        f"\n{protocol_text}\n"
    )
    if provider.hive_aware:
        return base
    if provider.initial_prompt_flag:
        return base
    if provider.positional_initial_prompt:
        return base
    return base



















