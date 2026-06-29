import { humanize, relTime } from "../lib/format";
import type { StatusResponse } from "../lib/types";
import { EXPRESSION_META } from "./expressions";
import { Dot, Field, Panel, cx } from "./ui";

export function StatusPanel({
  status,
  loading,
  error,
}: {
  status: StatusResponse | null;
  loading: boolean;
  error: string | null;
}) {
  const robot = status?.robot;
  const exprMeta = robot ? EXPRESSION_META[robot.expression] : undefined;

  return (
    <Panel
      eyebrow="telemetry"
      title="System Status"
      right={
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-mute">
          <span
            className={cx(
              "h-1.5 w-1.5 rounded-full",
              loading ? "animate-pulse-dot bg-cyan" : "bg-line-bright",
            )}
          />
          {loading ? "polling" : "4s poll"}
        </div>
      }
    >
      {error && !status ? (
        <div className="rounded-lg border border-amber/30 bg-amber/5 px-3 py-2 font-mono text-xs text-amber">
          {error}
        </div>
      ) : !status ? (
        <SkeletonRows />
      ) : (
        <div className="grid grid-cols-1 gap-x-8 gap-y-0 sm:grid-cols-2">
          <div>
            <Field label="robot">
              <span className="inline-flex items-center gap-2">
                <Dot color={robot!.online ? "green" : "red"} />
                <span className={robot!.online ? "text-phosphor" : "text-fault"}>
                  {robot!.online ? "ONLINE" : "OFFLINE"}
                </span>
              </span>
            </Field>
            <Field label="driver">{robot!.driver || "—"}</Field>
            <Field label="transport">{robot!.transport || "—"}</Field>
            <Field label="expression">
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden>{exprMeta?.emoji ?? "•"}</span>
                {robot!.expression || "—"}
              </span>
            </Field>
          </div>
          <div>
            <Field label="head yaw">
              {fmtDeg(robot!.head_yaw)}
            </Field>
            <Field label="head pitch">
              {fmtDeg(robot!.head_pitch)}
            </Field>
            <Field label="active mode">
              {status.active_mode ? (
                <span className="text-phosphor">{humanize(status.active_mode)}</span>
              ) : (
                <span className="text-mute">idle</span>
              )}
            </Field>
            <Field label="ai provider">
              <span className="inline-flex items-center gap-2">
                <Dot color={status.ai_available ? "green" : "gray"} />
                <span className={status.ai_available ? "text-ink" : "text-mute"}>
                  {status.ai_provider
                    ? `${status.ai_provider}${status.ai_available ? "" : " · offline"}`
                    : "none"}
                </span>
              </span>
            </Field>
          </div>

          {/* Last said + last error span full width */}
          <div className="sm:col-span-2">
            <Field label="last said">
              {robot!.last_said ? (
                <span className="italic text-soft">“{robot!.last_said}”</span>
              ) : (
                <span className="text-mute">—</span>
              )}
            </Field>
            <Field label="updated">
              <span className="text-mute">{relTime(robot!.updated_at)}</span>
            </Field>
          </div>

          {robot!.last_error && (
            <div className="sm:col-span-2 mt-3 flex items-start gap-2 rounded-lg border border-fault/30 bg-fault/5 px-3 py-2">
              <span className="mt-0.5 font-mono text-fault">!</span>
              <div className="min-w-0">
                <div className="eyebrow text-fault/80">last error</div>
                <div className="break-words font-mono text-xs text-fault">
                  {robot!.last_error}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function fmtDeg(n: number): string {
  const v = Math.round(n * 10) / 10;
  const sign = v > 0 ? "+" : "";
  return `${sign}${v}°`;
}

function SkeletonRows() {
  return (
    <div className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center justify-between border-b border-line/60 py-2.5"
        >
          <span className="h-2 w-16 animate-pulse rounded bg-line" />
          <span className="h-2 w-20 animate-pulse rounded bg-line" />
        </div>
      ))}
    </div>
  );
}
