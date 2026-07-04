// Agent status — shows what an AI agent on your PC is doing (it POSTs to /api/agent/status).
// Wiring guide: docs/agent-bridge.md.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { AgentStatus } from "../api";
import { useI18n } from "../i18n";

type Look = { he: string; en: string; dot: string; glyph: string };

const LOOKS: Record<string, Look> = {
  working: { he: "עובד", en: "Working", dot: "#1E88E5", glyph: "🔧" },
  waiting_permission: { he: "ממתין לאישור", en: "Waiting for approval", dot: "#FB8C00", glyph: "✋" },
  question: { he: "יש לו שאלה", en: "Has a question", dot: "#8E24AA", glyph: "❓" },
  done: { he: "סיים", en: "Done", dot: "#43A047", glyph: "✅" },
  error: { he: "שגיאה", en: "Error", dot: "#E53935", glyph: "⚠️" },
  idle: { he: "ממתין", en: "Idle", dot: "#6b7280", glyph: "💤" },
};

function ago(iso: string, he: boolean): string {
  if (!iso) return "";
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return he ? `לפני ${secs} שנ׳` : `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return he ? `לפני ${mins} דק׳` : `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return he ? `לפני ${hrs} שע׳` : `${hrs}h ago`;
}

export function AgentCard() {
  const { tr, lang } = useI18n();
  const he = lang === "he";
  const [st, setSt] = useState<AgentStatus | null>(null);

  const refresh = useCallback(() => {
    apiGet<AgentStatus>("/api/agent/status")
      .then(setSt)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const look = (st && LOOKS[st.state]) || LOOKS.idle;

  async function test(state: string) {
    try {
      await apiSend("/api/agent/status", "POST", { state, source: "dashboard-test" });
      refresh();
    } catch {
      /* best-effort test button */
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-card2 p-3">
        <span
          className="inline-block h-3.5 w-3.5 shrink-0 rounded-full"
          style={{ background: look.dot, boxShadow: `0 0 10px ${look.dot}` }}
        />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-lg">{look.glyph}</span>
            <span className="font-semibold">{tr(look.he, look.en)}</span>
          </div>
          {st?.text && <p className="truncate text-xs text-mute">{st.text}</p>}
        </div>
        <span className="ms-auto shrink-0 text-[11px] text-mute">
          {st?.source && <span dir="ltr" className="font-mono">{st.source}</span>}
          {st?.updated_at && <span className="ms-1">· {ago(st.updated_at, he)}</span>}
        </span>
      </div>

      <p className="text-xs text-mute">
        {tr(
          "חבר סוכן AI (למשל Claude Code) שירוץ על המחשב שלך והרובוט יראה לך מה הוא עושה. מדריך:",
          "Connect an AI agent (e.g. Claude Code) on your PC and the robot shows you what it's doing. Guide:",
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
            {LOOKS[s].glyph} {tr(LOOKS[s].he, LOOKS[s].en)}
          </button>
        ))}
      </div>
    </div>
  );
}
