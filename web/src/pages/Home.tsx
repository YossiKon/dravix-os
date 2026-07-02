// דף הבית — הכל בשביל לתפעל את הרובוט: מצב חי, שינה/ערות, צ׳אט, משחקים, ראש, פרצוף, לדים.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { Live, RobotConfig } from "../api";
import { RobotFace, stateLabel } from "../components/RobotFace";
import { Joystick } from "../components/Joystick";
import { Section, Spinner, toast, toastErr } from "../ui";

const GAME_HE: Record<string, string> = {
  dice: "🎲 קובייה",
  coin: "🪙 מטבע",
  "8ball": "🎱 כדור הקסם",
  joke: "😂 בדיחה",
  fortune: "🔮 צפה עתיד",
};

const EMOTE_HE: Record<string, string> = {
  happy: "🕺 ריקוד",
  love: "💗 אהבה",
  surprised: "😮 הפתעה",
  yes: "👍 כן",
  no: "👎 לא",
  curious: "🧐 סקרן",
  fistbump: "👊 כיף",
  wake: "🌅 התעוררות",
  sad: "🥺 עצוב",
  sleepy: "🥱 מנומנם",
};

interface ChatMsg {
  role: "user" | "bot";
  text: string;
}

const FACES: { name: string; glyph: string; he: string }[] = [
  { name: "neutral", glyph: "o_o", he: "רגיל" },
  { name: "happy", glyph: "^_^", he: "שמח" },
  { name: "sad", glyph: "T_T", he: "עצוב" },
  { name: "angry", glyph: ">_<", he: "כועס" },
  { name: "sleepy", glyph: "u_u", he: "עייף" },
  { name: "doubt", glyph: "o_O", he: "מסופק" },
];

const LED_COLORS: { name: string; css: string; he: string }[] = [
  { name: "red", css: "#ff5a52", he: "אדום" },
  { name: "orange", css: "#ff9440", he: "כתום" },
  { name: "yellow", css: "#ffc23d", he: "צהוב" },
  { name: "green", css: "#5ad674", he: "ירוק" },
  { name: "cyan", css: "#2ee6c8", he: "טורקיז" },
  { name: "blue", css: "#4d9bff", he: "כחול" },
  { name: "purple", css: "#a86bff", he: "סגול" },
  { name: "white", css: "#f2f2f2", he: "לבן" },
];

