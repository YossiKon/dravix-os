// Home — everything to operate the robot: live state, sleep/wake, chat, games, head, face, LEDs.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { Live, RobotConfig, SecurityInfo } from "../api";
import { RobotFace, stateLabel } from "../components/RobotFace";
import { Joystick } from "../components/Joystick";
import { SecurityGallery } from "../components/SecurityGallery";
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
  { name: "love", glyph: "♥_♥", he: "מאוהב", en: "In love" },
  { name: "dizzy", glyph: "x_x", he: "מסוחרר", en: "Dizzy" },
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
  const [galleryOpen, setGalleryOpen] = useState(false);
  // speaker volume (0-100); null until loaded / unsupported
  const [vol, setVol] = useState<number | null>(null);
  // the last photo taken via the 📸 ritual (shown inline under the camera)
  const [shot, setShot] = useState<{ day: string; name: string } | null>(null);
  // kitchen timers running on the core (the robot speaks when one fires)
  const [timers, setTimers] = useState<{ id: number | string; label: string; seconds_left: number }[]>([]);
  const [tMin, setTMin] = useState("");
  const [tLabel, setTLabel] = useState("");

  const takePhoto = () =>
    run("photo", async () => {
      const r = await apiSend<{ day: string; name: string }>("/api/robot/photo", "POST", {});
      setShot(r);
      void refreshSecurity();
    }, tr("📸 צולם! נשמר בגלריה", "📸 Snapped! Saved to the gallery"));
  const [boothBusy, setBoothBusy] = useState(false);
  async function photobooth() {
    setBoothBusy(true);
    try {
      const r = await apiSend<{ day: string; name: string }>("/api/robot/photobooth", "POST", {});
      setShot(r);
      toast(tr("📸 סלפי! נשמר בגלריה", "📸 Selfie! Saved to the gallery"));
      void refreshSecurity();
    } catch (e) {
      toastErr(e);
    } finally {
      setBoothBusy(false);
    }
  }
  const volTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // don't leave a pending volume PUT behind after unmount
  useEffect(() => () => { if (volTimer.current) clearTimeout(volTimer.current); }, []);

  function onVolume(v: number) {
    setVol(v);
    if (volTimer.current) clearTimeout(volTimer.current);
    volTimer.current = setTimeout(() => {
      apiSend("/api/robot/volume", "PUT", { volume: v }).catch(toastErr);
    }, 250); // debounce while dragging
  }

  const refreshSecurity = () =>
    apiGet<SecurityInfo>("/api/security/photos?limit=1").then(setSec).catch(() => undefined);

  const refreshTimers = () =>
    apiGet<{ timers: { id: number | string; label: string; seconds_left: number }[] }>("/api/timers")
      .then((r) => setTimers(r.timers))
      .catch(() => undefined);

  // Poll active timers every 5s while the tab is visible.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") void refreshTimers();
    };
    tick();
    const t = setInterval(tick, 5000);
    return () => clearInterval(t);
  }, []);

  async function startTimer(minutes: number, label: string) {
    if (!Number.isFinite(minutes) || minutes <= 0) return;
    if (minutes > 1440) {
      toast(tr("מקסימום 24 שעות (1440 דק׳)", "Max 24 hours (1440 min)"), "err");
      return;
    }
    try {
      await apiSend("/api/timer", "POST", { seconds: Math.round(minutes * 60), label });
      toast(tr("⏲ הטיימר הופעל", "⏲ Timer started"));
      setTMin("");
      setTLabel("");
      await refreshTimers();
    } catch (e) {
      toastErr(e);
    }
  }

  async function cancelTimer(id: number | string) {
    try {
      await apiSend(`/api/timers/${encodeURIComponent(String(id))}`, "DELETE");
      await refreshTimers();
    } catch (e) {
      toastErr(e);
    }
  }

  const fmtLeft = (s: number) => {
    const sec = Math.max(0, Math.round(s));
    return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
  };

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
    apiGet<{ supported: boolean; volume: number | null }>("/api/robot/volume")
      .then((r) => setVol(r.supported ? r.volume : null))
      .catch(() => undefined);
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

  // Ref (not state) so a second trigger mid-flight — e.g. the joystick, which has no
  // disabled prop — can't start an overlapping action.
  const runningRef = useRef(false);
  const run = useCallback(async (key: string, fn: () => Promise<unknown>, okMsg?: string) => {
    if (runningRef.current) return;
    runningRef.current = true;
    setBusy(key);
    try {
      await fn();
      if (okMsg) toast(okMsg);
    } catch (e) {
      toastErr(e);
    } finally {
      runningRef.current = false;
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
      // Local AI models can be slow — give chat a much longer deadline than the default.
      const r = await apiSend<{ text: string; conversation_id: string | null }>(
        "/api/ai/chat",
        "POST",
        { text: q, conversation_id: convId, speak },
        180000,
      );
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
        {/* speaker volume — synced with the slider on the robot's own status bar */}
        {vol != null && (
          <div className="mt-3 flex items-center gap-3">
            <span className="text-sm text-mute">🔊</span>
            <input
              type="range"
              min={0}
              max={100}
              value={vol}
              onChange={(e) => onVolume(Number(e.target.value))}
              className="h-2 flex-1 accent-teal"
              aria-label={tr("עוצמת קול", "Volume")}
            />
            <span dir="ltr" className="w-10 text-end font-mono text-xs text-mute">{vol}%</span>
          </div>
        )}
        {/* modes */}
        <div className="mt-3 flex flex-wrap gap-2">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={`chip ${
                state === m.id ||
                (m.id === "awake" && ["listening", "thinking", "speaking", "screensaver"].includes(state ?? ""))
                  ? "chip-on"
                  : ""
              }`}
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

      {/* ── kitchen timers — the robot speaks up when one fires ── */}
      <Section title={tr("⏲ טיימרים", "⏲ Timers")} delay={100}>
        <div className="flex flex-wrap gap-2">
          {[5, 10, 25, 50].map((m) => (
            <button key={m} className="chip" onClick={() => void startTimer(m, "")}>
              {tr(`${m} דק׳`, `${m} min`)}
            </button>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={1440}
            className="inp w-20 text-center"
            placeholder={tr("דק׳", "min")}
            value={tMin}
            onChange={(e) => setTMin(e.target.value)}
          />
          <input
            className="inp flex-1"
            placeholder={tr("תווית — למשל: פסטה", "Label — e.g. Pasta")}
            value={tLabel}
            onChange={(e) => setTLabel(e.target.value)}
          />
          <button
            className="btn btn-primary"
            disabled={!tMin || Number(tMin) <= 0 || Number(tMin) > 1440}
            onClick={() => void startTimer(Number(tMin), tLabel.trim())}
          >
            {tr("▶ הפעל", "▶ Start")}
          </button>
        </div>
        {timers.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {timers.map((t) => (
              <div key={t.id} className="flex items-center gap-2 rounded-2xl border border-line bg-card2 px-3 py-2 text-sm">
                <span className="flex-1">{t.label || tr("טיימר", "Timer")}</span>
                <span dir="ltr" className="font-mono text-xs text-teal">{fmtLeft(t.seconds_left)}</span>
                <button className="chip" onClick={() => void cancelTimer(t.id)} aria-label={tr("בטל טיימר", "Cancel timer")}>
                  ✖
                </button>
              </div>
            ))}
          </div>
        )}
        <p className="mt-2 text-xs text-mute">
          {tr("כשהזמן נגמר — הרובוט מכריז על זה בקול.", "When time is up — the robot announces it out loud.")}
        </p>
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
        {/* the LED bar's built-in animated effects (run on-device) */}
        <div className="mt-3 flex flex-wrap gap-2">
          {(
            [
              { he: "🌈 קשת", en: "🌈 Rainbow", effect: "Rainbow Effect With Custom Values" },
              { he: "✨ נצנוץ", en: "✨ Twinkle", effect: "Twinkle Effect With Custom Values" },
              { he: "🎲 אקראי", en: "🎲 Random", effect: "Random" },
              { he: "⏹ עצור", en: "⏹ Stop", effect: "None" },
            ] as const
          ).map((e) => (
            <button
              key={e.effect}
              className="chip"
              disabled={busy !== null}
              onClick={() => void run("ledfx", () => apiSend("/api/robot/leds/effect", "POST", { effect: e.effect }))}
            >
              {tr(e.he, e.en)}
            </button>
          ))}
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
                onError={() => {
                  // stream dropped (robot offline / privacy flipped) — collapse instead of a broken-image icon
                  setCamOn(false);
                  toast(tr("הזרם נותק", "Stream dropped"), "err");
                }}
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
          {!privacy.private && (
            <div className="mt-3 flex gap-2">
              <button className="btn flex-1" onClick={() => void takePhoto()}>
                {tr("📸 צלם", "📸 Photo")}
              </button>
              <button className="btn flex-1 disabled:opacity-50" disabled={boothBusy} onClick={() => void photobooth()}>
                {boothBusy ? tr("3… 2… 1…", "3… 2… 1…") : tr("🎬 סלפי 3-2-1", "🎬 Selfie 3-2-1")}
              </button>
            </div>
          )}
          {shot && (
            <img
              src={`/api/security/photo/${shot.day}/${shot.name}`}
              alt={tr("התמונה שצולמה", "The photo")}
              className="mt-3 w-full rounded-2xl border border-line bg-black"
            />
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

      {/* ── security mode — arm the robot as a little guard camera ──
          Also shown when the robot is offline but photos exist, so the saved gallery
          stays reachable exactly when you'd want to review it. */}
      {sec && ((props.config?.capabilities ?? []).includes("take_photo") || sec.total > 0) && (
        <Section title={tr("🛡 אבטחה", "🛡 Security")} delay={330}>
          <p className="mb-3 text-sm text-mute">
            {tr(
              "כשדרוך: שומר תמונה כל כמה שניות, מסייר עם הראש כל כמה דקות, ואפשר לצפות ולכוון אותו בלייב מכאן, מכל מכשיר ברשת הביתית.",
              "When armed: saves a frame every few seconds, patrols with its head every few minutes, and you can watch & steer live from here, from any device on your home network.",
            )}
          </p>
          {sec.armed && (
            <div className="mb-2 flex items-center gap-2 text-sm">
              {sec.recording ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-red/15 px-2 py-0.5 font-semibold text-red">
                  <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-red" />
                  {tr("● מקליט וידאו", "● Recording video")}
                </span>
              ) : (
                <span className="text-mute">{tr("🛡 דרוך — תמונות בלבד", "🛡 Armed — photos only")}</span>
              )}
            </div>
          )}
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
                      {sec.photos[0].ts ? sec.photos[0].ts.replace("T", " ") : sec.photos[0].name.replace(".jpg", "")}
                    </span>
                  </>
                )}
              </p>
              <button className="chip ms-auto" onClick={() => setGalleryOpen((g) => !g)}>
                {galleryOpen ? tr("סגור גלריה", "Close gallery") : tr("🖼 גלריה", "🖼 Gallery")}
              </button>
            </div>
          )}
          {galleryOpen && (
            <div className="mt-3">
              <SecurityGallery onChanged={refreshSecurity} />
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
