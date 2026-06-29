import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import type {
  BusEvent,
  ModeInfo,
  StatusResponse,
} from "../lib/types";

const POLL_MS = 4000;

interface DravixData {
  status: StatusResponse | null;
  statusError: string | null;
  modes: ModeInfo[];
  version: string | null;
  loadingStatus: boolean;
  loadingModes: boolean;
  /** Increments whenever a `mood.changed` event arrives (live mood refresh). */
  moodTick: number;
  refreshStatus: () => void;
  refreshModes: () => void;
  /** Apply a WS event optimistically to local status. */
  applyEvent: (event: BusEvent) => void;
}

export function useDravix(): DravixData {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [modes, setModes] = useState<ModeInfo[]>([]);
  const [version, setVersion] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadingModes, setLoadingModes] = useState(true);
  const [moodTick, setMoodTick] = useState(0);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refreshStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const s = await api.status();
      if (!mounted.current) return;
      setStatus(s);
      setStatusError(null);
    } catch (err) {
      if (!mounted.current) return;
      setStatusError(
        err instanceof ApiError
          ? err.status === 0
            ? "Core service unreachable"
            : err.detail
          : "Failed to load status",
      );
    } finally {
      if (mounted.current) setLoadingStatus(false);
    }
  }, []);

  const refreshModes = useCallback(async () => {
    setLoadingModes(true);
    try {
      const m = await api.modes();
      if (!mounted.current) return;
      setModes(m.modes ?? []);
    } catch {
      /* surfaced via status error; keep last-known modes */
    } finally {
      if (mounted.current) setLoadingModes(false);
    }
  }, []);

  // Initial load: health (for version) + status + modes.
  useEffect(() => {
    api
      .health()
      .then((h) => mounted.current && setVersion(h.version))
      .catch(() => {});
    refreshStatus();
    refreshModes();
  }, [refreshStatus, refreshModes]);

  // Poll status every 4s.
  useEffect(() => {
    const id = setInterval(refreshStatus, POLL_MS);
    return () => clearInterval(id);
  }, [refreshStatus]);

  // Optimistic updates from the event bus, so the UI reacts before the next poll.
  const applyEvent = useCallback(
    (event: BusEvent) => {
      const d = event.data ?? {};
      switch (event.type) {
        case "robot.face":
          if (typeof d.expression === "string")
            patchRobot(setStatus, { expression: d.expression });
          break;
        case "robot.head":
          patchRobot(setStatus, {
            ...(typeof d.yaw === "number" ? { head_yaw: d.yaw } : {}),
            ...(typeof d.pitch === "number" ? { head_pitch: d.pitch } : {}),
          });
          break;
        case "robot.say":
          if (typeof d.text === "string")
            patchRobot(setStatus, { last_said: d.text });
          break;
        case "robot.connected":
          patchRobot(setStatus, { online: true });
          break;
        case "robot.disconnected":
          patchRobot(setStatus, { online: false });
          break;
        case "mode.activated":
        case "mode.deactivated":
          // Mode topology changed — re-fetch the authoritative list + status.
          refreshModes();
          refreshStatus();
          break;
        case "mood.changed":
          // Patch status.mood optimistically + signal panels to refetch.
          if (d && typeof d.mood === "string") {
            setStatus((s) =>
              s && s.mood
                ? {
                    ...s,
                    mood: {
                      ...s.mood,
                      mood: d.mood as string,
                      ...(typeof d.expression === "string"
                        ? { expression: d.expression }
                        : {}),
                    },
                  }
                : s,
            );
          }
          setMoodTick((t) => t + 1);
          break;
        default:
          break;
      }
    },
    [refreshModes, refreshStatus],
  );

  return {
    status,
    statusError,
    modes,
    version,
    loadingStatus,
    loadingModes,
    moodTick,
    refreshStatus,
    refreshModes,
    applyEvent,
  };
}

function patchRobot(
  setStatus: React.Dispatch<React.SetStateAction<StatusResponse | null>>,
  patch: Partial<StatusResponse["robot"]>,
) {
  setStatus((s) => (s ? { ...s, robot: { ...s.robot, ...patch } } : s));
}
