import type { WsStatus } from "../hooks/useWebSocket";
import type { StatusResponse } from "../lib/types";
import { Dot, cx } from "./ui";

export interface NavItem {
  id: string;
  label: string;
  icon: string;
}

/**
 * Left navigation rail + brand + live connection telemetry.
 *
 * Only the pages passed in `items` are rendered — the parent decides which
 * pages exist for the robot's current capabilities/config (capability gating).
 */
export function Sidebar({
  items,
  active,
  onNavigate,
  status,
  version,
  wsStatus,
  coreUnreachable,
}: {
  items: NavItem[];
  active: string;
  onNavigate: (id: string) => void;
  status: StatusResponse | null;
  version: string | null;
  wsStatus: WsStatus;
  coreUnreachable: boolean;
}) {
  const online = status?.robot.online ?? false;
  const robotColor = coreUnreachable ? "amber" : online ? "green" : "red";
  const robotLabel = coreUnreachable
    ? "core unreachable"
    : online
      ? "robot online"
      : "robot offline";

  const wsMap = {
    connected: { color: "cyan" as const, label: "events live" },
    connecting: { color: "amber" as const, label: "connecting" },
    disconnected: { color: "gray" as const, label: "events off" },
  };
  const ws = wsMap[wsStatus];

  return (
    <>
      {/* ── Desktop: fixed left rail ─────────────────────────────────────── */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line/70 bg-void/80 backdrop-blur-xl lg:flex">
        <Brand version={version} />

        <nav className="scrollbar-thin flex-1 space-y-1 overflow-y-auto px-3 py-2">
          {items.map((it) => (
            <NavButton
              key={it.id}
              item={it}
              active={it.id === active}
              onClick={() => onNavigate(it.id)}
            />
          ))}
        </nav>

        <div className="space-y-2 border-t border-line/60 p-3">
          <StatusLine color={robotColor} pulse={online && !coreUnreachable} label={robotLabel} />
          <StatusLine color={ws.color} pulse={wsStatus === "connected"} label={ws.label} muted />
          {status?.robot.driver && (
            <div className="px-1 font-mono text-[10px] uppercase tracking-wider text-mute">
              driver · {status.robot.driver}
            </div>
          )}
        </div>
      </aside>

      {/* ── Mobile: top bar + scrolling tab strip ────────────────────────── */}
      <div className="sticky top-0 z-30 border-b border-line/70 bg-void/85 backdrop-blur-xl lg:hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          <Brand version={version} compact />
          <div className="flex items-center gap-2">
            <Dot color={robotColor} pulse={online && !coreUnreachable} />
            <Dot color={ws.color} pulse={wsStatus === "connected"} />
          </div>
        </div>
        <nav className="scrollbar-thin flex gap-1 overflow-x-auto px-3 pb-2">
          {items.map((it) => (
            <button
              key={it.id}
              onClick={() => onNavigate(it.id)}
              className={cx(
                "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5",
                "font-mono text-[11px] font-500 uppercase tracking-[0.08em] transition-all",
                it.id === active
                  ? "bg-phosphor/15 text-phosphor shadow-[0_0_18px_-8px_rgba(93,255,160,0.6)]"
                  : "text-soft hover:bg-panel-2 hover:text-ink",
              )}
            >
              <span aria-hidden>{it.icon}</span>
              {it.label}
            </button>
          ))}
        </nav>
      </div>
    </>
  );
}

function Brand({ version, compact }: { version: string | null; compact?: boolean }) {
  return (
    <div
      className={cx(
        "flex items-center gap-3",
        compact ? "" : "border-b border-line/60 px-4 py-4",
      )}
    >
      <div className="relative grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-phosphor/30 bg-phosphor/5">
        <span className="absolute inset-0 overflow-hidden rounded-lg">
          <span className="absolute -inset-y-2 left-0 w-1/3 bg-gradient-to-r from-transparent via-phosphor/20 to-transparent animate-sweep" />
        </span>
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-phosphor">
          <circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
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
        <div className="font-display text-lg font-700 tracking-tight text-ink">
          dravix<span className="text-phosphor text-glow">-os</span>
        </div>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.24em] text-mute">
          {version ? `stackchan · v${version}` : "stackchan console"}
        </div>
      </div>
    </div>
  );
}

function NavButton({
  item,
  active,
  onClick,
}: {
  item: NavItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cx(
        "group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40",
        active
          ? "bg-phosphor/[0.10] text-phosphor shadow-[inset_2px_0_0_0_rgba(93,255,160,0.9)]"
          : "text-soft hover:bg-panel-2 hover:text-ink",
      )}
    >
      <span
        className={cx(
          "grid h-6 w-6 shrink-0 place-items-center text-sm",
          active ? "text-phosphor" : "text-mute group-hover:text-soft",
        )}
        aria-hidden
      >
        {item.icon}
      </span>
      <span className="font-mono text-[12px] font-500 uppercase tracking-[0.08em]">
        {item.label}
      </span>
    </button>
  );
}

function StatusLine({
  color,
  pulse,
  label,
  muted,
}: {
  color: "green" | "amber" | "red" | "cyan" | "gray";
  pulse?: boolean;
  label: string;
  muted?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 px-1">
      <Dot color={color} pulse={pulse} />
      <span
        className={cx(
          "font-mono text-[11px] uppercase tracking-wider",
          muted ? "text-mute" : "text-soft",
        )}
      >
        {label}
      </span>
    </div>
  );
}
