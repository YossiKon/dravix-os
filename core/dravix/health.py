"""Robot health — why does it reboot, and what did it look like just before?

The firmware publishes the answer to every reboot as plain Home Assistant sensors: **Reset
Reason** (the ESP's own verdict), **Heap Free / Heap Largest Block / PSRAM Free** (memory),
**Loop Time** (how starved the main loop is) and **Uptime**. Nobody reads them. This module
does: it samples them, notices a reboot when uptime drops, records the reason together with
the last memory/loop picture seen *before* the drop, classifies it into something a person can
act on, and keeps a small ring of past reboots. It can also backfill from HA's recorder history,
so the first look already shows yesterday's crashes.

Pure functions (``classify``, ``detect``, ``parse_history``) do the thinking; ``RobotHealth``
holds the state and does the I/O. Polled from the existing 5s pusher every 6th tick.
"""
from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

from .logging import get_logger

if TYPE_CHECKING:
    from .events import EventBus
    from .integrations.homeassistant import HomeAssistant
    from .store import Store

log = get_logger("health")

ROLES = ("reset_reason", "heap_free", "heap_largest_block", "loop_time", "psram_free",
         "uptime", "firmware_version")
RING_MAX = 50
LOOP_WARN_MS = 100.0        # a main loop slower than this, sustained, starves the display + voice
HEAP_WARN_BYTES = 30_000    # internal heap below this = the next allocation may be the crash
_UNAVAILABLE = ("unavailable", "unknown", "", None)


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def classify(reason: str | None) -> dict[str, str]:
    """The ESP's reset reason → a kind and a plain-language verdict (he/en).

    The strings are what ESPHome's ``debug`` component publishes (esp_reset_reason names):
    "Software Reset CPU", "Task Watchdog", "Interrupt Watchdog", "Software Watchdog",
    "Brownout", "Power On Reset", "External System Reset", "Deep-Sleep Wake", "Exception",
    "Unknown" … case and punctuation vary between cores, so match loosely."""
    r = (reason or "").strip().lower()
    if not r:
        return {"kind": "none", "he": "אין עדיין סיבת אתחול", "en": "No reset reason yet"}
    if "watchdog" in r or "wdt" in r:
        return {"kind": "watchdog",
                "he": "הלולאה הראשית נחנקה (watchdog) — משהו מצייר/מחשב יותר מדי; ראה Loop Time",
                "en": "The main loop starved (watchdog) — something draws or computes too much; see Loop Time"}
    if "brownout" in r:
        return {"kind": "power", "he": "נפילת מתח (brownout) — מטען/כבל חלשים",
                "en": "Voltage sag (brownout) — a weak charger or cable"}
    if "panic" in r or "exception" in r or "prohibited" in r or "abort" in r or "assert" in r:
        return {"kind": "bug",
                "he": "קריסת תוכנה (panic) — באג בקושחה; צריך את הלוג של ESPHome מיד אחרי האתחול",
                "en": "A software crash (panic) — a firmware bug; the ESPHome log right after boot is needed"}
    if "deep" in r and "sleep" in r:
        return {"kind": "sleep", "he": "יקיצה משינה עמוקה — לא קריסה", "en": "Deep-sleep wake — not a crash"}
    if "software" in r:
        return {"kind": "software",
                "he": "אתחול יזום (OTA / כפתור Reboot / קריסה שהתאוששה) — אם לא ביקשת אותו, זה panic",
                "en": "A commanded restart (OTA / Reboot button / a recovered crash) — if you didn't ask for it, treat as a panic"}
    if "power" in r or "external" in r or "unknown" in r or "poweron" in r:
        return {"kind": "power",
                "he": "המכשיר איבד חשמל לרגע (Power On / External) — עם גלאי ה-brownout כבוי זו הצורה שנפילת מתח נראית בה: מטען 5V/2A+ וכבל קצר ועבה",
                "en": "The device lost power for a moment (Power On / External) — with the brownout detector off this is what a voltage sag looks like: a 5V/2A+ charger and a short, thick cable"}
    return {"kind": "other", "he": f"סיבה: {reason}", "en": f"Reason: {reason}"}


def detect(prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any] | None:
    """Pure: did the robot reboot between two samples? A reboot is UPTIME going DOWN.
    (Reset Reason alone can't tell — five identical watchdog reboots never change it.)
    Samples with an unavailable uptime are skipped: that's the robot MID-reboot; the reason
    arrives with the next good sample. Returns the reboot record or None."""
    up = cur.get("uptime")
    if up is None or prev is None or prev.get("uptime") is None:
        return None
    if up >= prev["uptime"]:
        return None
    reason = cur.get("reset_reason") or prev.get("reset_reason") or ""
    return {
        "at": cur.get("at") or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "reason": reason,
        **classify(reason),
        # the last picture BEFORE the drop is the pre-crash state
        "heap_free_before": prev.get("heap_free"),
        "heap_block_before": prev.get("heap_largest_block"),
        "loop_time_before": prev.get("loop_time"),
        "psram_free_before": prev.get("psram_free"),
        "uptime_before": prev.get("uptime"),
        "firmware": cur.get("firmware_version") or prev.get("firmware_version"),
    }


