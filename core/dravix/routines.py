"""Routines — named macros: a sequence of robot action steps run on demand.

A routine is a list of steps; each step may set the face, LEDs, head, play an emote, speak,
activate a mode, or wait. Capability-guarded, so it runs on any backend.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .dal.base import CAP_FACE, CAP_HEAD, CAP_LEDS, CAP_SAY, RobotController
from .emotes import play_emote
from .logging import get_logger

if TYPE_CHECKING:
    from .modes import ModeEngine

log = get_logger("routines")


async def run_routine(
    controller: RobotController, steps: list[dict[str, Any]], engine: "ModeEngine | None" = None
) -> None:
    for step in steps or []:
        try:
            if step.get("face") and controller.supports(CAP_FACE):
                await controller.set_face(step["face"])
            if step.get("leds") and controller.supports(CAP_LEDS):
                leds = step["leds"]
                await controller.set_leds(leds.get("color", "white"), float(leds.get("brightness", 1.0)))
            if step.get("head") and controller.supports(CAP_HEAD):
                yaw, pitch = step["head"]
                await controller.move_head(float(yaw), float(pitch))
            if step.get("emote"):
                await play_emote(controller, step["emote"])
            if step.get("say") and controller.supports(CAP_SAY):
                await controller.say(str(step["say"]))
            if step.get("activate_mode") and engine is not None:
                await engine.activate(step["activate_mode"])
            if step.get("wait"):
                await asyncio.sleep(min(float(step["wait"]), 10.0))
        except Exception as exc:  # noqa: BLE001 — one bad step shouldn't abort the routine
            log.warning("routine step failed: %s", exc)
