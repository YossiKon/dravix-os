# Dravix v2: the restart

A desk assistant robot on the M5Stack StackChan: cute like a pet, useful like a smart speaker,
and simple to set up. **The firmware is the whole product.** Flash it, adopt it in Home
Assistant, done. No add-on is needed (the v1 add-on stays in the repo, untouched).

Face spec chosen by the owner in the Face Lab (artifact, step 3):

```
dravix-faces style=A mouth=line hands=gloves neutral=1 happy=1 love=1 sad=1 angry=1 surprised=1
sleepy=1 doubt=1 dizzy=1 greet=1 done=1 wake=3 listening=3 thinking=3 speaking=2 petted=1 timer=1
error=1 bored=1 screensaver=1 sleep=2 boot=1
```

Style **A "Pebble"**: aqua (#5EF0E2) rounded-rectangle eyes on black. A **line** mouth appears only
when an expression needs it. **Glove** hands pop up from the bottom edge for a gesture and drop
away. Everything on screen is in English.

## What it does

| Area | v2 |
|---|---|
| Voice | Home Assistant Assist satellite, on-device wake word "Okay Nabu", a face for every stage |
| Screens | Swipe from the face: Screen 1 and Screen 2 (4 tiles each), then the air conditioner |
| Personality | 22 faces, touch pads (pet / hug), shake, lift, someone approaching, night sleep |
| Privacy | A small green dot top-right whenever the microphone or the camera is sending to HA |
| Settings in HA | Volume, brightness, screensaver and sleep times, quiet mode, mic mute, wake sound, the 8 tiles + the AC entity |

## Files

`deploy/esphome/v2/` holds the firmware as modules; the owner's stub lists them all:

| File | Owns |
|---|---|
| `base.yaml` | M5Stack BSP package (pinned), our vendored servo driver, audio, wake word, Assist, diagnostics |
| `face.yaml` | The face page (LVGL), the face state machine and the 30 fps render tick |
| `behavior.yaml` | Touch pads, IMU, proximity, light, timers, screensaver and sleep |
| `screens.yaml` | The two tile screens and the AC screen, entity ids from HA text fields |
| `stub.yaml` | The tiny file the owner pastes into the ESPHome add-on |

## Face state machine

**One variable (`g_face`), one writer (`face_set`), one renderer (the tick).** Nothing else
touches the face widgets. LEDs and head moves are started by `face_set` at state entry, so they
have one writer too. The v1 freezes came from latched flags with two owners; v2 has none.

Priority, high to low: **voice error** > **voice turn** > **timer ringing** > **reactions** >
**base**. Screensaver and sleep are base modes: any touch, wake word, timer or someone arriving
leaves them. A request below the current priority is dropped, never queued.

| State | Trigger | Kind | Lasts | Returns to |
|---|---|---|---|---|
| neutral | default | base | while nothing else | — |
| sleepy | night hours, awake, idle | base | while true | — |
| bored | nobody around for `bored_after_min` | base, yawns every ~60 s | while true | — |
| screensaver | idle `screensaver_min` (dim, still) | base mode | until any event | base |
| sleep | long press, night + charger, room dark | base mode, black | until touch / wake word / morning / light | boot |
| boot | power on, waking from sleep | one-shot | 4.0 s | base |
| happy | HA action, compliment | one-shot | 3.0 s | base |
| love | pet ≥ 3 s, or a hug (2 pads) | one-shot | 4.0 s | base |
| sad | HA action | one-shot | 5.0 s | base |
| angry | shaken 3× in 30 s | one-shot | 3.0 s | base |
| surprised | picked up | one-shot | 3.0 s | base |
| doubt | Assist heard nothing (`stt-no-text-recognized`) | one-shot | 4.0 s | base |
| dizzy | shaken | one-shot | 4.0 s | base |
| greet | someone comes close after ≥ 5 min away | one-shot | 3.0 s | base |
| done | timer set, a tile toggled and HA confirmed, HA action | one-shot | 2.6 s | base |
| error | pipeline error, HA gone | one-shot (voice prio) | 3.0 s | base |
| petted | a head pad is touched | held | while touched + 0.6 s | base (or love) |
| timer | an Assist timer finished | held | until touched, max 60 s | base |
| wake | wake word | voice, one-shot | 1.0 s | listening |
| listening | Assist listening | voice, held | until speech ends; watchdog 20 s | thinking |
| thinking | speech ended | voice, held | until the reply starts; watchdog 30 s | speaking |
| speaking | reply playing | voice, held | until the audio really stops (`voice_settle`); watchdog 60 s | base |

Each one-shot plays its Face Lab timeline once (intro, hold, outro back to the neutral pose);
held states loop their middle section. On every change the renderer blends the eye geometry from
the last drawn pose over 150 ms, so nothing pops.

## Honest limits (told to the owner)

- **"Done!"** Assist does not tell the robot whether it performed an action or only answered
  (`on_intent_end` carries no response type). Done is shown when a timer is set, when a tile tap
  is confirmed by HA, and when an HA automation calls the robot's `show_face` action.
- **Speaking LEDs and mouth** follow a rhythm while the reply plays; nothing in the speaker path
  exposes the real output level.
- **Head moves never overlap sound.** Servo writes are dropped during a voice turn and while the
  speaker plays (the v1 rule, never re-measured after the servo-driver patch).

## Carried over from v1 (behaviour proven on the robot)

Wake sequencing (chime before the session, `g_voice` set first), `voice_settle`, wake-word
re-arm on reconnect + fallback, the 5 s voice watchdog, `play_sfx` as the only sound path, the
`va_media_player` volume range 0.6–1.0, servo polls suspended during a turn, the vendored
non-blocking servo driver (`components-v2`).

## Cutover

1. Stop the Dravix add-on (it would be a second owner of the face).
2. In the existing stub, keep `device_name` (same node = over-the-air Install works) and replace
   the `packages:` block with the v2 one from `stub.yaml`.
3. Install. Rollback = put the old `packages:` block back (`ref: v0.1.18`).
