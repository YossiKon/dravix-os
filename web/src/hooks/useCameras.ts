import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

/**
 * Probes the Frigate cameras endpoint once to decide whether a Cameras page is
 * worth showing. Used purely for tab gating — the CamerasPanel does its own
 * (live) fetch. Returns null while unknown so the tab can stay hidden until we
 * know, then true/false.
 */
export function useHasCameras(): boolean | null {
  const [count, setCount] = useState<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    api
      .frigateCameras()
      .then((c) => {
        if (mounted.current) setCount(c.cameras?.length ?? 0);
      })
      .catch(() => {
        // Frigate unconfigured (404/501/502) → treat as no cameras.
        if (mounted.current) setCount(0);
      });
    return () => {
      mounted.current = false;
    };
  }, []);

  return count === null ? null : count > 0;
}
