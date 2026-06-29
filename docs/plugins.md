# Writing a dravix-os mode (plugin)

A **mode** is the unit of custom behavior. Modes are plain Python classes discovered from
`plugins/<name>/` at startup — no core changes needed. This is the extension surface for
adding "more options on top of stock."

## Anatomy

```
plugins/
  my_mode/
    plugin.yaml      # manifest
    mode.py          # a Mode subclass
```

### `plugin.yaml`

```yaml
name: my_mode
description: One line shown in the dashboard.
kind: foreground          # foreground (one at a time) | ambient (runs in background)
entrypoint: mode:MyMode   # <python-file>:<ClassName>
enabled: true
config:                   # arbitrary defaults, available as self.ctx.config
  color: blue
```

### `mode.py`

```python
from dravix.dal.base import CAP_FACE, CAP_LEDS, CAP_SAY, Expression
from dravix.events import Event
from dravix.modes import Mode, ModeMeta


class MyMode(Mode):
    meta = ModeMeta(name="my_mode", description="My mode", kind="foreground")

    async def on_enter(self) -> None:
        # Always guard by capability — backends differ (mock supports all; HA may not).
        if self.ctx.robot.supports(CAP_SAY):
            await self.ctx.robot.say(self.ctx.config.get("greet", "Hi!"))

    async def on_exit(self) -> None:
        ...

    async def on_event(self, event: Event) -> None:
        if event.type == "ha.motion":
            ...

    async def tick(self) -> None:
        # Called every engine tick (default 5s) while active. Optional.
        ...
```

## What you get — `self.ctx` (`ModeContext`)

| Field | What |
|-------|------|
| `ctx.robot` | `RobotController` — `set_face`, `move_head`, `say`, `set_leds`, `take_photo`, `listen`, and `supports(CAP_*)`. Always capability-guard. |
| `ctx.bus` | Event bus — `await ctx.bus.publish("my.event", **data)`; other modes (and the dashboard via WebSocket) can react. |
| `ctx.ai` | The active `AIProvider` (or `None`). `reply = await ctx.ai.converse("...")`. |
| `ctx.ha` | The `HomeAssistant` client (or `None`) — `states()`, `call_service(...)`. |
| `ctx.config` | Manifest `config` **merged with any runtime overrides** from the store. |
| `ctx.log` | A logger. |

## Capabilities

Guard every robot call with `ctx.robot.supports(CAP_FACE | CAP_HEAD | CAP_SAY | CAP_LEDS |
CAP_PHOTO | CAP_LISTEN)`. The mock driver supports all; the real backend advertises only what
the robot actually exposes (from discovery), so a well-written mode degrades gracefully.

## Events worth knowing

Emitted onto the bus by the system; subscribe to them in `on_event`:

- `robot.face` / `robot.head` / `robot.say` / `robot.leds` — robot actions happened
- `mode.activated` / `mode.deactivated`
- `ha.motion` / `presence.detected` / `ha.door` — from the Home Assistant event bridge
- plus anything modes publish (`pomodoro.phase`, `guard.alert`, `daynight.changed`, …)

## Runtime configuration (no redeploy)

Per-mode config and enable/disable are editable at runtime and persisted to `data/store.json`:

```bash
# override a mode's config (applied immediately if active)
curl -X PUT localhost:8800/api/config/modes/focus -d '{"config":{"led_color":"green"}}'
# disable / enable a mode
curl -X POST localhost:8800/api/config/modes/guard/disabled -d '{"disabled":true}'
# switch the AI provider live
curl -X PUT localhost:8800/api/config/ai_provider -d '{"provider":"claude"}'
```

## Foreground vs ambient

- **foreground** — one active at a time; activating one deactivates the current. Activate via
  `POST /api/modes/<name>/activate`.
- **ambient** — auto-starts at boot and runs alongside the foreground (e.g. `ambient_idle`,
  `daynight`). Toggle by activating its name again.

See [plugins/pomodoro/](../plugins/pomodoro/) and [plugins/guard/](../plugins/guard/) as
templates.
