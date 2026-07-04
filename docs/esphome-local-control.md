# Real local robot control — ESPHome firmware + dravix `ha` driver

This is the path to **actually controlling the StackChan** (head, face, LEDs, speech, camera)
from the dashboard and Home Assistant — **fully local, no xiaozhi cloud**. The robot is re-flashed
to **ESPHome firmware** (reversible), appears in HA as entities, and dravix drives it via its
`ha` driver. AI becomes **HA Assist** (local).

> **What's preserved:** 📷 camera (security cam → Frigate), 👆 petting (touch sensors → mood),
> head/servos, LEDs, speech. **Recreated:** 💃 dance (the built-in `dance` mode now moves the real
> servos). **Changed:** the animated face is drawn by our firmware (simpler than stock; tunable);
> on-device face-tracking is not included (the `follow` mode tracks people via Frigate instead,
> off-device); the AI moves to HA Assist.
>
> **Reversible:** re-flash the stock/xiaozhi firmware anytime via M5Burner.

## Step 0 — Back up the original firmware (your safety net) 🛡️

This makes a perfect, byte-for-byte snapshot of the robot **exactly as it is now** (xiaozhi and
all). Keep the file and you can always return to today's state.

On a computer with a USB-C cable to the robot:

```bash
pip install esptool                              # needs Python
# Put the StackChan in download mode: hold reset until the green LED, then release.
esptool read_flash 0 0x1000000 stackchan-original-backup.bin   # reads the full 16MB flash
```

Save `stackchan-original-backup.bin` somewhere safe. **To restore the original anytime:**

```bash
esptool write_flash 0 stackchan-original-backup.bin            # robot is back to exactly now
```

(esptool auto-detects the port; if needed add `--port COM3` / `--port /dev/ttyACM0`. M5Stack's
**M5Burner** also keeps the official StackChan firmwares if you ever prefer that route.)

## Step 1 — Flash the ESPHome firmware

You already run the **ESPHome Device Builder** add-on.

1. ESPHome Builder → **New device** → give it a name → skip the wizard's install step.
2. **Edit** the new device and replace ALL of its YAML with the tiny
   [deploy/esphome/stackchan-from-git.yaml](../deploy/esphome/stackchan-from-git.yaml) —
   it pulls the real firmware ([stackchan-dravix.yaml](../deploy/esphome/stackchan-dravix.yaml))
   from this repo on every build, so future firmware updates are just **Install** again.
   Edit the two Wi-Fi lines at the top; all personal knobs (device name, wake word, room
   thresholds) are commented substitutions in the same file.
3. First flash over USB-C: **Install → Plug into this computer** (the first build compiles a
   wake-word model, so it takes a while). Every later update is **Install → Wirelessly**.
4. The device joins Wi-Fi and Home Assistant discovers it
   (**Settings → Devices & services** → the new device → **Configure**).

## Step 2 — The entity ids (for reference — nothing to note down)

In HA → the StackChan device, you'll see entities like:

| Role | Typical entity |
|------|----------------|
| Face (expression) | `select.stackchan_face` |
| Head left/right | `number.stackchan_servo_x` (or `_yaw`) |
| Head up/down | `number.stackchan_servo_y` (or `_pitch`) |
| Speech (TTS) | `media_player.stackchan` |
| LED bar | `light.stackchan_*` |
| Camera | `camera.stackchan` |
| Petting | `binary_sensor.*touch*` (auto-mapped to `touch.pet`) |

## Step 3 — Point dravix at it: nothing to do

There is **no entity mapping to fill in**. The add-on's `ha` driver **auto-discovers** every
robot entity by suffix (face, head servos, mode, speaker, LEDs, camera, sensors, timers…) —
it works with any device name, or a renamed device. The dashboard's **Settings** page shows
what was found, read-only. (The add-on's `robot_entity_*` options exist only as manual
overrides for non-standard setups — leave them blank.)

## Step 4 — It's alive 🎉

Open the dashboard (**Open Web UI** on the add-on page):
- **Settings** shows the auto-wired entities that discovery found.
- The manual controls on **Home** (face buttons, head joystick, LED picker, volume) **move the
  real robot**.
- **Dance:** activate the `dance` mode — the head servos perform the routine.
- **Petting:** touch the head → the touch sensor fires `touch.pet` → the mood engine reacts.
- **Camera:** the Home tab's camera view / Frigate can use the robot's camera.
- **Talk to it:** HA Assist handles the conversation (local), and the face follows along.

## Reverting

Stop the add-on (robot keeps running its ESPHome firmware), or re-flash the stock firmware via
M5Burner to return to the original xiaozhi experience. dravix never touches the robot otherwise.
