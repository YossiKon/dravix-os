"""AI router package — provider factory + public types."""
from __future__ import annotations

from ..config import Settings
from ..integrations.homeassistant import HomeAssistant
from .base import AIProvider, AIReply

__all__ = ["AIProvider", "AIReply", "build_provider"]


def build_provider(settings: Settings, ha: HomeAssistant | None = None) -> AIProvider:
    """Construct the AI provider selected by configuration.

    Only ``ha_assist`` ships in Phase 0. Claude / OpenAI / Ollama adapters slot in here in
    Phase 4 behind the same ``AIProvider`` interface.
    """
    provider = settings.ai_provider.lower()
    if settings.local_only and provider in {"claude", "openai"}:
        raise ValueError(
            f"{provider!r} is a cloud provider but DRAVIX_LOCAL_ONLY is set — "
            "use 'ha_assist' (local pipeline) or 'ollama', or set DRAVIX_LOCAL_ONLY=false"
        )
    if provider == "ha_assist":
        from .ha_assist import HAAssistProvider

        if ha is None:
            raise ValueError("ha_assist provider requires a configured HomeAssistant client")
        return HAAssistProvider(ha=ha, agent_id=settings.ha_assist_agent)
    if provider == "claude":
        from .claude import ClaudeProvider

        if not settings.anthropic_api_key:
            raise ValueError("claude provider requires ANTHROPIC_API_KEY")
        return ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            max_tokens=settings.ai_max_tokens,
        )
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        if not settings.openai_api_key:
            raise ValueError("openai provider requires OPENAI_API_KEY")
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            max_tokens=settings.ai_max_tokens,
        )
    if provider == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(
            url=settings.ollama_url, model=settings.ollama_model, max_tokens=settings.ai_max_tokens
        )
    raise ValueError(f"unknown DRAVIX_AI_PROVIDER: {settings.ai_provider!r}")
