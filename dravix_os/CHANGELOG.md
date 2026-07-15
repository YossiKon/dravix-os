# Changelog

## 0.0.95

**🌐 A dashboard page on the robot — glance at any Home Assistant view** *(firmware 35 — update both)*

- **Dashboard page (Settings → 🌐 Dashboard page)**: paste an image URL and the robot gains a
  new page in its swipe cycle that shows it full-screen. Unlike the alert/snapshot image it
  **stays put** — it doesn't drift back to the face after a few minutes — and it **refreshes
  every 15 seconds** while you're on it, so it reads like a live screen. Swipe left/right to
  reach it (it sits after the Climate page); leave the field empty and the page simply drops
  out of the cycle.
- **Show a Home Assistant dashboard** with the community **Puppet** add-on, which renders any
  dashboard to a PNG. Install it, give it a long-lived token, then point the field at e.g.
  `http://homeassistant.local:10000/lovelace/0?viewport=320x240`. Any other URL that returns
  an image works too. While *isLocal* is on, only LAN URLs are accepted.
- The URL survives a robot reboot (the add-on re-asserts it), and the entity auto-discovers —
  nothing to wire up by hand.

**🔇 "Speaks on its own" toggle — quiet unless you want the chatter**

- New switch in **Settings** (default **off**): when off, the robot talks **only** during an AI
  conversation and when you press a "say" button in the dashboard. All the ambient chatter —
  the mood engine's bored quips, the *surprises* mode, per-person greetings, scheduled/reaction
  lines, and mode alerts — is muted. Turn it on to bring the talkative companion back.
- Gated at a single point (`say(..., proactive=True)`), so nothing autonomous slips through.

**😌 Calmer at rest — moves only every so often (firmware 35)**

- The autonomous "looking around" is now much sparser: the idle glance timer slowed (9s → 14s)
  and each move fires far less often — the physical **head turns only ~once every ~3 minutes**
  (was ~once a minute) and the on-screen gaze drifts ~once every ~45s (was ~13s). It still feels
  alive, just not restless. The idle glance/drift is also now suppressed **during a conversation**
  (the attentive face no longer jumps mid-turn). For finer control, the dashboard toggles
  **"Body language (head moves)"** and **"Idle glances / motion"** still work.

**🔧 Build fix + hardening (firmware 35)**

- **Firmware compiles again on ESPHome 2026.6.5.** A stricter LVGL type made the status-bar
  update-arrows (line widgets) fail to build; fixed, and the `select .state` calls were migrated
  to `current_option()` so the next ESPHome (2026.7.0) won't break either.
- **The 🌐 dashboard no longer re-downloads while the robot sleeps** — it paused the fetch only
  for the screensaver, not for sleep, so a robot left on the dashboard fetched all night.
- **Timers ring through the mute.** A kitchen timer / reminder you explicitly set now sounds even
  when "Speaks on its own" is off (that mute is for ambient chatter, not alerts). The `fistbump`
  emote's "Boom!" now also respects the mute when it fires from an ambient surprise/reaction.
- **Backup & restore fixed.** Re-importing your own `/api/export` backup used to fail once the
  robot had run a while — the personality/agent-display state wasn't on the importable list.
- **Screen-brightness slider** no longer loses your last drag when you switch tabs right after.
- The shipped add-on image now includes the firmware version file, so the **"firmware update
  available"** nudge actually works.

**🤫 Even calmer + a mouth that stops talking (firmware 35)**

- **Moves even less often.** The idle "looking around" was slowed further (interval 14s → 20s,
  lower odds): the physical head now turns only **~once every ~7 minutes**. For an instant, no-flash
  change you can also just turn off **Body language (head moves)** in Settings.
- **Fixed: the mouth looked like it was talking even in silence.** The talking-mouth animation
  followed the media player's *state*, which can linger on "playing" after the sound has actually
  stopped. It now follows the speaker's **real audio output**, so the mouth stops the instant the
  robot does.

## 0.0.94

**🔧 Tiny fix: the robot's first idle quip after a host reboot** *(install this instead of 0.0.93 — same features, same firmware 31)*

The bored-robot self-talk timer measured "time since the machine booted" instead of "time
since the last quip", so for 10 minutes after the Proxmox host (or the add-on's first-ever
start) rebooted, the robot skipped its first idle quip. One-line fix; this was also what kept
the project's CI red for a week (fresh CI machines always look "just booted").

## 0.0.93

**🙂 People — personal face-recognition greetings + a two-stage status bar** *(firmware 31 for the new status bar — update both)*

- **People (Settings → 🙂 People)**: teach the robot who's who. Add each person with their
  own greeting line (Hebrew + English, `{name}` works inside the line) and star ⭐ one
  favourite — they get the extra-warm welcome (brighter lights + a happy head-bob). When
  the robot recognizes a familiar face it now greets that person with *their* line, and
  seeing someone it knows genuinely lifts its mood a little.
  The recognition itself comes from **Frigate face recognition** — train the faces in
  Frigate and make sure the name there matches the name you enter here (the add-on's
  `frigate_url` / `frigate_camera` options wire it up). HA `person.*` arrivals use the
  same greetings too.
- **Two-stage swipe-down status bar (firmware 31)**: one swipe down now shows just a slim
  strip — Wi-Fi, time, date and battery — instead of the big panel. Swipe down **again**
  for everything else (volume / screen / LED sliders, power line, LOCAL button, update
  arrow). Swipe up closes it from either stage. The quick glance no longer covers half
  the face.

## 0.0.92

**🎮 Live remote — watch, steer, talk and record, all in one panel** *(no re-flash needed!)*

Open the camera on the Home tab and you now get a full teleoperation panel:

- **🎥 Live view** through the robot's eyes, with the **joystick right underneath** — steer
  the head while you watch what it sees.
- **🎙 Talk through the robot** (walkie-talkie): tap, speak into your phone/PC mic, tap to
  send — your voice plays out of the robot's speaker (and its mouth moves while it plays).
  Works from anywhere the dashboard works, including via HA remote access.
- **⏺ Record video on demand**: start/stop a real MP4 recording of what the robot sees
  (with a live seconds counter and a 15-minute safety cap). Clips are finalized properly
  and land in the gallery.
- **📸 Photo + 🎬 3-2-1 selfie** buttons are right there too, and a **🖼 Gallery** button
  opens the full media manager (view / download / delete / daily ZIP) without leaving the
  panel. Everything is stored by Home Assistant's add-on storage, managed from the site.

Privacy mode blocks all of it except talking (speaker-only), as it should.

## 0.0.91

