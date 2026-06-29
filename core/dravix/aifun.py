"""AI party tricks — one-shot prompts the robot speaks (joke, fact, riddle, ...).

Each is a single prompt to the active AI provider; the reply is spoken (with a face from its
emotion tag). Needs an AI provider configured.
"""
from __future__ import annotations

PROMPTS: dict[str, str] = {
    "joke": "Tell me one short, original joke — one or two lines. Begin with an emotion tag like (happy).",
    "fact": "Tell me one surprising fun fact in a single sentence. Begin with (happy) or (doubt).",
    "riddle": "Give me a short riddle — just the riddle, no answer. Begin with (doubt).",
    "compliment": "Give me a warm, specific compliment in one sentence. Begin with (happy).",
    "would_you_rather": "Ask me a fun 'would you rather' question, one line. Begin with (doubt).",
    "story": "Tell me a tiny three-sentence bedtime story. Begin with (sleepy).",
}


def kinds() -> list[str]:
    return list(PROMPTS)
