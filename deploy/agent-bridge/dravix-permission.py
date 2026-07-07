#!/usr/bin/env python3
"""dravix-permission — approve/reject a Claude Code tool from the robot's touchscreen.

Wire this to Claude Code's **PreToolUse** hook (usually with a matcher like "Bash" or
"Bash|Write|Edit", so only the tools you care about wait for you). When the tool is about
to run, the robot pops **Approve / Reject** buttons on its screen and speaks; tap one and
the tool proceeds or is blocked. You can also decide from the dashboard's AI-agent card.

The hook receives the tool call on stdin and prints a Claude Code permission decision on
stdout:
  * Approve → permissionDecision "allow"
  * Reject  → permissionDecision "deny"
  * Timeout / robot unreachable → prints nothing, so Claude Code falls back to its NORMAL
    prompt. It is fail-open by design: a missing robot never blocks or slows you beyond the
    poll timeout.

Env (defaults shown):
    DRAVIX_URL=http://localhost:8800     # the add-on base (or http://<HA-ip>:8800)
    DRAVIX_TOKEN=                        # only if you set DRAVIX_API_TOKEN on the add-on
    DRAVIX_AGENT=                        # fixed agent name (else the project folder)
    DRAVIX_PERM_TIMEOUT=120              # seconds to wait for a tap before falling back
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request


def _agent_name(payload: dict) -> str:
    name = os.environ.get("DRAVIX_AGENT", "").strip()
    if name:
        return name
    cwd = str(payload.get("cwd") or payload.get("workspace") or "").replace("\\", "/").rstrip("/")
    return (cwd.rsplit("/", 1)[-1] or "claude-code") if cwd else "claude-code"


def _summary(payload: dict) -> tuple[str, str]:
    """(tool, one-line human summary) for the robot prompt."""
    tool = str(payload.get("tool_name") or "tool")
    ti = payload.get("tool_input") or {}
    if isinstance(ti, dict):
        if ti.get("command"):
            return tool, str(ti["command"])
        if ti.get("file_path"):
            return tool, f"{tool} {ti['file_path']}"
        if ti.get("path"):
            return tool, f"{tool} {ti['path']}"
        if ti.get("url"):
            return tool, f"{tool} {ti['url']}"
    return tool, tool


def _api(base: str, path: str, token: str, body: dict | None = None, timeout: float = 4.0):
    url = f"{base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if body is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or "{}")


def _decide(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))


def main() -> None:
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    base = os.environ.get("DRAVIX_URL", "http://localhost:8800").rstrip("/")
    token = os.environ.get("DRAVIX_TOKEN", "").strip()
    try:
        # SHORT by default so a missed tap never freezes your agent for long. This hook makes
        # each matched tool WAIT for your approval — keep the window small.
        deadline = time.time() + float(os.environ.get("DRAVIX_PERM_TIMEOUT", "20"))
    except ValueError:
        deadline = time.time() + 20

    tool, summary = _summary(payload)
    try:
        created = _api(base, "/api/agent/permission", token,
                       {"source": _agent_name(payload), "tool": tool, "summary": summary})
    except Exception:
        return  # robot/add-on unreachable → say nothing → Claude Code's normal flow
    pid = created.get("id")
    if not pid:
        return
    # FAIL OPEN FAST: if the robot isn't reachable there's realistically no one to tap Approve,
    # so don't stall — fall straight through to Claude Code's normal prompt.
    if created.get("robot_ready") is False:
        return

    while time.time() < deadline:
        try:
            view = _api(base, f"/api/agent/permission/{pid}", token)
        except Exception:
            time.sleep(1.0)
            continue
        decision = view.get("decision")
        if decision == "approved":
            _decide("allow", "Approved on the robot")
            return
        if decision == "rejected":
            _decide("deny", "Rejected on the robot")
            return
        if decision == "expired":
            return  # fall back to Claude Code's normal prompt
        time.sleep(1.0)
    # timed out waiting for a tap → normal flow


if __name__ == "__main__":
    main()
