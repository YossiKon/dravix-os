"""Robot driver that controls the StackChan through Home Assistant entities/services.

Use this when the robot is exposed to HA (e.g. ESPHome entities for servos/LEDs, a TTS
target for speech). The concrete entity_ids depend on your HA setup, so they are supplied
via the ``entities`` map and validated against discovery. This is a working skeleton; the
exact service calls are finalized in Phase 1 once discovery reports your entities.
"""
from __future__ import annotations

import asyncio
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


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    """Parse ``#rrggbb`` → (r, g, b); None for a bare colour name so the caller falls back."""
    s = (value or "").strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


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
        # The head servos share ONE serial bus (SCS9009). Two writes too close together get
        # dropped (HA 500) — so every number write is serialized behind a lock and spaced out.
        self._bus_lock = asyncio.Lock()
        self._last_bus_write = 0.0

    def set_entities(self, entities: dict[str, str]) -> None:
        """Live-swap the HA entity map (from the dashboard). Clears cached number ranges."""
        self._entities = entities or {}
        self._num_meta.clear()

    def set_calibration(self, calibration: dict[str, Any]) -> None:
        self._calib = calibration or {}

    async def robot_health(self) -> dict[str, Any]:
        """The robot's own ESPHome debug diagnostics — Heap Free / Largest Block / Loop Time /
        PSRAM Free / Reset Reason / Uptime / WiFi — read straight off HA. No extra load on the
        robot: those sensors already publish on their own interval; we just read the last value.
        Matched by entity-id suffix so a device rename never breaks it."""
        try:
            states = await self._ha.states()
        except Exception as exc:  # noqa: BLE001 — HA hiccup; empty → dashboard shows "—"
            log.debug("robot_health: state fetch failed: %s", exc)
            return {}
        want = {  # entity-id suffix → our key
            "heap_free": "heap_free",
            "heap_largest_block": "heap_block",
            "loop_time": "loop_time",
            "psram_free": "psram_free",
            "reset_reason": "reset_reason",
            "uptime": "uptime",
            "wifi_signal": "wifi",
        }
        out: dict[str, Any] = {}
        for st in states:
            eid = str(st.get("entity_id", ""))
            if not eid.startswith("sensor."):
                continue
            for suffix, key in want.items():
                if key not in out and eid.endswith("_" + suffix):
                    out[key] = st.get("state")
        return out

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

    async def set_mode(self, mode: str) -> None:
        """Set the robot's power mode (awake | busy | sleep) via its ``mode_select`` entity."""
        sel = self._entities.get("mode_select")
        if not sel:
            raise NotImplementedError("no mode_select entity configured")
        await self._ha.call_service(
            "select", "select_option", {"entity_id": sel, "option": mode}
        )

    def _accessory_eid(self) -> str | None:
        """The firmware's ``face_accessory`` select sits on the same device as the Face select,
        so we derive it: select.X_face -> select.X_face_accessory (no extra config needed)."""
        face = self._entities.get("face_select")
        return f"{face}_accessory" if face else None

    async def set_accessory(self, option: str) -> None:
        """Put a cosmetic (glasses / hat / …) on the face, or 'None' to clear it."""
        sel = self._accessory_eid()
        if not sel:
            raise NotImplementedError("no face_select entity configured")
        await self._ha.call_service(
            "select", "select_option", {"entity_id": sel, "option": option}
        )

    async def accessory_current(self) -> str | None:
        """The accessory shown now (to highlight it in the dashboard), or None if unknown."""
        sel = self._accessory_eid()
        if not sel:
            return None
        try:
            return (await self._ha.get_state(sel)).get("state")
        except Exception:  # noqa: BLE001 — best-effort; the picker just won't pre-highlight
            return None

    async def set_background(self, option: str) -> None:
        """Set the themed backdrop behind the face (select.X_face -> select.X_face_background)."""
        face = self._entities.get("face_select")
        if not face:
            raise NotImplementedError("no face_select entity configured")
        await self._ha.call_service(
            "select", "select_option", {"entity_id": f"{face}_background", "option": option}
        )

    async def background_current(self) -> str | None:
        face = self._entities.get("face_select")
        if not face:
            return None
        try:
            return (await self._ha.get_state(f"{face}_background")).get("state")
        except Exception:  # noqa: BLE001 — best-effort highlight
            return None

    async def mode_options(self) -> list[str] | None:
        """The mode select's REAL options (from its HA attributes), or None if unknown —
        lets the API report what the firmware actually accepts instead of a guessed set."""
        sel = self._entities.get("mode_select")
        if not sel:
            return None
        try:
            attrs = (await self._ha.get_state(sel)).get("attributes", {})
        except Exception:  # noqa: BLE001 — unknown, fall back to the static set
            return None
        opts = attrs.get("options")
        return [str(o) for o in opts] if isinstance(opts, list) and opts else None

    async def _num_range(
        self, entity_id: str
    ) -> tuple[float | None, float | None, float | None]:
        """Return (min, max, step) for a number entity (from its HA attributes).

        Only a SUCCESSFUL lookup (real min/max) is cached — a robot that's offline/unavailable
        must not poison the cache with (None, None, None), or the head would stay dead after
        it comes back online. Failed lookups are simply retried on the next call."""
        meta = self._num_meta.get(entity_id)
        if meta is not None:
            return meta
        try:
            attrs = (await self._ha.get_state(entity_id)).get("attributes", {})
            meta = (attrs.get("min"), attrs.get("max"), attrs.get("step"))
        except Exception:  # noqa: BLE001 — best effort; use the raw value
            return (None, None, None)
        if meta[0] is not None and meta[1] is not None:
            self._num_meta[entity_id] = meta
        return meta

    # The head servos are on a serial servo bus (SCS9009). A write that arrives too soon after
    # another is dropped and HA returns a 500 — so writes are serialized behind a lock, spaced
    # by at least _MIN_BUS_SPACING, and retried. Spacing BEFORE the first attempt (not just
    # retrying after a failure) is what fixes two-writes-per-move_head reliably.
    _SET_ATTEMPTS = 3
    _SET_RETRY_DELAY = 0.3
    _MIN_BUS_SPACING = 0.3

    async def _set_number_value(self, entity_id: str, value: float) -> None:
        async with self._bus_lock:
            loop = asyncio.get_running_loop()
            gap = self._MIN_BUS_SPACING - (loop.time() - self._last_bus_write)
            if gap > 0:
                await asyncio.sleep(gap)
            last_exc: Exception | None = None
            for attempt in range(self._SET_ATTEMPTS):
                try:
                    await self._ha.call_service(
                        "number", "set_value", {"entity_id": entity_id, "value": value}
                    )
                    self._last_bus_write = loop.time()
                    return
                except Exception as exc:  # noqa: BLE001 — transient serial-bus NAK, retry
                    last_exc = exc
                    if attempt < self._SET_ATTEMPTS - 1:
                        log.debug(
                            "number.set_value %s=%s failed (%s), retrying", entity_id, value, exc
                        )
                        await asyncio.sleep(self._SET_RETRY_DELAY)
            self._last_bus_write = loop.time()
            assert last_exc is not None
            raise last_exc

    async def _set_head_axis(self, axis: str, entity_id: str, value: float) -> None:
        """Map a NORMALISED head command (-1..1, 0 = look straight) to a servo value.

        Rebuilt to be dead simple and always in range: read the servo's real min/max/step from
        HA (authoritative), take the calibrated ``center`` (the servo value that looks straight —
        set via 'Set as HOME', else the range midpoint), then move a fraction of the *available
        travel* toward max (positive) or min (negative). ``invert`` flips the direction. The
        result is always clamped to the real range, so it can never emit an out-of-range value
        (that out-of-range write is what made move_head 500). No calibration min/max to get wrong.
        """
        lo, hi, step = await self._num_range(entity_id)
        if lo is None or hi is None:
            return  # unknown servo range — do nothing rather than risk a bad write
        lo, hi = float(lo), float(hi)
        cal = (self._calib or {}).get(axis, {}) or {}
        center = float(cal["center"]) if cal.get("center") is not None else (lo + hi) / 2.0
        center = max(lo, min(hi, center))
        pos = -float(value) if cal.get("invert") else float(value)
        pos = max(-1.0, min(1.0, pos))
        out = center + pos * ((hi - center) if pos >= 0 else (center - lo))
        out = max(lo, min(hi, out))
        if step:
            out = round(out / float(step)) * float(step)
            out = max(lo, min(hi, out))
        await self._set_number_value(entity_id, out)

    async def move_head(self, yaw: float, pitch: float, speed: float = 1.0) -> None:
        yaw_e, pitch_e = self._entities.get("head_yaw"), self._entities.get("head_pitch")
        if not (yaw_e and pitch_e):
            raise NotImplementedError("no head servo entities configured")
        # ASLEEP = DEAD STILL. Every dravix-side mover (welcome, surprises, emotes, mood,
        # follow…) funnels through here — while the robot reports sleep/screensaver, head
        # commands are silently dropped so nothing can twitch it. Wake it first.
        state_e = self._entities.get("state_sensor")
        if state_e:
            try:
                st = str((await self._ha.get_state(state_e)).get("state") or "").strip().lower()
                if st in ("sleep", "screensaver"):
                    log.debug("move_head skipped — robot is %s", st)
                    return
            except Exception:  # noqa: BLE001 — can't read the state → don't block movement
                pass
        # Both writes go through _set_number_value, which serializes + spaces them on the
        # bus. PITCH FIRST on purpose: the firmware's pitch entity stamps its "commanded
        # move" marker — writing yaw first let the hand-turn detector see an unmarked yaw
        # jump and mistake the first dravix move after a long stillness for a hand.
        await self._set_head_axis("pitch", pitch_e, pitch)
        await self._set_head_axis("yaw", yaw_e, yaw)

    async def read_head_raw(self) -> dict[str, float | None]:
        """Read the servos' current raw angle values (for 'set current position as home')."""
        out: dict[str, float | None] = {}
        for axis, role in (("yaw", "head_yaw"), ("pitch", "head_pitch")):
            ent = self._entities.get(role)
            val: float | None = None
            if ent:
                try:
                    val = float((await self._ha.get_state(ent)).get("state"))
                except Exception:  # noqa: BLE001
                    val = None
            out[axis] = val
        return out

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

    async def get_text(self, role: str) -> str | None:
        """Read a mapped entity's state as text (e.g. the live state / last-heard sensors)."""
        ent = self._entities.get(role)
        if not ent:
            return None
        try:
            st = await self._ha.get_state(ent)
            value = st.get("state")
        except Exception:  # noqa: BLE001
            return None
        if value in (None, "unknown", "unavailable"):
            return None
        return str(value)

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
        await self._set_number_value(ent, value)

    async def say(self, text: str, voice: str | None = None) -> None:
        # Mirror whatever is spoken into the robot's on-screen speech bubble (like the
        # original app's text messages). Best-effort — older firmware has no such slot.
        bubble = self._entities.get("bubble_text")
        if bubble:
            from ..bidi import for_robot

            try:
                # the DISPLAYED bubble gets RTL-reordered (the robot's screen has no BIDI);
                # TTS below still receives the untouched logical text.
                # truncate the LOGICAL text, then reorder — visual-order Hebrew keeps its
                # logical start at the string END, so reorder-then-truncate chopped the
                # BEGINNING of the sentence instead of its tail.
                await self._ha.call_service(
                    "text", "set_value", {"entity_id": bubble, "value": for_robot(text[:120])}
                )
            except Exception:  # noqa: BLE001 — showing text must never block speaking
                pass
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
        data: dict[str, Any] = {
            "entity_id": engine, "media_player_entity_id": media, "message": text,
        }
        if voice:
            # tts.speak forwards engine options; piper/cloud/... pick the voice from here.
            data["options"] = {"voice": voice}
        await self._ha.call_service("tts", "speak", data)

    async def set_leds(self, color: str, brightness: float = 1.0) -> None:
        light = self._entities.get("led_light")
        if not light:
            raise NotImplementedError("no led_light entity configured")
        if color in ("off", "none", "") or brightness <= 0:
            await self._ha.call_service("light", "turn_off", {"entity_id": light})
            return
        data: dict[str, Any] = {"entity_id": light, "brightness_pct": int(brightness * 100)}
        # A "#rrggbb" value (used by the agent status lamp's colour-blind-safe palette) is an
        # rgb_color; a bare name ("blue", "orange") is a color_name — HA rejects a hex as name.
        rgb = _hex_to_rgb(color)
        if rgb is not None:
            data["rgb_color"] = list(rgb)
        else:
            data["color_name"] = color
        await self._ha.call_service("light", "turn_on", data)

    async def set_agent_text(self, text: str) -> None:
        """Write the persistent AI-agent badge on the robot's face (fw v20+ ``t_agent`` slot).

        Best-effort — firmware without the slot simply has no such entity, so we no-op."""
        ent = self._entities.get("agent_text")
        if not ent:
            return
        from ..bidi import for_robot

        try:
            # truncate logical, then reorder (see say() — order matters for Hebrew)
            await self._ha.call_service("text", "set_value", {"entity_id": ent, "value": for_robot(text[:32])})
        except Exception:  # noqa: BLE001 — a status badge must never break the caller
            pass

    async def set_permission(self, text: str) -> None:
        """Show/clear the on-robot Approve/Reject prompt (fw v21+ ``t_permission`` slot).

        Non-empty text pops the buttons; "" hides them. Best-effort — no-op without the slot."""
        ent = self._entities.get("permission_text")
        if not ent:
            return
        from ..bidi import for_robot

        try:
            # truncate logical, then reorder (see say() — order matters for Hebrew)
            await self._ha.call_service("text", "set_value", {"entity_id": ent, "value": for_robot(text[:80])})
        except Exception:  # noqa: BLE001 — the on-robot prompt must never break the caller
            pass

    async def take_photo(self) -> bytes | None:
        cam = self._entities.get("camera")
        if not cam:
            raise NotImplementedError("no camera entity configured")
        return await self._ha.camera_snapshot(cam)

    async def listen(self, timeout: float = 7.0) -> str | None:
        raise NotImplementedError("listen over HA uses the Assist pipeline (Phase 4)")

    async def show_image(self, image: bytes) -> None:
        raise NotImplementedError("showing an image over HA needs a custom display entity")

    async def is_private(self) -> bool:
        """True while the robot's Privacy-mode switch is ON (camera endpoints get blocked)."""
        ent = self._entities.get("privacy_switch")
        if not ent:
            return False
        try:
            return (await self._ha.get_state(ent)).get("state") == "on"
        except Exception:  # noqa: BLE001 — unreadable switch must not break the camera
            return False

    async def set_privacy(self, private: bool) -> None:
        ent = self._entities.get("privacy_switch")
        if not ent:
            raise NotImplementedError("no privacy_switch entity configured")
        await self._ha.call_service(
            "switch", "turn_on" if private else "turn_off", {"entity_id": ent}
        )

    async def show_image_url(self, url: str) -> None:
        """Show an image on the robot's screen by URL — the firmware's "Show image URL"
        text slot downloads it and displays it full-screen (empty string = back to face)."""
        ent = self._entities.get("image_url_text")
        if not ent:
            raise NotImplementedError("no image_url_text entity configured")
        await self._ha.call_service("text", "set_value", {"entity_id": ent, "value": url})

    async def get_status(self) -> dict[str, Any]:
        return {"driver": self.name, "entities": self._entities}
