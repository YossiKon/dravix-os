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
import uuid
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


def _utcnow() -> datetime.datetime:
    """Timezone-aware UTC — so the ISO strings we emit carry an offset and the dashboard's
    'x ago' is correct no matter the browser's timezone."""
    return datetime.datetime.now(datetime.timezone.utc)


# how strongly each state claims the robot (higher wins); ties → most recently updated.
_PRIORITY: dict[str, int] = {
    "waiting_permission": 5, "question": 4, "error": 3, "working": 2, "done": 1, "idle": 0,
}
_STALE_AFTER = 900.0   # seconds; an agent quiet this long stops holding the robot (still listed)
_PERM_TTL = 300.0      # seconds a permission request stays answerable before it's "expired"


def palette() -> dict[str, dict]:
    """The public state→{color,glyph} map (dashboard fetches it to stay in sync)."""
    return {s: {"color": lk.led, "glyph": lk.glyph} for s, lk in _LOOKS.items()}


def _short_for_robot(text: str, limit: int = 44) -> str:
    """Compact summary for the robot's small screen — at most ~2 lines. Collapses any
    whitespace/newlines (a multi-line command becomes one line) and clips long text so it
    never spills past the prompt box. The dashboard still shows the FULL summary."""
    one = " ".join((text or "").split())
    return one if len(one) <= limit else one[: limit - 2].rstrip() + ".."


def _badge(name: str, state: str, maxlen: int = 30) -> str:
    """"name: state" for the on-face label, fit into ``maxlen`` by shortening the NAME (never
    the state) so the important part is always readable. "" when there's nothing to show."""
    if state == "idle" or not name:
        return ""
    label = state.replace("_", " ")
    avail = maxlen - len(label) - 2  # ": "
    short = name if len(name) <= max(1, avail) else name[: max(1, avail - 1)] + "."
    return f"{short}: {label}"