**🍄❄ The Climate page speaks Mushroom too** *(same firmware 30 — one flash covers 0.0.90+91)*

The robot's Climate screen now matches the custom pages' design language: the AC name +
live status sit in a proper Mushroom header card (tinted orange halo + dot), the −/+
temperature buttons are rounded Mushroom tiles, and every HVAC mode is a colour-accented
pill — **the ACTIVE mode lights up** (tinted fill + border): blue COOL, orange HEAT, teal
FAN, amber DRY, green AUTO, red OFF. dravix now tells the robot which mode is active via
a tiny prefix on the status line, so the highlight is always live.

## 0.0.90

**🍄 Mushroom cards — on the robot AND in the editor** *(firmware 30 + this add-on: update both)*

The robot's 3 custom screens now render your Home Assistant entities as real
[lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)-style cards: a rounded
card with a tinted icon halo + colour dot, the entity name on top and its live state
underneath. Colours follow Mushroom's per-domain accents — amber for a lit light,
blue for switches, purple for an open cover, red for an UNLOCKED lock / green when
locked, orange for active climate, indigo for playing media, teal for scripts &
scenes, grey for anything off.

**The Screens editor is now true WYSIWYG:** the dashboard preview draws the exact same
Mushroom cards — same colours, same two-line layout, live states — so what you drag is
literally what the robot shows. Pick entities, drag them anywhere on the 320×240
preview, save — three custom pages, swipe between them on the robot; a tap on a card
still toggles/runs the entity.

The **Climate page stays its own separate screen** (swipe slot after the 3 custom
pages) — unaffected by your custom dashboards, as before.

## 0.0.89

**🐾 Petting raises the head again — and HOLDS it up.** *(no re-flash needed)*

Three things touched the head on every pet, and they fought: the firmware's little
nuzzle, dravix's head-lift (raise + hold ~10 s + settle — the feedback you're supposed
to feel), and the mood emote (happy/love), whose final "back to centre" step wiped the
raised head the instant it went up. Net result: no visible head-up at all.

Now the head belongs to ONE owner during a pet: the head-lift. The mood emote still
plays its face + LEDs (blush, love-eyes, pink pulse) but keeps its hands off the head.
Pet the head → it leans up into your hand, stays up while you keep petting, and settles
back down ~10 s after you stop.

## 0.0.88

**🔒 Privacy that actually disconnects, and badges you can see** *(firmware 29 — re-flash)*

- **The camera is REALLY detached in privacy mode.** Until now dravix blocked its own
  camera endpoints — but the camera is also a Home Assistant entity, and HA itself (or
  any automation/NVR going through it) could still fetch frames. Now flipping privacy ON
  **disables the camera entity in HA's registry** — it disappears from Home Assistant on
  the spot; nothing can snapshot or stream it. Privacy OFF re-enables it and reloads the
  integration so it comes straight back. Works from every toggle path (dashboard, HA UI,
  the robot itself) and survives restarts.
- **The microphone can't be woken remotely either.** All on-device start paths already
  refused during privacy; now even a session started remotely (HA assist-satellite
  services) is killed on its very first event — no listening face, no audio.
- **On-screen badges:** privacy now shows as a proper red **PRIVACY** pill on the face
  (was faint text), and a new teal **LOCAL** pill shows whenever isLocal is on — one
  glance tells you the robot is in stay-at-home mode.
- **isLocal verified end-to-end:** with the flag on, nothing leaves the LAN — cloud AI
  blocked, the cloud MCP bridge disconnected, update checks skipped, non-LAN image URLs
  rejected. (This was already enforced — now audited and badged.)

## 0.0.87

**😵 Shake the robot — it gets dizzy!** *(firmware 28 — re-flash; the add-on bump just
ships the bundled firmware for the update indicator)*

The CoreS3's built-in BMI270 accelerometer is now wired up (the stock BSP never exposed
it). Give the robot a real shake (3 jolts within 1.5 s — picking it up gently won't
trigger it) and it reacts: **x_x dizzy eyes + a "?"**, the face wobbles side-to-side like
its inner gyro needs a second, woozy violet LEDs and a warbly little whimper — then it
settles back to its resting face. Shaking wakes it from sleep (it's literally in your
hands), but never cancels night/focus/quiet, and it won't spam — one dizzy spell per
shake session. Detection runs fully on-device at 10 Hz without flooding Home Assistant.

## 0.0.86

Round-3 sweep: three fresh audits (core / dashboard / firmware 27) — deeper fixes, remote
access, and a set of "feels alive" features.

**🌍 The dashboard now works through Home Assistant Ingress** — open it from HA's sidebar,
**including remotely via Nabu Casa**. Direct LAN access on :8800 keeps working. (All URLs
became base-relative; assets, camera stream and gallery downloads included.)

**New on the dashboard:**
- **📜 Live diary** (Life tab) — a real-time feed of the robot's inner life: pets, greets,
  mood shifts, timers, agent updates, reactions — as they happen (with instant history).
- **⚡ Quick asks** (Home) — one-tap chips: how do you feel / time / weather / agenda /
  joke / fun fact / riddle / tiny story. Saved **routines** show as one-tap chips too.
- A slow AI reply no longer freezes the whole Home page (chat has its own spinner);
  restore-from-backup refreshes the page; Diagnostics logs show newest-first; entity
  pickers close on tap-outside/Escape; new entities appear without a reload; honest
  "running on mock fallback" warning when the real driver failed (was a fake green dot).

**Robot firmware 27** *(re-flash!)*:
- **Fixes:** status-bar taps no longer fall through (holding a slider used to put the robot
  to sleep; double-tapping LOCAL started the AI!); petting a SLEEPING robot can no longer
  blind-approve an agent permission (and the prompt no longer chirps at a black screen);
  turning "Greet on approach" off no longer kills the Presence sensor; waking from the
  screensaver redraws instantly; the agent's "focused" eyes can't get stuck anymore;
  Snake/DOOM-3D no longer self-move with no remote (wrong joystick neutral); Breakout
  beeps respect "Robot sounds"/quiet/night; brightness writes no longer light a sleeping
  screen; triple-tap STOP now stops pets/plug/IR/hot/cold/head gestures too; redundant
  mode-replays no longer hammer the servo bus on every pet.
- **🌙 The mode survives reboots** — a robot that rebooted at night wakes up as a night
  robot, not a bright awake one.
- **🧹 RAM back:** removed dead code — the unreachable DOOM-lite page (+50ms interval),
  antennae, sparkles, brows, wink leftovers, and the dead hold-to-reject path (~25 widgets
  + 2 intervals).
