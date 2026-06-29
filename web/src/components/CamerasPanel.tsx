import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { humanize } from "../lib/format";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, cx, errMsg } from "./ui";

const ROBOT_CAM_URL = "/camera/robot/snapshot.jpg";
const REFRESH_MS = 1000;

export function CamerasPanel() {
  const toasts = useToasts();
  const [cameras, setCameras] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [alert, setAlert] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const c = await api.frigateCameras();
      if (mounted.current) setCameras(c.cameras ?? []);
    } catch {
      // Frigate may be unconfigured (404/501/502) — treat as "no cameras".
      if (mounted.current) setCameras([]);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function showOnRobot(camera: string) {
    setBusy(camera);
    try {
      await api.frigateShow(camera, alert[camera] ?? false);
      toasts.ok(`Showing ${humanize(camera)} on robot`);
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Panel
        eyebrow="frigate"
        title="Cameras"
        right={
          <Button variant="subtle" onClick={refresh} loading={loading}>
            ⟳ Refresh
          </Button>
        }
      >
        {loading && cameras.length === 0 ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-xl bg-line/60" />
            ))}
          </div>
        ) : cameras.length === 0 ? (
          <p className="font-mono text-[11px] text-mute">
            No Frigate cameras available.
          </p>
        ) : (
          <div className="space-y-2">
            {cameras.map((cam) => (
              <div
                key={cam}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-panel-2/40 px-3.5 py-2.5"
              >
                <span className="min-w-0 flex-1 truncate font-display text-sm font-600 text-ink">
                  {humanize(cam)}
                </span>
                <label className="flex cursor-pointer items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-mute">
                  <input
                    type="checkbox"
                    checked={alert[cam] ?? false}
                    onChange={(e) =>
                      setAlert((a) => ({ ...a, [cam]: e.target.checked }))
                    }
                    className="h-3.5 w-3.5 accent-amber"
                  />
                  alert
                </label>
                <Button
                  variant="primary"
                  loading={busy === cam}
                  disabled={busy !== null && busy !== cam}
                  onClick={() => showOnRobot(cam)}
                >
                  Show on robot
                </Button>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel eyebrow="onboard" title="Robot Camera">
        <RobotCamera />
      </Panel>
    </div>
  );
}

/* ── Robot camera snapshot (refreshes ~1s, graceful on error) ───────────── */
function RobotCamera() {
  const [src, setSrc] = useState<string | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (!cancelled) setSrc(`${ROBOT_CAM_URL}?t=${Date.now()}`);
    };
    tick();
    const id = setInterval(tick, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-line bg-void/80">
      {/* grid backdrop shown behind / when no feed */}
      <div className="absolute inset-0 [background:linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:18px_18px]" />
      {src && (
        <img
          src={src}
          alt="Robot camera"
          onError={() => setErrored(true)}
          onLoad={() => setErrored(false)}
          className={cx(
            "absolute inset-0 h-full w-full object-cover",
            errored && "hidden",
          )}
        />
      )}
      {errored && (
        <div className="absolute inset-0 grid place-items-center">
          <div className="text-center">
            <div className="mx-auto mb-2 grid h-10 w-10 place-items-center rounded-full border border-line/70 text-mute">
              ⊘
            </div>
            <p className="font-mono text-[11px] uppercase tracking-wider text-mute">
              robot camera unavailable
            </p>
          </div>
        </div>
      )}
      <div className="absolute right-2 top-2 flex items-center gap-1.5 rounded-full border border-line bg-void/70 px-2 py-1 backdrop-blur">
        <span
          className={cx(
            "inline-block h-1.5 w-1.5 rounded-full",
            errored
              ? "bg-mute"
              : "animate-pulse-dot bg-fault shadow-[0_0_8px_2px_rgba(255,90,82,0.5)]",
          )}
        />
        <span className="font-mono text-[9px] uppercase tracking-wider text-soft">
          {errored ? "no feed" : "live"}
        </span>
      </div>
    </div>
  );
}
