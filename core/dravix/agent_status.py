"""Agent presence — let AI coding agents on your PC use the robot as a status lamp.

One OR MANY agents (Claude Code in two projects, Cursor, a CI runner, your own script …)
each POST their state to ``/api/agent/status`` with a ``source`` name. The robot reflects the
**winning** agent (the one that most needs you) with a face + LED colour and, for the states
that need you, a spoken line + a name bubble — so you can glance over and know *who* wants
what. Every other agent stays visible on the dashboard.

Which agent wins and how it's shown is chosen from the dashboard (``store.agent_prefs``):
  * **display** — bubble (spoken + 12 s speech bubble with the name), badge (a persistent
    on-face label, needs fw v20+), both, or off (dashboard only).
  * **primary** — pin one agent so it always wins, or auto (most-urgent state wins).

Colours are the **Okabe–Ito colour-blind-safe palette** and every state also carries a
distinct glyph, so the state never depends on colour alone. Everything is best-effort and
capability-guarded; the agent reaches the add-on over your LAN only, so it respects isLocal.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class _Look:
    """How the robot shows one agent state."""

    face: str            # an Expression value (neutral|happy|sad|doubt|…)
    led: str             # Okabe–Ito hex; the driver sends it as rgb_color
    brightness: float    # 0..1
    glyph: str           # non-colour cue (dashboard) — state never relies on colour alone
    say_en: str          # default spoken line (English) when the caller sends none
    say_he: str          # default spoken line (Hebrew)
    speak: bool          # speak by default for this state?


# state → look. Colours are Okabe–Ito (colour-blind-safe); the attention states
# (permission / question / error) speak by default, the ambient ones stay silent. Unknown
# states fall back to WORKING. Brightness also separates the states for a pure-colour LED:
# idle off, ambient dim, attention full.
_LOOKS: dict[str, _Look] = {
    "working":            _Look("doubt",   "#56B4E9", 0.6, "🔧", "",                     "",                     False),  # sky blue
    "waiting_permission": _Look("doubt",   "#E69F00", 1.0, "✋", "I need your approval.",  "צריך את האישור שלך.",  True),   # orange
    "question":           _Look("neutral", "#CC79A7", 1.0, "❓", "I have a question.",     "יש לי שאלה.",          True),   # reddish purple
    "done":               _Look("happy",   "#009E73", 0.8, "✅", "All done.",              "סיימתי.",              True),   # bluish green
    "error":              _Look("sad",     "#D55E00", 1.0, "⚠️", "Something went wrong.",   "משהו השתבש.",          True),   # vermillion
    "idle":               _Look("neutral", "#000000", 0.0, "💤", "",                     "",                     False),
}

STATES: tuple[str, ...] = tuple(_LOOKS.keys())

# how strongly each state claims the robot (higher wins); ties → most recently updated.
_PRIORITY: dict[str, int] = {
    "waiting_permission": 5, "question": 4, "error": 3, "working": 2, "done": 1, "idle": 0,
}
_STALE_AFTER = 900.0   # seconds; an agent quiet this long stops holding the robot (still listed)


def palette() -> dict[str, dict]:
    """The public state→{color,glyph} map (dashboard fetches it to stay in sync)."""
    return {s: {"color": lk.led, "glyph": lk.glyph} for s, lk in _LOOKS.items()}


class AgentPresence:
    """Holds every reporting agent and mirrors the winner onto the robot."""

    def __init__(self, robot, bus, store=None) -> None:  # noqa: ANN001
        self._robot = robot
        self._bus = bus
        self._store = store
        self._agents: dict[str, dict] = {}          # name -> {state, text, updated_dt}
        self._last: tuple[str, str] = ("", "")      # (winner_name, winner_state) last reflected

    # ── preferences (dashboard-managed) ─────────────────────────────────────────────
    def _prefs(self) -> dict:
        store = self._store
        if store is not None and hasattr(store, "agent_prefs"):
            try:
                return store.agent_prefs()
            except Exception:  # noqa: BLE001
                pass
        return {"display": "both", "primary": ""}

    # ── winner selection ────────────────────────────────────────────────────────────
    def _live(self, now: datetime.datetime) -> list[tuple[str, dict]]:
        return [
            (n, r) for n, r in self._agents.items()
            if (now - r["updated_dt"]).total_seconds() <= _STALE_AFTER
        ]

    def _winner(self, now: datetime.datetime) -> tuple[str, dict] | None:
        live = self._live(now)
        if not live:
            return None
        primary = self._prefs().get("primary", "")
        if primary:
            for n, r in live:
                if n == primary:
                    return (n, r)
        return max(live, key=lambda kv: (_PRIORITY.get(kv[1]["state"], 0), kv[1]["updated_dt"]))

    # ── public API ──────────────────────────────────────────────────────────────────
    def snapshot(self, now: datetime.datetime | None = None) -> dict:
        stamp = now or datetime.datetime.now()
        agents = []
        for n, r in sorted(self._agents.items(), key=lambda kv: kv[1]["updated_dt"], reverse=True):
            agents.append({
                "name": n,
                "state": r["state"],
                "text": r["text"],
                "updated_at": r["updated_dt"].isoformat(timespec="seconds"),
                "stale": (stamp - r["updated_dt"]).total_seconds() > _STALE_AFTER,
            })
        win = self._winner(stamp)
        winner = None
        if win is not None:
            n, r = win
            winner = {
                "name": n,
                "state": r["state"],
                "text": r["text"],
                "updated_at": r["updated_dt"].isoformat(timespec="seconds"),
            }
        prefs = self._prefs()
        return {
            "winner": winner,
            "agents": agents,
            "display": prefs.get("display", "both"),
            "primary": prefs.get("primary", ""),
            "palette": palette(),
        }

    async def set(
        self,
        state: str,
        text: str = "",
        *,
        say: bool | None = None,
        source: str = "",
        now: datetime.datetime | None = None,
    ) -> dict:
        """Record ``source``'s state and reflect the winning agent on the robot."""
        name = (source or "agent").strip() or "agent"
        stamp = now or datetime.datetime.now()
        self._agents[name] = {"state": state, "text": (text or "").strip(), "updated_dt": stamp}
        # drop long-dead agents so the registry can't grow without bound
        self._agents = {
            n: r for n, r in self._agents.items()
            if (stamp - r["updated_dt"]).total_seconds() <= _STALE_AFTER * 2
        }
        await self._reflect(self._winner(stamp), say, name, state)
        snap = self.snapshot(now=stamp)
        try:
            await self._bus.publish("agent.status", winner=snap["winner"], agents=snap["agents"])
        except Exception:  # noqa: BLE001 — publishing is a nicety for the live dashboard
            pass
        return snap

    def forget(self, name: str) -> bool:
        """Remove one agent (dashboard 'dismiss'). Returns True if it existed."""
        existed = self._agents.pop(name, None) is not None
        if existed:
            self._last = ("", "")  # force a re-reflect on the next update
        return existed

    # ── robot reflection ────────────────────────────────────────────────────────────
    async def _reflect(
        self, winner: tuple[str, dict] | None, say: bool | None, changed_name: str, changed_state: str,
    ) -> None:
        from .dal.base import CAP_FACE, CAP_LEDS, CAP_SAY

        wname = winner[0] if winner else ""
        wstate = winner[1]["state"] if winner else "idle"
        wtext = winner[1]["text"] if winner else ""
        look = _LOOKS.get(wstate, _LOOKS["idle"])
        changed = (wname, wstate) != self._last
        self._last = (wname, wstate)

        robot = self._robot
        display = self._prefs().get("display", "both")

        if changed:
            if robot.supports(CAP_FACE):
                try:
                    await robot.set_face(look.face)
                except Exception:  # noqa: BLE001 — a status lamp must never raise into the caller
                    pass
            if robot.supports(CAP_LEDS):
                try:
                    await robot.set_leds(look.led, look.brightness)
                except Exception:  # noqa: BLE001
                    pass
            if display in ("badge", "both"):
                writer = getattr(getattr(robot, "driver", None), "set_agent_text", None)
                if writer is not None:
                    badge = "" if (wstate == "idle" or not wname) else f"{wname}: {wstate.replace('_', ' ')}"
                    try:
                        await writer(badge)
                    except Exception:  # noqa: BLE001
                        pass

        # speak only when THIS update is the (changed) winner and it's an attention state
        want_say = say if say is not None else (look.speak and display in ("bubble", "both"))
        is_this_winner = wname == changed_name and wstate == changed_state
        if want_say and is_this_winner and (changed or bool(say)) and robot.supports(CAP_SAY):
            from .config import get_settings

            he = (get_settings().language or "en").startswith("he")
            base = wtext or (look.say_he if he else look.say_en)
            if base:
                line = f"{wname}: {base}" if (wname and wname != "agent") else base
                try:
                    await robot.say(line)
                except Exception:  # noqa: BLE001
                    pass
