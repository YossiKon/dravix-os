# Dravix

One page in Home Assistant's sidebar for your Dravix desk robot.

## What you can do on it

- **Mode**: Normal (it moves around), Busy (the head stays still) or Sleep (just a clock).
- **Private mode**: no camera and no microphone. Tap it twice to confirm; the robot restarts.
- **Sleep schedule**: when it falls asleep and when it wakes up, and whether it follows the schedule.
- **Screens**: tap a tile and pick a light, a switch, a fan, a scene, a script… from a list. Tiles
  1–4 are Screen 1 on the robot, 5–8 are Screen 2. Pick the air conditioner the same way. The robot
  restarts by itself about 20 seconds later to follow the new tile.
- **Play**: start any game on the robot, or make it show a face.
- **Voice & photos**: install the voice commands ("Okay Nabu, let's play rock paper scissors", in
  English and Hebrew) and the photo automation (photo booth and desk-guard pictures saved and sent
  to your phone) with one tap each.
- **Robot details**: what it heard last, what it answered, the firmware, and more.

## Before you start

1. The robot runs the Dravix firmware and is added to Home Assistant through ESPHome
   (see [the guide](https://github.com/YossiKon/dravix-os#install)).
2. Settings → Devices & services → ESPHome → the robot → **Configure** → turn on **Allow the device
   to perform Home Assistant actions** (the tiles, games and faces need it).

The page finds the robot by itself. Nothing to configure here.

## Privacy

The add-on never touches the robot's camera or microphone. It only reads and changes Home Assistant
entities, like the Home Assistant app does.

## Troubleshooting

- **"No robot yet"**: the robot needs Dravix firmware 2.0 or newer, and it must be in Home
  Assistant (ESPHome integration).
- **Games and faces don't start**: allow the device to perform Home Assistant actions (above).
- **"Couldn't install it"**: paste the automation yourself: Settings → Automations → Create →
  Edit in YAML, with the file from the repository (`docs/ha-voice.yaml` or `docs/ha-automations.yaml`).
