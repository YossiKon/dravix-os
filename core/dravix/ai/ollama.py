"""Local LLM provider via Ollama's chat API (httpx — no extra dependency, fully local)."""
from __future__ import annotations

import uuid

import httpx

from ..logging import get_logger
from ..persona import Persona
from .base import AIProvider, AIReply

log = get_logger("ai.ollama")

_HISTORY_LIMIT = 20


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(
        self,
        url: str = "http://localhost:11434",
        model: str = "llama3.2",
        max_tokens: int = 512,
        system: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._default_system = system or Persona().system_prompt
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._history: dict[str, list[dict[str, str]]] = {}

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
        r = await self._client.post(
            f"{self._url}/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": self._max_tokens},
            },
        )
        r.raise_for_status()
        reply = (r.json().get("message", {}).get("content") or "").strip()
        history.append({"role": "assistant", "content": reply})
        if len(history) > _HISTORY_LIMIT:
            del history[: len(history) - _HISTORY_LIMIT]
        return AIReply(text=reply, conversation_id=cid)

    async def close(self) -> None:
        await self._client.aclose()
