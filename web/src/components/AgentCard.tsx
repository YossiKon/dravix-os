// Agent status board — one or many AI agents on your PC report to /api/agent/status and
// the robot shows the WINNER. Colours are the Okabe-Ito colour-blind-safe palette and every
// state also has a glyph, so state never depends on colour alone. Guide: docs/agent-bridge.md.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { AgentEntry, AgentStatus } from "../api";
import { toastErr } from "../ui";
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
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    apiGet<AgentStatus>("/api/agent/status").then(setSt).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const pal = (state: string) => st?.palette?.[state] || FALLBACK[state] || FALLBACK.idle;
  const label = (state: string) => tr(LABELS[state]?.he ?? state, LABELS[state]?.en ?? state);

  // every mutating action goes through this: a shared busy flag (disables buttons) and
  // surfaced errors (no more silent swallow), refreshing from whatever the server returns.
  async function act(run: () => Promise<AgentStatus | unknown>, applies = true) {
    if (busy) return;
    setBusy(true);
    try {
      const r = await run();
      if (applies && r && typeof r === "object" && "agents" in (r as object)) setSt(r as AgentStatus);
      else refresh();
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(false);
    }
  }

  const test = (state: string) =>
    act(() => apiSend("/api/agent/status", "POST", { state, source: "dashboard-test" }), false);
  const dismiss = (name: string) =>
    act(() => apiSend<AgentStatus>(`/api/agent/status/${encodeURIComponent(name)}`, "DELETE"));
  const clearAll = () => act(() => apiSend<AgentStatus>("/api/agent/status/clear", "POST", {}));
  const decide = (id: string, decision: "approve" | "reject") =>
    act(() => apiSend(`/api/agent/permission/${id}/decide`, "POST", { decision }), false);
  const setPref = (patch: { display?: string; primary?: string; muted?: string[]; approvals?: boolean }) =>
    act(() => apiSend<AgentStatus>("/api/agent/prefs", "PUT", patch));

  const muted = new Set(st?.muted ?? []);
  const toggleMute = (name: string) => {
    const next = new Set(muted);
    next.has(name) ? next.delete(name) : next.add(name);
    return setPref({ muted: [...next] });
  };

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

  const perm = st?.permission && st.permission.decision === "pending" ? st.permission : null;

  return (
    <div className="space-y-3">
      {/* permission prompt — approve/reject a tool right here (also on the robot's screen) */}
      {perm && (
        <div className="rounded-2xl border-2 p-3" style={{ borderColor: "#E69F00" }}>
          <div className="flex items-center gap-2">
            <span className="text-lg">✋</span>
            <span dir="ltr" className="font-mono text-sm text-teal">{perm.agent}</span>
            <span className="font-semibold">{tr("מבקש אישור", "wants approval")}</span>
          </div>
          {perm.summary && (
            <p dir="ltr" className="mt-1 break-words rounded-lg bg-black/30 p-2 font-mono text-xs">{perm.summary}</p>
          )}
          <div className="mt-2 flex gap-2">
            <button
              className="btn flex-1 !bg-[#1f7a4d] !text-white disabled:opacity-50"
              disabled={busy}
              onClick={() => void decide(perm.id, "approve")}
            >
              {tr("✓ אשר", "✓ Approve")}
            </button>
            <button
              className="btn flex-1 !bg-[#b5471f] !text-white disabled:opacity-50"
              disabled={busy}
              onClick={() => void decide(perm.id, "reject")}
            >
              {tr("✗ דחה", "✗ Reject")}
            </button>
          </div>
        </div>
      )}

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
            <button
              className={`shrink-0 text-sm ${muted.has(winner.name) ? "text-amber" : "text-mute hover:text-teal"}`}
              disabled={busy}
              onClick={() => void toggleMute(winner.name)}
              title={muted.has(winner.name) ? tr("בטל השתקה", "Unmute") : tr("השתק", "Mute")}
            >
              {muted.has(winner.name) ? "🔇" : "🔊"}
            </button>
            <button
              className="shrink-0 text-xs text-mute hover:text-red disabled:opacity-50"
              disabled={busy}
              onClick={() => void dismiss(winner.name)}
              title={tr("הסר", "Dismiss")}
            >
              ✕
            </button>
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
              <button
                className={`text-sm ${muted.has(a.name) ? "text-amber" : "text-mute hover:text-teal"}`}
                disabled={busy}
                onClick={() => void toggleMute(a.name)}
                title={muted.has(a.name) ? tr("בטל השתקה", "Unmute") : tr("השתק", "Mute")}
              >
                {muted.has(a.name) ? "🔇" : "🔊"}
              </button>
              <button className="text-xs text-mute hover:text-red disabled:opacity-50" disabled={busy} onClick={() => void dismiss(a.name)} title={tr("הסר", "Dismiss")}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* MASTER kill-switch: approve/reject tools from the robot. OFF = never blocks your agent. */}
      <div className="flex items-center gap-2 rounded-xl border border-line bg-card2 px-3 py-2">
        <span className="text-sm">🔐</span>
        <div className="min-w-0">
          <div className="text-sm font-semibold">{tr("אישור פעולות מהרובוט", "Approve tools from the robot")}</div>
          <div className="text-[11px] text-mute">
            {st?.approvals
              ? tr("פועל — פקודות ממתינות לאישור שלך", "On — commands wait for your approval")
              : tr("כבוי — לא חוסם את הסוכן אף פעם", "Off — never blocks your agent")}
          </div>
        </div>
        <button
          className={`ms-auto shrink-0 rounded-full px-3 py-1 text-xs font-semibold transition disabled:opacity-50 ${
            st?.approvals ? "bg-teal text-black" : "bg-line text-mute"
          }`}
          disabled={busy}
          onClick={() => void setPref({ approvals: !st?.approvals })}
        >
          {st?.approvals ? tr("פועל", "ON") : tr("כבוי", "OFF")}
        </button>
      </div>

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
            disabled={busy}
            className={`chip disabled:opacity-50 ${st?.display === o.k ? "!border-teal !text-teal" : ""}`}
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
          disabled={busy}
          className={`chip disabled:opacity-50 ${!st?.primary ? "!border-teal !text-teal" : ""}`}
          onClick={() => void setPref({ primary: "" })}
        >
          {tr("אוטומטי (הכי דחוף)", "Auto (most urgent)")}
        </button>
        {agents.map((a) => (
          <button
            key={a.name}
            disabled={busy}
            className={`chip disabled:opacity-50 ${st?.primary === a.name ? "!border-teal !text-teal" : ""}`}
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
        {(["working", "waiting_permission", "question", "done", "error", "idle"] as const).map((s) => (
          <button key={s} className="chip disabled:opacity-50" disabled={busy} onClick={() => void test(s)}>
            {pal(s).glyph} {label(s)}
          </button>
        ))}
        {agents.length > 0 && (
          <button className="chip ms-auto disabled:opacity-50" disabled={busy} onClick={() => void clearAll()}>
            {tr("🗑 נקה הכל", "🗑 Clear all")}
          </button>
        )}
      </div>
    </div>
  );
}
