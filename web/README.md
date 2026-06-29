# web/ — management dashboard (Phase 2)

The full React + Vite + Tailwind dashboard lands in **Phase 2**. It will talk to the same
REST/WebSocket API the core already exposes (`/api/*`), and will manage both the new custom
modes *and* the robot's original behaviors.

Until then, the core service ships a built-in vanilla status + control page (served at `/`)
from [`core/dravix/web/static/index.html`](../core/dravix/web/static/index.html) — enough to
see live status, flip modes, move the head, set the face, talk, and chat through the AI
router.
