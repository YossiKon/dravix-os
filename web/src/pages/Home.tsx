// Home — everything to operate the robot: live state, sleep/wake, chat, games, head, face, LEDs.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { Live, RobotConfig, SecurityInfo } from "../api";
import { RobotFace, stateLabel } from "../components/RobotFace";
import { Joystick } from "../components/Joystick";
import { Section, Spinner, toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

type Bi = { he: string; en: string };

const GAMES: Record<string, Bi> = {
  dice: { he: "🎲 קובייה", en: "🎲 Dice" },
  coin: { he: "🪙 מטבע", en: "🪙 Coin flip" },
  "8ball": { he: "🎱 כדור הקסם", en: "🎱 Magic 8-ball" },
  joke: { he: "😂 בדיחה", en: "😂 Joke" },
  fortune: { he: "🔮 צפה עתיד", en: "🔮 Fortune" },
};

const EMOTES: Record<string, Bi> = {
  happy: { he: "🕺 ריקוד", en: "🕺 Dance" },
  love: { he: "💗 אהבה", en: "💗 Love" },
  surprised: { he: "😮 הפתעה", en: "😮 Surprise" },
  yes: { he: "👍 כן", en: "👍 Yes" },
  no: { he: "👎 לא", en: "👎 No" },
  curious: { he: "🧐 סקרן", en: "🧐 Curious" },
  fistbump: { he: "👊 כיף", en: "👊 Fist bump" },
  wake: { he: "🌅 התעוררות", en: "🌅 Wake up" },
  sad: { he: "🥺 עצוב", en: "🥺 Sad" },
  sleepy: { he: "🥱 מנומנם", en: "🥱 Sleepy" },
};

interface ChatMsg {
  role: "user" | "bot";
  text: string;
}

const MODES: { id: string; he: string; en: string; icon: string }[] = [
  { id: "awake", he: "ער", en: "Awake", icon: "☀" },
  { id: "morning", he: "בוקר", en: "Morning", icon: "🌅" },
  { id: "focus", he: "מרוכז", en: "Focus", icon: "🎯" },
  { id: "quiet", he: "שקט", en: "Quiet", icon: "🤫" },
  { id: "night", he: "לילה", en: "Night", icon: "🌌" },
  { id: "sleep", he: "שינה", en: "Sleep", icon: "😴" },
];

const FACES: { name: string; glyph: string; he: string; en: string }[] = [
  { name: "neutral", glyph: "o_o", he: "רגיל", en: "Neutral" },
  { name: "happy", glyph: "^_^", he: "שמח", en: "Happy" },
  { name: "sad", glyph: "T_T", he: "עצוב", en: "Sad" },
  { name: "angry", glyph: ">_<", he: "כועס", en: "Angry" },
  { name: "sleepy", glyph: "u_u", he: "עייף", en: "Sleepy" },
  { name: "doubt", glyph: "o_O", he: "מסופק", en: "Doubt" },
];

const LED_COLORS: { name: string; css: string; he: string; en: string }[] = [
  { name: "red", css: "#ff5a52", he: "אדום", en: "Red" },
  { name: "orange", css: "#ff9440", he: "כתום", en: "Orange" },
  { name: "yellow", css: "#ffc23d", he: "צהוב", en: "Yellow" },
  { name: "green", css: "#5ad674", he: "ירוק", en: "Green" },
  { name: "cyan", css: "#2ee6c8", he: "טורקיז", en: "Cyan" },
  { name: "blue", css: "#4d9bff", he: "כחול", en: "Blue" },
  { name: "purple", css: "#a86bff", he: "סגול", en: "Purple" },
  { name: "white", css: "#f2f2f2", he: "לבן", en: "White" },
];

export function HomePage(props: { config: RobotConfig | null }) {
  const { tr, lang } = useI18n();
  const L = (o: Bi) => tr(o.he, o.en);
  const pick = (o: Bi | undefined, fb: string) => (o ? L(o) : fb);

  const [live, setLive] = useState<Live | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  // chat with the HA Assist AI — a running conversation with memory
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [speak, setSpeak] = useState(true);
  const chatRef = useRef<HTMLDivElement>(null);
  // games + emotes offered by the core ("settled" = the fetch finished, even if empty/failed)
  const [games, setGames] = useState<string[]>([]);
  const [emotes, setEmotes] = useState<string[]>([]);
  const [gamesSettled, setGamesSettled] = useState(false);
  const [emotesSettled, setEmotesSettled] = useState(false);
  // live view through the robot's camera (off by default — saves bandwidth)
  const [camOn, setCamOn] = useState(false);
  // privacy mode: camera blocked + on-device mic off
  const [privacy, setPrivacy] = useState<{ supported: boolean; private: boolean }>({
    supported: false,
    private: false,
  });
  // security mode: armed state + how many snapshots are stored (null = not loaded yet)
  const [sec, setSec] = useState<SecurityInfo | null>(null);

  const refreshSecurity = () =>
    apiGet<SecurityInfo>("/api/security/photos?limit=1").then(setSec).catch(() => undefined);

  useEffect(() => {
    apiGet<{ games: string[] }>("/api/fun")
      .then((r) => setGames(r.games))
      .catch(() => undefined)
      .finally(() => setGamesSettled(true));
    apiGet<{ emotes: string[] }>("/api/emotes")
      .then((r) => setEmotes(r.emotes))
      .catch(() => undefined)
      .finally(() => setEmotesSettled(true));
    apiGet<{ supported: boolean; private: boolean }>("/api/robot/privacy").then(setPrivacy).catch(() => undefined);
    void refreshSecurity();
  }, []);

  async function toggleSecurity() {
    try {
      if (sec?.armed) await apiSend("/api/modes/deactivate", "POST", {});
      else await apiSend("/api/modes/security/activate", "POST", {});
      await refreshSecurity();
      toast(
        sec?.armed
          ? tr("מצב אבטחה כבוי", "Security disarmed")
          : tr("🛡 מצב אבטחה דרוך — מצלם ומסייר", "🛡 Security armed — snapping & patrolling"),
      );
    } catch (e) {
      toastErr(e);
    }
  }

  async function togglePrivacy() {
    const next = !privacy.private;
    try {
      await apiSend("/api/robot/privacy", "PUT", { private: next });
      setPrivacy((p) => ({ ...p, private: next }));
      if (next) setCamOn(false);
      toast(
        next
          ? tr("מצב פרטיות פועל — מצלמה ומיקרופון כבויים 🔒", "Privacy on — camera & mic off 🔒")
          : tr("מצב פרטיות כובה", "Privacy off"),
      );
    } catch (e) {
      toastErr(e);
    }
  }

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight });
  }, [msgs]);

  // Poll the robot's live state (published by the firmware) every 2.5s while visible.
  useEffect(() => {
    let stop = false;
    let misses = 0;
    async function tick() {
      if (document.visibilityState === "visible") {
        try {
          const l = await apiGet<Live>("/api/robot/live");
          misses = 0;
          if (!stop) setLive(l);
        } catch {
          // Keep the last known state through a blip, but after 3 straight
          // misses admit the robot is gone and show the offline face.
          misses += 1;
          if (misses >= 3 && !stop) setLive(null);
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
    const q = text.trim();
    if (!q) return;
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setText("");
    setBusy("ask");
    try {
      const r = await apiSend<{ text: string; conversation_id: string | null }>("/api/ai/chat", "POST", {
        text: q,
        conversation_id: convId,
        speak,
      });
      setConvId(r.conversation_id ?? null);
      setMsgs((m) => [...m, { role: "bot", text: r.text }]);
    } catch (e) {
      toastErr(e);
      // Failed — put the question back in the input and drop its bubble, so nothing is lost.
      setMsgs((m) => (m.length && m[m.length - 1]?.role === "user" ? m.slice(0, -1) : m));
      setText((cur) => cur || q);
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
            {online ? (state ? stateLabel(state, lang) : tr("מחובר", "Connected")) : tr("לא מחובר", "Offline")}
          </span>
          {live?.battery != null && (
            <span
              className={`chip ${live.battery < 20 ? "border-red/60 text-red" : ""}`}
              title={tr("סוללת הרובוט", "Robot battery")}
            >
              🔋 {live.battery}%
            </span>
          )}
          {privacy.supported && (
            <button
              className={`chip ${privacy.private ? "border-red/60 bg-red/15 text-red" : ""}`}
              onClick={() => void togglePrivacy()}
            >
              {privacy.private ? tr("🔒 פרטיות פועלת", "🔒 Privacy on") : tr("🔓 מצב פרטיות", "🔓 Privacy")}
            </button>
          )}
        </div>
        {/* modes */}
        <div className="mt-3 flex flex-wrap gap-2">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={`chip ${state === m.id || (m.id === "awake" && state === "awake") ? "chip-on" : ""}`}
              disabled={busy !== null}
              onClick={() => void run(`mode-${m.id}`, () => apiSend("/api/robot/mode", "POST", { mode: m.id }))}
            >
              {m.icon} {L(m)}
            </button>
          ))}
        </div>
        {/* what it heard / answered — live */}
        {(live?.heard || live?.reply) && (
          <div className="mt-3 space-y-2">
            {live?.heard && (
              <div className="me-8 rounded-2xl rounded-tr-md border border-line bg-card2 px-4 py-2 text-sm">
                <span className="text-mute">{tr("שמעתי: ", "Heard: ")}</span>
                {live.heard}
              </div>
            )}
            {live?.reply && (
              <div className="ms-8 rounded-2xl rounded-tl-md border border-teal/30 bg-teal/10 px-4 py-2 text-sm">
                <span className="text-teal/70">{tr("עניתי: ", "Replied: ")}</span>
                {live.reply}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── chat with the HA Assist AI ── */}
      <Section title={tr("דבר איתו", "Talk to it")} delay={60}>
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
          placeholder={tr("שאל אותו כל דבר — הוא זוכר את השיחה…", "Ask it anything — it remembers the conversation…")}
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
            {busy === "ask" ? <Spinner /> : "🤖"} {tr("שלח לבינה", "Send to AI")}
          </button>
          <button
            className="btn"
            disabled={!text.trim() || busy !== null}
            onClick={() =>
              void run("say", async () => {
                await apiSend("/api/robot/say", "POST", { text });
                setText("");
              }, tr("הרובוט מקריא 📢", "Reading aloud 📢"))
            }
          >
            {tr("📢 הקרא", "📢 Read aloud")}
          </button>
          <button className={`chip ${speak ? "chip-on" : ""}`} onClick={() => setSpeak((v) => !v)}>
            {tr("🔊 שידבר בקול", "🔊 Speak aloud")}
          </button>
          {msgs.length > 0 && (
            <button
              className="chip"
              onClick={() => {
                setMsgs([]);
                setConvId(null);
              }}
            >
              {tr("🗑 שיחה חדשה", "🗑 New chat")}
            </button>
          )}
        </div>
      </Section>

      {/* ── games + tricks ── */}
      <Section title={tr("משחקים וקטעים", "Games & tricks")} delay={90}>
        <label className="lbl">{tr("משחקים (הוא עונה בקול + על המסך)", "Games (answers by voice + on screen)")}</label>
        <div className="mb-3 flex flex-wrap gap-2">
          {games.map((g) => (
            <button key={g} className="chip" disabled={busy !== null} onClick={() => void playGame(g)}>
              {pick(GAMES[g], g)}
            </button>
          ))}
          {games.length === 0 && (
            <span className="text-sm text-mute">
              {gamesSettled ? tr("אין משחקים זמינים", "No games available") : tr("טוען…", "Loading…")}
            </span>
          )}
        </div>
        <label className="lbl">{tr("קטעים (תנועה + פרצוף + לדים)", "Tricks (motion + face + LEDs)")}</label>
        <div className="flex flex-wrap gap-2">
          {emotes.map((e) => (
            <button
              key={e}
              className="chip"
              disabled={busy !== null}
              onClick={() => void run("emote", () => apiSend("/api/robot/emote", "POST", { name: e }))}
            >
              {pick(EMOTES[e], e)}
            </button>
          ))}
          {emotes.length === 0 && (
            <span className="text-sm text-mute">
              {emotesSettled ? tr("אין קטעים זמינים", "No tricks available") : tr("טוען…", "Loading…")}
            </span>
          )}
        </div>
      </Section>

      {/* ── head ── */}
      <Section title={tr("הזזת ראש", "Move the head")} delay={120}>
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
            {tr("⊙ למרכז", "⊙ Center")}
          </button>
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() =>
              void run("home", () => apiSend("/api/robot/head/home", "POST"), tr("המיקום הנוכחי נקבע כ׳ישר׳", "Current position set as 'straight'"))
            }
          >
            {tr("⌖ קבע כ׳ישר׳", "⌖ Set as 'straight'")}
          </button>
        </div>
        <p className="mt-2 text-xs text-mute">
          {tr(
            "גרור על המשטח ושחרר — הראש יזוז לשם. ״קבע כ׳ישר׳״ = כיול: קודם יישר את הראש עם היד.",
            "Drag on the pad and release — the head moves there. 'Set as straight' = calibrate: line the head up by hand first.",
          )}
        </p>
      </Section>

      {/* ── face ── */}
      <Section title={tr("פרצוף", "Face")} delay={180}>
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
              <span className="text-xs text-mute">{L(f)}</span>
            </button>
          ))}
        </div>
      </Section>

      {/* ── LEDs ── */}
      <Section title={tr("לדים", "LEDs")} delay={240}>
        <div className="flex flex-wrap items-center gap-2.5">
          {LED_COLORS.map((c) => (
            <button
              key={c.name}
              title={L(c)}
              aria-label={L(c)}
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
            {tr("⏻ כבוי", "⏻ Off")}
          </button>
        </div>
      </Section>

      {/* ── robot camera (only when a camera is mapped) ── */}
      {(props.config?.capabilities ?? []).includes("take_photo") && (
        <Section title={tr("מצלמה", "Camera")} delay={300}>
          {privacy.private ? (
            <p className="rounded-2xl border border-red/30 bg-red/10 p-3 text-sm text-red">
              {tr("🔒 מצב פרטיות פועל — המצלמה חסומה לגמרי (גם לכלים חיצוניים).", "🔒 Privacy on — the camera is fully blocked (external tools too).")}
            </p>
          ) : camOn ? (
            <>
              <img
                src="/camera/robot/stream.mjpeg"
                alt={tr("מצלמת הרובוט", "Robot camera")}
                className="w-full rounded-2xl border border-line bg-black"
              />
              <button className="btn mt-3 w-full" onClick={() => setCamOn(false)}>
                {tr("⏹ עצור צפייה", "⏹ Stop")}
              </button>
            </>
          ) : (
            <button className="btn btn-primary w-full" onClick={() => setCamOn(true)}>
              {tr("🎥 צפה דרך העיניים של הרובוט", "🎥 See through the robot's eyes")}
            </button>
          )}
          <p className="mt-2 text-xs text-mute">
            {tr(
              "אותו זרם זמין לכל NVR או כלי לזיהוי אנשים (למשל Frigate):",
              "The same stream is available to any NVR or person-detection tool (e.g. Frigate):",
            )}{" "}
            <span dir="ltr" className="font-mono">/camera/robot/stream.mjpeg</span>
          </p>
        </Section>
      )}

      {/* ── security mode — arm the robot as a little guard camera ── */}
      {(props.config?.capabilities ?? []).includes("take_photo") && sec && (
        <Section title={tr("🛡 אבטחה", "🛡 Security")} delay={330}>
          <p className="mb-3 text-sm text-mute">
            {tr(
              "כשדרוך: שומר תמונה כל כמה שניות, מסייר עם הראש כל כמה דקות, ואפשר לצפות ולכוון אותו בלייב מכאן (גם מרחוק, דרך הגישה של Home Assistant).",
              "When armed: saves a frame every few seconds, patrols with its head every few minutes, and you can watch & steer live from here (remotely too, via Home Assistant's remote access).",
            )}
          </p>
          <button
            className={`btn w-full ${sec.armed ? "btn-danger" : "btn-primary"}`}
            onClick={() => void toggleSecurity()}
          >
            {sec.armed ? tr("⏹ כבה מצב אבטחה", "⏹ Disarm") : tr("🛡 הפעל מצב אבטחה", "🛡 Arm security mode")}
          </button>
          {sec.total > 0 && (
            <div className="mt-3 flex items-center gap-3">
              {sec.photos[0] && (
                <img
                  src={`/api/security/photo/${sec.photos[0].day}/${sec.photos[0].name}`}
                  alt={tr("התמונה האחרונה", "Latest snapshot")}
                  className="h-16 w-24 rounded-xl border border-line object-cover"
                />
              )}
              <p className="text-xs text-mute">
                {tr(`${sec.total} תמונות שמורות`, `${sec.total} snapshots saved`)}
                {sec.photos[0] && (
                  <>
                    {" · "}
                    <span dir="ltr" className="font-mono">
                      {sec.photos[0].day} {sec.photos[0].name.replace(".jpg", "")}
                    </span>
                  </>
                )}
              </p>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
