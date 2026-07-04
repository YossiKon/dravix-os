# Turn the robot into a status lamp for an AI agent

Run an AI coding agent on your PC — **Claude Code**, Cursor, an editor extension, a CI job,
or your own script — and let the **StackChan on your desk show you what it's doing** without
you watching the screen:

| Agent state | Robot face | LED | Speaks? |
|---|---|---|---|
| `working` | concentrating | 🔵 blue (dim) | no |
| `waiting_permission` | doubtful | 🟠 amber | **"I need your approval."** |
| `question` | neutral | 🟣 purple | **"I have a question."** |
| `done` | happy | 🟢 green | **"All done."** |
| `error` | sad | 🔴 red | **"Something went wrong."** |
| `idle` | neutral | off | no |

The attention states (permission / question / error) speak so you look up from across the
room; the ambient ones (working / idle) stay silent. Everything is best-effort and
capability-guarded, and the agent reaches the add-on **over your LAN only** — nothing leaves
your network, so it fully respects the master **isLocal** switch.

## How it works

Your agent POSTs its state to one endpoint on the add-on; dravix mirrors it onto the robot:

```
POST http://<add-on>:8800/api/agent/status
Content-Type: application/json
{ "state": "waiting_permission", "text": "Allow: rm build/?", "source": "claude-code" }
```

- `state` — one of the six above (required).
- `text` — optional line shown/spoken **instead** of the state's default (e.g. the actual
  permission question).
- `say` — optional `true`/`false` to force speech on or off for this one call.
- `source` — optional label for who's reporting.

Read the current status any time with `GET /api/agent/status`, or watch the **Agent** card on
the dashboard. If you set `DRAVIX_API_TOKEN` on the add-on, send it as
`Authorization: Bearer <token>` (or `?token=`).

Try it by hand:

```bash
curl -X POST http://localhost:8800/api/agent/status \
  -H 'Content-Type: application/json' \
  -d '{"state":"done"}'
```

## Wiring Claude Code (the easy path)

Claude Code fires **hooks** on its lifecycle events. A tiny bridge script maps each hook to
the endpoint above.

1. Copy [`deploy/agent-bridge/dravix-notify.py`](../deploy/agent-bridge/dravix-notify.py)
   somewhere on your PC (it needs only Python 3 — no packages).

2. Merge the `hooks` + `env` blocks from
   [`deploy/agent-bridge/claude-settings.example.json`](../deploy/agent-bridge/claude-settings.example.json)
   into your `~/.claude/settings.json` (all projects) or a project's `.claude/settings.json`.
   In each command, replace `PATH_TO` with the real path to `dravix-notify.py`, and use
   `python` on Windows or `python3` on macOS/Linux.

3. Point it at your add-on via the `env` block:
   - `DRAVIX_URL` — `http://localhost:8800` if the agent runs on the same box as the add-on,
     otherwise `http://<home-assistant-ip>:8800`.
   - `DRAVIX_TOKEN` — only if you set `DRAVIX_API_TOKEN` on the add-on.

That's it. Now:

| Claude Code hook | Fires when | Robot shows |
|---|---|---|
| `UserPromptSubmit` | you send a message | `working` |
| `PreToolUse` | before each tool runs | `working` |
| `Notification` | it needs permission / your input | `waiting_permission` or `question` (inferred from the message) |
| `Stop` | it finishes the turn | `done` |
| `SessionStart` | a session opens | `idle` |

The `Notification` hook reads the message text and picks `waiting_permission` when it mentions
permission/approval, otherwise `question`.

## Wiring anything else

Any tool that can run a shell command or make an HTTP call can drive the lamp — there's no
Claude-specific magic, just the one endpoint. Examples:

```bash
# a long build/deploy script
curl -sX POST "$DRAVIX_URL/api/agent/status" -d '{"state":"working"}' -H 'Content-Type: application/json'
make deploy && \
  curl -sX POST "$DRAVIX_URL/api/agent/status" -d '{"state":"done"}'  -H 'Content-Type: application/json' || \
  curl -sX POST "$DRAVIX_URL/api/agent/status" -d '{"state":"error"}' -H 'Content-Type: application/json'
```

Or reuse `dravix-notify.py` directly: `python3 dravix-notify.py done`.
