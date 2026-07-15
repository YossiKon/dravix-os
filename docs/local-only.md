# Running fully local (no cloud)

dravix-os is built local-first. With `DRAVIX_LOCAL_ONLY=true` (the default), it refuses cloud
AI providers and keeps everything on your own box. Nothing in dravix-os phones home — it only
talks to your **Home Assistant**, your **robot**, and your chosen **LLM**, all on your LAN.

## The three places "cloud" could sneak in — and how we keep them local

### 1. The AI brain
- **`DRAVIX_LOCAL_ONLY=true`** makes `build_provider` reject `claude`/`openai`. Allowed:
  - `ha_assist` — Home Assistant's Assist pipeline. **Configure HA with a local pipeline** for
    end-to-end local voice: **Ollama** (LLM) + **faster-whisper** (STT) + **Piper** (TTS).
    dravix-os just forwards text; HA owns the models.
  - `ollama` — dravix-os talks to your local Ollama directly (`DRAVIX_OLLAMA_URL`,
    `DRAVIX_OLLAMA_MODEL`). No HA needed for chat.
- To deliberately use a cloud model, set `DRAVIX_LOCAL_ONLY=false` *and* pick `claude`/`openai`.

### 2. The robot
The robot runs the **dravix ESPHome firmware**, which talks **only to your Home Assistant** on the
LAN — no M5Stack cloud, no phone-app "agent." dravix-os drives it through the HA entities that
firmware exposes (the `ha` driver), so all robot control stays inside your network.

> If you're coming from the stock M5Stack firmware, flashing the dravix ESPHome firmware (see
> [esphome-local-control.md](esphome-local-control.md)) is what makes the robot fully local — it
> replaces the cloud/app path entirely.

### 3. Cameras (Frigate)
Frigate runs on your box; HA proxies its snapshots locally. dravix-os fetches frames via your
HA / Frigate on the LAN — see [frigate.md](frigate.md). No cloud.

## Network posture

| dravix-os talks to | When |
|--------------------|------|
| Home Assistant (`DRAVIX_HA_URL`, LAN) | Assist, events, camera snapshots, services |
| The robot (via Home Assistant, LAN) | All robot control (dravix ESPHome firmware → HA entities) |
| Ollama (`DRAVIX_OLLAMA_URL`, LAN/localhost) | Local LLM chat (if selected) |
| Frigate (`DRAVIX_FRIGATE_URL`, LAN) | Optional direct snapshots |
| **the internet** | **only** if you opt into a cloud AI provider |

The project permission allowlist also blocks outbound shell calls by default — see
`.claude/settings.local.json`.
