import { useMemo, useState } from "react";
import type { WsStatus } from "../hooks/useWebSocket";
import { clockTime } from "../lib/format";
import type { BusEvent } from "../lib/types";
import { Button, Dot, Panel, cx } from "./ui";

// Color-code event types by their namespace / verb.
function toneFor(type: string): { text: string; chip: string } {
  if (type.includes("error") || type.includes("fault"))
    return { text: "text-fault", chip: "border-fault/40 bg-fault/10 text-fault" };
  if (type.startsWith("mode."))
    return {
      text: "text-phosphor",
      chip: "border-phosphor/40 bg-phosphor/10 text-phosphor",
    };
  if (type.includes("connect"))
    return { text: "text-cyan", chip: "border-cyan/40 bg-cyan/10 text-cyan" };
  if (type.startsWith("mood") || type.startsWith("robot.emote"))
    return {
      text: "text-magenta",
      chip: "border-magenta/40 bg-magenta/10 text-magenta",
    };
  if (type.startsWith("robot.face") || type.startsWith("robot.say"))
    return { text: "text-amber", chip: "border-amber/40 bg-amber/10 text-amber" };
  if (type.startsWith("robot.head"))
    return {
      text: "text-magenta",
      chip: "border-magenta/40 bg-magenta/10 text-magenta",
    };
  return { text: "text-soft", chip: "border-line bg-panel-2 text-soft" };
}

function summarize(data: Record<string, unknown>): string {
  const keys = Object.keys(data ?? {});
  if (keys.length === 0) return "";
  const parts = keys.slice(0, 4).map((k) => {
    const v = data[k];
    const s =
      typeof v === "object" && v !== null ? JSON.stringify(v) : String(v);
    return `${k}=${s.length > 40 ? s.slice(0, 39) + "…" : s}`;
  });
  return parts.join("  ");
}

export function EventsLog({
  log,
  status,
  onClear,
}: {
  log: BusEvent[];
  status: WsStatus;
  onClear: () => void;
}) {
  const [paused, setPaused] = useState(false);
  // Snapshot when paused so the feed visually freezes.
  const frozen = useMemo(() => (paused ? log.slice() : log), [paused, log]);

  const statusMeta = {
    connected: { color: "cyan" as const, label: "live" },
    connecting: { color: "amber" as const, label: "connecting" },
    disconnected: { color: "gray" as const, label: "disconnected" },
  }[status];

  return (
    <Panel
      eyebrow="event bus"
      title="Live Events"
      className="flex h-full flex-col"
      bodyClassName="flex-1 flex flex-col min-h-0"
      right={
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-full border border-line bg-panel/70 px-2.5 py-1">
            <Dot color={statusMeta.color} pulse={status === "connected"} />
            <span className="font-mono text-[10px] uppercase tracking-wider text-soft">
              {statusMeta.label}
            </span>
          </span>
        </div>
      }
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {frozen.length} event{frozen.length === 1 ? "" : "s"}
          {paused && " · paused"}
        </span>
        <div className="flex gap-1.5">
          <Button
            variant="subtle"
            className="px-2.5 py-1"
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? "▸ Resume" : "❚❚ Pause"}
          </Button>
          <Button
            variant="subtle"
            className="px-2.5 py-1"
            disabled={log.length === 0}
            onClick={onClear}
          >
            Clear
          </Button>
        </div>
      </div>

      <div className="scrollbar-thin -mx-1 flex-1 space-y-px overflow-y-auto px-1 min-h-[220px]">
        {frozen.length === 0 ? (
          <div className="grid h-full place-items-center">
            <div className="text-center">
              <div className="mx-auto mb-2 h-8 w-8 rounded-full border border-line/70" />
              <p className="font-mono text-[11px] text-mute">
                {status === "disconnected"
                  ? "Event stream offline — actions still work via REST."
                  : "Waiting for events…"}
              </p>
            </div>
          </div>
        ) : (
          frozen.map((e, i) => <Row key={`${e.ts}-${i}`} event={e} />)
        )}
      </div>
    </Panel>
  );
}

function Row({ event }: { event: BusEvent }) {
  const tone = toneFor(event.type);
  const summary = summarize(event.data);
  return (
    <div className="group flex items-start gap-2.5 rounded-md px-2 py-1.5 font-mono text-[11.5px] hover:bg-panel-2/60">
      <span className="shrink-0 pt-px tabular-nums text-mute">
        {clockTime(event.ts)}
      </span>
      <span
        className={cx(
          "shrink-0 rounded border px-1.5 py-0.5 text-[10px] tracking-wide",
          tone.chip,
        )}
      >
        {event.type}
      </span>
      {summary && (
        <span className="min-w-0 truncate pt-0.5 text-soft" title={summary}>
          {summary}
        </span>
      )}
    </div>
  );
}
