"""Anthropic Claude AI provider.

Uses the official ``anthropic`` SDK (Messages API). Keeps a short rolling history per
conversation_id since the API is stateless. The persona system prompt asks Claude to prefix
replies with an emotion tag like ``(happy)`` — the chat layer parses that to drive the face.

Default model is ``claude-opus-4-8`` (most capable). For a robot that chats frequently,
``claude-haiku-4-5`` (fast + cheap) or ``claude-sonnet-4-6`` (balanced) are good alternatives —
set ``DRAVIX_CLAUDE_MODEL``.
"""
from __future__ import annotations

import uuid
from typing import Any

from ..logging import get_logger
from ..persona import Persona
from .base import AIProvider, AIReply

log = get_logger("ai.claude")

_HISTORY_LIMIT = 20  # keep the last N turns per conversation


def _extract_text(message: Any) -> str:
    parts = [b.text for b in getattr(message, "content", []) if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-opus-4-8",
        max_tokens: int = 512,
        system: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key or None
        self._model = model
        self._max_tokens = max_tokens
        self._default_system = system or Persona().system_prompt
        self._client = client
        self._history: dict[str, list[dict[str, str]]] = {}

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy — optional dependency

            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def converse(
        self,
        text: str,
        *,
        system: str | None = None,
        conversation_id: str | None = None,
    ) -> AIReply:
        cid = conversation_id or uuid.uuid4().hex
        history = self._history.setdefault(cid, [])
        history.append({"role": "user", "content": text})
        client = self._ensure_client()
        message = await client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system or self._default_system,
            messages=list(history),
        )
        reply = _extract_text(message)
        history.append({"role": "assistant", "content": reply})
        if len(history) > _HISTORY_LIMIT:
            del history[: len(history) - _HISTORY_LIMIT]
        return AIReply(text=reply, conversation_id=cid)
