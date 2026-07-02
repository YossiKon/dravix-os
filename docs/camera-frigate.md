# Robot camera ⇄ Frigate — person detection and more

Everything local. Two directions:

## 1. The robot's camera INTO Frigate (person detection)

dravix serves the robot's GC0308 camera as a standard MJPEG stream that Frigate can
ingest — no extra proxy needed:

```
http://<dravix-host>:8800/camera/robot/stream.mjpeg      (≈2 fps)
http://<dravix-host>:8800/camera/robot/snapshot.jpg
```

Add to Frigate's `config.yml`:

```yaml
cameras:
  stackchan:
    ffmpeg:
      inputs:
        - path: http://<dravix-host>:8800/camera/robot/stream.mjpeg?fps=2
          input_args: -r 2 -f mjpeg
          roles: [detect]
    detect:
      width: 320      # GC0308 is a small sensor — keep detect small
      height: 240
      fps: 2
    objects:
      track: [person, cat, dog]
```

Notes:
- The stream is low-fps/low-res — fine for "someone is in front of the robot", not for
  fast motion. Raise `?fps=` up to 10 if the network allows.
- Frigate 0.16+ can also do **face recognition** on tracked persons (Settings →
  Face Recognition) — the robot can then greet people by name (see automation below).

## 2. Frigate snapshots ONTO the robot's screen

The dravix firmware exposes a **`text` entity `Show image URL`** — set it to any image
URL and the robot downloads and shows it full-screen for ~25s, then returns to its face.
Map it in the dashboard: **הגדרות → חיבור ישויות → Show-image URL**.

Ways to trigger it:
- `POST /api/robot/show_image` `{"url": "http://<frigate>:5000/api/<cam>/latest.jpg?height=240"}`
- `POST /api/frigate/show` `{"camera": "<frigate-cam>", "alert": true}` (uses `DRAVIX_FRIGATE_URL`)
- Directly from an HA automation via `text.set_value`.

**HA automation — person at the door → the robot shows them + announces:**

```yaml
alias: Robot shows who's at the door
trigger:
  - platform: mqtt
    topic: frigate/events
    payload: new
    value_template: "{{ value_json.type }}"
condition:
  - "{{ trigger.payload_json['after']['label'] == 'person' }}"
  - "{{ trigger.payload_json['after']['camera'] == 'doorbell' }}"
action:
  - service: text.set_value
    target: { entity_id: text.dravix_show_image_url }
    data:
      value: >-
        http://<frigate>:5000/api/events/{{ trigger.payload_json['after']['id'] }}/snapshot.jpg?height=240
  - service: rest_command.dravix_notify   # or POST http://<dravix>:8800/api/notify
    data: { text: "מישהו בדלת!" }
```

With Frigate face recognition, use `after.sub_label` to greet by name:
`"היי {{ trigger.payload_json['after']['sub_label'] }}!"`.

Tip: always append `?height=240` to Frigate snapshot URLs — the robot's screen is
320×240 and the download stays tiny.
