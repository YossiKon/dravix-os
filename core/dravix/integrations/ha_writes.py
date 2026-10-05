"""The write gate — every ``call_service`` dravix makes passes through here.

The robot is an ESP32 whose ESPHome API handles a few writes a second at best, and every
write HA forwards to an UNAVAILABLE entity costs a "Referenced entities … are missing or not
currently available" warning in HA's log (~1,500 an hour were counted). So for writes that
SET a robot entity (text/number/select/light/switch) the gate:

a. **skips targets that are unavailable or missing** in the state mirror. The latest value
   is held for ``PENDING_TTL_S`` and delivered the moment the entity comes back (the mirror
   tells us — no polling, no retry storm); an ``unknown`` target is probed with exponential
   backoff instead of written every time;
b. **drops a repeat of our own last value while it is still in place** (or still in
   flight). It never drops a DIFFERENT value — a revert to what HA still shows is a change —
   and an outside change (a tap on the robot, a reboot wiping an optimistic slot) re-arms
   the write at once; a value the robot keeps not showing is re-asserted with exponential
   backoff. Entities whose writes are COMMANDS (``set_always_write``: the head servos —
   every pitch write stamps the firmware's "commanded move" marker — the face, the speech
   bubble, the tip, the show-image URL, the agent prompts) skip this step;
c. **rate-limits to one write per entity per ``RATE_S``** — a burst collapses to its LAST
   value, delivered when the window opens. Entities on a **lane** (the two head servos share
   one serial bus) are not coalesced: each write waits its turn on the lane, in order and
   spaced (0.3 s), exactly as the servo bus always required — so a nod isn't flattened;
d. **backs off exponentially after a failed write** (the held value is retried);
e. serialises writes that share a physical bus (lanes).

Only the ROBOT's entities are gated (``set_scope``: its discovered prefixes) — a call to
anything else in the house, or to ``all`` / several targets, passes straight through as it
always did. Voice services (``tts.speak`` / ``assist_satellite.announce`` /
``media_player.*``) at the robot only get (a), without the replay — a sentence is worth
saying now or not at all.

A skipped or deferred write returns ``[]`` — the same thing HA returned for a write it
silently dropped on an unavailable entity — and is logged at DEBUG only. A write that is
actually sent and fails still raises, exactly as before.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from ..logging import get_logger
from .ha_state import UNAVAILABLE, UNKNOWN

log = get_logger("ha.writes")

SETTERS = {
    ("text", "set_value"), ("number", "set_value"), ("select", "select_option"),
    ("light", "turn_on"), ("light", "turn_off"), ("switch", "turn_on"), ("switch", "turn_off"),
}
AVAILABILITY_ONLY = {("tts", "speak"), ("assist_satellite", "announce")}

MISSING = object()  # sentinel: HA has no such entity

RATE_S = 1.0             # (c) at most one write per entity per second
PENDING_TTL_S = 30.0     # (a) a value held for an unavailable entity expires after this
SETTLE_S = 3.0           # (b) an accepted write may take this long to show in the mirror
REASSERT_MIN_S = 5.0     # (b) first re-assert of a value the robot doesn't show
REASSERT_MAX_S = 600.0
PROBE_MIN_S = 2.0        # (a) writes to an "unknown" target: 2 s, 4 s, … 60 s apart
PROBE_MAX_S = 60.0
FAIL_MIN_S = 1.0         # (d) after a failed write: 1 s, 2 s, … 60 s
FAIL_MAX_S = 60.0

StateLookup = Callable[[str], Awaitable[Any]]   # → state dict | None (unreadable) | MISSING
Sender = Callable[[str, str, dict], Awaitable[Any]]


@dataclass
class _Lane:
    spacing: float
    retries: int
    retry_delay: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last: float = float("-inf")


@dataclass
class _Ent:
    req_seq: int = 0                 # number of the NEWEST request (older ones never win)
    last_sig: Any = None             # the last value HA accepted from us …
    last_req: tuple | None = None    # … as (domain, service, data), for shows()
    last_at: float = float("-inf")   # when we last sent (reserved before the network await)
    landed: bool = False             # the mirror has shown last_sig since we sent it
    dirty: bool = False              # … and then (or instead) something else replaced it
    reassert: float = field(default_factory=lambda: REASSERT_MIN_S)
    fail_backoff: float = 0.0
    fail_until: float = float("-inf")
    probe_backoff: float = 0.0
    probe_until: float = float("-inf")
    pending: tuple | None = None     # (domain, service, data, expires, seq)
    timer: asyncio.Task | None = None
    timer_at: float = float("inf")


def _targets(data: dict) -> list[str]:
    eid = (data or {}).get("entity_id")
    if isinstance(eid, str):
        return [e.strip() for e in eid.split(",") if e.strip()]
    if isinstance(eid, (list, tuple)):
        return [str(e) for e in eid]
    return []


def signature(domain: str, service: str, data: dict) -> tuple:
    """What a setter asks for, minus the target — two equal signatures = the same write."""
    if domain == "number":
        try:
            return (domain, float(data.get("value")))
        except (TypeError, ValueError):
            return (domain, data.get("value"))
    if domain == "text":
        return (domain, str(data.get("value", "")))
    if domain == "select":
        return (domain, str(data.get("option", "")))
    rest = tuple(sorted((k, repr(v)) for k, v in (data or {}).items() if k != "entity_id"))
    return (domain, service, rest)


def shows(domain: str, service: str, data: dict, st: dict | None) -> bool:
    """Does the mirrored state show what this setter asked for?"""
    if not isinstance(st, dict):
        return False
    state = st.get("state")
    if domain == "text":
        return state == str(data.get("value", ""))
    if domain == "number":
        try:
            step = float((st.get("attributes") or {}).get("step") or 0)
            return abs(float(state) - float(data.get("value"))) <= max(1e-6, step / 2)
        except (TypeError, ValueError):
            return False
    if domain == "select":
        return state == str(data.get("option", ""))
    if domain in ("switch", "light"):
        want = "on" if service == "turn_on" else "off"
        if state != want:
            return False
        rgb = data.get("rgb_color")
        if want == "on" and rgb is not None:
            have = (st.get("attributes") or {}).get("rgb_color")
            return have is not None and list(have) == list(rgb)
        return True
    return False


class WriteGate:
    def __init__(
        self,
        send: Sender,
        lookup: StateLookup,
        *,
        rate_s: float = RATE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send_raw = send
        self._lookup = lookup
        self._rate = rate_s
        self._clock = clock
        self._ents: dict[str, _Ent] = {}
        self._lanes: dict[str, _Lane] = {}
        self._always: set[str] = set()
        self._prefixes: tuple[str, ...] = ()
        self._scope_ids: set[str] = set()
        self.skipped = 0     # counters for /api/status — proof the gate is doing its job
        self.deferred = 0
        self.sent = 0

    # ── configuration ─────────────────────────────────────────────────────────────
    def set_scope(self, prefixes: Iterable[str], entity_ids: Iterable[str] = ()) -> None:
        """Which entities are the ROBOT's: any ``<domain>.<prefix>_…`` for these object-id
        prefixes, plus the listed ids. Everything else passes straight through."""
        self._prefixes = tuple(p + "_" for p in prefixes if p)
        self._scope_ids = {e for e in entity_ids if e}

    def set_always_write(self, entity_ids: Iterable[str]) -> None:
        """Entities whose every write is a COMMAND (re-sending the same value does
        something): never deduplicated — still availability-gated and rate-limited."""
        self._always.update(e for e in entity_ids if e)

    def set_lane(self, entity_ids: list[str], *, spacing: float, retries: int = 1,
                 retry_delay: float = 0.0) -> None:
        """Serialise writes to these entities (they share one physical bus): ``spacing``
        seconds between any two, ``retries`` attempts per write. Re-registering keeps the
        existing lane (and its lock) so a rebuilt driver can't open a second one."""
        ids = [e for e in entity_ids if e]
        lane = next((self._lanes[e] for e in ids if e in self._lanes), None)
        if lane is None:
            lane = _Lane(spacing=spacing, retries=max(1, retries), retry_delay=retry_delay)
        else:
            lane.spacing, lane.retries, lane.retry_delay = spacing, max(1, retries), retry_delay
        for eid in ids:
            self._lanes[eid] = lane

    def in_scope(self, eid: str) -> bool:
        if eid in self._scope_ids or eid in self._always or eid in self._lanes:
            return True
        object_id = eid.split(".", 1)[-1]
        return bool(self._prefixes) and object_id.startswith(self._prefixes)

    def close(self) -> None:
        """Shutdown: cancel every armed flush (held values are dropped)."""
        for e in self._ents.values():
            if e.timer is not None and not e.timer.done():
                e.timer.cancel()
            e.timer, e.pending = None, None

    def stats(self) -> dict[str, int]:
        return {"sent": self.sent, "skipped": self.skipped, "deferred": self.deferred,
                "pending": sum(1 for e in self._ents.values() if e.pending)}

    # ── entry point ──────────────────────────────────────────────────────────────
    async def call(self, domain: str, service: str, data: dict | None = None) -> Any:
        data = dict(data or {})
        key = (domain, service)
        targets = _targets(data)
        if key in SETTERS:
            if len(targets) == 1 and self.in_scope(targets[0]):
                eid = targets[0]
                e = self._ents.setdefault(eid, _Ent())
                e.req_seq += 1
                return await self._submit(eid, domain, service, data, seq=e.req_seq)
            return await self._send(None, domain, service, data)  # not the robot's: untouched
        if key in AVAILABILITY_ONLY or domain in ("media_player", "assist_satellite"):
            check = targets
            if domain == "tts":  # the engine is HA-side; the SPEAKER is the robot
                check = _targets({"entity_id": data.get("media_player_entity_id")})
            for eid in check:
                if self.in_scope(eid) and not await self._available(eid):
                    self._skip(f"{domain}.{service}", [eid])
                    return []
        return await self._send(None, domain, service, data)

    async def call_many(self, calls: list[tuple[str, str, dict]]) -> list[Any]:
        """A batch (e.g. all six card title/body slots): every write is gated on its own,
        the ones that survive go out together — pipelined on the one websocket — instead
        of one request after another. Failures come back as exceptions in the list."""
        return await asyncio.gather(
            *(self.call(d, s, data) for d, s, data in calls), return_exceptions=True
        )

    # ── availability ─────────────────────────────────────────────────────────────
    async def _state(self, eid: str) -> Any:
        try:
            return await self._lookup(eid)
        except Exception:  # noqa: BLE001 — can't tell → let the write through
            return None

    async def _available(self, eid: str) -> bool:
        st = await self._state(eid)
        if st is MISSING:
            return False
        return not (isinstance(st, dict) and st.get("state") == UNAVAILABLE)

    def _skip(self, what: str, targets: list[str]) -> None:
        self.skipped += 1
        log.debug("skipped %s → %s (unavailable / missing in HA)", what, targets)

    # ── the setter path ──────────────────────────────────────────────────────────
    async def _submit(self, eid: str, domain: str, service: str, data: dict, *,
                      seq: int, expires: float | None = None) -> Any:
        e = self._ents.setdefault(eid, _Ent())
        st = await self._state(eid)
        if seq != e.req_seq:
            return []  # a newer request arrived while we looked — it wins
        now = self._clock()
        hold_until = expires if expires is not None else now + PENDING_TTL_S
        if st is MISSING or (isinstance(st, dict) and st.get("state") == UNAVAILABLE):
            # (a) keep the latest value briefly; the mirror's "available again" delivers it
            e.pending = (domain, service, data, hold_until, seq)
            self._skip(f"{domain}.{service}", [eid])
            return []
        sig = signature(domain, service, data)
        mirror = st if isinstance(st, dict) else None
        if eid not in self._always and sig == e.last_sig and not e.dirty:
            # (b) a repeat of OUR last value: drop it while it's in place or in flight,
            # re-assert with backoff when the robot keeps not showing it
            in_place = e.landed and shows(domain, service, data, mirror)
            in_flight = not e.landed and now - e.last_at < SETTLE_S
            backing_off = not e.landed and now - e.last_at < e.reassert
            if in_place or in_flight or backing_off:
                e.pending = None  # this is the newest wish — nothing older may land after it
                self.skipped += 1
                return []
        lane = self._lanes.get(eid)
        unknown = mirror is not None and mirror.get("state") == UNKNOWN
        ready_at = max(
            # (c) — a LANE entity is not coalesced: it waits its turn on the lane (in order,
            # spaced) like the servo bus always did, so every step of a nod is delivered
            e.last_at + self._rate if lane is None else float("-inf"),
            e.fail_until,                                                     # (d)
            e.probe_until if unknown else float("-inf"),                      # (a) probe
        )
        if now < ready_at:
            # hold it at least until it can go out (a 60 s backoff must not outlive the hold)
            e.pending = (domain, service, data, max(hold_until, ready_at + RATE_S), seq)
            self.deferred += 1
            self._arm(eid, ready_at - now)
            return []
        e.pending = None
        reassert = sig == e.last_sig and not e.dirty
        e.last_at = now  # reserve the window BEFORE the await: a racing write is deferred
        try:
            result = await self._send(eid, domain, service, data)
        except Exception:
            e.last_at = self._clock()
            e.fail_backoff = min(FAIL_MAX_S, max(FAIL_MIN_S, e.fail_backoff * 2))
            e.fail_until = e.last_at + e.fail_backoff
            raise
        e.last_at = self._clock()
        e.last_sig, e.last_req = sig, (domain, service, data)
        e.landed = shows(domain, service, data, mirror)  # usually False until the mirror says so
        e.dirty = False
        e.fail_backoff, e.fail_until = 0.0, float("-inf")
        if unknown:
            e.probe_backoff = min(PROBE_MAX_S, max(PROBE_MIN_S, e.probe_backoff * 2))
            e.probe_until = e.last_at + e.probe_backoff
        else:
            e.probe_backoff, e.probe_until = 0.0, float("-inf")
        e.reassert = min(REASSERT_MAX_S, e.reassert * 2) if reassert else REASSERT_MIN_S
        return result

    def _arm(self, eid: str, delay: float) -> None:
        e = self._ents[eid]
        when = self._clock() + max(0.0, delay)
        if e.timer is not None and not e.timer.done():
            if e.timer_at <= when:
                return  # an earlier flush is armed — it re-evaluates with the latest value
            e.timer.cancel()

        async def _later() -> None:
            await asyncio.sleep(max(0.0, delay) + 0.001)
            e.timer = None
            e.timer_at = float("inf")
            await self._flush(eid)

        e.timer_at = when
        e.timer = asyncio.get_running_loop().create_task(_later())

    async def _flush(self, eid: str) -> None:
        e = self._ents.get(eid)
        if e is None or e.pending is None:
            return
        domain, service, data, expires, seq = e.pending
        e.pending = None
        if self._clock() > expires:
            log.debug("dropped a stale write to %s (held %.0fs)", eid, PENDING_TTL_S)
            return
        try:
            await self._submit(eid, domain, service, data, seq=seq, expires=expires)
        except Exception as exc:  # noqa: BLE001 — a deferred write has no caller to raise to
            log.debug("deferred %s.%s → %s failed: %s", domain, service, eid, exc)
            if e.pending is None and seq == e.req_seq:   # (d) retry it after the backoff
                e.pending = (domain, service, data, expires, seq)
                self._arm(eid, e.fail_until - self._clock())

    # ── mirror feedback ──────────────────────────────────────────────────────────
    def on_state(self, eid: str, old: dict | None, new: dict | None) -> None:
        """Mirror listener: track whether our last value landed / was replaced, and deliver
        a held value the moment its entity comes back."""
        e = self._ents.get(eid)
        if e is None or new is None:
            return
        if e.last_req is not None:
            if shows(*e.last_req, new):
                e.landed, e.dirty = True, False
                e.reassert = REASSERT_MIN_S
            elif e.landed or (old is not None and old.get("state") != new.get("state")):
                e.dirty = True  # an outside change (or a wipe) replaced / overtook our value
        if e.pending is not None and new.get("state") != UNAVAILABLE:
            try:
                lane = self._lanes.get(eid)
                gap = lane.spacing if lane is not None else self._rate
                self._arm(eid, max(0.0, e.last_at + gap - self._clock()))
            except RuntimeError:  # no running loop (sync test context)
                pass

    def on_resync(self) -> None:
        """A fresh snapshot arrived (after a websocket outage): every value we sent may
        have been replaced meanwhile, and every held value gets a fresh look."""
        for eid, e in self._ents.items():
            e.landed, e.dirty = False, e.last_req is not None
            if e.pending is not None:
                try:
                    self._arm(eid, max(0.0, e.last_at + self._rate - self._clock()))
                except RuntimeError:
                    pass

    # ── sending ──────────────────────────────────────────────────────────────────
    async def _send(self, eid: str | None, domain: str, service: str, data: dict) -> Any:
        lane = self._lanes.get(eid) if eid else None
        if lane is None:
            result = await self._send_raw(domain, service, data)
            self.sent += 1
            return result
        async with lane.lock:
            last_exc: Exception | None = None
            for attempt in range(lane.retries):
                gap = lane.spacing - (self._clock() - lane.last)
                if gap > 0:
                    await asyncio.sleep(gap)
                try:
                    result = await self._send_raw(domain, service, data)
                    lane.last = self._clock()
                    self.sent += 1
                    return result
                except Exception as exc:  # noqa: BLE001 — a serial-bus NAK; retry
                    lane.last = self._clock()
                    last_exc = exc
                    if attempt < lane.retries - 1:
                        log.debug("%s.%s %s failed (%s), retrying", domain, service, eid, exc)
                        await asyncio.sleep(lane.retry_delay)
            assert last_exc is not None
            raise last_exc
