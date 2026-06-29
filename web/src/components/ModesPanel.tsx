import { useState } from "react";
import { ApiError, api } from "../lib/api";
import { humanize } from "../lib/format";
import type { ModeInfo } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, cx } from "./ui";

export function ModesPanel({
  modes,
  activeMode,
  loading,
  onChanged,
}: {
  modes: ModeInfo[];
  activeMode: string | null;
  loading: boolean;
  onChanged: () => void;
}) {
  const toasts = useToasts();
  const [busy, setBusy] = useState<string | null>(null);

  const foreground = modes.filter((m) => m.kind !== "ambient");
  const ambient = modes.filter((m) => m.kind === "ambient");

  async function run(label: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(label);
    try {
      await fn();
      toasts.ok(ok);
      onChanged();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toasts.error(msg);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel
      eyebrow="behaviors"
      title="Modes"
      right={
        activeMode && (
          <Button
            variant="danger"
            loading={busy === "__deactivate"}
            onClick={() =>
              run(
                "__deactivate",
                () => api.deactivateMode(),
                "Foreground mode stopped",
              )
            }
          >
            Stop active
          </Button>
        )
      }
    >
      {loading && modes.length === 0 ? (
        <SkeletonModes />
      ) : modes.length === 0 ? (
        <p className="font-mono text-xs text-mute">No modes registered.</p>
      ) : (
        <div className="space-y-5">
          <Group label="Foreground · mutually exclusive">
            {foreground.length === 0 ? (
              <Empty>No foreground modes.</Empty>
            ) : (
              foreground.map((m) => (
                <ModeRow
                  key={m.name}
                  mode={m}
                  busy={busy === m.name}
                  anyBusy={busy !== null}
                  onActivate={() =>
                    run(
                      m.name,
                      () => api.activateMode(m.name),
                      `Activated “${humanize(m.name)}”`,
                    )
                  }
                  onStop={() =>
                    run(
                      m.name,
                      () => api.deactivateMode(),
                      `Stopped “${humanize(m.name)}”`,
                    )
                  }
                />
              ))
            )}
          </Group>

          {ambient.length > 0 && (
            <Group label="Ambient · run in background">
              {ambient.map((m) => (
                <ModeRow
                  key={m.name}
                  mode={m}
                  ambient
                  busy={busy === m.name}
                  anyBusy={busy !== null}
                  onActivate={() =>
                    run(
                      m.name,
                      () => api.activateMode(m.name),
                      `Ambient “${humanize(m.name)}” engaged`,
                    )
                  }
                  // Ambient stop also routes through activate-toggle on the backend;
                  // there's no per-ambient stop endpoint, so we re-activate to toggle.
                  onStop={() =>
                    run(
                      m.name,
                      () => api.activateMode(m.name),
                      `Toggled “${humanize(m.name)}”`,
                    )
                  }
                />
              ))}
            </Group>
          )}
        </div>
      )}
    </Panel>
  );
}

function ModeRow({
  mode,
  busy,
  anyBusy,
  ambient,
  onActivate,
  onStop,
}: {
  mode: ModeInfo;
  busy: boolean;
  anyBusy: boolean;
  ambient?: boolean;
  onActivate: () => void;
  onStop: () => void;
}) {
  return (
    <div
      className={cx(
        "group flex items-center gap-3 rounded-xl border px-3.5 py-3 transition-colors",
        mode.active
          ? "border-phosphor/35 bg-phosphor/[0.06]"
          : "border-line bg-panel-2/40 hover:border-line-bright",
      )}
    >
      <span
        className={cx(
          "h-7 w-1 shrink-0 rounded-full transition-colors",
          mode.active ? "bg-phosphor shadow-glow" : "bg-line-bright",
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-display text-sm font-600 text-ink">
            {humanize(mode.name)}
          </span>
          {mode.active && (
            <span className="rounded bg-phosphor/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-phosphor">
              {ambient ? "engaged" : "active"}
            </span>
          )}
        </div>
        {mode.description && (
          <p className="mt-0.5 truncate font-mono text-[11px] text-mute">
            {mode.description}
          </p>
        )}
      </div>
      {mode.active ? (
        <Button
          variant="subtle"
          loading={busy}
          disabled={anyBusy && !busy}
          onClick={onStop}
        >
          Stop
        </Button>
      ) : (
        <Button
          variant="primary"
          loading={busy}
          disabled={anyBusy && !busy}
          onClick={onActivate}
        >
          Activate
        </Button>
      )}
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="eyebrow mb-2 flex items-center gap-2">
        {label}
        <span className="h-px flex-1 bg-line/70" />
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-[11px] text-mute">{children}</p>;
}

function SkeletonModes() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-xl bg-line/60" />
      ))}
    </div>
  );
}
