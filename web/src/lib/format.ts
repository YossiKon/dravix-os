// Small formatting helpers shared across components.

/** HH:MM:SS from an epoch-seconds or epoch-ms timestamp (or now). */
export function clockTime(ts?: number): string {
  const ms = ts == null ? Date.now() : ts < 1e12 ? ts * 1000 : ts;
  const d = new Date(ms);
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

/** "3s ago" style relative time from epoch seconds/ms. */
export function relTime(ts?: number | string): string {
  if (ts == null || ts === "") return "—";
  const n = typeof ts === "string" ? Date.parse(ts) : ts < 1e12 ? ts * 1000 : ts;
  if (Number.isNaN(n)) return String(ts);
  const diff = Math.max(0, Date.now() - n);
  const s = Math.floor(diff / 1000);
  if (s < 2) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

/** Title-case a snake/kebab identifier for display. */
export function humanize(s: string): string {
  return s
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}
