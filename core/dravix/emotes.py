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

# step keys: face(str) · head([yaw,pitch]) · leds([color,brightness]) · say(str) · wait(seconds)
EMOTES: dict[str, list[dict[str, Any]]] = {
    "happy": [
        {"face": "happy", "leds": ["yellow", 0.8]},
        {"head": [20, 8], "wait": 0.25},
        {"head": [-20, 8], "wait": 0.25},
        {"head": [0, 0]},
    ],
    "love": [
        {"face": "happy", "leds": ["magenta", 0.9]},
        {"head": [0, -8], "wait": 0.3},
        {"head": [0, 4]},
    ],
    "sad": [
        {"face": "sad", "leds": ["blue", 0.2]},
        {"head": [0, -14], "wait": 0.4},
        {"head": [0, 0]},
    ],
    "surprised": [
        {"face": "doubt", "leds": ["white", 1.0]},
        {"head": [0, 12], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "yes": [
        {"face": "happy"},
        {"head": [0, 12], "wait": 0.2},
        {"head": [0, -12], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "no": [
        {"face": "doubt"},
        {"head": [22, 0], "wait": 0.2},
        {"head": [-22, 0], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "curious": [
        {"face": "doubt"},
        {"head": [16, 6], "wait": 0.3},
        {"head": [-16, 6], "wait": 0.3},
        {"head": [0, 0]},
    ],
    "sleepy": [
        {"face": "sleepy", "leds": ["amber", 0.1]},
        {"head": [0, -10]},
    ],
    "wake": [
        {"face": "neutral", "leds": ["white", 0.4]},
        {"head": [0, 8], "wait": 0.2},
        {"head": [0, 0]},
    ],
    "fistbump": [
        {"face": "happy"},
        {"head": [0, 12], "wait": 0.15},
        {"leds": ["green", 1.0]},
        {"say": "Boom!"},
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
