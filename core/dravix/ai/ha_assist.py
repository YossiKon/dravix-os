"""AI provider backed by Home Assistant's Assist conversation pipeline.

This is the default: HA already owns STT/LLM/TTS on your host, and it has full smart-home
context. dravix-os just forwards text and reads back the spoken response.
"""
from __future__ import annotations

from typing import Any

from ..integrations.homeassistant import HomeAssistant
from ..logging import get_logger
from .base import AIProvider, AIReply

log = get_logger("ai.ha_assist")


def _extract_speech(response: dict[str, Any]) -> str:
    """Pull the plain-text reply out of HA's conversation response envelope."""
    try:
        speech = response["response"]["speech"]["plain"]["speech"]
        if speech:
            return str(speech)
    except (KeyError, TypeError):
        pass
    return ""


class HAAssistProvider(AIProvider):
    name = "ha_assist"

    def __init__(self, ha: HomeAssistant, agent_id: str | None = None) -> None:
        self._ha = ha
        self._agent_id = agent_id or None

    async def converse(
        self,
        text: str,
        *,
        system: str | None = None,
        conversation_id: str | None = None,
    ) -> AIReply:
        # HA Assist's persona is configured on the HA side; ``system`` is accepted for
        # interface parity and will be applied via prompt-prefixing for non-Assist providers.
        result = await self._ha.conversation(
            text, agent_id=self._agent_id, conversation_id=conversation_id
        )
        reply = _extract_speech(result)
        cid = result.get("conversation_id") if isinstance(result, dict) else None
        return AIReply(text=reply, conversation_id=cid, raw=result)