- **🔧 Build reliability:** the M5Stack component code is now PINNED and never re-fetched —
  this removes the git-cache corruption that broke ESPHome builds ("shallow.lock exists" /
  "Directory not empty") and stops upstream changes floating under us.
- **New life:** 💗 **affection streak** — pets within 90s escalate (blush → love-eyes+purr →
  full melt with floating hearts); 🔋 a "fully charged!" happy stretch when unplugged full.

**Robot brain (core):**
- Welcome greetings and the birthday party no longer leave the LED bar burning (and the
  greeting head-perk settles back down).
- Reaction rules + scheduled actions now respect night/focus/quiet like everything else
  (add `"respect_quiet": false` to a rule that MUST fire at night). Mode changes are exempt.
- Idle self-talk is now **in your language**, varies by time of day, and is capped at one
  quip per 10 minutes; **petting reflects the bond** — a new robot is curious, a loved one
  melts (and the ♥ pet-face is no longer wiped an instant after it appears).
- Frigate face-recognition now publishes a `face.seen` event — reaction rules can key on a
  person (`{"on":"face.seen","match":{"person":"yossi"}}`) for per-person magic.
- Hardening: store.json writes throttled (~200× less flash wear from vitals); a corrupt
  store no longer gets silently overwritten with defaults (preserved as .corrupt); the AC
  page is only re-written when something changed; big gallery videos stream instead of
  loading into RAM; the notifications inbox is spoken paced (messages no longer cut each
  other off) and only spoken messages are cleared; /api/event can no longer approve agent
  permissions or flip isLocal from outside; /ws/events honors the API token; expired
  permission requests can't pile up; attention LEDs re-assert if a gesture wiped them.

## 0.0.85

Voice-session polish *(firmware 26 — re-flash; the add-on bump just ships the new bundled
firmware so the "update available" indicator works)*:

- **👂 Listening closes itself when nobody talks.** After "Okay Nabu" / a double-tap, if no
  voice is detected within **5 seconds** the robot ends the session on its own — no more
  hanging on the big-eyed listening face. Once you DO start talking it never cuts you off
  (voice-activity detection disarms the timer). Tunable via the `listen_timeout_s`
  substitution in the git-stub.
- **💛 One yellow light for the whole conversation.** The LED bar now stays YELLOW from the
  moment the robot hears you until the AI finishes speaking — the cyan "thinking" flash in
  the middle is gone (it made one conversation read as three unrelated events). At the end
  of the reply the LEDs return to whatever they were before.

## 0.0.84

User-feedback round on 0.0.83 — lights that return to themselves, and a face that always
tells you what the AI is doing.

- **💡 Every decorative light turns itself back off after a few seconds.** Reaction rules,
  scheduled actions, notifications, and the agent lamp's ambient states (working/done) now
  PULSE and auto-revert instead of leaving the LED bar burning. Only states that actively
  need you — waiting-for-permission / question / error — hold their colour until resolved.
  A colour you pick deliberately from the dashboard's LED buttons still persists (there's
  an explicit Off).
- **🎭 Face feedback for everything the AI does** *(fw 25 — re-flash)*:
  - **Talking** — the mouth now animates for ALL speech, not just on-device voice chats:
    the firmware watches its own speaker, so dashboard-chat replies, notifications, timers
    and the birthday line all move the mouth for exactly as long as the audio plays.
  - **Thinking** — while the AI composes a reply to a dashboard chat, the eyes drift up in
    the pondering face (new "AI state" slot).
  - **Focused** — while a coding agent (Claude Code etc.) is working, the robot shows the
    narrowed concentrating eyes instead of the old permanently-confused "doubt" face.
  - Listening / thinking / speaking during on-device voice conversations worked before and
    still take priority over all external hints.
  - Triple-tap STOP now also cuts external TTS mid-sentence (it only stopped pipeline speech).
- **🖼 Defaults confirmed:** the face background stays plain white and accessories stay off
  unless YOU pick one — themes/accessories are opt-in from the dashboard, exactly as before.

## 0.0.83

Full-system fix pass — the three audits (dashboard, core service, robot firmware) in one release.

**The robot feels alive again (core):**
- **😊 The face can cheer up now.** Mood no longer drifts unbounded into "sad forever" when ignored
  (boredom is floored well above the sad threshold), thresholds are symmetric (happy > 0.35 / sad <
  −0.35), and the dashboard mood text finally matches the face.
- **🎭 The face un-sticks itself.** Mood compares against what's *actually* on the face instead of a
  private cache — so a face left behind by an emote, an agent status or the dashboard is reclaimed on
  the next mood tick instead of sticking forever (the "permanently confused while Claude Code runs" bug).
- **🔋 Energy can't pin at 0 anymore.** Waking the robot manually mid-auto-nap used to latch a flag
  (persisted!) that disabled auto-napping forever; it now re-arms on wake.
- **💡 LEDs stop leaking.** Every emote restores the LED bar when it ends — no more cyan/orange bar
  burning all night after a pet, a feed or a wellness tip.
- **🌙 Agent status respects night/sleep.** A "done" report at 3 a.m. no longer talks and lights up the
  bedroom; a crashed agent no longer holds an orange LED + doubt face forever (a stale-agent sweeper
  releases the robot, and expired permission prompts are cleared server-side too).
- **🐾 A pet no longer slams the head to full pitch** (degrees were fed into the normalized head API),
  and the love emote now uses the firmware's real ♥_♥ face.
- **🛡 Robustness:** the mood/vitals/nudge loops survive bad ticks instead of dying silently; mood
  persists to disk only when it actually changed (flash wear).
- **🔤 Hebrew fixes:** permission prompts were double-reversed (now reordered once, by the driver);
  truncation now happens *before* reordering (long Hebrew lost its beginning, not its end); decimals,
  times (12:30), ranges (24>21) and English phrases inside Hebrew stay intact; brackets are mirrored.
  New add-on option `robot_rtl_fix` (leave on unless the firmware ever enables LV_USE_BIDI).
- **🗣 Language toggle applies everywhere:** agent speech, the birthday greeting and the photobooth
  countdown now honor the dashboard's live language, not just the add-on option.

**Dashboard:**
- **💾 Restore-from-backup actually works** (the file the dashboard itself exports was rejected with a
  cryptic error).
- **🌱 The Hebrew temperament sliders pointed at the WRONG trait** (RTL mirroring) — fixed.
- **Errors are readable now** — validation failures showed "[object Object]"; every call also has a
  timeout so a hung backend can't leave spinners stuck forever.
