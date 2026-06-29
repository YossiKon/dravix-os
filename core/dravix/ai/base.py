"""Pluggable AI provider interface.

A provider turns a user utterance (+ optional persona/system prompt) into a reply. The
default is Home Assistant Assist; Claude / OpenAI / Ollama adapters implement the same
interface and are selected by ``DRAVIX_AI_PROVIDER`` without changing any caller.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class AIReply:
    text: str
    conversation_id: str | None = None
    raw: dict | None = None


class AIProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def converse(
        self,
        text: str,
        *,
        system: str | None = None,
        conversation_id: str | None = None,
    ) -> AIReply:
        """Return the assistant's reply to ``text``."""

    async def close(self) -> None:  # optional override
        return None
