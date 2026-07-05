// Agent status board — one or many AI agents on your PC report to /api/agent/status and
// the robot shows the WINNER. Colours are the Okabe-Ito colour-blind-safe palette and every
// state also has a glyph, so state never depends on colour alone. Guide: docs/agent-bridge.md.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { AgentEntry, AgentStatus } from "../api";
import { useI18n } from "../i18n";

const LABELS: Record<string, { he: string; en: string }> = {
  working: { he: "עובד", en: "Working" },
  waiting_permission: { he: "ממתין לאישור", en: "Waiting for approval" },
  question: { he: "יש לו שאלה", en: "Has a question" },
  done: { he: "סיים", en: "Done" },
  error: { he: "שגיאה", en: "Error" },
  idle: { he: "ממתין", en: "Idle" },
};
// fallback palette (server also sends one so robot + dashboard always match)
const FALLBACK: Record<string, { color: string; glyph: string }> = {
  working: { color: "#56B4E9", glyph: "🔧" },
  waiting_permission: { color: "#E69F00", glyph: "✋" },
  question: { color: "#CC79A7", glyph: "❓" },
  done: { color: "#009E73", glyph: "✅" },
  error: { color: "#D55E00", glyph: "⚠️" },
  idle: { color: "#999999", glyph: "💤" },
};

function ago(iso: string, he: boolean): string {
  if (!iso) return "";
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return he ? `לפני ${secs} שנ׳` : `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return he ? `לפני ${mins} דק׳` : `${mins}m ago`;
  return he ? `לפני ${Math.round(mins / 60)} שע׳` : `${Math.round(mins / 60)}h ago`;
}

export function AgentCard() {
  const { tr, lang } = useI18n();
  const he = lang === "he";
  const [st, setSt] = useState<AgentStatus | null>(null);

  const refresh = useCallback(() => {
    apiGet<AgentStatus>("/api/agent/status").then(setSt).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const pal = (state: string) => st?.palette?.[state] || FALLBACK[state] || FALLBACK.idle;
  const label = (state: string) => tr(LABELS[state]?.he ?? state, LABELS[state]?.en ?? state);

  async function test(state: string) {
    try {
      await apiSend("/api/agent/status", "POST", { state, source: "dashboard-test" });
      refresh();
    } catch {
      /* best-effort */
    }
  }
  async function dismiss(name: string) {
    try {
      setSt(await apiSend<AgentStatus>(`/api/agent/status/${encodeURIComponent(name)}`, "DELETE"));
    } catch {
      /* ignore */
    }
  }
  async function setPref(patch: { display?: string; primary?: string }) {
    try {
      setSt(await apiSend<AgentStatus>("/api/agent/prefs", "PUT", patch));
    } catch {
      /* ignore */
    }
  }

  const agents = st?.agents ?? [];
  const winner = st?.winner ?? null;

  const Dot = ({ state }: { state: string }) => {
    const p = pal(state);
    return (
      <span className="inline-flex items-center gap-1">
        <span
          className="inline-block h-3 w-3 shrink-0 rounded-full"
          style={{ background: p.color, boxShadow: `0 0 8px ${p.color}` }}
        />
        <span aria-hidden className="text-base leading-none">{p.glyph}</span>
      </span>
    );
  };

  return (
    <div className="space-y-3">
      {/* winner banner */}
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-card2 p-3">
        {winner ? (
          <>
            <Dot state={winner.state} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span dir="ltr" className="font-mono text-sm text-teal">{winner.name}</span>
                <span className="font-semibold">{label(winner.state)}</span>
              </div>
              {winner.text && <p className="truncate text-xs text-mute">{winner.text}</p>}
            </div>
            <span className="ms-auto shrink-0 text-[11px] text-mute">{ago(winner.updated_at, he)}</span>
          </>
        ) : (
          <span className="text-sm text-mute">
            {tr("אין סוכן מחובר כרגע.", "No agent connected right now.")}
          </span>
        )}
      </div>

      {/* every reporting agent */}
      {agents.length > 1 && (
        <div className="space-y-1.5">
          {agents.map((a: AgentEntry) => (
            <div
              key={a.name}
              className={`flex items-center gap-2 rounded-xl border px-2 py-1.5 ${
                winner?.name === a.name ? "border-teal bg-card2" : "border-line bg-card2/40"
              } ${a.stale ? "opacity-50" : ""}`}
            >
              <Dot state={a.state} />
              <span dir="ltr" className="font-mono text-xs text-teal">{a.name}</span>
              <span className="text-xs">{label(a.state)}</span>
              {a.text && <span className="truncate text-[11px] text-mute">· {a.text}</span>}
              <span className="ms-auto shrink-0 text-[10px] text-mute">{ago(a.updated_at, he)}</span>
              <button className="text-xs text-mute hover:text-red" onClick={() => void dismiss(a.name)} title={tr("הסר", "Dismiss")}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* display mode — bubble (spoken) / badge (on-screen, needs fw v20) / both / off */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-mute">{tr("הצגה:", "Show on robot:")}</span>
        {(
          [
            { k: "bubble", he: "🗨 בועה", en: "🗨 Bubble" },
            { k: "badge", he: "🏷 תגית", en: "🏷 Badge" },
            { k: "both", he: "שניהם", en: "Both" },
            { k: "off", he: "כבוי", en: "Off" },
          ] as const
        ).map((o) => (
          <button
            key={o.k}
            className={`chip ${st?.display === o.k ? "!border-teal !text-teal" : ""}`}
            onClick={() => void setPref({ display: o.k })}
          >
            {tr(o.he, o.en)}
          </button>
        ))}
      </div>

      {/* priority — auto (most urgent) or pin one agent */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-mute">{tr("עדיפות:", "Priority:")}</span>
        <button
          className={`chip ${!st?.primary ? "!border-teal !text-teal" : ""}`}
          onClick={() => void setPref({ primary: "" })}
        >
          {tr("אוטומטי (הכי דחוף)", "Auto (most urgent)")}
        </button>
        {agents.map((a) => (
          <button
            key={a.name}
            className={`chip ${st?.primary === a.name ? "!border-teal !text-teal" : ""}`}
            onClick={() => void setPref({ primary: a.name })}
          >
            📌 <span dir="ltr" className="font-mono">{a.name}</span>
          </button>
        ))}
      </div>

      <p className="text-xs text-mute">
        {tr(
          "חבר סוכני AI (Claude Code וכו') מהמחשב. אפשר כמה בו-זמנית — הרובוט מראה את הדחוף ביותר. מדריך:",
          "Connect AI agents (Claude Code, etc.) from your PC. Several at once is fine — the robot shows the most urgent. Guide:",
        )}{" "}
        <a
          className="text-teal underline"
          href="https://github.com/YossiKon/dravix-os/blob/main/docs/agent-bridge.md"
          target="_blank"
          rel="noreferrer"
        >
          docs/agent-bridge.md
        </a>
      </p>

      <div className="flex flex-wrap gap-2">
        <span className="self-center text-xs text-mute">{tr("בדיקה:", "Test:")}</span>
        {(["working", "waiting_permission", "question", "done", "idle"] as const).map((s) => (
          <button key={s} className="chip" onClick={() => void test(s)}>
            {pal(s).glyph} {label(s)}
          </button>
        ))}
      </div>
    </div>
  );
}
