# Real local robot control — ESPHome firmware + dravix `ha` driver

This is the path to **actually controlling the StackChan** (head, face, LEDs, speech, camera)
from the dashboard and Home Assistant — **fully local, no xiaozhi cloud**. The robot is re-flashed
to **ESPHome firmware** (reversible), appears in HA as entities, and dravix drives it via its
`ha` driver. AI becomes **HA Assist** (local).

> **What's preserved:** 📷 camera (security cam → Frigate), 👆 petting (touch sensors → mood),
> head/servos, LEDs, speech. **Recreated:** 💃 dance (the built-in `dance` mode now moves the real
> servos). **Changed:** the animated face is drawn by our firmware (simpler than stock; tunable);
> face-tracking is not included; the AI moves to HA Assist.
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

1. Add two secrets in ESPHome (`secrets.yaml`): `wifi_ssid`, `wifi_password`, and a
   `stackchan_api_key` (ESPHome can generate an encryption key for you).
2. ESPHome Builder → **New device** → ESP32-S3 (M5Stack CoreS3). Replace the generated YAML with
   [deploy/esphome/stackchan-dravix.yaml](../deploy/esphome/stackchan-dravix.yaml).
3. **Install → Manual download → Factory format.**
4. Connect the StackChan by USB-C, hold reset until the green LED, open <https://web.esphome.io/>,
   **Connect → Install** the downloaded factory `.bin`.
5. Press reset. The device joins Wi-Fi and Home Assistant discovers it
   (**Settings → Devices & services → ESPHome → Configure**, enter the API key).

> **First-flash tuning (normal for custom firmware):** open the device page in HA / the ESPHome
> logs and note the real ids for the **display**, **microphone**, **speaker**. Set them in the two
> `TODO` spots in the YAML (`m5core_display`, `mic`, `spkr`) and re-install. The hardware entities
> (servos/camera/touch/LEDs) work immediately; the **face drawing** + **voice** are the parts you
> may adjust once.

## Step 2 — Note the entity ids

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

## Step 3 — Point dravix at it (add-on Configuration)

In the **dravix-os** add-on → **Configuration**:

```
robot_driver: ha
robot_entity_face:         select.stackchan_face
robot_entity_head_yaw:     number.stackchan_servo_x
robot_entity_head_pitch:   number.stackchan_servo_y
robot_entity_media_player: media_player.stackchan
robot_entity_light:        light.stackchan_led
robot_entity_camera:       camera.stackchan
```

Leave `xiaozhi_mcp_url` blank (that's the cloud path). **Save → Restart.**

## Step 4 — It's alive 🎉

Open the dashboard → **Console**:
- System Status shows **DRIVER: ha**, and the **Capabilities** row lights up Say / Set Face /
  Move Head / Set Leds / Take Photo.
- The manual controls (face buttons, head sliders, LED picker) now **move the real robot**.
- **Dance:** activate the `dance` mode — the head servos perform the routine.
- **Petting:** touch the head → the touch sensor fires `touch.pet` → the mood engine reacts.
- **Camera:** the Cameras tab / Frigate can use `camera.stackchan`.
- **Talk to it:** HA Assist handles the conversation (local), and the face follows along.

## Reverting

Stop the add-on (robot keeps running its ESPHome firmware), or re-flash the stock firmware via
M5Burner to return to the original xiaozhi experience. dravix never touches the robot otherwise.