- The idle-motion toggle no longer shows ON when it's actually off; custom wellness tips load back
  into the editor; a failed Screens load offers Retry (and can't wipe your layout); the accessory
  picker reverts + explains when the robot didn't take it; saved security photos stay reachable while
  the robot is offline; timers are capped at 24 h with a clear message; double-taps can't fire actions
  twice; the fallback page's head sliders send valid values and its face list includes love/dizzy.

**Robot firmware (fw 24 — re-flash to get these):**
- **🖼 "Face background" works now** — the theme was repainted to white by the very next render within
  seconds. The face render owns the background (stars included) and the eyes go light on dark themes.
- **😵 The confused face is finally visible** — teal x-eyes + yellow "?" were near-invisible on the
  white awake face; they now pick dark marks on light backgrounds (and stay teal/yellow on dark ones).
- **🌙 Modes hold.** Petting/tickling/waving/asking no longer silently cancel night/focus/quiet; a
  sleeping robot no longer wakes because someone walked past; and it doesn't snack itself in
  do-not-disturb.
- **🤖 The head stops drifting off-centre** — shakes/nods can't restart mid-sequence anymore (each
  collision used to walk the head ±12°); reactions settle back to the mood's resting face instead of
  forcing neutral.
- **🛑 Triple-tap STOP now stops *everything*** — dance, eating, drinking, tickles, waves and greets,
  props included; the LED effect is cancelled too.
- **✨ Less flicker, less churn:** blinks no longer flicker the cheeks/x-eyes; the background is only
  repainted when it actually changes (full-screen invalidation on every blink is gone); the sleep
  animation stops once the backlight is off; the "feels hot" sweat drop survives its own reaction.

## 0.0.82

- **😐 The idle face no longer gets stuck on "happy" (blushing).** The mood engine now shows a happy
  face only when the mood is *clearly* positive (threshold raised 0.25 → 0.45), and ambient presence /
  the robot talking nudge the mood a lot less. So the face sits **neutral by default** and varies with
  real interactions (a pet, a chat) instead of staying blushing all the time. *(The restored **confused
  "x-eyes + ?" face** is a robot-firmware change — re-flash ESPHome to get it.)*

## 0.0.81

- **🔤 Hebrew on the robot's cards + AC page now reads the right way round.** The robot's LVGL screen
  has no bidirectional-text support, so logical-order Hebrew rendered **reversed / unreadable**. dravix
  already reordered greetings, wellness tips, speech and the permission line to visual order — but the
  **3 display cards** (titles + entity rows) and the **climate/AC page** (name + info) were missing that
  step, so their Hebrew came out backwards. Both now go through the same visual-reorder before being
  sent to the robot (ASCII / numbers are left untouched, and TTS still speaks the original text).

## 0.0.80

- **🗂 Screen cards now SNAP to a grid — no more overlapping.** In the drag editor each card locks to a
  2×4 grid, so they can never sit on top of each other; drag to arrange and they slot in cleanly. (The
  Mushroom look + colour chips come from the **robot firmware** — re-flash the ESPHome firmware so the
  robot shows the styled cards instead of the raw text.)

## 0.0.79

- **🩺 New "Diagnostics" tab — see WHY the robot freezes/resets, right on the dashboard.** Live robot
  health, read off Home Assistant every 5 s with **zero extra load on the robot** (the ESPHome debug
  sensors already publish): **Free RAM (heap)**, Largest Block, **Loop Time**, **Uptime**, Free PSRAM,
  WiFi, and the **last Reset Reason** — colour-coded (red when heap is low, loop-time spikes, or uptime
  stays low = it's resetting). Plus an **add-on Logs viewer** (in-memory ring buffer, newest last) with
  an all/warnings filter and a **Copy-all** button, so errors can be captured and sent along.
- **🖱️ Screens is now a drag-and-drop layout editor.** Each card is a live 320×240 preview of the
  robot's screen — drag entities anywhere (pointer-based, works on touch) and the robot places each row
  exactly there, Mushroom-style with a colour chip by state.
- **🔒 Fix: a card tap could hit the WRONG device.** An entity whose name/state contained a newline
  split into two rows, shifting every row below it, so a tap fired the wrong entity (e.g. a lock instead
  of a lamp). Now sanitized. Also fixes the drag-editor layout being silently dropped by the API before
  it reached the robot, and STOP (triple-tap) not clearing the "thinking" state.

## 0.0.78

- **🔐 Master on/off for on-robot approvals — right on the dashboard.** A new toggle on the
  AI-agent card turns the whole approve-tools-from-the-robot mechanism on or off, **no
  `settings.json` needed**. It's **OFF by default**: with it off, a permission request
  short-circuits on the server (nothing shown on the robot, `robot_ready:false`), so even an
  installed `PreToolUse` hook **can never block your agent**. Flip it **on** only when you want
  commands to wait for your tap. (Persisted; also in `/api/status` + `PUT /api/agent/prefs`.)

## 0.0.77

- **Fix: the on-robot approval could stall your agent.** The permission hook makes each matched
  tool WAIT for you to tap Approve — if the robot wasn't being watched, commands stalled for the
  full 120 s timeout. Now: (1) the default timeout is a short **20 s**; (2) the hook **fails open
  instantly when the robot is offline** (the add-on reports `robot_ready`, no one to tap → don't
  block); (3) the approval hook is now **opt-in / off by default** in the example config (only
  the non-blocking status lamp is on by default), with a loud warning and how-to-disable in
  docs/agent-bridge.md. If it's blocking you now: remove the `dravix-permission.py` `PreToolUse`
  entry from `~/.claude/settings.json` (the status-lamp hooks never block).

## 0.0.76

- **🌱 It becomes its own over weeks.** A new hidden **temperament** slowly drifts (a small,
  capped step **once per day**) toward how the robot was treated — three axes: calm↔excitable,
  shy↔bold, independent↔clingy — so no two units end up the same. It's the slow counterpart to
  the fast mood, fully local and persistent. See it grow on the dashboard's **Life** tab
  ("🌱 Temperament") and via `GET /api/personality` (also in `/api/status`).

## 0.0.75

- **🙂 Greets you by name.** The welcome mode now says who it sees — "Welcome back, Yossi!" —
  from either the arriving Home Assistant person's name **or Frigate face recognition** (it
  polls Frigate for a recognised face `sub_label` while active). A configured **primary**
  person gets an extra-warm greeting (love face + a happy double-bob). All local; falls back
  to a plain "Welcome back!" when no name is known. Configure `use_frigate_faces`,
  `frigate_camera`, `primary`, and the `{name}` greeting line from the dashboard's Modes editor.

## 0.0.74

