import type { XiaoZhiStatus } from "../lib/types";
import { Dot, Panel } from "./ui";

/**
 * Compact cloud (xiaozhi) bridge status for the Agent hub.
 *
 * Renders ONLY when the bridge is configured — the parent gates on
 * `status.xiaozhi?.configured`. Shows connection state + advertised cloud
 * tool count; the full tool list lives on the (also gated) Cloud page.
 */
export function CloudStatus({ xiaozhi }: { xiaozhi: XiaoZhiStatus }) {
  const { connected, last_error, tools } = xiaozhi;
  return (
    <Panel
      eyebrow="cloud · xiaozhi"
      title="Cloud Bridge"
      right={
        <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
          <Dot color={connected ? "green" : "amber"} pulse={!connected} />
          <span className={connected ? "text-phosphor" : "text-amber"}>
            {connected ? "connected" : "connecting…"}
          </span>
        </span>
      }
    >
      <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-panel-2/40 px-3.5 py-3">
        <span className="eyebrow">cloud actions</span>
        <span className="font-mono text-sm tabular-nums text-ink">
          <span className="text-cyan">{tools.length}</span> available
        </span>
      </div>
      {!connected && last_error && (
        <p className="mt-2 break-words font-mono text-[11px] text-fault">{last_error}</p>
      )}
    </Panel>
  );
}
