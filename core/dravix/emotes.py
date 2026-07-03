"""Emote library — named animated reactions, the EMO/Vector-style "alive" gestures.

Each emote is a short sequence of capability-guarded steps (face / head / LEDs / say / wait),
so the same emote runs on the mock driver (logged) and, unchanged, on the real robot.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, RobotController
from .logging import get_logger

log = get_logger("emotes")

# step keys: face(str) · head([yaw,pitch] normalised -1..1) · leds([color,brightness]) ·
# say(str) · wait(seconds). Head values are a fraction of travel (0 = straight).
EMOTES: dict[str, list[dict[str, Any]]] = {
    "happy": [
        {"face": "happy", "leds": ["yellow", 0.8]},
        {"head": [0.45, 0.2], "wait": 0.25},
        {"head": [-0.45, 0.2], "wait": 0.25},
        {"head": [0, 0]},
    ],
    "love": [
        {"face": "happy", "leds": ["magenta", 0.9]},
        {"head": [0, -0.2], "wait": 0.3},
        {"head": [0, 0.1]},
    ],
    "sad": [
        {"face": "sad", "leds": ["blue", 0.2]},
        {"head": [0, -0.35], "wait": 0.4},
        {"head": [0, 0]},
    ],
    "surprised": [
        {"face": "doubt", "leds": ["white", 1.0]},
        {"head": [0, 0.3], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "yes": [
        {"face": "happy"},
        {"head": [0, 0.3], "wait": 0.2},
        {"head": [0, -0.3], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "no": [
        {"face": "doubt"},
        {"head": [0.5, 0], "wait": 0.2},
        {"head": [-0.5, 0], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "curious": [
        {"face": "doubt"},
        {"head": [0.35, 0.15], "wait": 0.3},
        {"head": [-0.35, 0.15], "wait": 0.3},
        {"head": [0, 0]},
    ],
    "sleepy": [
        {"face": "sleepy", "leds": ["amber", 0.1]},
        {"head": [0, -0.25]},
    ],
    "wake": [
        {"face": "neutral", "leds": ["white", 0.4]},
        {"head": [0, 0.2], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "fistbump": [
        {"face": "happy"},
        {"head": [0, 0.3], "wait": 0.15},
        {"leds": ["green", 1.0]},
        {"say": "Boom!"},
        {"head": [0, 0]},
    ],
    # ── vitals / needs feedback (fed by the VitalsEngine) ──
    "eat": [  # nom nom — bobs the head down to the "food" and chews, warm leds
        {"face": "happy", "leds": ["orange", 0.9]},
        {"head": [0, 0.35], "wait": 0.25},
        {"head": [0, 0.1], "wait": 0.2},
        {"head": [0, 0.35], "wait": 0.25},
        {"head": [0, 0.1], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "yawn": [  # tired — a slow droop + dim amber
        {"face": "sleepy", "leds": ["amber", 0.15]},
        {"head": [0, -0.3], "wait": 0.5},
        {"head": [0, -0.1]},
    ],
    "calm": [  # soothe — settle to neutral, soft blue, gentle centre
        {"face": "neutral", "leds": ["blue", 0.25]},
        {"head": [0, -0.1], "wait": 0.4},
        {"head": [0, 0]},
    ],
    "play": [  # excited play — quick wiggle, bright cyan
        {"face": "happy", "leds": ["cyan", 1.0]},
        {"head": [0.4, 0.15], "wait": 0.18},
        {"head": [-0.4, 0.15], "wait": 0.18},
        {"head": [0.3, 0.2], "wait": 0.18},
        {"head": [0, 0]},
    ],
    "nudge": [  # "hey, notice me" — a gentle attention wiggle for a wellness tip
        {"leds": ["cyan", 1.0]},
        {"head": [0.3, 0.1], "wait": 0.2},
        {"head": [-0.3, 0.1], "wait": 0.2},
        {"head": [0, 0]},
    ],
}


def emote_names() -> list[str]:
    return sorted(EMOTES)


async def play_emote(robot: RobotController, name: str) -> None:
    steps = EMOTES.get(name)
    if steps is None:
        raise KeyError(name)
    for step in steps:
        if "face" in step and robot.supports(CAP_FACE):
            await robot.set_face(step["face"])
        if "leds" in step and robot.supports(CAP_LEDS):
            color, bright = step["leds"]
            await robot.set_leds(color, float(bright))
        if "head" in step and robot.supports(CAP_HEAD):
            yaw, pitch = step["head"]
            await robot.move_head(float(yaw), float(pitch), speed=1.0)
        if "say" in step and robot.supports(CAP_SAY):
            await robot.say(str(step["say"]))
        if step.get("wait"):
            await asyncio.sleep(float(step["wait"]))