- **📢 Physical notifications from Home Assistant.** New `POST /api/robot/notify` — the robot
  faces you + nods, pulses the LED in an event-class colour (Okabe–Ito, colour-blind-safe:
  calendar=amber, message=blue, doorbell/delivery=green, alert=red, info=teal) and optionally
  speaks. Movement is auto-dropped while it sleeps and speech is skipped while asleep. Drive it
  from an HA automation, e.g. a `rest_command`:
  ```yaml
  rest_command:
    dravix_notify:
      url: "http://<add-on>:8800/api/robot/notify"
      method: POST
      content_type: "application/json"
      payload: '{"kind":"{{ kind }}","text":"{{ text }}","say":true}'
  ```
  Then call it on a doorbell/calendar/message trigger — a glanceable, non-disruptive alert.

## 0.0.73

- **🎬 Photobooth selfie with a 3-2-1 countdown.** New **Selfie 3-2-1** button on the Camera
  card (and `POST /api/robot/photobooth`): the robot counts "3… 2… 1…" out loud with matching
  faces and amber LED pulses, flashes the LED bar white like a shutter, then snaps the shot
  into the gallery. (First of a batch of new companion-robot features being added; no flashing
  needed for this one.)

## 0.0.72

- **Shorter approval prompt on the robot.** The Approve/Reject prompt now shows a compact
  ≤2-line summary (whitespace collapsed, long commands clipped) so it fits the small screen,
  and the robot speaks the short "I need your approval" line instead of reading out a long
  command. The **dashboard still shows the full command** (it has room).

## 0.0.71

- **🖐 Head gestures now do both approve *and* reject** (firmware **v23**). While an
  Approve/Reject prompt is up: a **quick tap** on the head approves (happy nuzzle), a
  **3-second hold** rejects (a "no" head-shake). They can't be confused — one is a tap, the
  other a deliberate hold — and the back-of-head tickle is unaffected. Outside a prompt a head
  touch is still just a pet.

## 0.0.70

- **🖐 Pet the robot's head to approve** (firmware **v22**). When an Approve/Reject prompt is
  up, a pet on the head (touch zones 1–2) approves the action — same as tapping Approve — and
  the robot nuzzles happily. It only approves while a prompt is showing; the rest of the time
  a head-pet is just a pet. The back-of-head tickle is unchanged.

## 0.0.69

- **🔇 Mute a chatty agent on its own.** Each agent on the AI-agent card now has a mute
  toggle — silence one agent's speech while the others still talk (previously you could only
  mute *all* speech via display:off). Muted agents still show on the robot and dashboard.
- **● Recording indicator.** The Security card shows a pulsing **Recording video** badge when
  the guard is armed *and* set to record video (vs "Armed — photos only"), so you can tell at
  a glance whether video is being captured.
- **Snappier, clearer dashboard.** The AI-agent card's buttons now disable while a request is
  in flight and surface errors instead of failing silently.

## 0.0.68

- **✋ Approve / reject an AI agent's action from the robot's screen** (firmware **v21**).
  When Claude Code is about to run a tool, the robot pops **Approve / Reject** buttons (and
  speaks); tap one to allow or block it — or decide from the dashboard's AI-agent card. Wire
  it with the new `deploy/agent-bridge/dravix-permission.py` PreToolUse hook (scope it to the
  tools you want to gate). Fail-open: if you don't answer in time or the robot is offline, it
  falls back to Claude Code's normal prompt. Buttons are green **Approve** / vermillion
  **Reject** with words, so they're clear for any colour vision.
- **Dashboard AI-agent card**: shows the pending approval with Approve/Reject, a **Clear all**
  button, and you can now dismiss the single connected agent too.
- **Fixes from a full review sweep:** the security Gallery no longer hammers the server with a
  refetch loop while open; **dismissing an agent now actually resets the robot** (face/LED/badge
  no longer freeze on the removed agent); turning **Privacy ON blocks the camera instantly** (no
  ~1.5 s window); the on-face agent badge hides in sleep/screensaver and never truncates the
  state; the security video recorder backs off instead of hot-spinning ffmpeg on a failing
  stream; the camera stream stops cleanly on client disconnect; agent timestamps are timezone-
  correct.

## 0.0.67

- **🤖 Multiple AI agents at once + choose whose status shows.** Connect several agents
  (Claude Code in two projects, Cursor, CI…) — each reports under its own name and they all
  appear on the dashboard's **AI agent** card. The robot reflects the **winning** agent:
  *Auto* (most-urgent state wins) or *pin* one agent as primary — chosen from the site.
  Dismiss any agent; ones that go quiet 15 min stop holding the robot.
- **Choose where "whose status" shows** (Show on robot:): **🗨 Bubble** — the robot speaks +
  shows the name in its speech bubble (no flashing needed); **🏷 Badge** — a small persistent
  `name: state` label on the face (firmware **v20**); **Both** / **Off**.
- **🎨 Colour-blind-safe status colours.** The agent-status palette is now Okabe–Ito, and
  every state also carries a distinct **glyph + brightness**, so state never depends on colour
  alone. The robot LED now takes exact colours (hex → `rgb_color`), and the on-face badge is
  plain text — unambiguous for any colour vision.
- **🔒 Privacy mode hardened.** Privacy now blocks the camera at a single choke point
  (`RobotController.take_photo`) so **security snapshots, the photo ritual, and the video
  stream all yield nothing** while it's on — on top of the firmware already killing the
  microphone (wake word + voice pipeline stopped). The mic and camera are both fully off.

## 0.0.66

- **🤖 Turn the robot into a status lamp for an AI agent on your PC.** Run Claude Code
  (or Cursor, a CI job, any script) and the StackChan shows you what it's doing without
  you watching the screen: **working** (🔵 blue, concentrating face), **waiting for your
  approval** (🟠 amber — *"I need your approval."*), **has a question** (🟣 purple),
  **done** (🟢 green — *"All done."*), **error** (🔴 red), **idle**. The attention states
  speak so you look up from across the room; the ambient ones stay silent.
  - New endpoints: `POST /api/agent/status` (`state` + optional `text`/`say`/`source`) and
    `GET /api/agent/status`; the state also rides along in `/api/status`.
  - New **AI agent** card on the dashboard shows the live state, source & time, with test
    buttons — everything managed from the site.
  - Ready-to-use Claude Code wiring: a tiny `dravix-notify.py` bridge + example hooks in
    `deploy/agent-bridge/`, full guide in **docs/agent-bridge.md**. It's fail-quiet and
    LAN-only, so it never breaks your agent and fully respects isLocal.

## 0.0.65

