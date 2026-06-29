import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import { clockTime } from "../lib/format";
import { CAP, type StatusResponse } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, cx } from "./ui";

interface ChatMsg {
  id: number;
  role: "user" | "robot";
  text: string;
  ts: number;
  pending?: boolean;
}

export function TalkPanel({ status }: { status: StatusResponse | null }) {
  const toasts = useToasts();
  const canSay = (status?.robot.capabilities ?? []).includes(CAP.say);
  const aiAvailable = status?.ai_available ?? false;

  return (
    <Panel eyebrow="voice + intelligence" title="Talk">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <SayBox
          disabled={!status || !canSay}
          reason={!canSay ? "Driver lacks say" : undefined}
          onSay={async (text) => {
            try {
              await api.say(text);
              toasts.ok("Spoken");
              return true;
            } catch (err) {
              toasts.error(err instanceof ApiError ? err.detail : String(err));
              return false;
            }
          }}
        />
        <ChatBox aiAvailable={aiAvailable} provider={status?.ai_provider ?? null} />
      </div>
    </Panel>
  );
}

/* ── Say (literal speech) ───────────────────────────────────────────────── */
function SayBox({
  disabled,
  reason,
  onSay,
}: {
  disabled: boolean;
  reason?: string;
  onSay: (text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    const ok = await onSay(t);
    setBusy(false);
    if (ok) setText("");
  }

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex items-center gap-2">
        <span className="eyebrow">Say · literal</span>
        {disabled && reason && (
          <span className="rounded border border-amber/30 bg-amber/5 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-amber">
            {reason}
          </span>
        )}
      </div>
      <textarea
        value={text}
        disabled={disabled}
        placeholder="Type exactly what the robot should speak…"
        rows={3}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
        }}
        className={cx(
          "w-full resize-none rounded-xl border border-line bg-void/60 px-3.5 py-3",
          "font-body text-sm text-ink placeholder:text-mute/70",
          "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
          "disabled:cursor-not-allowed disabled:opacity-40",
        )}
      />
      <div className="mt-2 flex items-center justify-between">
        <span className="font-mono text-[10px] text-mute">⌘/Ctrl + Enter</span>
        <Button
          variant="primary"
          loading={busy}
          disabled={disabled || !text.trim()}
          onClick={submit}
        >
          ▸ Speak
        </Button>
      </div>
    </div>
  );
}

/* ── Chat (AI router) ───────────────────────────────────────────────────── */
function ChatBox({
  aiAvailable,
  provider,
}: {
  aiAvailable: boolean;
  provider: string | null;
}) {
  const toasts = useToasts();
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const convoId = useRef<string | undefined>(undefined);
  const idRef = useRef(1);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [msgs]);

  async function submit() {
    const t = text.trim();
    if (!t || busy) return;
    const userMsg: ChatMsg = {
      id: idRef.current++,
      role: "user",
      text: t,
      ts: Date.now(),
    };
    const pendingId = idRef.current++;
    setMsgs((m) => [
      ...m,
      userMsg,
      { id: pendingId, role: "robot", text: "", ts: Date.now(), pending: true },
    ]);
    setText("");
    setBusy(true);
    try {
      // speak:true → the robot voices the reply per the product spec.
      const res = await api.chat(t, convoId.current, true);
      convoId.current = res.conversation_id;
      setMsgs((m) =>
        m.map((x) =>
          x.id === pendingId
            ? { ...x, text: res.text, pending: false, ts: Date.now() }
            : x,
        ),
      );
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : String(err);
      setMsgs((m) => m.filter((x) => x.id !== pendingId));
      toasts.error(detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="eyebrow">Chat · AI router · speaks reply</span>
        <span
          className={cx(
            "font-mono text-[10px] uppercase tracking-wider",
            aiAvailable ? "text-phosphor" : "text-mute",
          )}
        >
          {provider ?? "no provider"}
          {provider && !aiAvailable ? " · offline" : ""}
        </span>
      </div>

      <div
        ref={scrollRef}
        className="scrollbar-thin mb-2 h-[148px] space-y-2.5 overflow-y-auto rounded-xl border border-line bg-void/40 p-3"
      >
        {msgs.length === 0 ? (
          <div className="grid h-full place-items-center text-center">
            <p className="font-mono text-[11px] leading-relaxed text-mute">
              {aiAvailable
                ? "Start a conversation. The robot will speak each reply aloud."
                : "AI provider not configured — chat is unavailable."}
            </p>
          </div>
        ) : (
          msgs.map((m) => <Bubble key={m.id} msg={m} />)
        )}
      </div>

      <div className="flex items-end gap-2">
        <input
          value={text}
          disabled={!aiAvailable || busy}
          placeholder={aiAvailable ? "Ask the robot anything…" : "AI offline"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          className={cx(
            "min-w-0 flex-1 rounded-xl border border-line bg-void/60 px-3.5 py-2.5",
            "font-body text-sm text-ink placeholder:text-mute/70",
            "focus:border-cyan/50 focus:outline-none focus:ring-1 focus:ring-cyan/30",
            "disabled:cursor-not-allowed disabled:opacity-40",
          )}
        />
        <Button
          variant="primary"
          loading={busy}
          disabled={!aiAvailable || !text.trim()}
          onClick={submit}
        >
          Send
        </Button>
      </div>
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div className={cx("flex animate-fade-up", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cx(
          "max-w-[85%] rounded-2xl px-3 py-2 text-[13px] leading-snug",
          isUser
            ? "rounded-br-sm border border-line bg-panel-2 text-ink"
            : "rounded-bl-sm border border-cyan/25 bg-cyan/[0.07] text-ink",
        )}
      >
        {msg.pending ? (
          <span className="flex items-center gap-1.5 py-0.5 text-cyan">
            <Dot3 />
          </span>
        ) : (
          <>
            <span className="whitespace-pre-wrap break-words">{msg.text}</span>
            <span className="mt-1 block text-right font-mono text-[9px] text-mute">
              {clockTime(msg.ts)}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

function Dot3() {
  return (
    <span className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-cyan"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </span>
  );
}