def sample_from_states(states: list[dict] | dict[str, dict], entities: dict[str, str]) -> dict[str, Any]:
    """Pure: one health sample from a HA state dump, given the role → entity_id map."""
    by_id = states if isinstance(states, dict) else {s.get("entity_id", ""): s for s in states}
    out: dict[str, Any] = {"at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    for role in ROLES:
        eid = entities.get(role)
        st = (by_id.get(eid) or {}).get("state") if eid else None
        if st in _UNAVAILABLE:
            out[role] = None
        elif role in ("reset_reason", "firmware_version"):
            out[role] = str(st)
        else:
            out[role] = _num(st)
    return out


def parse_history(rows: list[list[dict]], entities: dict[str, str]) -> list[dict[str, Any]]:
    """Pure: HA recorder history (``/api/history/period`` → one list per entity, each a list
    of ``{entity_id, state, last_changed}``) → the reboots it contains, oldest first. Walks the
    uptime series for drops and pairs each with the reset reason in force right after it."""
    ups: list[tuple[str, float]] = []
    reasons: list[tuple[str, str]] = []
    up_id, rr_id = entities.get("uptime"), entities.get("reset_reason")
    for series in rows or []:
        for row in series:
            eid = row.get("entity_id"); st = row.get("state"); when = row.get("last_changed") or row.get("last_updated") or ""
            if eid == up_id and st not in _UNAVAILABLE and _num(st) is not None:
                ups.append((when, _num(st)))
            elif eid == rr_id and st not in _UNAVAILABLE:
                reasons.append((when, str(st)))
    ups.sort(); reasons.sort()
    found: list[dict[str, Any]] = []
    prev: tuple[str, float] | None = None
    for when, up in ups:
        if prev is not None and up < prev[1]:
            # the reason published at/after the drop, else the last one before it
            after = [r for t, r in reasons if t >= when]
            before = [r for t, r in reasons if t < when]
            reason = (after[0] if after else (before[-1] if before else ""))
            found.append({"at": when, "reason": reason, **classify(reason), "uptime_before": prev[1],
                          "heap_free_before": None, "loop_time_before": None, "from_history": True})
        prev = (when, up)
    return found


class RobotHealth:
    """Samples the diagnostic sensors, records reboots, answers the dashboard."""

    def __init__(self, ha: "HomeAssistant | None", store: "Store", bus: "EventBus | None") -> None:
        self._ha, self._store, self._bus = ha, store, bus
        self._prev: dict[str, Any] | None = None
        self.last: dict[str, Any] = {}
        self._backfilled = False

    def _entities(self, discovered: dict[str, str]) -> dict[str, str]:
        return {r: discovered[r] for r in ROLES if discovered.get(r)}

    async def backfill(self, discovered: dict[str, str], hours: int = 24) -> int:
        """Read yesterday's reboots from HA's recorder — once. Returns how many were new."""
        if self._backfilled or self._ha is None:
            return 0
        self._backfilled = True
        ents = self._entities(discovered)
        if not ents.get("uptime"):
            return 0
        try:
            rows = await self._ha.history([e for r, e in ents.items() if r in ("uptime", "reset_reason")], hours)
        except Exception as exc:  # noqa: BLE001 — recorder may be off / HA old; live sampling still works
            log.debug("health backfill skipped: %s", exc)
            return 0
        known = {r.get("at") for r in self._store.reboots()}
        new = [r for r in parse_history(rows, ents) if r["at"] not in known]
        for r in new:
            self._store.add_reboot(r, RING_MAX)
        if new:
            log.info("health: backfilled %d reboot(s) from HA history", len(new))
        return len(new)

    async def sample(self, discovered: dict[str, str], states: list[dict] | None = None) -> dict[str, Any] | None:
        """One tick: read the sensors, record a reboot if uptime dropped. Returns the reboot
        record when one was detected (also published as ``robot.rebooted``)."""
        if self._ha is None:
            return None
        ents = self._entities(discovered)
        if not ents:
            return None
        if states is None:
            states = await self._ha.states()
        cur = sample_from_states(states, ents)
        self.last = cur
        event = detect(self._prev, cur)
        if cur.get("uptime") is not None:      # never let a mid-reboot sample become "prev"
            self._prev = cur
        if event:
            self._store.add_reboot(event, RING_MAX)
            log.warning("health: robot rebooted — %s (%s)", event.get("reason"), event.get("kind"))
            if self._bus is not None:
                try:
                    await self._bus.publish("robot.rebooted", **{k: v for k, v in event.items() if k not in ("he", "en")})
                except Exception:  # noqa: BLE001 — the record is saved either way
                    pass
        return event

    def snapshot(self) -> dict[str, Any]:
        """What the dashboard shows: live numbers with thresholds, the 24h count, the ring."""
        ring = self._store.reboots()
        now = _dt.datetime.now(_dt.timezone.utc)
        day = 0
        for r in ring:
            try:
                t = _dt.datetime.fromisoformat(str(r.get("at")).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=_dt.timezone.utc)
                if (now - t).total_seconds() <= 86400:
                    day += 1
            except (TypeError, ValueError):
                continue
        last = ring[-1] if ring else None
        live = self.last or {}
        loop = live.get("loop_time"); heap = live.get("heap_free")
        return {
            "live": live,
            "warnings": {
                "loop": loop is not None and loop > LOOP_WARN_MS,
                "heap": heap is not None and heap < HEAP_WARN_BYTES,
            },
            "reboots_24h": day,
            "last_reboot": last,
            "reboots": ring[-20:],
            "thresholds": {"loop_ms": LOOP_WARN_MS, "heap_bytes": HEAP_WARN_BYTES},
        }