- **🎥 Continuous video recording in Security mode.** Turn on `record_video` (Security
  plugin options) and the robot records the live camera to disk while armed — ffmpeg
  pulls the same privacy-gated stream the dashboard uses and writes `clip_seconds`-long
  `vid_HHMMSS.mp4` clips into the day-folders (`video_fps`, default 4 fps). It follows
  every existing rule: when privacy / isLocal / a quiet mode closes the stream the clip
  just ends and recording resumes when it reopens — nothing leaves your box.
- **Gallery now shows recorded clips too** (dashboard → Home → Security → Gallery): each
  day lists its clips with time & size — **▶ play**, **⬇ download**, or **🗑 delete** each
  one. Distinct from the on-demand 🎬 timelapse. Clips prune with `keep_days` like photos.

## 0.0.64

- **🖼 Security gallery — full media management** (dashboard → Home → Security →
  Gallery). Captures are grouped **by day with date & time**; you can:
  - **view** any shot full-size,
  - **download** a single photo, or a whole day as a **ZIP**,
  - build & download a **🎬 timelapse MP4** of a day (ffmpeg, bundled in the add-on),
  - **delete** a single photo, a whole day, or clear everything.
  (Captures live in the add-on's persistent `/data/security/YYYY-MM-DD/`, pruned after
  `keep_days`.)

## 0.0.63

- **❄ Control your AC from the robot's screen** (firmware v19): a new CLIMATE page in
  the swipe cycle (…GAMES → VITALS → **CLIMATE**) for the AC you picked in the Climate
  tab — big **−/+** target temperature, **COOL / HEAT / FAN / DRY / AUTO** modes,
  **OFF**, and a **FAN SPEED** cycle. It shows the live temp/mode/fan; buttons act
  immediately.
- **🔆 Brightness sliders on the robot**: swipe ⬇ now has three sliders — **volume**,
  **screen brightness**, and **LED brightness** — each live-mirroring the real value.
- **Fixed: dragging a status-bar slider changed screens.** While the status bar is
  open, horizontal drags belong to its sliders — they no longer flip cards.
- **Cleaner card rows**: toggleable entities now read as **ON / OFF** (covers
  OPEN/CLOSED, locks OPEN/LOCKED) instead of the raw `off` / `closed` state.

## 0.0.62

Plugin consistency + docs pass (no firmware change — just Update the add-on).

- **The "do-not-disturb" rule now holds everywhere.** A dedicated review found the older
  plugins didn't all respect sleep / calm modes; fixed via one shared helper:
  - **ambient_idle**: no head twitch in night/focus/quiet (and it no longer fights the
    foreground mode's face); a stale config value (`glance_yaw: 18`) that made it slam the
    head to the hard limit is fixed to `0.35`.
  - **daynight**: stopped painting the face/LEDs directly (it left the LED lit all night and
    fought the firmware's own night mode) — it now just tells the mood engine day↔night.
  - **guard**: alerts are throttled (a flapping sensor can't machine-gun), and at night the
    spoken warning is held (face + LEDs still alert).
  - **dance**: no LED disco while the robot is asleep; it now pauses idle glances so they
    don't fight the choreography, and turns the LEDs off on exit.
  - **frigate_watch**: it silently never worked on the real backend — now the robot
    downloads the snapshot itself (like the camera-image feature), throttled and DND-aware.
  - **follow**: pauses while the robot is asleep instead of chasing a phantom head position.
  - **companion**: stopped a reflex that flashed HAPPY on *every* utterance and overwrote each
    reply's real emotion; **welcome**: now wakes the robot before greeting (no more
    disembodied voice) and fixes a case that could make it literally say "None"; **pomodoro**,
    **security**, **surprises**: small guards + localization.
- **Docs refreshed**: the README cheat-sheet + feature maps now cover everything added since
  0.0.35 (volume, interactive cards, gestures, battery gauge, security, schedule, timers,
  personas/voice/memories/backup, update awareness, IR…).

## 0.0.61

The full-audit release: a bug-hunt across everything built recently (12 verified
findings — all fixed), plus complete dashboard management.

**Now manageable from the dashboard** (nothing needs the API anymore):
- 🔆 Screen brightness slider · 🎭 AI personas (pick / add / delete) · 🗣 TTS voice
  picker · 🧠 Memories (view / add / delete) · ⏲ Kitchen timers on the Home tab
  (quick 5/10/25/50-min chips, custom label, live countdown, cancel — the robot
  announces when one fires) · 💾 Backup & restore (download / upload one JSON).

**Fixed (firmware v18 + add-on):**
- Tapping a card row could actuate the WRONG entity when another row's entity had
  been renamed/removed (row alignment) — now impossible.
- A finger straight to the nose triggered boop AND greet together; LED flashes could
  fire mid-sleep; the LOCAL button showed grey after reboot while isLocal was on;
  breathing stomped the vertical part of every glance; a stale head position could be
  restored after toggling Body language off during sleep.
- Focus-mode tips are now truly bubble-only (a dravix-side wiggle bypassed the calm
  gates), and the mood engine now honors sleep/calm modes like everything else.
- The first dashboard move after a long stillness could startle the robot ("who
  touched me?!") — command order fixed.
- Over-long card text no longer wedges a card stale.

## 0.0.60

- **🕐 Day schedule**: set preset hours in Settings and the robot follows them by
  itself — e.g. 07:30 → morning (sunrise scene), 23:00 → sleep — with an optional
  spoken line per entry ("Good morning!"). Any number of entries, applied live.
  This joins the other ways it already senses the day: room light (sleep when dark,
  wake when bright) and your own HA automations (e.g. the sun entity).

## 0.0.59

Four little life-moments (firmware v17):

- **It catches a cold** 🥶: when it's genuinely cold outside (your HA weather entity,
  threshold configurable), the sneezes get frequent and it tells you "It's cold out —
  I've caught the sniffles". Warms up → back to normal.
- **Morning stretch** 🥱: waking from sleep, the head rises with a sleepy yawn face,
  then a bright-eyed shake — like it's shaking the sleep off.
- **"Nom, electricity!"** 🔌: plug in the charger while it's awake — happy face and a
  green flash.
- **📸 Photo ritual**: a new button in the dashboard's Camera section — the robot
  smiles for the shot, and the photo lands in the same gallery the security mode uses
  (shown right there too).

## 0.0.58

- **Volume control, both ends** (firmware v16): a real slider on the robot's
  swipe-down status bar (drag it — it also live-mirrors the actual speaker volume),
  and a matching 🔊 slider on the dashboard Home tab. Same speaker, always in sync.
- **It sneezes now** 🤧 (the beloved EMO bit): once in a while, among its little
  surprises — dizzy face, a shake, and an "Achoo!" that pops in its speech bubble.

## 0.0.57

- **Listening is a face, not a label** (firmware v15): when you talk to it, no more
  "Listening..." text — just the listening FACE (big curious eyes) and an attentive
  little perk-up, like it leans in.
- **A real comic speech bubble** 💬: the AI's words now appear in a bubble at the TOP
  of the screen with a tail pointing to the mouth — and the animated talking mouth
  stays fully visible while it speaks (the old bubble used to sit right on top of it).

## 0.0.56

- **Control Home Assistant FROM the robot's screen** (firmware v14): each of the 3
  cards now shows up to 4 finger-sized tappable rows — tap a row and it toggles
  lights/switches/fans/covers/locks, presses buttons, runs scripts & scenes, triggers
  automations, or flips the AC on/off. Sensors and other read-only entities just
  display. Pick what's on each card in the dashboard's Screens tab, as before.
- **Fixed: cards showed nothing.** The pusher used to trust a local "already wrote
  that" cache — but every robot reboot wipes the on-device text, so cards stayed
  blank. It now compares against the robot's REAL text and self-heals within
  seconds of any reboot (and re-discovers the slots each cycle, so device renames
  can't strand it either).
- **Dashboard language now reaches the robot**: switching English/עברית in the header
  also updates the server — wellness tips and greetings follow your language.

## 0.0.55

- **Wave at it 👋** (firmware v13): wave a hand at the robot's nose sensor (3 quick
  near/far swings) — it wakes, waves back with its head, happy face, warm flash.
- **Wellness tips follow YOU now**: they fire in *focus* too — that's exactly when
  you're at the desk (your work/gaming automations set it) — quietly (bubble only, no
  wiggle). And a new **Presence nearby** sensor (proximity) tells HA when someone is
  actually at the desk; tips are skipped when nobody's been there for 15 minutes.
  Sleep/night/quiet/away modes stay reminder-free.
- **Truly random idle motion**: it now skips beats (no fixed rhythm), varies how far
  it looks, mixes sideways glances with up/down tilts and diagonal looks, and drifts
  back near-centre instead of the exact same spot — no more "same move every time".

## 0.0.54

- **Asleep means completely still — sealed at every layer** (firmware v12). Beyond the
  firmware's own gesture gates, now: (1) the add-on drops ALL head commands (welcome
  celebrations, surprises, emotes, mood, follow…) while the robot reports
  sleep/screensaver; (2) the robot itself ignores any pitch command from any source
  while asleep. The only movements left in sleep are the intended droop when falling
  asleep and the rise when waking.

