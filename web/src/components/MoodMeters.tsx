import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Mood } from "../lib/types";
import { Meter, Panel } from "./ui";

/**
 * Live mood readout for the Agent hub: valence / arousal / affection gauges.
 *
 * Seeds from `status.mood` (from the shared status poll) and re-fetches the
 * authoritative mood whenever `moodTick` changes (a `mood.changed` WS event).
 * No independent poller — it rides the existing status poll + event bus.
 */
export function MoodMeters({
  initialMood,
  moodTick,
}: {
  initialMood?: Mood;
  moodTick: number;
}) {
  const [mood, setMood] = useState<Mood | undefined>(initialMood);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Keep in sync with the status poll's mood snapshot.
  useEffect(() => {
    if (initialMood) setMood(initialMood);
  }, [initialMood]);

  const refresh = useCallback(async () => {
    try {
      const m = await api.mood();
      if (mounted.current) setMood(m);
    } catch {
      /* mood endpoint optional — keep last-known */
    }
  }, []);

  // A mood.changed event bumps moodTick → pull the authoritative values.
  useEffect(() => {
    if (moodTick > 0) refresh();
  }, [moodTick, refresh]);

  if (!mood) return null;

  return (
    <Panel eyebrow="affect" title="Mood">
      <div className="mb-3 flex items-center justify-between rounded-xl border border-line bg-panel-2/40 px-3.5 py-2.5">
        <span className="eyebrow">current</span>
        <span className="font-mono text-sm capitalize text-phosphor">{mood.mood}</span>
      </div>
      <div className="space-y-3">
        <Meter
          label="valence"
          value={mood.valence}
          display={mood.valence.toFixed(2)}
          color="phosphor"
          signed
        />
        <Meter
          label="arousal"
          value={mood.arousal}
          display={mood.arousal.toFixed(2)}
          color="amber"
        />
        <Meter
          label="affection"
          value={mood.affection}
          display={mood.affection.toFixed(2)}
          color="magenta"
        />
      </div>
    </Panel>
  );
}