export function HomePage(props: { config: RobotConfig | null }) {
  const [live, setLive] = useState<Live | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  // chat with the HA Assist AI — a running conversation with memory
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [speak, setSpeak] = useState(true);
  const chatRef = useRef<HTMLDivElement>(null);
  // games + emotes offered by the core
  const [games, setGames] = useState<string[]>([]);
  const [emotes, setEmotes] = useState<string[]>([]);
  // live view through the robot's camera (off by default — saves bandwidth)
  const [camOn, setCamOn] = useState(false);

  useEffect(() => {
    apiGet<{ games: string[] }>("/api/fun").then((r) => setGames(r.games)).catch(() => undefined);
    apiGet<{ emotes: string[] }>("/api/emotes").then((r) => setEmotes(r.emotes)).catch(() => undefined);
  }, []);

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight });
  }, [msgs]);

  // Poll the robot's live state (published by the firmware) every 2.5s while visible.
  useEffect(() => {
    let stop = false;
    async function tick() {
      if (document.visibilityState === "visible") {
        try {
          const l = await apiGet<Live>("/api/robot/live");
          if (!stop) setLive(l);
        } catch {
          /* keep the last known state */
        }
      }
    }
    void tick();
    const t = setInterval(() => void tick(), 2500);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  const run = useCallback(async (key: string, fn: () => Promise<unknown>, okMsg?: string) => {
    setBusy(key);
    try {
      await fn();
      if (okMsg) toast(okMsg);
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(null);
    }
  }, []);

  // Send a chat message to the HA Assist AI (keeps the conversation id = memory).
  async function ask() {
    const t = text.trim();
    if (!t) return;
    setMsgs((m) => [...m, { role: "user", text: t }]);
    setText("");
    setBusy("ask");
    try {
      const r = await apiSend<{ text: string; conversation_id: string | null }>("/api/ai/chat", "POST", {
        text: t,
        conversation_id: convId,
        speak,
      });
      setConvId(r.conversation_id ?? null);
      setMsgs((m) => [...m, { role: "bot", text: r.text }]);
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(null);
    }
  }

  // Play a party trick — the robot speaks the result; it also lands in the chat thread.
  async function playGame(name: string) {
    setBusy("game");
    try {
      const r = await apiSend<{ text?: string }>(`/api/fun/${encodeURIComponent(name)}`, "POST");
      if (r.text) setMsgs((m) => [...m, { role: "bot", text: r.text ?? "" }]);
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(null);
    }
  }

  const online = props.config?.online ?? false;
  const state = live?.state ?? null;

  return (
    <div className="space-y-4">
      {/* ── the live robot ── */}
      <div className="animate-rise">
        <RobotFace state={state} online={online} />
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="chip">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                online ? (state === "sleep" ? "bg-mute" : "bg-green animate-breathe") : "bg-red"
              }`}
            />
            {online ? (state ? stateLabel(state) : "מחובר") : "לא מחובר"}
          </span>
          <div className="flex gap-2">
            <button
              className={`btn ${state !== "sleep" ? "btn-primary" : ""}`}
              disabled={busy !== null}
              onClick={() => void run("wake", () => apiSend("/api/robot/mode", "POST", { mode: "awake" }), "הרובוט ער")}
            >
              ☀ ער
            </button>
            <button
              className={`btn ${state === "sleep" ? "btn-primary" : ""}`}
              disabled={busy !== null}
              onClick={() => void run("sleep", () => apiSend("/api/robot/mode", "POST", { mode: "sleep" }), "לילה טוב 😴")}
            >
              🌙 שינה
            </button>
          </div>
        </div>
        {/* what it heard / answered — live */}
        {(live?.heard || live?.reply) && (
          <div className="mt-3 space-y-2">
            {live?.heard && (
              <div className="me-8 rounded-2xl rounded-tr-md border border-line bg-card2 px-4 py-2 text-sm">
                <span className="text-mute">שמעתי: </span>
                {live.heard}
              </div>
            )}
            {live?.reply && (
              <div className="ms-8 rounded-2xl rounded-tl-md border border-teal/30 bg-teal/10 px-4 py-2 text-sm">
                <span className="text-teal/70">עניתי: </span>
                {live.reply}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── chat with the HA Assist AI ── */}
      <Section title="דבר איתו" delay={60}>
        {msgs.length > 0 && (
          <div ref={chatRef} className="mb-3 max-h-72 space-y-2 overflow-y-auto pe-1">
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="me-8 rounded-2xl rounded-tr-md border border-line bg-card2 px-4 py-2 text-sm">
                  {m.text}
                </div>
              ) : (
                <div key={i} className="ms-8 rounded-2xl rounded-tl-md border border-teal/30 bg-teal/10 px-4 py-2 text-sm">
                  {m.text}
                </div>
              ),
            )}
          </div>
        )}
        <textarea
          className="inp min-h-20 resize-none"
          placeholder="שאל אותו כל דבר — הוא זוכר את השיחה…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && text.trim() && busy === null) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn btn-amber flex-1" disabled={!text.trim() || busy !== null} onClick={() => void ask()}>
            {busy === "ask" ? <Spinner /> : "🤖"} שלח לבינה
          </button>
          <button
            className="btn"
            disabled={!text.trim() || busy !== null}
            onClick={() =>
              void run("say", async () => {
                await apiSend("/api/robot/say", "POST", { text });
                setText("");
              }, "הרובוט מקריא 📢")
            }
          >
            📢 הקרא
          </button>
          <button className={`chip ${speak ? "chip-on" : ""}`} onClick={() => setSpeak((v) => !v)}>
            🔊 שידבר בקול
          </button>
          {msgs.length > 0 && (
            <button
              className="chip"
              onClick={() => {
                setMsgs([]);
                setConvId(null);
              }}
            >
              🗑 שיחה חדשה
            </button>
          )}
        </div>
      </Section>

      {/* ── games + tricks ── */}
      <Section title="משחקים וקטעים" delay={90}>
        <label className="lbl">משחקים (הוא עונה בקול + על המסך)</label>
        <div className="mb-3 flex flex-wrap gap-2">
          {games.map((g) => (
            <button key={g} className="chip" disabled={busy !== null} onClick={() => void playGame(g)}>
              {GAME_HE[g] ?? g}
            </button>
          ))}
          {games.length === 0 && <span className="text-sm text-mute">טוען…</span>}
        </div>
        <label className="lbl">קטעים (תנועה + פרצוף + לדים)</label>
        <div className="flex flex-wrap gap-2">
          {emotes.map((e) => (
            <button
              key={e}
              className="chip"
              disabled={busy !== null}
              onClick={() => void run("emote", () => apiSend("/api/robot/emote", "POST", { name: e }))}
            >
              {EMOTE_HE[e] ?? e}
            </button>
          ))}
          {emotes.length === 0 && <span className="text-sm text-mute">טוען…</span>}
        </div>
      </Section>

      {/* ── head ── */}
      <Section title="הזזת ראש" delay={120}>
        <Joystick
          onRelease={(yaw, pitch) =>
            void run("head", () => apiSend("/api/robot/head", "POST", { yaw, pitch, speed: 0.6 }))
          }
        />
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() => void run("center", () => apiSend("/api/robot/head", "POST", { yaw: 0, pitch: 0, speed: 0.5 }))}
          >
            ⊙ למרכז
          </button>
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() =>
              void run("home", () => apiSend("/api/robot/head/home", "POST"), "המיקום הנוכחי נקבע כ׳ישר׳")
            }
          >
            ⌖ קבע כ׳ישר׳
          </button>
        </div>
        <p className="mt-2 text-xs text-mute">גרור על המשטח ושחרר — הראש יזוז לשם. ״קבע כ׳ישר׳״ = כיול: קודם יישר את הראש עם היד.</p>
      </Section>

      {/* ── face ── */}
      <Section title="פרצוף" delay={180}>
        <div className="grid grid-cols-3 gap-2">
          {FACES.map((f) => (
            <button
              key={f.name}
              className="btn flex-col gap-0.5 py-2"
              disabled={busy !== null}
              onClick={() => void run("face", () => apiSend("/api/robot/face", "POST", { expression: f.name }))}
            >
              <span dir="ltr" className="font-mono text-lg text-teal">
                {f.glyph}
              </span>
              <span className="text-xs text-mute">{f.he}</span>
            </button>
          ))}
        </div>
      </Section>

      {/* ── LEDs ── */}
      <Section title="לדים" delay={240}>
        <div className="flex flex-wrap items-center gap-2.5">
          {LED_COLORS.map((c) => (
            <button
              key={c.name}
              title={c.he}
              aria-label={c.he}
              className="h-12 w-12 rounded-full border-2 border-line-2 transition active:scale-90"
              style={{ background: c.css }}
              disabled={busy !== null}
              onClick={() => void run("led", () => apiSend("/api/robot/leds", "POST", { color: c.name, brightness: 0.8 }))}
            />
          ))}
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() => void run("ledoff", () => apiSend("/api/robot/leds", "POST", { color: "off", brightness: 0 }))}
          >
            ⏻ כבוי
          </button>
        </div>
      </Section>

      {/* ── robot camera (only when a camera is mapped) ── */}
      {(props.config?.capabilities ?? []).includes("take_photo") && (
        <Section title="מצלמה" delay={300}>
          {camOn ? (
            <>
              <img
                src="/camera/robot/stream.mjpeg"
                alt="מצלמת הרובוט"
                className="w-full rounded-2xl border border-line bg-black"
              />
              <button className="btn mt-3 w-full" onClick={() => setCamOn(false)}>
                ⏹ עצור צפייה
              </button>
            </>
          ) : (
            <button className="btn btn-primary w-full" onClick={() => setCamOn(true)}>
              🎥 צפה דרך העיניים של הרובוט
            </button>
          )}
          <p className="mt-2 text-xs text-mute">
            אותו זרם משמש גם את Frigate לזיהוי אנשים: <span dir="ltr" className="font-mono">/camera/robot/stream.mjpeg</span>
          </p>
        </Section>
      )}
    </div>
  );
}