## 0.0.53

- **Status-bar polish** (firmware v11): the firmware-update indicator is now a proper
  amber **⬆ arrow icon** on the swipe-down status bar, and the battery line is clean —
  just "~2.3h left" (or "charging"); the raw W/mA readings stay available in Home
  Assistant as the INA226 sensors.

## 0.0.52

- **You now SEE firmware updates everywhere** (firmware v10):
  - **In Home Assistant**: a new `Firmware update available` sensor turns on the
    moment a newer firmware ships — build any automation/notification on it.
  - **On the robot**: an amber **FW+** badge appears on the swipe-down status bar.
  - **How it works**: the add-on writes the newest version into the robot's
    "Latest firmware" slot (every 6 h + whenever the Updates card opens); the robot
    compares it to what it's running. Fully local — works with isLocal on.
  - Updating is still one press: **Install** in ESPHome.

## 0.0.51

- **Asleep = truly still** (firmware v9): every gesture path (nudge / shake / nod) is
  now hard-blocked in sleep AND screensaver — no matter who commands it (a mood, an
  expression, a tip). Only waking itself moves the head back up.
- **Everything the robot knows is now in Home Assistant**: new diagnostic entities —
  WiFi signal (dBm), Uptime, IP address, Connected SSID, Chip temperature, Battery
  voltage — joining Battery level/charging, real power, reset reason, heap, loop time
  and the rest.

## 0.0.50

- **The every-few-minutes resets — root-caused and fixed** (firmware v8). Live
  diagnosis on the running robot: `Reset Reason = task watchdog`, average loop
  ~170 ms, every full-screen redraw 61 ms. The robot's main loop is legitimately
  heavy (animated face + on-device wake word + sensors + serial servos) — under a
  burst it starved the chip's IDLE task past the 5-second default and the watchdog
  rebooted a healthy robot. Fix: watchdog window 5s→15s, IDLE-task watching off
  (real hangs still reset via the loop's own watchdog), and quieter logging (INFO)
  to lighten every loop iteration. **Press Install in ESPHome to get firmware v8.**

## 0.0.49

Everything is now managed from the add-on dashboard in your browser:

- **🧩 Full Modes manager** (Settings): every plugin mode — follow, security, welcome,
  surprises, pomodoro, guard, dance, frigate-watch… — with run/stop, enable/disable,
  and an editor for each mode's settings (toggles for booleans, fields for
  numbers/text). Save applies live, no restart.
- **🎂 Birthday**: set your date (MM-DD) in Settings — once a year, that morning, the
  robot celebrates you: love-eyes, party lights and a spoken greeting.
- **🎁 NEW Surprises mode** (ambient): every hour or two, when awake and undisturbed,
  the robot does one small unprompted delight — a wiggle, a spin, a happy flash. The
  "it feels alive" secret of EMO/Vector, and you can tune or disable it in the Modes
  manager.
- **📝 Wellness tips editor** (Life tab): write your own reminder lines (one per
  line); empty restores the built-ins.

## 0.0.48

The "feels alive" release (firmware v7) — inspired by what people love most about
EMO, Vector, Cozmo and Eilik, plus the last gems from the original firmware:

- **It breathes.** The face rises and settles on a slow gentle sine while idle, and
  sways its head in tiny conversational moves while talking.
- **Hand-turn awareness**: twist its head by hand and it goes wide-eyed (x_x), then
  decides it liked it. And in the calm modes (night/focus/quiet) it now moves
  **zero** — body language fully off, not even slowly.
- **Boop!** Put a finger right up to its nose sensor → love-eyes + a happy nod.
- **It cares about games** (the Cozmo magic): gloats with a double-nod + green flash
  when it beats you at Rock-Paper-Scissors, huffs and turns away when it loses, and
  slumps sadly on a Simon/Flappy game-over.
- **Welcome home** 🏠 (better than Vector — HA knows you arrived): when a person
  entity flips to `home`, the robot perks toward the door, love-eyes, green LEDs and
  greets out loud. Per-person cool-down, silent in do-not-disturb modes.
