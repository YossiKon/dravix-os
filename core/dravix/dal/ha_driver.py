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

    def __init__(
        self,
        ha: HomeAssistant,
        entities: dict[str, str] | None = None,
        calibration: dict[str, Any] | None = None,
    ) -> None:
        self._ha = ha
        self._entities = entities or {}
        # Per-axis head calibration: {yaw:{center,min,max,invert}, pitch:{...}}. Any field may be
        # None → fall back to the servo entity's own min/max (center defaults to their midpoint).
        self._calib = calibration or {}
        # Cache each number entity's (min, max, step) so we clamp + snap values to the
        # device's real range — ESPHome rejects out-of-range / off-step values with a 500.
        self._num_meta: dict[str, tuple[float | None, float | None, float | None]] = {}

    def set_entities(self, entities: dict[str, str]) -> None:
        """Live-swap the HA entity map (from the dashboard). Clears cached number ranges."""
        self._entities = entities or {}
        self._num_meta.clear()

    def set_calibration(self, calibration: dict[str, Any]) -> None:
        self._calib = calibration or {}

    async def connect(self) -> None:
        if not await self._ha.ping():
            raise ConnectionError("Home Assistant not reachable / token invalid")
        log.info("HA robot driver ready (entities: %s)", self._entities)

    async def close(self) -> None:
        # The shared HomeAssistant client is closed by the app, not here.
        return None

    async def capabilities(self) -> set[str]:
        caps: set[str] = set()
        tts = self._entities.get("tts_engine", "")
        media = self._entities.get("media_player")
        # Speech works either via tts.speak (needs a tts.* engine + a media_player) or via
        # assist_satellite.announce (the satellite plays on its own speaker — no media_player).
        if (tts.startswith("assist_satellite.")) or (media and tts):
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

    async def _num_range(
        self, entity_id: str
    ) -> tuple[float | None, float | None, float | None]:
        """Return (min, max, step) for a number entity, cached (from its HA attributes)."""
        meta = self._num_meta.get(entity_id)
        if meta is None:
            try:
                attrs = (await self._ha.get_state(entity_id)).get("attributes", {})
                meta = (attrs.get("min"), attrs.get("max"), attrs.get("step"))
            except Exception:  # noqa: BLE001 — best effort; use the raw value
                meta = (None, None, None)
            self._num_meta[entity_id] = meta
        return meta

    async def _set_head_axis(self, axis: str, entity_id: str, value: float) -> None:
        """Map a dravix head command (degrees, 0 = look straight) to a calibrated servo value.

        dravix sends head angles centered on 0. The servo value is ``center + command`` where the
        user calibrates each axis from the dashboard: ``center`` (the servo value that looks
        straight ahead — fixes a head that 'falls' down/up), ``invert`` (flip direction), and
        optional ``min``/``max`` travel limits (default to the entity's own range). With no
        calibration this reduces to the old behaviour (center = the servo's midpoint).
        """
        lo_e, hi_e, step = await self._num_range(entity_id)
        cal = (self._calib or {}).get(axis, {}) or {}
        lo = cal.get("min") if cal.get("min") is not None else lo_e
        hi = cal.get("max") if cal.get("max") is not None else hi_e
        have_range = lo is not None and hi is not None
        if cal.get("center") is not None:
            center = float(cal["center"])
        elif have_range:
            center = (float(lo) + float(hi)) / 2.0  # servo midpoint (old default)
        else:
            center = 0.0
        cmd = -float(value) if cal.get("invert") else float(value)
        out = center + cmd
        if have_range:
            out = max(float(lo), min(float(hi), out))
        if step:
            out = round(out / float(step)) * float(step)
        await self._ha.call_service(
            "number", "set_value", {"entity_id": entity_id, "value": out}
        )

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        yaw_e, pitch_e = self._entities.get("head_yaw"), self._entities.get("head_pitch")
        if not (yaw_e and pitch_e):
            raise NotImplementedError("no head servo entities configured")
        await self._set_head_axis("yaw", yaw_e, yaw)
        await self._set_head_axis("pitch", pitch_e, pitch)

    async def get_number(self, role: str) -> float | None:
        """Read a mapped number entity's current value (e.g. screensaver_number)."""
        ent = self._entities.get(role)
        if not ent:
            return None
        try:
            st = await self._ha.get_state(ent)
            return float(st.get("state"))
        except Exception:  # noqa: BLE001
            return None

    async def set_number(self, role: str, value: float) -> None:
        """Set a mapped number entity (clamped/snapped to its range)."""
        ent = self._entities.get(role)
        if not ent:
            raise NotImplementedError(f"no {role} entity configured")
        lo, hi, step = await self._num_range(ent)
        if lo is not None and hi is not None:
            value = max(float(lo), min(float(hi), float(value)))
        if step:
            value = round(value / float(step)) * float(step)
        await self._ha.call_service("number", "set_value", {"entity_id": ent, "value": value})

    async def say(self, text: str, voice: str | None = None) -> None:
        engine = self._entities.get("tts_engine", "")
        # An assist_satellite speaks via its own announce service (no separate media_player).
        if engine.startswith("assist_satellite."):
            await self._ha.call_service(
                "assist_satellite", "announce", {"entity_id": engine, "message": text}
            )
            return
        media = self._entities.get("media_player")
        if not media:
            raise NotImplementedError("no media_player entity configured for TTS")
        if not engine:
            raise NotImplementedError(
                "set the TTS entity to your HA TTS engine (e.g. tts.piper) or an "
                "assist_satellite.* to enable speech"
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
