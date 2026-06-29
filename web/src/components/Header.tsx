import type { WsStatus } from "../hooks/useWebSocket";
import type { StatusResponse } from "../lib/types";
import { Dot, cx } from "./ui";

export function Header({
  status,
  version,
  wsStatus,
  statusError,
}: {
  status: StatusResponse | null;
  version: string | null;
  wsStatus: WsStatus;
  statusError: boolean;
}) {
  const online = status?.robot.online ?? false;
  // Robot connection state: green online, red offline, amber if we can't reach core.
  const robotColor = statusError ? "amber" : online ? "green" : "red";
  const robotLabel = statusError
    ? "core unreachable"
    : online
      ? "robot online"
      : "robot offline";

  const wsMap = {
    connected: { color: "cyan" as const, label: "events: live" },
    connecting: { color: "amber" as const, label: "events: connecting" },
    disconnected: { color: "gray" as const, label: "events: disconnected" },
  };
  const ws = wsMap[wsStatus];

  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-void/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="relative grid h-9 w-9 place-items-center rounded-lg border border-phosphor/30 bg-phosphor/5">
            <span className="absolute inset-0 overflow-hidden rounded-lg">
              <span className="absolute -inset-y-2 left-0 w-1/3 bg-gradient-to-r from-transparent via-phosphor/20 to-transparent animate-sweep" />
            </span>
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-phosphor">
              <circle
                cx="12"
                cy="12"
                r="6.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
              />
              <circle cx="12" cy="12" r="2" fill="currentColor" />
              <path
                d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className="leading-none">
            <div className="flex items-baseline gap-2">
              <span className="font-display text-lg font-700 tracking-tight text-ink">
                dravix
                <span className="text-phosphor text-glow">-os</span>
              </span>
            </div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.28em] text-mute">
              stackchan console
            </div>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {/* Robot connection pill */}
          <Pill>
            <Dot color={robotColor} pulse={online && !statusError} />
            <span
              className={cx(
                "font-mono text-[11px] uppercase tracking-wider",
                statusError
                  ? "text-amber"
                  : online
                    ? "text-phosphor"
                    : "text-fault",
              )}
            >
              {robotLabel}
            </span>
          </Pill>

          {/* Events / WS pill */}
          <Pill>
            <Dot color={ws.color} pulse={wsStatus === "connected"} />
            <span className="font-mono text-[11px] uppercase tracking-wider text-soft">
              {ws.label}
            </span>
          </Pill>

          {/* Version */}
          {version && (
            <Pill>
              <span className="font-mono text-[11px] tracking-wider text-mute">
                v{version}
              </span>
            </Pill>
          )}
        </div>
      </div>
    </header>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-panel/70 px-3 py-1.5">
      {children}
    </div>
  );
}
