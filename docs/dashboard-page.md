# 🌐 Dashboard page — a Home Assistant view on the robot

The robot can show a **live screenshot of a Home Assistant dashboard** (or any image URL) as
its own page in the swipe cycle. Unlike the alert/snapshot image, it **stays put** — it never
drifts back to the face — and it **refreshes every 15 seconds** while you're on it, so it reads
like a live screen.

- Swipe **left/right** past the face → cards → games → vitals → climate to reach it.
- The page only joins the cycle when a **Dashboard URL** is set; clear the URL and it drops
  back out.

The robot is an ESP32 — it can't run a real browser. So it doesn't load a *web page*, it loads
an *image*. That's fine for a Home Assistant dashboard, because the community **Puppet** add-on
renders any HA dashboard to a PNG that the robot can fetch.

## Set it up

1. **Install the Puppet add-on** (by *balloob*, the founder of Home Assistant):
   - HA → **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add
     `https://github.com/balloob/home-assistant-addons`, then install **Puppet**.
   - Create a **long-lived access token** (HA → your profile → *Long-lived access tokens*) and
     paste it into the add-on's **Configuration** options. Start the add-on.
   - Puppet now serves screenshots on **port 10000**: any dashboard path you request comes back
     as a PNG. It holds the token itself — the token never goes in the URL.

2. **Point dravix at it** — dashboard → **Settings → 🌐 Dashboard page**, paste the URL, Save:

   ```
   http://homeassistant.local:10000/lovelace/0?viewport=320x240
   ```

   - `lovelace/0` is the dashboard path — swap it for the view you want (e.g.
     `lovelace/energy`, or `dashboard-mobile/0`).
   - `viewport=320x240` matches the robot's screen. Want sharper text? Ask Puppet for a larger
     shot and let the robot downscale, e.g. `viewport=480x360` (the firmware resizes to fit).
   - Puppet clips to the viewport height. To capture a whole scrollable view, use
     `viewport=320xauto` (it may then be letter-boxed on the robot).
   - Other useful Puppet params: `&zoom=1.3` (bigger UI), `&wait=3000` (wait longer for cards
     to load before the shot).

That's it — swipe to the **🌐** page. The URL survives a robot reboot (the add-on re-asserts it
every few seconds), and the firmware entity auto-discovers, so there's nothing to wire up by
hand.

## Notes & limits

- **Any image URL works**, not just Puppet — anything that returns an image the robot can
  fetch on your LAN (a camera snapshot, a Grafana render, a weather map…). A *general website*
  won't work: there's no browser on the robot to render it, and something has to turn it into an
  image first. Puppet is that "something" for HA dashboards.
- **isLocal / local-only mode**: while it's on, only **LAN** URLs are accepted (Puppet on your
  home network qualifies). Public URLs are rejected — the dashboard is meant to be a local view.
- **PNG** is Puppet's default output and what the firmware expects. If you point at a source
  that returns JPEG, use a URL that yields PNG (or the built-in *Show image* / Frigate paths,
  which already handle JPEG).
- **Screensaver**: the normal idle screensaver still dims the screen on its timer (the image
  stays, just dimmed; a touch restores it). For an always-bright wall display, raise or disable
  the screensaver timer in **Settings**.
- **Readability**: for HA data specifically, the three built-in **Screens** cards (pick entities
  per card, tap rows to control them) are far more legible on a 320×240 panel. The 🌐 page shines
  for a full dashboard with graphs, cameras, or a layout you've designed yourself.
