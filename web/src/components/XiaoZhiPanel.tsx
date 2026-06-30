import type { XiaoZhiStatus } from "../lib/types";
import { Dot, Panel } from "./ui";

/**
 * Cloud (xiaozhi) bridge panel.
 *
 * Surfaces the cloud bridge connection state and — crucially — the list of
 * actions the robot's AI can perform over the cloud. These are the
 * "what can be done from the cloud" tools the user asked to make visible.
 *
 * Renders only when the bridge is configured; otherwise shows a subtle hint.
 */
export function XiaoZhiPanel({ xiaozhi }: { xiaozhi?: XiaoZhiStatus }) {
  // Not configured (or status not yet loaded) → keep it minimal & quiet.
  if (!xiaozhi?.configured) {
    return (
      <Panel eyebrow="cloud · xiaozhi" title="Cloud Bridge">
        <p className="font-mono text-[11px] text-mute">
          Cloud bridge not configured — set a xiaozhi MCP URL to expose actions
          to the cloud.
        </p>
      </Panel>
    );
  }

  const { connected, last_error, tools } = xiaozhi;

  return (
    <Panel
      eyebrow="cloud · xiaozhi"
      title="Cloud Bridge"
      right={
        <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
          <Dot color={connected ? "green" : "amber"} pulse={!connected} />
          <span className={connected ? "text-phosphor" : "text-amber"}>
            {connected ? "CONNECTED" : "CONFIGURED (connecting…)"}
          </span>
        </span>
      }
    >
      {/* Error line: only when not connected and we actually have an error. */}
      {!connected && last_error && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-fault/30 bg-fault/5 px-3 py-2">
          <span className="mt-0.5 font-mono text-fault">!</span>
          <div className="min-w-0">
            <div className="eyebrow text-fault/80">bridge error</div>
            <div className="break-words font-mono text-[11px] text-fault">
              {last_error}
            </div>
          </div>
        </div>
      )}

      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="eyebrow">cloud actions</span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {tools.length} available
        </span>
      </div>

      {tools.length === 0 ? (
        <p className="font-mono text-[11px] text-mute">
          {connected
            ? "Bridge connected — no cloud actions advertised yet."
            : "No cloud actions reported."}
        </p>
      ) : (
        <ul className="scrollbar-thin max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {tools.map((tool) => (
            <li
              key={tool.name}
              className="flex items-start gap-2.5 rounded-lg border border-line/70 bg-panel-2/60 px-3 py-2"
            >
              <span className="mt-px shrink-0 rounded border border-cyan/40 bg-cyan/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-cyan">
                ☁ cloud
              </span>
              <div className="min-w-0 flex-1">
                <div className="break-words font-mono text-xs text-ink">
                  {tool.name}
                </div>
                {tool.description && (
                  <div className="mt-0.5 break-words text-[11px] leading-snug text-mute">
                    {tool.description}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
