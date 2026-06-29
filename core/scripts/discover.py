#!/usr/bin/env python3
"""Capability discovery — run this FIRST.

Connects to (a) the robot's MCP server and (b) Home Assistant, lists what each exposes, and
writes ``docs/capability-report.md``. This report is the ground truth we build the real
drivers against — so nothing is hard-coded against guessed tool names.

Usage:
    cd core && python scripts/discover.py
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import sys
from pathlib import Path

# Make ``import dravix`` work whether or not the package is pip-installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dravix.config import DOCS_DIR, get_settings  # noqa: E402
from dravix.dal.mcp_driver import DEFAULT_TOOL_CANDIDATES  # noqa: E402
from dravix.integrations.homeassistant import HomeAssistant  # noqa: E402
from dravix.integrations.mcp_client import MCPClient  # noqa: E402

REPORT = DOCS_DIR / "capability-report.md"
HA_RELEVANT = ("light", "number", "media_player", "camera", "switch", "select", "button")


def _schema_params(tool) -> str:
    schema = getattr(tool, "inputSchema", None) or {}
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not props:
        return "—"
    required = set(schema.get("required", []))
    return ", ".join(f"{k}{'*' if k in required else ''}" for k in props)


async def probe_mcp(url: str, transport: str, token: str | None, label: str) -> dict:
    out: dict = {"label": label, "url": url, "ok": False, "tools": [], "error": None}
    if not url:
        out["error"] = "not configured"
        return out
    client = MCPClient(url, transport=transport, token=token)
    try:
        await client.connect()
        out["transport"] = client.active_transport
        for t in await client.list_tools():
            out["tools"].append(
                {"name": t.name, "description": getattr(t, "description", "") or "",
                 "params": _schema_params(t)}
            )
        out["ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await client.close()
    return out


async def probe_ha(url: str, token: str) -> dict:
    out: dict = {"ok": False, "url": url, "error": None, "by_domain": {}, "relevant": {}}
    if not (url and token):
        out["error"] = "not configured"
        return out
    ha = HomeAssistant(url, token)
    try:
        if not await ha.ping():
            out["error"] = "unreachable or invalid token"
            return out
        states = await ha.states()
        out["ok"] = True
        out["count"] = len(states)
        for s in states:
            eid = s.get("entity_id", "")
            domain = eid.split(".", 1)[0] if "." in eid else "?"
            out["by_domain"][domain] = out["by_domain"].get(domain, 0) + 1
            if domain in HA_RELEVANT:
                out["relevant"].setdefault(domain, []).append(eid)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await ha.close()
    return out


def _map_recommendation(robot: dict) -> dict[str, str]:
    """Suggest a verb→tool mapping from the robot's actual tool names."""
    names = {t["name"] for t in robot.get("tools", [])}
    mapping: dict[str, str] = {}
    for cap, candidates in DEFAULT_TOOL_CANDIDATES.items():
        for cand in candidates:
            if cand in names:
                mapping[cap] = cand
                break
    return mapping


def render(robot: dict, ha_mcp: dict, ha: dict) -> str:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["# Capability report\n", f"_Generated {now} by `scripts/discover.py`._\n"]

    def mcp_section(title: str, data: dict) -> None:
        lines.append(f"## {title}\n")
        lines.append(f"- URL: `{data.get('url') or '(none)'}`")
        if data["ok"]:
            lines.append(f"- Status: ✅ connected via `{data.get('transport','?')}`")
            lines.append(f"- Tools: {len(data['tools'])}\n")
            lines.append("| tool | params | description |")
            lines.append("|------|--------|-------------|")
            for t in sorted(data["tools"], key=lambda x: x["name"]):
                desc = t["description"].replace("\n", " ")[:80]
                lines.append(f"| `{t['name']}` | {t['params']} | {desc} |")
            lines.append("")
        else:
            lines.append(f"- Status: ❌ {data.get('error')}\n")

    mcp_section("Robot MCP server", robot)
    if robot["ok"]:
        mapping = _map_recommendation(robot)
        lines.append("### Recommended robot driver config\n")
        lines.append("Set in `.env`:\n```")
        lines.append("DRAVIX_ROBOT_DRIVER=mcp")
        lines.append(f"DRAVIX_ROBOT_MCP_TRANSPORT={robot.get('transport','auto')}")
        lines.append("```")
        if mapping:
            lines.append("\nResolved verb → tool mapping:\n")
            for cap, tool in mapping.items():
                lines.append(f"- `{cap}` → `{tool}`")
            unmapped = [c for c in DEFAULT_TOOL_CANDIDATES if c not in mapping]
            if unmapped:
                lines.append(f"\n⚠️ Unmapped verbs (no matching tool found): {', '.join(unmapped)}")
                lines.append("Add explicit overrides once you confirm the right tool names.")
        else:
            lines.append("\n⚠️ No verbs auto-mapped — inspect the tool table above and set overrides.")
        lines.append("")

    mcp_section("Home Assistant MCP server", ha_mcp)

    lines.append("## Home Assistant (REST)\n")
    if ha["ok"]:
        lines.append(f"- URL: `{ha['url']}`")
        lines.append(f"- Status: ✅ {ha['count']} entities\n")
        lines.append("Entities by domain (robot-relevant domains expanded):\n")
        for domain in sorted(ha["by_domain"]):
            count = ha["by_domain"][domain]
            if domain in ha["relevant"]:
                eids = ", ".join(f"`{e}`" for e in ha["relevant"][domain][:20])
                lines.append(f"- **{domain}** ({count}): {eids}")
            else:
                lines.append(f"- {domain} ({count})")
        lines.append("")
    else:
        lines.append(f"- Status: ❌ {ha.get('error')}\n")

    lines.append("## Next steps\n")
    lines.append("1. If the robot MCP table looks right, set `DRAVIX_ROBOT_DRIVER=mcp` and restart.")
    lines.append("2. Confirm the verb→tool mapping; add overrides for anything unmapped.")
    lines.append("3. Note the robot-relevant HA entities — they enable the `ha` fallback driver.")
    return "\n".join(lines) + "\n"


async def main() -> int:
    s = get_settings()
    print("dravix-os discovery\n" + "=" * 40)
    print(f"robot MCP : {s.robot_mcp_url or '(not set)'}")
    print(f"HA        : {s.ha_url or '(not set)'}")
    print(f"HA MCP    : {s.ha_mcp_url or '(not set)'}\n")

    robot = await probe_mcp(s.robot_mcp_url, s.robot_mcp_transport, s.robot_mcp_token, "robot")
    ha_mcp = await probe_mcp(s.ha_mcp_url, "auto", s.ha_token, "ha-mcp")
    ha = await probe_ha(s.ha_url, s.ha_token)

    for label, d in (("robot MCP", robot), ("HA MCP", ha_mcp)):
        status = f"✅ {len(d['tools'])} tools" if d["ok"] else f"❌ {d['error']}"
        print(f"{label:10}: {status}")
    print(f"{'HA REST':10}: " + (f"✅ {ha.get('count','?')} entities" if ha["ok"] else f"❌ {ha['error']}"))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(robot, ha_mcp, ha), encoding="utf-8")
    print(f"\nWrote {REPORT}")
    if not (robot["ok"] or ha["ok"]):
        print("\nNothing connected. Fill in DRAVIX_ROBOT_MCP_URL / DRAVIX_HA_* in .env and retry.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
