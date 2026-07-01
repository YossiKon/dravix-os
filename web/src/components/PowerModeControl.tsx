import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useToasts } from "../hooks/useToasts";
import type { RobotMode } from "../lib/types";
import { Button, Panel, errMsg } from "./ui";

/**
 * Sleep now / Wake — flips the robot's HA `select.dravix_mode` (mode_select role)
 * between "sleep" and "awake". Only renders when the robot config actually maps a
 * mode_select entity, so it stays hidden on mock / partial backends.
 */
export function PowerModeControl() {
  const toasts = useToasts();
  const [hasMode, setHasMode] = useState(false);
  const [busy, setBusy] = useState<RobotMode | null>(null);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const cfg = await api.getRobotConfig();
        if (mounted.current) setHasMode(!!cfg.entities?.mode_select);
      } catch {
        /* config unavailable → keep the control hidden */
      }
    })();
  }, []);

  const setMode = useCallback(
    async (mode: RobotMode) => {
      setBusy(mode);
      try {
        await api.setRobotMode(mode);
        toasts.ok(mode === "sleep" ? "Robot going to sleep" : "Robot waking up");
      } catch (err) {
        toasts.error(errMsg(err));
      } finally {
        if (mounted.current) setBusy(null);
      }
    },
    [toasts],
  );

  if (!hasMode) return null;

  return (
    <Panel eyebrow="power" title="Sleep / Wake">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="subtle"
          loading={busy === "sleep"}
          disabled={busy !== null}
          onClick={() => setMode("sleep")}
        >
          😴 Sleep now
        </Button>
        <Button
          variant="primary"
          loading={busy === "awake"}
          disabled={busy !== null}
          onClick={() => setMode("awake")}
        >
          ☀️ Wake
        </Button>
        <p className="w-full font-mono text-[10px] leading-relaxed text-mute">
          Puts the robot's screen/face to sleep or wakes it via Home Assistant.
        </p>
      </div>
    </Panel>
  );
}
