"""Tests for the pluggable AI providers (no network, no cloud SDKs required)."""
from __future__ import annotations

import httpx
import pytest

from dravix.ai import build_provider
from dravix.ai.claude import ClaudeProvider
from dravix.ai.ollama import OllamaProvider
from dravix.config import Settings


# ── Claude (injected fake anthropic client) ──────────────────────────────────
class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, captured: list) -> None:
        self._captured = captured

    async def create(self, **kwargs):
        self._captured.append(kwargs)
        return _Message("(happy) Hi there!")


class _FakeAnthropic:
    def __init__(self, captured: list) -> None:
        self.messages = _FakeMessages(captured)


async def test_claude_provider_shapes_request_and_reads_text():
    captured: list = []
    provider = ClaudeProvider(model="claude-haiku-4-5", client=_FakeAnthropic(captured))
    reply = await provider.converse("hello")
    assert reply.text == "(happy) Hi there!"
    assert reply.conversation_id
    sent = captured[0]
    assert sent["model"] == "claude-haiku-4-5"
    assert sent["messages"] == [{"role": "user", "content": "hello"}]
    assert isinstance(sent["system"], str) and sent["system"]
    # Second turn reuses the conversation history.
    await provider.converse("again", conversation_id=reply.conversation_id)
    assert captured[1]["messages"][0] == {"role": "user", "content": "hello"}
    assert captured[1]["messages"][-1] == {"role": "user", "content": "again"}


# ── Ollama (httpx MockTransport) ─────────────────────────────────────────────
async def test_ollama_provider_round_trip():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = httpx.Response  # placeholder; real body read below
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "(sleepy) mm hello"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(model="llama3.2", client=client)
    reply = await provider.converse("hi")
    assert reply.text == "(sleepy) mm hello"
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["model"] == "llama3.2"
    assert seen["body"]["messages"][-1] == {"role": "user", "content": "hi"}
    await provider.close()


# ── Factory ──────────────────────────────────────────────────────────────────
def test_build_provider_ollama_and_unknown():
    p = build_provider(Settings(_env_file=None, ai_provider="ollama"), ha=None)
    assert p.name == "ollama"
    with pytest.raises(ValueError):
        build_provider(Settings(_env_file=None, ai_provider="bogus"), ha=None)
