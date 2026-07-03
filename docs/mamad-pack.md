# The Mamad Pack — the robot as a work-room / security-room companion

For desks that live in a work/gaming room which doubles as the apartment's mamad
(reinforced security room — common in Israeli homes). Everything below is
**HA automations only — no reflash needed**
(uses the entities the dravix firmware already exposes: `select.dravix_mode`,
`sensor.dravix_state`, `light.dravix_stackchan_light_bar`, `text.dravix_show_image_url`).

First add these helpers to `configuration.yaml` (once) — replace `<DRAVIX_HOST>` with the
address of the machine running the dravix-os add-on/service (e.g. your HA host's IP):

```yaml
rest_command:
  dravix_announce:
    url: "http://<DRAVIX_HOST>:8800/api/announce"
    method: post
    content_type: application/json
    payload: '{"text": "{{ text }}", "expression": "{{ expression | default(''neutral'') }}"}'
  dravix_emote:
    url: "http://<DRAVIX_HOST>:8800/api/robot/emote"
    method: post
    content_type: application/json
    payload: '{"name": "{{ name }}"}'
```

## 1 · צבע אדום — the robot is the alert companion

Install **Oref Alert** from HACS (`amitfin/oref_alert`), pick your city in its config flow.
It creates `binary_sensor.oref_alert` (on during an alert for your areas).

```yaml
automation:
  - alias: "רובוט — צבע אדום"
    trigger:
      - platform: state
        entity_id: binary_sensor.oref_alert
        to: "on"
    action:
      # wake up, kill light-shows, go RED
      - service: select.select_option
        target: { entity_id: select.dravix_mode }
        data: { option: awake }
      - service: light.turn_on
        target: { entity_id: light.dravix_stackchan_light_bar }
        data: { rgb_color: [255, 0, 0], brightness_pct: 100 }
      - service: rest_command.dravix_announce
        data: { text: "צבע אדום! כולם לממד", expression: "angry" }
      # show the entrance camera on the robot's screen so you can see everyone coming
      - service: text.set_value
        target: { entity_id: text.dravix_show_image_url }
        data:
          value: "http://<FRIGATE_IP>:5000/api/<ENTRANCE_CAM>/latest.jpg?height=240"

  - alias: "רובוט — סוף אזעקה (אחרי 10 דקות שהייה)"
    trigger:
      - platform: state
        entity_id: binary_sensor.oref_alert
        to: "off"
        for: "00:10:00"        # Home-Front guidance: stay 10 minutes
    action:
      - service: light.turn_on
        target: { entity_id: light.dravix_stackchan_light_bar }
        data: { rgb_color: [0, 255, 80], brightness_pct: 60 }
      - service: rest_command.dravix_announce
        data: { text: "האירוע הסתיים, אפשר לצאת מהממד", expression: "happy" }
      - delay: "00:00:10"
      - service: light.turn_off
        target: { entity_id: light.dravix_stackchan_light_bar }
```

## 2 · פומודורו — the robot makes you take breaks

Uses the live `sensor.dravix_state` — when you've been in **focus** (🎯 מרוכז) for 50
minutes straight, the robot interrupts you, kindly.

```yaml
automation:
  - alias: "רובוט — פומודורו: הפסקה אחרי 50 דקות ריכוז"
    trigger:
      - platform: state
        entity_id: sensor.dravix_state
        to: "focus"
        for: "00:50:00"
    action:
      - service: rest_command.dravix_announce
        data: { text: "עברו חמישים דקות. קום, תימתח, שתה מים", expression: "happy" }
      - service: rest_command.dravix_emote
        data: { name: "happy" }
```

(Every re-entry to focus restarts the 50-minute count automatically.)

## 3 · גיימינג — auto do-not-disturb

Easiest path: the official **Steam** integration (Settings → Integrations → Steam,
needs a Steam API key). Your Steam sensor exposes the current game.

```yaml
automation:
  - alias: "רובוט — מצב מרוכז כשמשחק"
    trigger:
      - platform: template
        value_template: "{{ state_attr('sensor.steam_YOURID', 'game') not in (none, '') }}"
    action:
      - service: select.select_option
        target: { entity_id: select.dravix_mode }
        data: { option: focus }

  - alias: "רובוט — חזרה לער כשמפסיק לשחק"
    trigger:
      - platform: template
        value_template: "{{ state_attr('sensor.steam_YOURID', 'game') in (none, '') }}"
        for: "00:03:00"
    action:
      - service: select.select_option
        target: { entity_id: select.dravix_mode }
        data: { option: awake }
```

(Non-Steam games / consoles: HASS.Agent on the PC exposes an ActiveWindow sensor —
trigger on your game's window title instead.)

## 4 · שומר אוויר — the mamad is a sealed room

A mamad gets stuffy fast (CO₂ → fatigue, headaches, worse aim 😉). Buy a **Sensirion
SCD40/SCD41** board (~₪80-120) + any ESP32; flash with:

```yaml
# minimal ESPHome node for the air sensor
esphome: { name: mamad-air }
esp32: { board: esp32dev }
wifi: { ssid: !secret wifi_ssid, password: !secret wifi_password }
api:
ota: [ { platform: esphome } ]
i2c: { sda: 21, scl: 22 }
sensor:
  - platform: scd4x
    co2: { name: "Mamad CO2", id: co2 }
    temperature: { name: "Mamad Temperature" }
    humidity: { name: "Mamad Humidity" }
```

Then:

```yaml
automation:
  - alias: "רובוט — מחניק בממד"
    trigger:
      - platform: numeric_state
        entity_id: sensor.mamad_co2
        above: 1200
        for: "00:05:00"
    action:
      - service: rest_command.dravix_announce
        data: { text: "מחניק פה. פתח את הדלת לדקה", expression: "doubt" }
  - alias: "רובוט — ממש מחניק בממד"
    trigger:
      - platform: numeric_state
        entity_id: sensor.mamad_co2
        above: 1600
    action:
      - service: light.turn_on
        target: { entity_id: light.dravix_stackchan_light_bar }
        data: { rgb_color: [255, 120, 0], brightness_pct: 80 }
      - service: rest_command.dravix_announce
        data: { text: "רמת פחמן דו חמצני גבוהה מאוד, תאוורר עכשיו", expression: "angry" }
```

Tip: put the CO₂ on one of the robot's swipe cards (dashboard → מסכים).

## 5 · WiFi בממ"ד

Concrete+steel walls attenuate WiFi. Swipe DOWN on the robot → the status page shows
`WiFi -XX dB`. Below **-75 dB** consistently → consider an AP/mesh node near the room
(affects the robot's voice latency and Frigate stream stability).
