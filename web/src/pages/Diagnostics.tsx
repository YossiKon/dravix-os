// Diagnostics — the robot's LIVE memory/health + the add-on's recent logs. The one place to see
// if the robot is starving for RAM or spiking loop-time (→ resets), and to COPY logs to send along.
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../api";
import { Section, toast } from "../ui";
import { useI18n } from "../i18n";

interface HealthResp {
  supported: boolean;
  metrics: Record<string, string | null>;
  error?: string;
}
interface LogRow {
  ts: string;
  level: string;
  name: string;
  msg: string;
}

const numOr = (v: string | null | undefined): number | null => {
  if (v == null || v === "" || v === "unknown" || v === "unavailable") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const fmtKb = (v: string | null | undefined) => {
  const n = numOr(v);
  return n == null ? "—" : `${Math.round(n / 1024).toLocaleString()} KB`;
};
const fmtMb = (v: string | null | undefined) => {
  const n = numOr(v);
  return n == null ? "—" : `${(n / 1048576).toFixed(1)} MB`;
};
const fmtMs = (v: string | null | undefined) => {
  const n = numOr(v);
  return n == null ? "—" : `${Math.round(n)} ms`;
};
const fmtDbm = (v: string | null | undefined) => {
  const n = numOr(v);
  return n == null ? "—" : `${Math.round(n)} dBm`;
};
const fmtUptime = (v: string | null | undefined) => {
  const n = numOr(v);
  if (n == null) return "—";
  const s = Math.floor(n);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
};

const GREEN = "#5dffa0";
const AMBER = "#ffb84d";
const RED = "#ff6b6b";
const cHeap = (v: string | null | undefined) => {
  const n = numOr(v);
  if (n == null) return undefined;
  const k = n / 1024;
  return k < 25 ? RED : k < 50 ? AMBER : GREEN;
};
const cLoop = (v: string | null | undefined) => {
  const n = numOr(v);
  if (n == null) return undefined;
  return n > 500 ? RED : n > 150 ? AMBER : GREEN;
};
const cUp = (v: string | null | undefined) => {
  const n = numOr(v);
  if (n == null) return undefined;
  return n < 120 ? RED : n < 600 ? AMBER : GREEN;
};

export function DiagnosticsPage() {
  const { tr } = useI18n();
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [onlyErrors, setOnlyErrors] = useState(false);

  const refresh = useCallback(() => {
    apiGet<HealthResp>("/api/robot/health").then(setHealth).catch(() => undefined);
    apiGet<{ logs: LogRow[] }>(`/api/logs${onlyErrors ? "?level=WARNING" : ""}`)
      .then((r) => setLogs(r.logs))
      .catch(() => undefined);
  }, [onlyErrors]);

  useEffect(() => {
    refresh();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const m = health?.metrics ?? {};

  const copyLogs = () => {
    const text = logs.map((l) => `${l.ts} ${l.level} ${l.name} | ${l.msg}`).join("\n");
    if (!text) return;
    navigator.clipboard?.writeText(text).then(
      () => toast(tr("הלוגים הועתקו — הדבק לי אותם", "Logs copied — paste them to me")),
      () => undefined,
    );
  };

  const cards: {
    key: string;
    he: string;
    en: string;
    fmt: (v: string | null | undefined) => string;
    color?: (v: string | null | undefined) => string | undefined;
    hintHe?: string;
    hintEn?: string;
  }[] = [
    { key: "heap_free", he: "RAM פנוי (heap)", en: "Free RAM (heap)", fmt: fmtKb, color: cHeap, hintHe: "מתחת ~25KB → ריסטים", hintEn: "< ~25KB → resets" },
    { key: "heap_block", he: "בלוק רציף גדול", en: "Largest block", fmt: fmtKb, hintHe: "הרבה < heap → פרגמנטציה", hintEn: "≪ heap → fragmentation" },
    { key: "loop_time", he: "זמן-לולאה", en: "Loop time", fmt: fmtMs, color: cLoop, hintHe: "קפיצות → תקיעה/watchdog", hintEn: "spikes → hang/watchdog" },
    { key: "uptime", he: "זמן-פעילות", en: "Uptime", fmt: fmtUptime, color: cUp, hintHe: "תמיד נמוך → מאתחל", hintEn: "always low → resetting" },
    { key: "psram_free", he: "PSRAM פנוי", en: "Free PSRAM", fmt: fmtMb, hintHe: "מתוך 8MB", hintEn: "of 8MB" },
    { key: "wifi", he: "WiFi", en: "WiFi", fmt: fmtDbm },
  ];

  return (
    <div className="space-y-4">
      <Section title={tr("🩺 בריאות הרובוט (חי)", "🩺 Robot health (live)")}>
        {health && !health.supported ? (
          <p className="text-sm text-mute">{tr("לא נתמך בדרייבר הנוכחי (צריך חיבור HA).", "Not supported by the current driver (needs HA).")}</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              {cards.map((c) => {
                const raw = m[c.key];
                const col = c.color ? c.color(raw) : undefined;
                return (
                  <div key={c.key} className="rounded-2xl border border-line bg-card2 p-3">
                    <div className="text-xs text-mute">{tr(c.he, c.en)}</div>
                    <div className="font-mono text-lg font-semibold" style={col ? { color: col } : undefined}>
                      {c.fmt(raw)}
                    </div>
                    {(c.hintHe || c.hintEn) && (
                      <div className="mt-0.5 text-[10px] text-mute">{tr(c.hintHe ?? "", c.hintEn ?? "")}</div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-2 rounded-2xl border border-line bg-card2 p-3">
              <div className="text-xs text-mute">{tr("סיבת האתחול האחרון", "Last reset reason")}</div>
              <div className="font-mono text-sm">{m.reset_reason || "—"}</div>
            </div>
            <p className="mt-2 text-[11px] text-mute">
              {tr(
                "מתעדכן כל 5 שניות. החיישנים כבר רצים על הרובוט — אין עומס נוסף. (Flash הוא קבוע-קומפילציה — רואים אותו בלוג-ההתקנה, לא משתנה בזמן ריצה.)",
                "Updates every 5s. The sensors already run on the robot — no extra load. (Flash is a build-time number — shown in the Install log, doesn't change at runtime.)",
              )}
            </p>
          </>
        )}
      </Section>

      <Section title={tr("📋 לוגים", "📋 Logs")} delay={40}>
        <div className="mb-2 flex items-center justify-between gap-2">
          <button className="btn" onClick={() => setOnlyErrors((x) => !x)}>
            {onlyErrors ? tr("מציג: שגיאות+אזהרות", "Showing: warnings+") : tr("מציג: הכל", "Showing: all")}
          </button>
          <button className="btn" onClick={copyLogs}>
            {tr("📋 העתק הכל", "📋 Copy all")}
          </button>
        </div>
        <div
          dir="ltr"
          className="max-h-80 overflow-auto rounded-xl border border-line bg-black/40 p-2 font-mono text-[11px] leading-relaxed"
        >
          {logs.length === 0 ? (
            <div className="p-2 text-mute">{tr("אין לוגים עדיין.", "No logs yet.")}</div>
          ) : (
            logs.map((l, i) => {
              const err = l.level === "ERROR" || l.level === "CRITICAL";
              const warn = l.level === "WARNING";
              return (
                <div key={i} className="whitespace-pre-wrap break-words">
                  <span className="text-mute">{l.ts} </span>
                  <span style={{ color: err ? RED : warn ? AMBER : undefined }} className={err || warn ? "" : "text-mute"}>
                    {l.level}
                  </span>
                  <span className="text-mute"> {l.name} | </span>
                  <span style={err ? { color: RED } : undefined}>{l.msg}</span>
                </div>
              );
            })
          )}
        </div>
        <p className="mt-2 text-[11px] text-mute">
          {tr(
            "אלה הלוגים של ה-add-on (שגיאות HA / דחיפה / API). לקריסות הפירמוור עצמו — ESPHome → Logs. כשמשהו נשבר: לחץ 'העתק הכל' ושלח לי.",
            "These are the add-on's logs (HA / push / API errors). For firmware crashes themselves — ESPHome → Logs. When something breaks: hit 'Copy all' and send it to me.",
          )}
        </p>
      </Section>
    </div>
  );
}
