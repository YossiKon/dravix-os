"""OpenAI AI provider (chat completions). Uses the official ``openai`` SDK."""
from __future__ import annotations

import uuid
from typing import Any

from ..logging import get_logger
from ..persona import Persona
from .base import AIProvider, AIReply

log = get_logger("ai.openai")

_HISTORY_LIMIT = 20


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
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
            import openai  # lazy — optional dependency

            self._client = openai.AsyncOpenAI(api_key=self._api_key)
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
        messages = [{"role": "system", "content": system or self._default_system}, *history]
        client = self._ensure_client()
        resp = await client.chat.completions.create(
            model=self._model, max_tokens=self._max_tokens, messages=messages
        )
        reply = (resp.choices[0].message.content or "").strip()
        history.append({"role": "assistant", "content": reply})
        if len(history) > _HISTORY_LIMIT:
            del history[: len(history) - _HISTORY_LIMIT]
        return AIReply(text=reply, conversation_id=cid)
