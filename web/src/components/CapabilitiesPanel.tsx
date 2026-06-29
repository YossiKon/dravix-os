import { humanize } from "../lib/format";
import { Chip, Panel } from "./ui";

// Capabilities we recognise + a friendly hint about what they unlock.
const KNOWN: Record<string, string> = {
  say: "Speak literal text",
  set_face: "Set facial expression",
  move_head: "Pan / tilt the head",
  set_leds: "Drive the RGB LEDs",
};

export function CapabilitiesPanel({
  capabilities,
  ready,
}: {
  capabilities: string[];
  ready: boolean;
}) {
  const caps = new Set(capabilities);
  // Show the well-known set (with on/off state) plus any extras the backend reports.
  const known = Object.keys(KNOWN);
  const extras = capabilities.filter((c) => !KNOWN[c]);

  return (
    <Panel eyebrow="driver surface" title="Capabilities">
      {!ready ? (
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <span key={i} className="h-7 w-24 animate-pulse rounded-md bg-line" />
          ))}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {known.map((c) => (
              <Chip
                key={c}
                tone={caps.has(c) ? "on" : "off"}
                title={
                  caps.has(c)
                    ? KNOWN[c]
                    : `${KNOWN[c]} — not supported by current driver`
                }
              >
                <span className="text-[8px] leading-none">
                  {caps.has(c) ? "●" : "○"}
                </span>
                {humanize(c)}
              </Chip>
            ))}
            {extras.map((c) => (
              <Chip key={c} tone="on" title="Reported by backend">
                <span className="text-[8px] leading-none">●</span>
                {humanize(c)}
              </Chip>
            ))}
          </div>
          {capabilities.length === 0 && (
            <p className="mt-3 font-mono text-[11px] text-mute">
              Driver reports no capabilities — manual controls are disabled.
            </p>
          )}
        </>
      )}
    </Panel>
  );
}
