#!/usr/bin/env python3
"""dravix-notify — bridge an AI agent's lifecycle to the dravix robot status lamp.

The robot on your desk becomes a status light for an AI coding agent (Claude Code,
Cursor, …) running on your PC. Each hook calls this once; the robot shows a face + LED
colour and, when it needs YOU, says a short line.

Usage (a hook's event JSON arrives on stdin — this script never needs args to work):
    dravix-notify.py working   # agent started a turn / is running a tool
    dravix-notify.py notify    # a Notification hook — permission vs question inferred from stdin
    dravix-notify.py done      # agent finished its turn
    dravix-notify.py idle      # session start / gone quiet
    dravix-notify.py error     # something failed

Multiple agents at once? Each instance registers under its own name so the robot can show
whose status it is. The name is, in order: $DRAVIX_AGENT, else the project folder name (the
hook's cwd basename), else "claude-code". Run Claude Code in two projects and you'll see two
agents on the dashboard.

Point it at your add-on with env vars (defaults shown):
    DRAVIX_URL=http://localhost:8800   # the dravix-os dashboard/API base (or http://<HA-ip>:8800)
    DRAVIX_TOKEN=                      # only if you set DRAVIX_API_TOKEN on the add-on
    DRAVIX_AGENT=                      # optional fixed name for this agent (else the project folder)

It is deliberately fail-quiet: any error (robot offline, bad URL, timeout) is swallowed and
the script exits 0, so a missing robot can never break or slow down your agent.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request


def _classify(arg: str, message: str) -> tuple[str, str]:
    """Map a hook trigger + its message to a dravix agent state and display text."""
    if arg == "notify":
        low = message.lower()
        if any(w in low for w in ("permission", "approve", "allow", "authoriz")):
            return "waiting_permission", message
        return "question", message
    # working | done | idle | error | (any state name passed straight through)
    return arg, message if arg in ("error",) else ""


def _agent_name(payload: dict) -> str:
    """This agent's registry name: $DRAVIX_AGENT, else the project folder, else claude-code."""
    name = os.environ.get("DRAVIX_AGENT", "").strip()
    if name:
        return name
    cwd = str(payload.get("cwd") or payload.get("workspace") or "").replace("\\", "/").rstrip("/")
    if cwd:
        return cwd.rsplit("/", 1)[-1] or "claude-code"
    return "claude-code"


def main() -> None:
    arg = (sys.argv[1] if len(sys.argv) > 1 else "working").strip().lower()

    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    message = str(payload.get("message", "")).strip()

    state, text = _classify(arg, message)
    body = json.dumps({"state": state, "text": text, "source": _agent_name(payload)}).encode()

    base = os.environ.get("DRAVIX_URL", "http://localhost:8800").rstrip("/")
    req = urllib.request.Request(
        f"{base}/api/agent/status",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    token = os.environ.get("DRAVIX_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass  # a status lamp must never break your agent


if __name__ == "__main__":
    main()
