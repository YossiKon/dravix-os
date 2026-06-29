# Personality, emotes & reactions

The "alive" desk-robot layer — the EMO/Vector-style behaviors.

## Mood engine

A small **persistent** affective state that makes the robot feel alive:

- **valence** (-1..1, how positive) · **arousal** (0..1, how energetic) · **affection** (0..1, bond)
- **drifts** back toward baseline over time (so a spike fades)
- **nudged by events**: being talked to / petted raise valence + affection; motion/alerts raise
  arousal; long stretches with no interaction drift it toward *bored*; night lowers energy
- **shows on the face when idle** — when no foreground mode owns the screen, the mood picks the
  expression (happy / sleepy / sad / neutral / …). A foreground mode (focus, pomodoro, …) keeps
  control of the face while active.
- **persists** across restarts (in `data/store.json`), so the robot keeps its personality.

```bash
curl localhost:8800/api/mood
# {"valence":0.5,"arousal":0.6,"affection":0.7,"mood":"excited","expression":"happy"}
```

### Interactions (petting)

The robot's hardware touch zones surface as `touch.pet` / `touch.tap` / `robot.touched` events
once that channel is wired (discovery). Until then — and from the dashboard — drive them:

```bash
curl -X POST localhost:8800/api/robot/interact -d '{"kind":"pet"}'   # pet | tap | touched | spoke
```

A pet raises valence/affection and triggers a `love` emote; tap → `curious`; etc.

## Emotes

Named animated reactions (sequences of face + head + LEDs + speech), capability-guarded so they
run on any backend:

```bash
curl localhost:8800/api/emotes                       # happy, love, fistbump, curious, yes, no, ...
curl -X POST localhost:8800/api/robot/emote -d '{"name":"fistbump"}'
```

Add your own in [`core/dravix/emotes.py`](../core/dravix/emotes.py) — each is a list of steps.

## Fun, time & weather

Little party tricks (it speaks the result + plays an emote), plus time/weather read-outs:

```bash
curl localhost:8800/api/fun                 # dice, coin, 8ball, joke, fortune
curl -X POST localhost:8800/api/fun/dice    # "I rolled a 4!" + emote
curl -X POST localhost:8800/api/fun/joke
curl -X POST localhost:8800/api/say/time    # "It's 14:30."
curl -X POST localhost:8800/api/say/weather # from DRAVIX_WEATHER_ENTITY (a HA weather.* entity)
```

And the robot does small things **on its own** when it's been ignored a while — an occasional
glance + quip (the mood engine's idle behavior), so it never feels dead on the desk.

## Reactions (event → action rules, no code)

Wire "when X happens, do Y" from config (persisted, editable live), without writing a plugin:

```bash
curl -X PUT localhost:8800/api/reactions -d '{"reactions":[
  {"name":"front-door","on":"presence.detected",
   "match":{"entity_id":"binary_sensor.front_door_person"},
   "throttle_s":30,"face":"doubt","say":"Someone is at the {entity_id}.",
   "frigate_show":"camera.front_door"}
]}'
```

A rule's `on` is any bus event (`ha.motion`, `presence.detected`, `ha.door`, `guard.alert`,
`mood.changed`, …). Actions: `face`, `leds`, `say` (templated over the event data), `frigate_show`,
`activate_mode`. `match` filters by event fields; `throttle_s` rate-limits.

## Announce

For HA automations / Frigate / anything to make the robot speak (with a matching face):

```bash
curl -X POST localhost:8800/api/announce -d '{"text":"(happy) Dinner is ready!"}'
```

Wire it from Home Assistant with a `rest_command` pointing at `/api/announce`.

## Personas (switchable personalities)

Keep several personalities and switch between them — each sets the AI **system prompt** (and a
voice / default expression). Switching the active persona rebuilds the AI provider live.

```bash
curl -X PUT localhost:8800/api/personas -d '{"personas":[
  {"name":"Buddy","system_prompt":"You are a warm, upbeat desk buddy. Short, spoken replies. Start with an emotion tag like (happy).","default_expression":"happy"},
  {"name":"Sarcastic","system_prompt":"You are a dry, witty robot. Keep it terse and a little sarcastic.","default_expression":"doubt"}
]}'
curl -X POST localhost:8800/api/personas/active -d '{"name":"Sarcastic"}'   # null = built-in default
```

The active persona is persisted; with `DRAVIX_AI_PROVIDER=ha_assist` the persona is the system
prompt dravix sends — note HA Assist may also have its own configured persona.

## Memory (it remembers things)

Tell the robot facts and it keeps them — and feeds them to the AI as context (for cloud/Ollama
providers; HA Assist owns its own pipeline).

```bash
# natural: just say it in chat
curl -X POST localhost:8800/api/ai/chat -d '{"text":"remember that I like tea","speak":false}'
# or manage directly
curl localhost:8800/api/memory
curl -X POST   localhost:8800/api/memory -d '{"text":"My standup is at 9:30"}'
curl -X DELETE localhost:8800/api/memory/<id>
```

## Routines (named macros)

A routine is a named sequence of action steps (face / leds / head / emote / say / wait /
activate_mode) — run it on demand, from a schedule, or a reaction.

```bash
curl -X PUT localhost:8800/api/routines -d '{"routines":[
  {"name":"good-morning","steps":[
    {"emote":"wake"},
    {"say":"Good morning!"},
    {"activate_mode":"companion"}
  ]}
]}'
curl -X POST localhost:8800/api/routines/good-morning/run
```

## Schedule & timers

Daily jobs (good-morning, reminders) and one-shot timers — the alarms a desk robot needs.

```bash
# daily jobs (persisted, editable live). action = say/face/emote/activate_mode
curl -X PUT localhost:8800/api/schedule -d '{"schedule":[
  {"name":"good-morning","at":"08:00","days":[0,1,2,3,4],
   "action":{"emote":"wake","say":"Good morning! Let's have a good day."}},
  {"name":"standup","at":"09:30","action":{"say":"Time for standup."}}
]}'

# one-shot timer (fires a `timer.done` event + speaks)
curl -X POST localhost:8800/api/timer -d '{"seconds":300,"label":"tea","say":"Your tea is ready."}'
```

`at` is local `HH:MM`; `days` is optional (0=Mon..6=Sun). Each job fires once per day. Timers
and `schedule.fired`/`timer.done` events also flow onto the bus, so [reactions](#reactions-event--action-rules-no-code)
can hook them too.
