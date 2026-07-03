"""Tests for switchable personas and system-prompt threading into the AI router."""
from __future__ import annotations

from dravix.ai import build_provider
from dravix.config import Settings
from dravix.persona import Persona, resolve_persona
from dravix.store import Store


def test_resolve_persona_default_and_active(tmp_path):
    s = Store(tmp_path / "s.json")
    assert resolve_persona(s).name == "Dravix"  # built-in default when none active
    s.set_personas([
        {"name": "Grumpy", "system_prompt": "Be terse and grumpy.", "default_expression": "doubt"}
    ])
    s.set_active_persona("Grumpy")
    p = resolve_persona(s)
    assert p.name == "Grumpy"
    assert "grumpy" in p.system_prompt.lower()
    assert p.default_expression.value == "doubt"


def test_build_provider_threads_system_prompt():
    p = build_provider(Settings(_env_file=None, ai_provider="ollama"), system="SYS-XYZ")
    assert p._default_system == "SYS-XYZ"
    p2 = build_provider(Settings(_env_file=None, ai_provider="ollama"))
    assert p2._default_system == Persona().system_prompt