class AgentPresence:
    """Holds every reporting agent and mirrors the winner onto the robot."""

    def __init__(self, robot, bus, store=None) -> None:  # noqa: ANN001
        self._robot = robot
        self._bus = bus
        self._store = store
        self._agents: dict[str, dict] = {}          # name -> {state, text, updated_dt}
        self._last: tuple[str, str] = ("", "")      # (winner_name, winner_state) last reflected
        self._perms: dict[str, dict] = {}           # id -> permission request
        self._current: str | None = None            # the request shown on the robot right now

    # ── preferences (dashboard-managed) ─────────────────────────────────────────────
    def _prefs(self) -> dict:
        store = self._store
        if store is not None and hasattr(store, "agent_prefs"):
            try:
                return store.agent_prefs()
            except Exception:  # noqa: BLE001
                pass
        return {"display": "both", "primary": "", "muted": [], "approvals": False}

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
        stamp = now or _utcnow()
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
            "muted": prefs.get("muted", []),
            "approvals": prefs.get("approvals", False),
            "palette": palette(),
            "permission": self.current_permission(now=stamp),
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
        stamp = now or _utcnow()
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

    async def forget(self, name: str, *, now: datetime.datetime | None = None) -> bool:
        """Remove one agent (dashboard 'dismiss') and re-reflect the robot. Returns True if
        it existed. Passing the just-removed name as changed_name keeps this SILENT — that
        name is no longer live, so it can never equal the new winner and trigger speech."""
        existed = self._agents.pop(name, None) is not None
        if existed:
            stamp = now or _utcnow()
            await self._reflect(self._winner(stamp), False, name, "idle")
        return existed

    async def clear(self) -> dict:
        """Drop every agent and reset the robot to idle (dashboard 'clear all')."""
        self._agents = {}
        await self._reflect(None, False, "", "idle")
        return self.snapshot()

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
                    try:
                        await writer(_badge(wname, wstate))
                    except Exception:  # noqa: BLE001
                        pass

        # speak only when THIS update is the (changed) winner, it's an attention state, and
        # the agent isn't individually muted (a chatty agent can be silenced on its own)
        muted = wname in set(self._prefs().get("muted", []))
        want_say = say if say is not None else (look.speak and display in ("bubble", "both") and not muted)
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

    # ── on-robot permission approvals ───────────────────────────────────────────────
    # An agent can ASK for a yes/no ("run this command?"). The robot shows Approve/Reject
    # buttons (fw v21) and/or the dashboard shows them; the agent polls for the answer. The
    # robot's tap has no request id, so it resolves whichever request is on-screen now.
    def current_permission(self, *, now: datetime.datetime | None = None) -> dict | None:
        if not self._current:
            return None
        return self.permission_view(self._current, now=now)

    def permission_view(self, pid: str, *, now: datetime.datetime | None = None) -> dict | None:
        p = self._perms.get(pid)
        if p is None:
            return None
        stamp = now or _utcnow()
        expired = p["decision"] is None and (stamp - p["created_dt"]).total_seconds() > _PERM_TTL
        return {
            "id": p["id"],
            "agent": p["agent"],
            "tool": p["tool"],
            "summary": p["summary"],
            "decision": p["decision"] or ("expired" if expired else "pending"),
            "created_at": p["created_dt"].isoformat(timespec="seconds"),
        }

    async def _show_permission(self, text: str) -> None:
        writer = getattr(getattr(self._robot, "driver", None), "set_permission", None)
        if writer is not None:
            try:
                await writer(text[:80])
            except Exception:  # noqa: BLE001 — the on-robot prompt is best-effort
                pass

    async def _robot_ready(self) -> bool:
        """Is the robot actually reachable to show a prompt? Used so the agent's permission
        hook can FAIL OPEN FAST (not stall) when there's realistically no one to tap — e.g.
        the robot is offline. The live state sensor is our reachability proxy (None = offline);
        backends without one (mock) are treated as ready so behaviour/tests are unchanged."""
        reader = getattr(getattr(self._robot, "driver", None), "get_text", None)
        if reader is None:
            return True
        try:
            return (await reader("state_sensor")) is not None
        except Exception:  # noqa: BLE001 — can't tell → assume not reachable, fail open fast
            return False

    async def request_permission(
        self, agent: str, tool: str = "", summary: str = "", *, now: datetime.datetime | None = None,
    ) -> dict:
        # MASTER kill-switch (dashboard): when approvals are OFF, don't gate at all — no
        # request, no robot prompt. robot_ready=False makes the agent's hook fall straight
        # through to Claude Code's normal flow, so an installed hook can never block you.
        if not self._prefs().get("approvals", False):
            return {"decision": "disabled", "robot_ready": False}
        name = (agent or "agent").strip() or "agent"
        stamp = now or _utcnow()
        pid = uuid.uuid4().hex[:8]
        text = (summary or tool or "Approve?").strip()
        self._perms[pid] = {
            "id": pid, "agent": name, "tool": (tool or "").strip(), "summary": text,
            "created_dt": stamp, "decision": None, "decided_dt": None,
        }
        # drop decided requests older than a minute so the map can't grow without bound
        self._perms = {
            k: v for k, v in self._perms.items()
            if v["decision"] is None or (stamp - (v["decided_dt"] or stamp)).total_seconds() < 60
        }
        self._current = pid
        # the asking agent is now waiting_permission (the winner → face/LED). Speak the SHORT
        # default line ("I need your approval"), NOT the long command — text="" keeps the
        # spoken line and the winner bubble short.
        await self.set("waiting_permission", "", source=name, now=stamp)
        # …plus the Approve/Reject buttons + a compact ≤2-line summary on the robot's screen.
        await self._show_permission(_short_for_robot(f"{name}: {text}"))
        view = self.permission_view(pid, now=stamp)
        # tell the caller whether the robot can realistically be tapped, so its hook can fail
        # open fast instead of stalling for the whole timeout when the robot is offline.
        view["robot_ready"] = await self._robot_ready()
        return view

    async def decide_permission(
        self, pid: str, decision: str, *, now: datetime.datetime | None = None,
    ) -> dict | None:
        p = self._perms.get(pid)
        return await self._apply_decision(p, decision, now=now) if p else None

    async def decide_current(
        self, decision: str, *, now: datetime.datetime | None = None,
    ) -> dict | None:
        """Resolve the request currently shown on the robot (the robot's tap has no id)."""
        p = self._perms.get(self._current) if self._current else None
        return await self._apply_decision(p, decision, now=now) if p else None

    async def _apply_decision(
        self, p: dict, decision: str, *, now: datetime.datetime | None = None,
    ) -> dict:
        stamp = now or _utcnow()
        approved = str(decision).strip().lower() in ("approve", "approved", "allow", "yes", "true", "ok")
        if p["decision"] is None:
            p["decision"] = "approved" if approved else "rejected"
            p["decided_dt"] = stamp
        if self._current == p["id"]:
            await self._show_permission("")
            self._current = None
            # if another request is still waiting, promote it onto the screen
            nxt = next(
                (q for q in self._perms.values()
                 if q["decision"] is None and (stamp - q["created_dt"]).total_seconds() <= _PERM_TTL),
                None,
            )
            if nxt is not None:
                self._current = nxt["id"]
                await self._show_permission(_short_for_robot(f"{nxt['agent']}: {nxt['summary']}"))
        # move the asking agent on: approved → back to working, rejected → idle
        await self.set("working" if approved else "idle", "", source=p["agent"], now=stamp)
        return self.permission_view(p["id"], now=stamp)
