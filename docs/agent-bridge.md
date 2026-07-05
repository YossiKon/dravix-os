# Turn the robot into a status lamp for your AI agents

Run AI coding agents on your PC — **Claude Code**, Cursor, editor extensions, CI jobs, your
own scripts — and the **StackChan on your desk shows you what they're doing** without you
watching the screen. Connect **one or many at once**; the robot shows the one that most needs
you, and the dashboard shows them all.

| Agent state | Face | LED (Okabe–Ito) | Glyph | Speaks? |
|---|---|---|---|---|
| `working` | concentrating | 🔵 sky blue `#56B4E9` | 🔧 | no |
| `waiting_permission` | doubtful | 🟠 orange `#E69F00` | ✋ | **"I need your approval."** |
| `question` | neutral | 🟣 reddish-purple `#CC79A7` | ❓ | **"I have a question."** |
| `done` | happy | 🟢 bluish-green `#009E73` | ✅ | **"All done."** |
| `error` | sad | 🔴 vermillion `#D55E00` | ⚠️ | **"Something went wrong."** |
| `idle` | neutral | off | 💤 | no |

**Colour-blind friendly by design.** The palette is [Okabe–Ito](https://jfly.uni-koeln.de/color/),
chosen so the states stay distinct for the common colour-vision types, and **every state also
carries a glyph and a distinct brightness** — so you never rely on colour alone. On the robot's
screen the badge is plain text (`claude: working`), which is unambiguous regardless of colour
vision.

The attention states (permission / question / error) speak so you look up from across the
room; the ambient ones stay silent. Everything is best-effort, capability-guarded, and reaches
the add-on **over your LAN only** — so it fully respects the master **isLocal** switch.

## Several agents at once

Each agent reports under a **name** (`source`). Run Claude Code in two projects and you'll see
two agents on the dashboard's **AI agent** card. The robot reflects the **winning** agent:

- **Auto (default)** — the most urgent state wins (`waiting_permission` > `question` > `error`
  > `working` > `done` > `idle`); ties break by most-recent.
- **Pinned** — from the dashboard, pin one agent so it always wins the robot.

An agent that goes quiet for 15 min stops holding the robot (it's still listed, greyed out).
You can dismiss any agent from the card.

### Where "whose status" shows on the robot — you choose

From the **AI agent** card (**Show on robot:**):

- **🗨 Bubble** — when the winner needs you, the robot speaks and the name appears in its
  speech bubble (`claude: needs your approval`). Works with the firmware you already have.
- **🏷 Badge** — a small persistent label in the corner of the face showing `name: state`.
  Needs firmware **v20+** (flash it once — it adds one tiny label, no reset risk).
- **Both** (default) / **Off** (dashboard only).

## How it works

Your agent POSTs its state to one endpoint; dravix mirrors the winner onto the robot:

```
POST http://<add-on>:8800/api/agent/status
Content-Type: application/json
{ "state": "waiting_permission", "text": "Allow: rm build/?", "source": "claude" }
```

- `state` — one of the six above (required).
- `text` — optional line shown/spoken **instead** of the state's default.
- `say` — optional `true`/`false` to force speech on/off for this call.
- `source` — the agent's name (the registry key). Two instances should use two names.

Other endpoints: `GET /api/agent/status` (every agent + the winner + palette),
`DELETE /api/agent/status/<name>` (dismiss), `PUT /api/agent/prefs` (`display`, `primary`).
The winner also rides along in `GET /api/status`. If you set `DRAVIX_API_TOKEN` on the add-on,
send it as `Authorization: Bearer <token>` (or `?token=`).

Try it by hand:

```bash
curl -X POST http://localhost:8800/api/agent/status \
  -H 'Content-Type: application/json' \
  -d '{"state":"done","source":"test"}'
```

## Wiring Claude Code (the easy path)

Claude Code fires **hooks** on its lifecycle events. A tiny bridge script maps each hook to
the endpoint above.

1. Copy [`deploy/agent-bridge/dravix-notify.py`](../deploy/agent-bridge/dravix-notify.py)
   somewhere on your PC (it needs only Python 3 — no packages).

2. Merge the `hooks` + `env` blocks from
   [`deploy/agent-bridge/claude-settings.example.json`](../deploy/agent-bridge/claude-settings.example.json)
   into your `~/.claude/settings.json` (all projects) or a project's `.claude/settings.json`.
   Replace `PATH_TO` with the real path, and use `python` on Windows or `python3` on
   macOS/Linux.

3. Point it at your add-on via the `env` block:
   - `DRAVIX_URL` — `http://localhost:8800` if the agent runs on the same box as the add-on,
     else `http://<home-assistant-ip>:8800`.
   - `DRAVIX_TOKEN` — only if you set `DRAVIX_API_TOKEN` on the add-on.
   - `DRAVIX_AGENT` — optional fixed name for this agent. **Left unset, each project shows as
     its own agent automatically** (the bridge uses the project folder name).

| Claude Code hook | Fires when | Robot shows |
|---|---|---|
| `UserPromptSubmit` | you send a message | `working` |
| `PreToolUse` | before each tool runs | `working` |
| `Notification` | it needs permission / your input | `waiting_permission` or `question` |
| `Stop` | it finishes the turn | `done` |
| `SessionStart` | a session opens | `idle` |

## Approve / reject a tool from the robot

Close the loop: when Claude Code is about to run a tool, the **robot pops Approve / Reject
buttons** on its screen (fw **v21**) and you tap to allow or block it — no reaching for the
keyboard. You can decide from the dashboard's AI-agent card too.

1. Copy [`deploy/agent-bridge/dravix-permission.py`](../deploy/agent-bridge/dravix-permission.py)
   next to the other bridge script.
2. In `claude-settings.example.json` there's a second `PreToolUse` entry that runs it. **Scope
   its `matcher`** to the tools you want to gate — `"Bash"` (commands) or `"Bash|Write|Edit"`
   (commands + file changes). Every matched tool then waits for your tap.
3. Tap **Approve** → the tool runs. Tap **Reject** → it's blocked. If you don't answer within
   `DRAVIX_PERM_TIMEOUT` (default 120 s) or the robot is unreachable, it **falls back to Claude
   Code's normal prompt** — it never hard-blocks you.

Under the hood: the hook POSTs `/api/agent/permission`, the robot (and dashboard) show the
request, your tap fires `esphome.dravix_permission` back to dravix, and the hook returns
`allow`/`deny` to Claude Code. The buttons are green **Approve** / vermillion **Reject** with
the words on them — clear regardless of colour vision.

## Wiring anything else

Any tool that can run a shell command or make an HTTP call can drive the lamp — there's just
the one endpoint. Reuse `dravix-notify.py` directly (`python3 dravix-notify.py done`) or:

```bash
curl -sX POST "$DRAVIX_URL/api/agent/status" -H 'Content-Type: application/json' \
  -d '{"state":"working","source":"deploy"}'
make deploy \
  && curl -sX POST "$DRAVIX_URL/api/agent/status" -d '{"state":"done","source":"deploy"}'  -H 'Content-Type: application/json' \
  || curl -sX POST "$DRAVIX_URL/api/agent/status" -d '{"state":"error","source":"deploy"}' -H 'Content-Type: application/json'
```
