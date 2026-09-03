# Voice setup — making "Okay, Nabu" answer

The robot does two things by itself: it hears the wake word and it shows you it is listening.
Everything after that is Home Assistant's **Assist pipeline** — hearing your words
(speech-to-text), deciding what to say (a conversation agent) and saying it (text-to-speech).
If any of the three is missing, the robot listens, the light goes out, and nothing happens.
This page wires all three.

> The dravix dashboard checks this for you: **Settings → 🎙️ Okay Nabu** lists what the
> robot's pipeline has and what it is missing. After firmware 41 the robot also reports the
> reason for its last failed turn in the **Last voice problem** entity in Home Assistant.

## 1 · Pick your language — it decides the rest

| | Fully local (no cloud) | Needs Home Assistant Cloud |
|---|---|---|
| **English** | ✅ Whisper + Piper + the built-in agent | — |
| **Hebrew** and most other languages | Whisper hears them, but Piper has no Hebrew voice (check the current voice list in the Piper add-on) | ✅ Cloud speech-to-text + text-to-speech |

For a project whose headline switch is *isLocal*, English-local is the recommended default.
You can run an English pipeline on a Hebrew Home Assistant — the pipeline's language is its own.

## 2 · Install the engines (English, local)

Both are official add-ons: **Settings → Add-ons → Add-on Store**.

1. **Whisper** (speech-to-text). Start it. In its *Configuration* choose a model — `base-int8`
   is a good desk-robot balance on a small box; `small-int8` hears better and costs more CPU.
2. **Piper** (text-to-speech). Start it. Pick a voice you like in its *Configuration*
   (`en_US-lessac-medium` is a safe default).
3. Both register themselves under **Settings → Devices & services → Wyoming**. If a
   *Discovered* card appears there, click **Configure** — that is what creates the
   `stt.faster_whisper` and `tts.piper` entities the pipeline needs.

For Hebrew: subscribe to **Home Assistant Cloud** (Settings → Home Assistant Cloud) — it
provides both engines, then continue below and pick *Home Assistant Cloud* in each field.

## 3 · Build the pipeline

**Settings → Voice assistants → Add assistant** (or open the existing one):

| Field | Set it to |
|---|---|
| Name | anything — `Robot` |
| Language | `English` (or your cloud language) |
| Conversation agent | **Home Assistant** — controls your house, answers timers/weather, needs nothing else. For open chat, an LLM agent (OpenAI / Google / Ollama) — the *Prefer handling commands locally* toggle keeps house control local either way |
| Speech-to-text | `faster-whisper` (or *Home Assistant Cloud*) |
| Text-to-speech | `piper` + a voice (or *Home Assistant Cloud*) |
| Wake word | leave **empty** — see below |

Save it.

## 4 · Point the robot at it

**Settings → Devices & services → ESPHome → the robot** (or Voice assistants → the pipeline →
*Devices*). On the robot's device page there is an **Assistant** select — choose the pipeline
you just made. `preferred` follows whichever pipeline is starred in Voice assistants; that is
fine too. The **Finished speaking detection** select next to it is worth setting to *Relaxed*
if the robot cuts you off.

### Why there is no wake-word picker for this robot

Home Assistant's voice-assistant dialog offers to choose a wake word for satellites whose
wake word Home Assistant runs. This robot runs **its own** wake word on the device
(`micro_wake_word`), so that picker is empty or absent. It is expected — the wake word works
regardless of the pipeline, and it keeps working under privacy mode's rules (off) and offline.

## 5 · Try it

Say **"Okay, Nabu"**. The light turns **cyan** (listening); ask something; **amber** (thinking);
**green** while it answers.

If it goes quiet instead, read **Last voice problem** on the robot's device page:

| It says | It means |
|---|---|
| `heard nothing — check the pipeline's speech-to-text` | Whisper returned no words: not running, wrong language, or the microphone level — try closer, and set the model to `small-int8` |
| `no reply — check the pipeline's conversation agent` | No agent picked, or the agent had nothing to say |
| `stt-no-text-recognized`, `intent-failed`, `tts-failed` … | The pipeline's own error code — the engine it names is the one to look at |

The dashboard's **Settings → 🎙️ Okay Nabu** card runs the same check from the outside.
