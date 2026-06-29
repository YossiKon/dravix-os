"""The robot's long-term memory of facts the user tells it (fed to the AI as context).

Stored in the persistent store; surfaced to cloud/local LLM providers by prepending to the
system prompt. (HA Assist owns its own pipeline, so injected memory doesn't reach it.)
"""
from __future__ import annotations

_MAX = 30  # cap how many facts we inject


def build_memory_context(store) -> str:
    mems = store.memories() if store is not None else []
    if not mems:
        return ""
    lines = "\n".join(f"- {m.get('text', '')}" for m in mems[:_MAX])
    return "Things to remember about the user (use when relevant):\n" + lines
