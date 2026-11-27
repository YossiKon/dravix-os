# How the Dravix firmware works

Dravix is plain ESPHome. A robot's device file (template:
[`deploy/esphome/stackchan.yaml`](../deploy/esphome/stackchan.yaml)) pulls
[`deploy/esphome/stackchan-dravix.yaml`](../deploy/esphome/stackchan-dravix.yaml) from GitHub on
every Install, and that entry brings in the modules in `deploy/esphome/v2/`.

Face spec, chosen by the owner in the Face Lab:

```
dravix-faces style=A mouth=line hands=gloves neutral=1 happy=1 love=1 sad=1 angry=1 surprised=1
sleepy=1 doubt=1 dizzy=1 greet=1 done=1 wake=3 listening=3 thinking=3 speaking=2 petted=1 timer=1
error=1 bored=1 screensaver=1 sleep=2 boot=1
```

Style **"Pebble"**: aqua (#5EF0E2) rounded-rectangle eyes on black. A thin **line** mouth appears
only when an expression needs it. **Glove** hands pop up from the bottom edge for a gesture and
drop away.

## Modules

| File | Owns |
|---|---|
| `hardware.yaml` | The M5Stack StackChan BSP, **vendored** (MIT, commit 238ba98): M5Stack declares its components as `github://m5stack/esphome-yaml/components`, which ESPHome 2026.11 rejects while loading a package. Changes are marked `# dravix:` (BLE improv removed, a camera id, a faster proximity poll) |
| `components.yaml` | Every external component source in the git-url form every ESPHome version accepts: M5Stack's drivers (pinned commit) and ours (`components-v3` tag) |
| `base.yaml` | Audio, the wake word, Assist, diagnostics, the green dot's inputs, camera frames for the games |
| `face.yaml` | The face page (LVGL), the face state machine, the HA `show_face` action |
| `face_tick.yaml` | The 30 fps render tick: every pose from the Face Lab, the 150 ms blend, the LED effect |
| `behavior.yaml` | Touch pads, IMU (shake, lift), proximity (hello, Bang! aim, desk guard), light, night, screensaver, sleep, timers, head moves |
| `screens.yaml` | Screen 1 and Screen 2 (4 tiles each) and the air conditioner, entity ids from HA text fields |
| `games.yaml` | The Games screen, the game stage and its 50 ms tick, the camera games, the HA `play_game` action |
| `modes.yaml` | Normal / Busy / Sleep (`mode_set`), the mode menu, the clock page, the status bar, the battery, idle glances, private mode, the `set_mode` and `private_mode` actions |

Images are PNGs in `deploy/esphome/v2/img/` (drawn by `make_images.py`). Builds fetch them from
the **`img-v1` tag**, so a pinned robot never sees an image change under it; a new or changed
image needs a new `img-vN` tag and a bump of `img_base` in `base.yaml`.

## Face state machine

**One variable (`g_face`), one writer (`face_set`), one renderer (the tick).** Nothing else
touches the face widgets. LEDs and head moves start in `face_set` at state entry, so they have
one writer too.

Priority, high to low: **voice error** > **voice turn** > **timer ringing** > **reactions** >
**base**. Screensaver and sleep are base modes: any touch, the wake word, a timer or someone
arriving leaves them. A request below the current priority is dropped, never queued.

| State | Trigger | Kind | Lasts | Returns to |
|---|---|---|---|---|
| neutral | default | base | while nothing else | — |
| sleepy | night hours, awake, idle | base | while true | — |
| bored | nobody around for "Bored after" | base, yawns every ~60 s | while true | — |
| screensaver | idle for "Screensaver after" (dim, still) | base mode | until any event | base |
| sleep | Sleep mode: the menu, HA's Mode, a voice command, or night + a dark room | base mode → the clock page | until the mode changes (only an automatic sleep ends by itself: morning, light) | boot |
| boot | power on, waking from sleep | one-shot | 4.0 s | base |
| happy | HA action, Chameleon | one-shot | 3.0 s | base |
| love | pet ≥ 3 s, or a hug (2 pads) | one-shot | 4.0 s | base |
| sad | HA action | one-shot | 5.0 s | base |
| angry | shaken 3× in 30 s | one-shot | 3.0 s | base |
| surprised | picked up | one-shot | 3.0 s | base |
| doubt | Assist heard nothing | one-shot | 4.0 s | base |
| dizzy | shaken | one-shot | 4.0 s | base |
| greet | someone comes close after ≥ 5 min away | one-shot | 3.0 s | base |
| done | timer set, a tile tap confirmed by HA, HA action | one-shot | 2.6 s | base |
| error | pipeline error, HA gone for 30 s | one-shot (voice priority) | 3.0 s | base |
| petted | a head pad is touched | held | while touched + 0.6 s | base (or love) |
| timer | an Assist timer finished | held | until touched, max 60 s | base |
| wake | the wake word | voice, one-shot | 1.0 s | listening |
| listening | Assist listening | voice, held | until speech ends | thinking |
| thinking | speech ended | voice, held | until the reply starts | speaking |
| speaking | the reply plays | voice, held | until the audio really stops (`voice_settle`) | base |
| hands up | Bang!: a finger pointed at it (proximity) | held | up to 10 s | shot, or base |
| shot | Bang!: a loud BOOM (or a tap) while hands up | one-shot | 3.2 s | revive |
| revive | after shot | one-shot | 2.4 s | base |

A voice turn that dies without an end event is released by the 5 s voice watchdog, so a voice
face can never stay stuck. Each one-shot plays its timeline once (intro, hold, outro back to the
neutral pose); held states loop their middle section. On every change the renderer blends the
eye geometry from the last drawn pose over 150 ms, so nothing pops.

## Modes and private mode

`g_mode` (restored) is 0 Normal, 1 Busy, 2 Sleep, and `mode_set` is its only writer. Normal adds a
glance to one side every 25–70 s on the resting face and the perk-up at the wake word; Busy gates
`head_to`; Sleep shows the dim clock page (`ui_tick` brings it back after a voice turn or a timer)
and ignores the pads, the IMU, people and light. Whatever Home Assistant asks for during a voice
turn (HA's voice commands arrive at the intent stage, before the reply) waits in `g_pend_*` and
runs from `voice_done`.

Private mode (`g_private`, restored): the microphone stops and its mute state hands out silence,
every way the microphone starts checks the flag (including a session HA starts), and toggling
restarts the robot; on a boot in private mode `on_boot` (priority 600, after the restored globals,
before the camera's setup) marks the camera failed, so it is never started.

## Games

While a game runs (`g_game ≠ 0`) the head pads are game buttons, and shake, lift, hello and
petting stay quiet. Leaving the game stage, the wake word or a ringing timer ends the game.
Rock paper scissors ends by itself after two missed picks.

The camera games never stream: the robot asks its camera for **one frame** at a time
(`request_image`), copies the JPEG in `on_image`, and decodes it with the camera library's
`jpg2rgb565` — at 1/8 (40×30) for a colour or for movement, at 1/2 (160×120, shown ×2) for a photo
or the mirror, into one PSRAM buffer. The green dot shows for two seconds after every frame, and
stays on while Follow me or the mirror runs. Photo booth and Desk guard frames fire the HA event
`esphome.dravix_photo` (`reason: photo | guard`); [`ha-automations.yaml`](ha-automations.yaml)
saves the picture and sends it to a phone.

## Honest limits

- **"Done!"** Assist doesn't tell the robot whether it performed an action or only answered.
  Done shows when a timer is set, when HA confirms a tile tap, and when an automation calls the
  robot's `show_face` action.
- **Speaking LEDs and mouth** follow a rhythm while the reply plays; nothing in the speaker path
  exposes the real output level.
- **The head keeps still while it listens and talks**: servo writes are dropped during a voice
  turn and while the speaker plays. The one exception is the Normal-mode perk-up at the wake word,
  sent before the session opens (it overlaps the chime).
- **Bang!** listens for a loud sound 15 dB over the room ("Bang loudness" sets the floor). Its
  own head move is ignored for 1.5 s.
- The camera games look at colour and movement only: no face or hand recognition.

## CI

[`.github/workflows/firmware.yml`](../.github/workflows/firmware.yml) compiles main with a device
file that includes the entry, on ESPHome 2026.8.2 and the latest release. Compile errors are
copied into the run's annotations.
