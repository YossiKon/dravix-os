# Frigate integration (local)

Two directions, both fully local (Frigate + HA run on your box):

1. **Show a Frigate camera on the robot's screen.**
2. **Feed the robot's own camera into Frigate** so Frigate detects on it too.

---

## 1. Show a Frigate camera on the robot's screen

dravix-os fetches the snapshot from Home Assistant's camera proxy (or directly from Frigate)
and pushes it to the robot's display.

```bash
# list available camera entities
curl localhost:8800/api/frigate/cameras

# show one on the robot now (+ alert face)
curl -X POST localhost:8800/api/frigate/show \
  -H 'content-type: application/json' \
  -d '{"camera":"camera.front_door","alert":true}'

# or any image URL
curl -X POST localhost:8800/api/robot/show_image -d '{"url":"http://.../snap.jpg"}'
```

**Automatic on detection** — enable the `frigate_watch` mode and set its camera. When Frigate
reports a person/motion/door (surfaced on the bus by the [HA event bridge](../README.md)), the
robot shows that camera and looks alert:

```bash
curl -X PUT localhost:8800/api/config/modes/frigate_watch \
  -d '{"config":{"camera":"camera.front_door"}}'
curl -X POST localhost:8800/api/modes/frigate_watch/activate
```

**Requires** the robot to expose a "display image" capability (`show_image`). `discover.py`
reports whether the robot's MCP surface has it; the driver maps it automatically. If the robot
can't be told to display an arbitrary image, this is the one spot that may need the M5Stack
app's image API or a small firmware helper — we'll see from discovery.

Config: `DRAVIX_FRIGATE_CAMERA` sets a default camera; `DRAVIX_FRIGATE_URL` (optional) lets
dravix-os pull straight from Frigate instead of via HA.

---

## 2. Feed the robot's camera into Frigate

dravix-os re-serves the robot's camera as a **standard HTTP camera** that Frigate (or HA) can
ingest — so Frigate runs its local detection on the robot's view too, and the results show up
in HA like any other camera.

```
snapshot : http://<dravix-host>:8800/camera/robot/snapshot.jpg
mjpeg    : http://<dravix-host>:8800/camera/robot/stream.mjpeg   (?fps=2)
```

Add it to your Frigate config:

```yaml
# frigate.yml
cameras:
  stackchan:
    ffmpeg:
      inputs:
        - path: http://<dravix-host>:8800/camera/robot/stream.mjpeg
          roles: [detect]
    detect:
      width: 640
      height: 480
      fps: 2
    objects:
      track: [person]
```

**Requires** the robot's camera capability (`take_photo` / a stream) on its control surface.
The relay polls `take_photo` at `fps` and re-emits MJPEG; if the robot exposes a native RTSP/
MJPEG stream, we can proxy that directly instead (one driver change once discovery confirms the
stream URL). On the mock driver these endpoints return `503` (no real frames) — by design.

All of this stays on your LAN: robot → dravix-os → Frigate → Home Assistant.

---

## 3. Follow mode — real-time head tracking

Once the robot's own camera is tracked in Frigate (section 2 above), dravix can make the
**robot's head follow a person in real time**. dravix asks Frigate where the person is in the
robot's camera frame and nudges the head to re-centre them — a small P-controller running on the
normalised `move_head(-1..1)` facade.

All the vision work stays on the **Frigate host**; the ESP32 only receives head commands. So this
adds **no load to the robot** (no extra CPU, no reboots) — the tracking is entirely off-device.

It's a **foreground plugin mode** called `follow`. Activate it from the dashboard (Modes) or the
API. Point it at the Frigate camera that sees you (the robot's own camera, re-served in section 2)
and give it your Frigate base URL:

```bash
# configure, then activate
curl -X PUT localhost:8800/api/config/modes/follow \
  -H 'content-type: application/json' \
  -d '{"config":{"camera":"stackchan","label":"person","frigate_url":"http://<frigate>:5000"}}'
curl -X POST localhost:8800/api/modes/follow/activate
```

(`frigate_url` falls back to `DRAVIX_FRIGATE_URL` if left blank.) When it loses you for
`lost_timeout` seconds it eases the head back to centre (`recenter_when_lost`).

**Requires a real, movable head** — i.e. the `ha` driver against the ESPHome firmware (`CAP_HEAD`).
On the mock driver, or any backend without a head, `follow` just logs a warning and does nothing.

### Tuning (live, no redeploy)

Every knob is a per-mode config value, editable at runtime via `PUT /api/config/modes/follow` — so
you can tune it live from the dashboard while watching the robot:

```bash
curl -X PUT localhost:8800/api/config/modes/follow \
  -H 'content-type: application/json' \
  -d '{"config":{"gain_yaw":0.5,"gain_pitch":0.4,"deadzone":0.12,"invert_yaw":false,"update_hz":2.0}}'
```

| Knob | What it does |
|------|--------------|
| `gain_yaw` / `gain_pitch` | How hard the head turns/tilts toward you (the P gains). |
| `deadzone` | Ignore small offsets so it doesn't jitter (fraction of the half-frame). |
| `invert_yaw` / `invert_pitch` | Flip if it moves the wrong way. |
| `update_hz` | Tracking updates per second. |
| `camera` / `label` / `frigate_url` | Which Frigate camera, what to follow, and where Frigate lives. |

> **On smoothness:** the robot's servo bus is capped at roughly **2 Hz**, so `update_hz` above ~2
> doesn't help — the result is *smooth with a slight lag, not instant*. That's expected.

> **Matching your Frigate version:** the detection box is read from Frigate's event data, and its
> shape varies between versions. If tracking is offset or inverted, check `box_format`
> (`xywh` vs `xyxy`) and the `frame_w` / `frame_h` you tell dravix the detector runs at.

See [`plugins/follow/plugin.yaml`](../plugins/follow/plugin.yaml) for the full, commented list of
config options (including `max_step`, `speed`, `lost_timeout` and `recenter_when_lost`).
