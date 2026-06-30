"""Robot driver that controls the StackChan through Home Assistant entities/services.

Use this when the robot is exposed to HA (e.g. ESPHome entities for servos/LEDs, a TTS
target for speech). The concrete entity_ids depend on your HA setup, so they are supplied
via the ``entities`` map and validated against discovery. This is a working skeleton; the
exact service calls are finalized in Phase 1 once discovery reports your entities.
"""
from __future__ import annotations

from typing import Any

from ..integrations.homeassistant import HomeAssistant
from ..logging import get_logger
from .base import (
    CAP_FACE,
    CAP_HEAD,
    CAP_LEDS,
    CAP_PHOTO,
    CAP_SAY,
    Expression,
    RobotDriver,
)

log = get_logger("dal.ha")


class HARobotDriver(RobotDriver):
    name = "ha"
    transport = "homeassistant"

    def __init__(self, ha: HomeAssistant, entities: dict[str, str] | None = None) -> None:
        self._ha = ha
        self._entities = entities or {}
        # Cache each number entity's (min, max, step) so we clamp + snap values to the
        # device's real range — ESPHome rejects out-of-range / off-step values with a 500.
        self._num_meta: dict[str, tuple[float | None, float | None, float | None]] = {}

    async def connect(self) -> None:
        if not await self._ha.ping():
            raise ConnectionError("Home Assistant not reachable / token invalid")
        log.info("HA robot driver ready (entities: %s)", self._entities)

    async def close(self) -> None:
        # The shared HomeAssistant client is closed by the app, not here.
        return None

    async def capabilities(self) -> set[str]:
        caps: set[str] = set()
        if self._entities.get("media_player") and self._entities.get("tts_engine"):
            caps.add(CAP_SAY)
        if self._entities.get("led_light"):
            caps.add(CAP_LEDS)
        if self._entities.get("head_yaw") and self._entities.get("head_pitch"):
            caps.add(CAP_HEAD)
        if self._entities.get("face_select"):
            caps.add(CAP_FACE)
        if self._entities.get("camera"):
            caps.add(CAP_PHOTO)
        return caps

    async def set_face(self, expression: Expression) -> None:
        # The ESPHome firmware exposes a `select` entity whose options are the expression
        # names (neutral|happy|sad|angry|sleepy|doubt). Setting it redraws the face.
        sel = self._entities.get("face_select")
        if not sel:
            raise NotImplementedError("no face_select entity configured")
        value = expression.value if isinstance(expression, Expression) else str(expression)
        await self._ha.call_service(
            "select", "select_option", {"entity_id": sel, "option": value}
        )

    async def _set_number(self, entity_id: str, value: float) -> None:
        """Set a number entity, clamped to its min/max and snapped to its step.

        The StackChan servos are e.g. yaw -164..164, pitch 0..90, step 5 — sending an
        out-of-range or off-step value makes ESPHome/HA return a 500. Clamp + snap first.
        """
        meta = self._num_meta.get(entity_id)
        if meta is None:
            try:
                attrs = (await self._ha.get_state(entity_id)).get("attributes", {})
                meta = (attrs.get("min"), attrs.get("max"), attrs.get("step"))
            except Exception:  # noqa: BLE001 — best effort; use the raw value
                meta = (None, None, None)
            self._num_meta[entity_id] = meta
        lo, hi, step = meta
        if lo is not None:
            value = max(float(lo), value)
        if hi is not None:
            value = min(float(hi), value)
        if step:
            value = round(value / float(step)) * float(step)
        await self._ha.call_service("number", "set_value", {"entity_id": entity_id, "value": value})

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        yaw_e, pitch_e = self._entities.get("head_yaw"), self._entities.get("head_pitch")
        if not (yaw_e and pitch_e):
            raise NotImplementedError("no head servo entities configured")
        await self._set_number(yaw_e, yaw)
        await self._set_number(pitch_e, pitch)

    async def say(self, text: str, voice: str | None = None) -> None:
        media = self._entities.get("media_player")
        if not media:
            raise NotImplementedError("no media_player entity configured for TTS")
        engine = self._entities.get("tts_engine")
        if not engine:
            raise NotImplementedError(
                "set robot_entity_tts to your HA TTS engine (e.g. tts.piper) to enable speech"
            )
        # tts.speak: entity_id = the TTS engine, media_player_entity_id = the speaker.
        await self._ha.call_service(
            "tts",
            "speak",
            {"entity_id": engine, "media_player_entity_id": media, "message": text},
        )

    async def set_leds(self, color: str, brightness: float = 1.0) -> None:
        light = self._entities.get("led_light")
        if not light:
            raise NotImplementedError("no led_light entity configured")
        await self._ha.call_service(
            "light",
            "turn_on",
            {"entity_id": light, "color_name": color, "brightness_pct": int(brightness * 100)},
        )

    async def take_photo(self) -> bytes | None:
        cam = self._entities.get("camera")
        if not cam:
            raise NotImplementedError("no camera entity configured")
        return await self._ha.camera_snapshot(cam)

    async def listen(self, timeout: float = 7.0) -> str | None:
        raise NotImplementedError("listen over HA uses the Assist pipeline (Phase 4)")

    async def show_image(self, image: bytes) -> None:
        raise NotImplementedError("showing an image over HA needs a custom display entity")

    async def get_status(self) -> dict[str, Any]:
        return {"driver": self.name, "entities": self._entities}
