"""Persona + emotion tag parsing.

StackChan AI firmwares conventionally prefix replies with an emotion tag like ``(Happy)`` or
``[sad]``. ``parse_expression`` extracts that tag (so we can drive the face) and returns the
clean text to speak. ``Persona`` bundles the system prompt + voice + default expression.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .dal.base import Expression

# Leading tag like "(Happy)", "[happy]", "(happy):" — case-insensitive.
_TAG_RE = re.compile(r"^\s*[\(\[]\s*([a-zA-Z]+)\s*[\)\]]\s*:?\s*")


def parse_expression(text: str) -> tuple[Expression, str]:
    """Split a leading emotion tag from ``text``.

    Returns ``(expression, clean_text)``. If no tag is present, returns
    ``(Expression.NEUTRAL, text)`` unchanged.
    """
    if not text:
        return Expression.NEUTRAL, text
    m = _TAG_RE.match(text)
    if not m:
        return Expression.NEUTRAL, text.strip()
    expr = Expression.coerce(m.group(1))
    clean = text[m.end():].strip()
    return expr, clean


@dataclass
class Persona:
    name: str = "StackChan"
    system_prompt: str = (
        "You are StackChan, a small, warm, witty desktop robot companion. Keep replies short "
        "and spoken-friendly. When it fits, begin your reply with an emotion tag in "
        "parentheses, one of: (neutral) (happy) (sad) (angry) (sleepy) (doubt)."
    )
    voice: str | None = None
    default_expression: Expression = Expression.NEUTRAL


def resolve_voice(store) -> str | None:
    """Effective TTS voice: the store override, else the active persona's voice, else none."""
    if store is None:
        return None
    return store.voice() or resolve_persona(store).voice


def resolve_persona(store) -> Persona:
    """Return the active persona from the store, or the built-in default."""
    if store is None:
        return Persona()
    name = store.active_persona()
    if name:
        for p in store.personas():
            if p.get("name") == name:
                return Persona(
                    name=p.get("name", "StackChan"),
                    system_prompt=p.get("system_prompt") or Persona().system_prompt,
                    voice=p.get("voice"),
                    default_expression=Expression.coerce(p.get("default_expression", "neutral")),
                )
    return Persona()