- **Sleep breathing**: asleep on the charger, the LED bar breathes very dimly (EMO's
  beloved charger snooze). Wakes → instantly dark.
- **On-screen chat text**: whatever the robot says (dashboard chat / announcements)
  now also shows in its speech bubble — like the original app's text messages.

## 0.0.47

Mined the original StackChan firmware + the M5Stack BSP for unused hardware — and
wired all of it in (firmware v6):

- **The robot is an IR blaster**: the BSP ships an infrared transmitter + a ready
  "Default AC" climate entity + an IR proxy for Home Assistant — pick
  `climate.*_default_ac` in the dashboard's Climate tab and the ROBOT controls your AC.
  And with the IR **receiver**, the robot now notices when anyone uses a TV/AC remote
  in the room and glances over, curious (throttled, never in calm modes).
- **Two new expressions** (ported from the original avatar's decorators): **in love**
  (pink eyes + blush + adoring nod) and **dizzy** (x_x eyes + a shake) — plus real
  **angry eyebrows** and a **sweat drop** while busy.
- **Real LED animations**: Party now runs the light bar's built-in rainbow effect, and
  the dashboard's LED section gained effect buttons — Rainbow / Twinkle / Random / Stop.
- **Graceful motion**: calm modes (night/quiet/focus) slow the head servos to gentle,
  quiet moves; normal speed everywhere else.

## 0.0.46

- **The battery number is now the REAL one** (firmware v5): read straight from the
  AXP2101 power chip's own fuel gauge — the exact same source the original StackChan
  firmware uses — plus a true hardware charging flag (no more guessing from current
  direction). The load-compensated LiPo model from 0.0.45 stays as the automatic
  fallback. New HA entities: `Battery level` and `Battery charging`.
- **NEW Security mode** 🛡: arm it from the dashboard (Home → Security) and the robot
  becomes a guard camera — saves a snapshot every few seconds to the add-on's storage
  (browse via `/api/security/photos`), patrols with its head every few minutes, and
  stays fully steerable with live view from the dashboard — including remotely through
  Home Assistant's remote access. Day-folders auto-prune (default 7 days); everything
  stays on your box.

## 0.0.45

- **An honest battery gauge** (firmware v4). The % now comes from a real battery model,
  not a straight line: load-sag compensation using the INA226's live current (a servo
  move no longer "drops" the battery), exponential smoothing, the true 1S-LiPo discharge
  curve (that long flat 3.8V plateau), and charging detection. While charging the status
  bar shows `%+` in cyan and says "charging" instead of a made-up time-left; low battery
  turns the label red.
- The good estimate is now a proper HA sensor (`Battery`, device-class battery) — visible
  in HA, auto-discovered by dravix, and shown as a 🔋 chip on the dashboard Home tab
  (red under 20%).

## 0.0.44

- **Everything personal is now a local knob** (firmware v3): device name (run several
  robots!), wake-word model, entity prefix, battery, and room thresholds are all
  substitutions — the git-stub lists the complete set, documented; Wi-Fi stays in your
  local secrets. The repo firmware contains nothing person-specific.

## 0.0.43

- **isLocal is a pure user choice**: on or off, set by you, persisted, and never flipped
  automatically (the add-on option only seeds the very first run). ON now means
  *everything stays inside your home network* — cloud AI blocked, cloud bridge
  disconnected, LAN-only images, and no update checks leave the house.
- **Choose it on the robot too**: firmware v2 adds a "Local only" switch and a LOCAL
  button on the robot's swipe-down status bar (teal when on). The robot, Home Assistant,
  and the dashboard all stay in sync automatically.

## 0.0.42

- **Releases + rollback**: every version now gets a git tag (`v0.0.42`) and a GitHub
  Release automatically. Firmware rollback = point the ESPHome stub's `ref:` at an older
  tag and press Install; add-on rollback = revert the version (all images stay on GHCR).
- **Update visibility**: the firmware now publishes its version to HA, and Settings shows
  an **Updates** card — add-on version vs the newest release, robot firmware vs the
  firmware this release ships — with plain instructions (and no internet calls while
  isLocal is on).
- **i18n built to grow**: languages live in one registry; adding a language is one
  dictionary file (`web/src/locales/TEMPLATE.example.ts`) + one registry line — the
  header button cycles through all of them. Core tips likewise take new languages with
  a single dict entry.

## 0.0.41

- **English is now the default everywhere** (open-source ready): the dashboard opens in
  English (Hebrew auto-selected for Hebrew browsers, and the header toggle switches live),
  wellness tips default to English, and the add-on has a `language: en|he` option.
- **The robot's default name is "Dravix"** — shown in the header and known to the AI;
  rename it any time in Settings. An explicit name overrides a persona's, the default
  doesn't.

## 0.0.40

- **isLocal — master local-only switch** (Settings): when ON, only local things run —
  cloud AI providers are blocked, the cloud MCP bridge disconnects, and robot images
  load only from LAN addresses. When OFF everything behaves normally. Applied live,
  no restart, and it overrides the add-on's `local_only` option both ways.
- **Zero-setup entity wiring**: the robot's Home Assistant entities (face, head, mode,
  privacy, speaker, camera, sensors, timers…) are now AUTO-DISCOVERED by suffix — the
  Settings page shows what was found, read-only. Nothing to fill in, works with any
  device name or a renamed device.

## 0.0.39

- **Zero-config install**: the add-on now uses the Supervisor's own HA token when no
  long-lived token is pasted (leave `ha_token`/`ha_url` blank).
- **Raspberry Pi support**: aarch64 image is now built alongside amd64.
- **Works for any robot name**: the dashboard finds the robot's behaviour switches by
  suffix (no longer assumes a `dravix_*` entity prefix), and the firmware's HA entity
  prefix is now a single `substitutions:` value.
- **Dashboard**: connectivity is re-checked continuously (the online dot is live);
  offline states are shown honestly (no more frozen "Speaking…"/0% vitals); fonts are
  self-hosted (works on an internet-free LAN); chat input survives a failed send;
  climate no longer clamps to 16–30° when HA reports no limits.
- **Service hardening**: optional API token (`DRAVIX_API_TOKEN`), validated
  config import, SSRF guards on image/camera endpoints, the reaction engine survives
  bad rules, startup falls back to the mock driver instead of crashing, head control
  recovers automatically after the robot was offline.
- Wellness nudges are now bilingual (`DRAVIX_LANG`, default `en`, or the dashboard
  language) and configurable via the `wellness_tips` store key.

## 0.0.38 and earlier

See the git history.
