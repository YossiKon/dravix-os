"""An in-memory mirror of Home Assistant's states, fed by ONE websocket subscription.

Why: dravix used to ask HA for ``GET /api/states`` — every entity in the house, serialised
from scratch — every few seconds, just to read the thirty-odd robot entities. On a
3,000-entity install that made dravix the top source of HA core load. HA's
``subscribe_entities`` command (the same one every open HA dashboard tab uses) sends the
full state set ONCE per connection and then only compressed diffs, so every read here is a
dictionary lookup with no HA traffic at all.

Frame format (``homeassistant.components.websocket_api``, compressed states):

- ``{"a": {entity_id: {"s": state, "a": attrs, "c": context, "lc": ts, "lu": ts}}}`` —
  added entities; the FIRST frame after subscribing is the full snapshot. ``lu`` is left
  out when it equals ``lc``.
- ``{"c": {entity_id: {"+": {...changed fields...}, "-": {"a": [removed attr keys]}}}}`` —
  changes; ``"+"."a"`` holds only the attributes that changed.
- ``{"r": [entity_id, ...]}`` — removed entities.

The mirror stores REST-shaped dicts (``entity_id/state/attributes/last_changed/
last_updated``) so ``HomeAssistant.states()`` / ``get_state()`` callers see exactly what
the REST API used to return. Stored dicts are replaced, never mutated, so a caller holding
an old dict never sees it change under it. This module is pure (no I/O) — the websocket
lives in :mod:`ha_events`.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Any, Callable

UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"

# (entity_id, old_state_dict | None, new_state_dict | None)
Change = tuple[str, "dict[str, Any] | None", "dict[str, Any] | None"]


def _iso(ts: Any) -> str | None:
    try:
        return _dt.datetime.fromtimestamp(float(ts), tz=_dt.timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def expand(entity_id: str, compressed: dict[str, Any]) -> dict[str, Any]:
    """One compressed state (``{"s","a","lc","lu"}``) → the REST ``/api/states`` shape."""
    lc = _iso(compressed.get("lc"))
    lu = _iso(compressed.get("lu")) if "lu" in compressed else lc
    return {
        "entity_id": entity_id,
        "state": compressed.get("s"),
        "attributes": dict(compressed.get("a") or {}),
        "last_changed": lc,
        "last_updated": lu,
    }


def apply_diff(current: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    """Apply one ``{"+": …, "-": …}`` diff to a REST-shaped state → a NEW dict."""
    plus = diff.get("+") or {}
    minus = diff.get("-") or {}
    new = dict(current)
    if "s" in plus:
        new["state"] = plus["s"]
    if plus.get("a") or minus.get("a"):
        attrs = dict(current.get("attributes") or {})
        attrs.update(plus.get("a") or {})
        for key in minus.get("a") or ():
            attrs.pop(key, None)
        new["attributes"] = attrs
    if "lc" in plus:
        new["last_changed"] = new["last_updated"] = _iso(plus["lc"])
    elif "lu" in plus:
        new["last_updated"] = _iso(plus["lu"])
    return new


class StateMirror:
    """All of HA's states, kept current by the ``subscribe_entities`` stream."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._ready = asyncio.Event()
        self._awaiting_snapshot = True
        self._listeners: list[Callable[[str, "dict | None", "dict | None"], None]] = []
        self._resync_listeners: list[Callable[[], None]] = []
        self.synced = False
        self.resyncs = 0  # how many full snapshots arrived (1 = the first connect)

    # ── lifecycle (driven by the websocket owner) ────────────────────────────────
    def begin_sync(self) -> None:
        """A (re)subscription was sent: the next ``"a"`` frame is a full snapshot."""
        self._awaiting_snapshot = True

    def mark_stale(self) -> None:
        """The connection dropped — readers must not trust the mirror until it resyncs.
        The last snapshot is kept (nothing reads it while ``synced`` is False)."""
        self.synced = False
        self._ready.clear()

    async def wait_ready(self, timeout: float) -> bool:
        if self.synced:
            return True
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return self.synced

    # ── frames ───────────────────────────────────────────────────────────────────
    def apply(self, event: dict[str, Any]) -> list[Change]:
        """Fold one subscribe_entities event into the mirror. Returns the per-entity
        changes (old, new) for listeners — empty for the initial snapshot, which is a
        sync, not a series of transitions."""
        changes: list[Change] = []
        added = event.get("a")
        if self._awaiting_snapshot and added is not None:
            self._states = {eid: expand(eid, c) for eid, c in added.items()}
            self._awaiting_snapshot = False
            self.synced = True
            self.resyncs += 1
            self._ready.set()
            for fn in list(self._resync_listeners):
                fn()
            return changes
        for eid, c in (added or {}).items():
            old = self._states.get(eid)
            new = expand(eid, c)
            self._states[eid] = new
            changes.append((eid, old, new))
        for eid, diff in (event.get("c") or {}).items():
            old = self._states.get(eid)
            if old is None:
                continue  # a diff for an entity we never saw — wait for the next snapshot
            new = apply_diff(old, diff or {})
            self._states[eid] = new
            changes.append((eid, old, new))
        for eid in event.get("r") or ():
            old = self._states.pop(eid, None)
            if old is not None:
                changes.append((eid, old, None))
        for eid, old, new in changes:
            for fn in list(self._listeners):
                fn(eid, old, new)
        return changes

    # ── reads ────────────────────────────────────────────────────────────────────
    def get(self, entity_id: str) -> dict[str, Any] | None:
        return self._states.get(entity_id)

    def state_of(self, entity_id: str) -> str | None:
        """The bare state string, or None when HA has no such entity."""
        st = self._states.get(entity_id)
        return None if st is None else st.get("state")

    def all(self) -> list[dict[str, Any]]:
        return list(self._states.values())

    def __len__(self) -> int:
        return len(self._states)

    # ── listeners ────────────────────────────────────────────────────────────────
    def add_listener(self, fn: Callable[[str, "dict | None", "dict | None"], None]) -> None:
        """``fn(entity_id, old, new)`` after every change (sync — keep it cheap)."""
        self._listeners.append(fn)

    def add_resync_listener(self, fn: Callable[[], None]) -> None:
        """``fn()`` after every full snapshot (first connect and every reconnect)."""
        self._resync_listeners.append(fn)
