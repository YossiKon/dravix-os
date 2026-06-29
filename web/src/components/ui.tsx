import type { ButtonHTMLAttributes, ReactNode } from "react";
import { ApiError } from "../lib/api";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Normalise any thrown value into a user-facing message (backend `detail`). */
export function errMsg(err: unknown): string {
  if (err instanceof ApiError)
    return err.status === 0 ? "Core service unreachable" : err.detail;
  return err instanceof Error ? err.message : String(err);
}

/* ── Panel ──────────────────────────────────────────────────────────────── */
export function Panel({
  title,
  eyebrow,
  right,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  eyebrow?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cx(
        "relative rounded-2xl border border-line bg-panel/80 shadow-panel backdrop-blur-sm",
        "before:pointer-events-none before:absolute before:inset-x-5 before:top-0 before:h-px",
        "before:bg-gradient-to-r before:from-transparent before:via-line-bright before:to-transparent",
        className,
      )}
    >
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            {eyebrow && <div className="eyebrow mb-0.5">{eyebrow}</div>}
            {title && (
              <h2 className="font-display text-[15px] font-600 tracking-wide text-ink">
                {title}
              </h2>
            )}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </header>
      )}
      <div className={cx("px-5 pb-5 pt-4", bodyClassName)}>{children}</div>
    </section>
  );
}

/* ── Button ─────────────────────────────────────────────────────────────── */
type Variant = "primary" | "ghost" | "danger" | "subtle";

const variants: Record<Variant, string> = {
  primary:
    "bg-phosphor/15 text-phosphor border-phosphor/40 hover:bg-phosphor/25 hover:border-phosphor/70 shadow-[0_0_18px_-6px_rgba(93,255,160,0.6)]",
  danger:
    "bg-fault/10 text-fault border-fault/40 hover:bg-fault/20 hover:border-fault/70",
  ghost:
    "bg-transparent text-soft border-line hover:text-ink hover:border-line-bright hover:bg-panel-2",
  subtle:
    "bg-panel-2 text-soft border-line hover:text-ink hover:border-line-bright",
};

export function Button({
  variant = "ghost",
  className,
  children,
  loading,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cx(
        "relative inline-flex items-center justify-center gap-2 rounded-lg border px-3.5 py-2",
        "font-mono text-xs font-500 uppercase tracking-[0.08em] transition-all duration-150",
        "disabled:cursor-not-allowed disabled:opacity-40 active:translate-y-px",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40",
        variants[variant],
        className,
      )}
    >
      {loading && (
        <span className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

/* ── Status dot ─────────────────────────────────────────────────────────── */
const dotColor = {
  green: "bg-phosphor shadow-[0_0_10px_2px_rgba(93,255,160,0.55)]",
  amber: "bg-amber shadow-[0_0_10px_2px_rgba(255,180,84,0.5)]",
  red: "bg-fault shadow-[0_0_10px_2px_rgba(255,90,82,0.5)]",
  cyan: "bg-cyan shadow-[0_0_10px_2px_rgba(92,200,255,0.5)]",
  gray: "bg-mute",
} as const;

export function Dot({
  color,
  pulse,
  className,
}: {
  color: keyof typeof dotColor;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-block h-2.5 w-2.5 rounded-full",
        dotColor[color],
        pulse && "animate-pulse-dot",
        className,
      )}
    />
  );
}

/* ── Field row (label : value) ──────────────────────────────────────────── */
export function Field({
  label,
  children,
  mono = true,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 py-2 last:border-b-0">
      <span className="eyebrow shrink-0">{label}</span>
      <span
        className={cx(
          "min-w-0 truncate text-right text-[13px] text-ink",
          mono && "font-mono",
        )}
      >
        {children}
      </span>
    </div>
  );
}

/* ── Chip ───────────────────────────────────────────────────────────────── */
export function Chip({
  children,
  tone = "default",
  title,
}: {
  children: ReactNode;
  tone?: "default" | "on" | "off" | "warn";
  title?: string;
}) {
  const tones = {
    default: "border-line bg-panel-2 text-soft",
    on: "border-phosphor/40 bg-phosphor/10 text-phosphor",
    off: "border-line bg-panel/60 text-mute line-through decoration-mute/50",
    warn: "border-amber/40 bg-amber/10 text-amber",
  } as const;
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-[11px] tracking-wide",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

/* ── Tabs (segmented nav) ───────────────────────────────────────────────── */
export interface TabDef {
  id: string;
  label: string;
  badge?: ReactNode;
}

export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cx(
        "scrollbar-thin flex gap-1 overflow-x-auto rounded-xl border border-line bg-panel/70 p-1 backdrop-blur",
        className,
      )}
    >
      {tabs.map((t) => {
        const selected = t.id === active;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(t.id)}
            className={cx(
              "relative flex shrink-0 items-center gap-1.5 rounded-lg px-3.5 py-2",
              "font-mono text-[11px] font-500 uppercase tracking-[0.08em] transition-all",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40",
              selected
                ? "bg-phosphor/15 text-phosphor shadow-[0_0_18px_-8px_rgba(93,255,160,0.6)]"
                : "text-soft hover:bg-panel-2 hover:text-ink",
            )}
          >
            {t.label}
            {t.badge}
          </button>
        );
      })}
    </div>
  );
}

/* ── Meter (labelled gauge bar) ─────────────────────────────────────────── */
const meterColor = {
  phosphor: "bg-phosphor shadow-[0_0_10px_-2px_rgba(93,255,160,0.7)]",
  cyan: "bg-cyan shadow-[0_0_10px_-2px_rgba(92,200,255,0.7)]",
  magenta: "bg-magenta shadow-[0_0_10px_-2px_rgba(255,110,199,0.7)]",
  amber: "bg-amber shadow-[0_0_10px_-2px_rgba(255,180,84,0.7)]",
} as const;

export function Meter({
  label,
  value,
  display,
  color = "phosphor",
  /** When true, value is in [-1,1] and 0 sits at centre. */
  signed = false,
}: {
  label: string;
  value: number;
  display?: string;
  color?: keyof typeof meterColor;
  signed?: boolean;
}) {
  // Normalise to a 0..100 fill. Signed values render from centre outward.
  const pct = signed
    ? Math.max(0, Math.min(100, (value + 1) * 50))
    : Math.max(0, Math.min(100, value * 100));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {label}
        </span>
        <span className="font-mono text-xs tabular-nums text-ink">
          {display ?? value.toFixed(2)}
        </span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-void/80 ring-1 ring-inset ring-line">
        {signed && (
          <span className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-line-bright/80" />
        )}
        <span
          className={cx(
            "absolute top-0 h-full rounded-full transition-all duration-300",
            meterColor[color],
          )}
          style={
            signed
              ? value >= 0
                ? { left: "50%", width: `${pct - 50}%` }
                : { left: `${pct}%`, width: `${50 - pct}%` }
              : { left: 0, width: `${pct}%` }
          }
        />
      </div>
    </div>
  );
}

/* ── Toggle switch ──────────────────────────────────────────────────────── */
export function Toggle({
  on,
  disabled,
  onChange,
  label,
}: {
  on: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cx(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40",
        on
          ? "border-phosphor/50 bg-phosphor/25"
          : "border-line bg-panel-2",
      )}
    >
      <span
        className={cx(
          "inline-block h-3.5 w-3.5 rounded-full transition-transform",
          on ? "translate-x-4 bg-phosphor shadow-glow" : "translate-x-0.5 bg-mute",
        )}
      />
    </button>
  );
}
