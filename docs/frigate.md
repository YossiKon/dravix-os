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
