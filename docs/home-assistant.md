# Home Assistant ↔ dravix-os — easy integration

dravix-os already speaks both directions with Home Assistant:

- **HA → robot**: call dravix-os's HTTP API from HA (announce, notify, agenda, run a routine,
  play an emote, show a camera, …). Copy-paste `rest_command`s below.
- **robot ← HA**: the built-in **event bridge** turns HA motion/presence/door events into bus
  events, which `guard`/`frigate_watch`/your reactions react to (no config needed beyond a HA
  token). See [../README.md](../README.md).

Set `DRAVIX_HA_URL` + `DRAVIX_HA_TOKEN` in dravix-os (a long-lived token from your HA profile),
and point the URL below at the dravix-os host (`http://<dravix-host>:8800`).

## 1. Add `rest_command`s (HA `configuration.yaml`)

```yaml
rest_command:
  dravix_announce:
    url: "http://dravix-host:8800/api/announce"
    method: POST
    content_type: "application/json"
    payload: '{"text": "{{ text }}"}'

  dravix_notify:                       # queue/speak a notification
    url: "http://dravix-host:8800/api/notify"
    method: POST
    content_type: "application/json"
    payload: '{"text": "{{ text }}", "speak": {{ speak | default(true) | tojson }}}'

  dravix_emote:                        # play a named emote
    url: "http://dravix-host:8800/api/robot/emote"
    method: POST
    content_type: "application/json"
    payload: '{"name": "{{ name }}"}'

  dravix_routine:                      # run a saved routine by name
    url: "http://dravix-host:8800/api/routines/{{ name }}/run"
    method: POST

  dravix_agenda:
    url: "http://dravix-host:8800/api/say/agenda"
    method: POST
  dravix_weather:
    url: "http://dravix-host:8800/api/say/weather"
    method: POST
  dravix_show_camera:
    url: "http://dravix-host:8800/api/frigate/show"
    method: POST
    content_type: "application/json"
    payload: '{"camera": "{{ camera }}", "alert": true}'
```

Then call them from anywhere in HA: **Developer Tools → Services →** `rest_command.dravix_announce`
with `{"text": "Dinner is ready!"}`.

## 2. Example automations

```yaml
automation:
  - alias: "Welcome home"
    trigger: { platform: state, entity_id: person.you, to: "home" }
    action:
      - service: rest_command.dravix_emote
        data: { name: "happy" }
      - service: rest_command.dravix_announce
        data: { text: "Welcome home!" }

  - alias: "Front door person → show camera"
    trigger: { platform: state, entity_id: binary_sensor.front_door_person, to: "on" }
    action:
      - service: rest_command.dravix_show_camera
        data: { camera: "camera.front_door" }

  - alias: "Good morning"
    trigger: { platform: time, at: "08:00:00" }
    action:
      - service: rest_command.dravix_routine
        data: { name: "good-morning" }
```

> Prefer to keep it all inside dravix-os? Use its own **scheduler** (`/api/schedule`) and
> **reactions** (`/api/reactions`) instead of HA automations — same result, no HA YAML.

## 3. Notifications as a HA `notify` target (optional)

```yaml
notify:
  - name: stackchan
    platform: rest
    resource: "http://dravix-host:8800/api/notify"
    method: POST_JSON
    data_template: { text: "{{ message }}" }
```

Now `notify.stackchan` makes the robot speak any HA notification.

## Going back to the original — always, easily

dravix-os **never touches the robot's firmware**. To return to the stock experience, just stop
dravix-os (turn off the add-on / `docker compose down` / stop the LXC). The robot is exactly as
it shipped — original app, OTA updates, all stock features. The HA `rest_command`s above simply
stop responding; remove them from HA if you like. And the code's original state is preserved on
git `main` (`git checkout main`).
