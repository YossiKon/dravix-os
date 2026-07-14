// Settings — robot connection, behaviour, head calibration, timers, AI. Entity wiring is
// AUTO-DISCOVERED by the core (discovery.py) — shown here read-only, nothing to fill in.
import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { AppConfig, HAEntity, PluginMode, RobotConfig, ScreenTimers, Updates } from "../api";
import { Section, Toggle, toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

type Bi = { he: string; en: string };

// Labels for the robot's behaviour switches (matched by entity object_id suffix).
const BEHAVIORS: { suffix: string; he: string; en: string }[] = [
  { suffix: "greet_on_approach", he: "ברכה כשמישהו מתקרב", en: "Greet on approach" },
  { suffix: "sleep_when_dark", he: "שינה כשחשוך בחדר", en: "Sleep when the room is dark" },
  { suffix: "touch_reaction", he: "תגובה לליטוף", en: "React to petting" },
  { suffix: "speaking_leds", he: "לדים צהובים בשיחה", en: "Amber LEDs while talking" },
  { suffix: "random_blink", he: "מצמוץ טבעי", en: "Natural blinking" },
  { suffix: "idle_head_drift", he: "מבט/תנועה עצמאית", en: "Idle glances / motion" },
  { suffix: "tap_face_to_talk", he: "הקשה על הפרצוף = דיבור", en: "Tap face to talk" },
  { suffix: "body_language", he: "שפת גוף (תנועות ראש)", en: "Body language (head moves)" },
  { suffix: "mood_leds", he: "לדים לפי רגש", en: "Mood LEDs" },
];

// Labels for the entity roles (falls back to the server's English label).
const ROLES: Record<string, Bi> = {
  face_select: { he: "פרצוף (Face select)", en: "Face (select)" },
  head_yaw: { he: "ראש — ימינה / שמאלה", en: "Head — left / right" },
  head_pitch: { he: "ראש — למעלה / למטה", en: "Head — up / down" },
  media_player: { he: "רמקול (להקראה)", en: "Speaker (for TTS)" },
  tts_engine: { he: "קול — מנוע דיבור", en: "Voice — TTS engine" },
  led_light: { he: "פס הלדים", en: "LED bar" },
  camera: { he: "מצלמה", en: "Camera" },
  screensaver_number: { he: "טיימר שומר מסך (דקות)", en: "Screensaver timer (min)" },
  sleep_number: { he: "טיימר שינה (דקות)", en: "Sleep timer (min)" },
  mode_select: { he: "מצב (ער / שינה)", en: "Mode (awake / sleep)" },
  state_sensor: { he: "מצב חי (State)", en: "Live state (State sensor)" },
  heard_sensor: { he: "מה שמע (Last heard)", en: "Last heard" },
  reply_sensor: { he: "מה ענה (Last reply)", en: "Last reply" },
  image_url_text: { he: "הצגת תמונה (Show image URL)", en: "Show image URL" },
  dash_url_text: { he: "כתובת דשבורד (🌐)", en: "Dashboard URL (🌐)" },
  privacy_switch: { he: "מצב פרטיות (Privacy)", en: "Privacy mode" },
  islocal_switch: { he: "מקומי בלבד (isLocal)", en: "Local-only (isLocal)" },
  battery_sensor: { he: "אחוז סוללה", en: "Battery %" },
  presence_sensor: { he: "נוכחות ליד השולחן", en: "Presence nearby" },
  bubble_text: { he: "בועת דיבור (טקסט)", en: "Speech bubble (text)" },
  latest_fw_text: { he: "קושחה אחרונה זמינה", en: "Latest firmware" },
  brightness_number: { he: "בהירות מסך", en: "Screen brightness" },
  climate_name_text: { he: "מזגן — שם", en: "Climate name" },
  climate_set_text: { he: "מזגן — יעד", en: "Climate target" },
  climate_info_text: { he: "מזגן — מידע", en: "Climate info" },
};

// A custom AI personality — a name + system prompt (optional dedicated voice).
interface Persona {
  name: string;
  system_prompt: string;
  voice?: string;
}

interface Memory {
  id: number | string;
  text: string;
}

// A known person (face recognition) — name as trained in Frigate + their own greeting.
interface Person {
  name: string;
  line: string;
  line_he: string;
  primary: boolean;
}

const PROVIDERS: Record<string, Bi> = {
  ha_assist: { he: "העוזר של Home Assistant", en: "Home Assistant Assist" },
  claude: { he: "Claude", en: "Claude" },
  openai: { he: "OpenAI", en: "OpenAI" },
  ollama: { he: "Ollama (מקומי)", en: "Ollama (local)" },
};

export function SettingsPage(props: {
  config: RobotConfig | null;
  entities: HAEntity[];
  version: string;
  onConfigChanged: () => void;
}) {
  const { tr } = useI18n();
  const pick = (o: Bi | undefined, fb: string) => (o ? tr(o.he, o.en) : fb);

  const cfg = props.config;
  const [timers, setTimers] = useState<{ saver: string; sleep: string }>({ saver: "", sleep: "" });
  const [app, setApp] = useState<AppConfig | null>(null);
  const [switches, setSwitches] = useState<HAEntity[]>([]);
  const [robotName, setRobotName] = useState<string | null>(null); // null = not user-edited yet
  // 🌐 dashboard page URL (a HA dashboard screenshot, e.g. via the Puppet add-on)
  const [dashUrl, setDashUrl] = useState<string | null>(null); // null = not loaded yet
  const [dashSaved, setDashSaved] = useState(""); // the value the server currently holds
  const [updates, setUpdates] = useState<Updates | null>(null);
  const [modes, setModes] = useState<PluginMode[]>([]);
  const [openMode, setOpenMode] = useState<string | null>(null); // which mode's config is expanded
  const [modeEdits, setModeEdits] = useState<Record<string, Record<string, unknown>>>({});
  const [birthday, setBirthdayState] = useState<string | null>(null); // null = not edited yet
  // day schedule: preset hours → robot modes ("07:30 morning, 23:00 sleep")
  const [sched, setSched] = useState<{ at: string; mode: string; say: string }[]>([]);
  const [schedLoaded, setSchedLoaded] = useState(false);
  // screen brightness (10-100); null = robot doesn't expose it
  const [bright, setBright] = useState<number | null>(null);
  const brightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // custom AI personas + the active one (null = built-in default)
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [activePersona, setActivePersona] = useState<string | null>(null);
  const [personaOpen, setPersonaOpen] = useState(false);
  const [pName, setPName] = useState("");
  const [pPrompt, setPPrompt] = useState("");
  // TTS voice override
  const [voices, setVoices] = useState<string[]>([]);
  const [voiceLoaded, setVoiceLoaded] = useState(false);
  const [voiceText, setVoiceText] = useState("");
  // long-term memories fed into every conversation
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memText, setMemText] = useState("");
  // known people (face recognition) — per-person greeting + the ⭐ favourite
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
  const restoreInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    apiGet<{ entities: HAEntity[] }>("/api/ha/entities?domains=switch")
      .then((r) => setSwitches(r.entities))
      .catch(() => undefined);
    apiGet<{ url: string }>("/api/config/dashboard_url")
      .then((r) => {
        setDashUrl(r.url ?? "");
        setDashSaved(r.url ?? "");
      })
      .catch(() => setDashUrl(""));
  }, []);

  // Match each behaviour switch by object_id SUFFIX (switch.<anything>_greet_on_approach or
  // switch.greet_on_approach) — prefix-agnostic, so any device name works. Shortest wins on ties.
  const behaviors = useMemo(() => {
    return BEHAVIORS.flatMap((b) => {
      const candidates = switches.filter((s) => {
        const obj = s.entity_id.split(".")[1] ?? "";
        return obj === b.suffix || obj.endsWith(`_${b.suffix}`);
      });
      if (candidates.length === 0) return [];
      const ent = candidates.reduce((best, s) => (s.entity_id.length < best.entity_id.length ? s : best));
      return [{ ...ent, he: b.he, en: b.en }];
    });
  }, [switches]);

  async function flipBehavior(entityId: string, on: boolean) {
    try {
      await apiSend("/api/ha/switch", "POST", { entity_id: entityId, on });
      setSwitches((cur) =>
        cur.map((s) => (s.entity_id === entityId ? { ...s, state: on ? "on" : "off" } : s)),
      );
    } catch (e) {
      toastErr(e);
    }
  }

  useEffect(() => {
    apiGet<ScreenTimers>("/api/robot/screen")
      .then((t) => {
        setTimers({
          saver: t.screensaver_min != null ? String(t.screensaver_min) : "",
          sleep: t.sleep_min != null ? String(t.sleep_min) : "",
        });
        setBright(t.brightness ?? null);
      })
      .catch(() => undefined);
    apiGet<AppConfig>("/api/config").then(setApp).catch(toastErr);
    void refreshPersonas();
    apiGet<{ voice: string | null; override: string | boolean | null; voices: string[] }>("/api/voice")
      .then((r) => {
        setVoices(r.voices);
        setVoiceText(typeof r.override === "string" ? r.override : r.override ? r.voice ?? "" : "");
        setVoiceLoaded(true);
      })
      .catch(() => undefined);
    void refreshMemories();
    apiGet<{ people: Person[] }>("/api/people")
      .then((r) => {
        setPeople(r.people);
        setPeopleLoaded(true);
      })
      .catch(() => undefined);
    apiGet<Updates>("/api/updates").then(setUpdates).catch(() => undefined);
    apiGet<{ schedule: { at?: string; action?: { mode?: string; say?: string } }[] }>("/api/schedule")
      .then((r) =>
        setSched(
          r.schedule.map((j) => ({
            at: j.at ?? "",
            mode: j.action?.mode ?? "",
            say: j.action?.say ?? "",
          })),
        ),
      )
      .catch(() => undefined)
      .finally(() => setSchedLoaded(true));
    void refreshModes();
  }, []);

  async function saveSchedule() {
    try {
      const jobs = sched
        .filter((r) => /^([01]?\d|2[0-3]):[0-5]\d$/.test(r.at) && (r.mode || r.say))
        .map((r, i) => ({
          name: `day${i + 1}`,
          at: r.at,
          enabled: true,
          action: { ...(r.mode ? { mode: r.mode } : {}), ...(r.say ? { say: r.say } : {}) },
        }));
      await apiSend("/api/schedule", "PUT", { schedule: jobs });
      toast(tr("סדר היום נשמר — הרובוט יעקוב אחריו", "Day schedule saved — the robot will follow it"));
    } catch (e) {
      toastErr(e);
    }
  }

  const refreshModes = () =>
    apiGet<{ modes: PluginMode[] }>("/api/modes")
      .then((r) => setModes(r.modes))
      .catch(() => undefined);

  async function setModeDisabled(name: string, disabled: boolean) {
    try {
      await apiSend(`/api/config/modes/${name}/disabled`, "POST", { disabled });
      await refreshModes();
    } catch (e) {
      toastErr(e);
    }
  }

  async function toggleModeActive(m: PluginMode) {
    try {
      if (m.active) await apiSend("/api/modes/deactivate", "POST", {});
      else await apiSend(`/api/modes/${m.name}/activate`, "POST", {});
      await refreshModes();
    } catch (e) {
      toastErr(e);
    }
  }

  async function saveModeConfig(name: string) {
    try {
      const base = modes.find((m) => m.name === name)?.config ?? {};
      await apiSend(`/api/config/modes/${name}`, "PUT", { config: { ...base, ...(modeEdits[name] ?? {}) } });
      toast(tr("ההגדרות נשמרו והוחלו", "Config saved & applied"));
      setModeEdits((cur) => ({ ...cur, [name]: {} }));
      await refreshModes();
    } catch (e) {
      toastErr(e);
    }
  }

  async function saveBirthday() {
    try {
      await apiSend("/api/config/birthday", "PUT", { date: (birthday ?? "").trim() });
      toast(tr("🎂 נשמר — הוא יחגוג אותך", "🎂 Saved — it will celebrate you"));
    } catch (e) {
      toastErr(e);
    }
  }

  async function setDriver(driver: string) {
    try {
      const res = await apiSend<RobotConfig>("/api/robot/config", "PUT", { driver });
      if (res.error) toast(res.error, "err");
      props.onConfigChanged();
    } catch (e) {
      toastErr(e);
    }
  }

  async function setInvert(axis: "yaw" | "pitch", invert: boolean) {
    try {
      // Always merge into the SERVER's current calibration (not our possibly-stale copy) —
      // otherwise flipping a toggle could silently erase a freshly captured head centre.
      const fresh = await apiGet<RobotConfig>("/api/robot/config");
      const cal = { ...fresh.calibration, [axis]: { ...(fresh.calibration[axis] ?? {}), invert } };
      await apiSend("/api/robot/config", "PUT", { calibration: cal });
      props.onConfigChanged();
    } catch (e) {
      toastErr(e);
    }
  }

  async function resetCalibration() {
    try {
      await apiSend("/api/robot/config", "PUT", { calibration: {} });
      toast(tr("הכיול אופס", "Calibration reset"));
      props.onConfigChanged();
    } catch (e) {
      toastErr(e);
    }
  }

  async function saveTimers() {
    // Number("abc") is NaN, which JSON-serializes to null and silently no-ops — validate
    const bad = [timers.saver, timers.sleep].some((t) => t !== "" && !Number.isFinite(Number(t)));
    if (bad) {
      toast(tr("ערך לא תקין — מספרים בלבד", "Invalid value — numbers only"), "err");
      return;
    }
    try {
      await apiSend("/api/robot/screen", "PUT", {
        screensaver_min: timers.saver === "" ? null : Number(timers.saver),
        sleep_min: timers.sleep === "" ? null : Number(timers.sleep),
      });
      toast(tr("הטיימרים עודכנו על הרובוט", "Timers updated on the robot"));
    } catch (e) {
      toastErr(e);
    }
  }

  // Debounced brightness — PUTs while dragging, like the volume slider on Home.
  function onBrightness(v: number) {
    setBright(v);
    if (brightTimer.current) clearTimeout(brightTimer.current);
    brightTimer.current = setTimeout(() => {
      apiSend("/api/robot/screen", "PUT", { brightness: v }).catch(toastErr);
    }, 250);
  }

  useEffect(
    () => () => {
      if (brightTimer.current) clearTimeout(brightTimer.current);
    },
    [],
  );

  // ── personas ──
  const refreshPersonas = () =>
    apiGet<{ personas: Persona[]; active: string | null }>("/api/personas")
      .then((r) => {
        setPersonas(r.personas);
        setActivePersona(r.active);
      })
      .catch(() => undefined);

  async function activatePersona(name: string | null) {
    try {
      await apiSend("/api/personas/active", "POST", { name });
      await refreshPersonas();
    } catch (e) {
      toastErr(e);
    }
  }

  async function addPersona() {
    const name = pName.trim();
    const prompt = pPrompt.trim();
    if (!name || !prompt) return;
    try {
      await apiSend("/api/personas", "PUT", { personas: [...personas, { name, system_prompt: prompt }] });
      setPName("");
      setPPrompt("");
      setPersonaOpen(false);
      toast(tr("האישיות נוספה", "Persona added"));
      await refreshPersonas();
    } catch (e) {
      toastErr(e);
    }
  }

  async function deletePersona(name: string) {
    try {
      await apiSend("/api/personas", "PUT", { personas: personas.filter((p) => p.name !== name) });
      if (activePersona === name) await apiSend("/api/personas/active", "POST", { name: null });
      await refreshPersonas();
    } catch (e) {
      toastErr(e);
    }
  }

  // ── voice ──
  async function saveVoice() {
    try {
      const v = voiceText.trim();
      await apiSend("/api/voice", "PUT", { voice: v || null });
      toast(v ? tr("הקול נשמר", "Voice saved") : tr("חזרה לקול ברירת המחדל", "Back to the default voice"));
    } catch (e) {
      toastErr(e);
    }
  }

  // ── memories ──
  const refreshMemories = () =>
    apiGet<{ memories: Memory[] }>("/api/memory")
      .then((r) => setMemories(r.memories))
      .catch(() => undefined);

  async function addMemory() {
    const text = memText.trim();
    if (!text) return;
    try {
      await apiSend("/api/memory", "POST", { text });
      setMemText("");
      await refreshMemories();
    } catch (e) {
      toastErr(e);
    }
  }

  async function deleteMemory(id: number | string) {
    try {
      await apiSend(`/api/memory/${encodeURIComponent(String(id))}`, "DELETE");
      await refreshMemories();
    } catch (e) {
      toastErr(e);
    }
  }

  // ── people (face recognition) ──
  function editPerson(i: number, patch: Partial<Person>) {
    setPeople((cur) => cur.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  }

  function setPrimary(i: number) {
    // one favourite at a time — starring someone un-stars everyone else
    setPeople((cur) => cur.map((p, j) => ({ ...p, primary: j === i ? !p.primary : false })));
  }

  async function savePeople() {
    try {
      // the server sanitizes (name required, dedupe, one primary) and echoes the result
      const r = await apiSend<{ people: Person[] }>("/api/people", "PUT", { people });
      setPeople(r.people);
      toast(tr("האנשים נשמרו", "People saved"));
    } catch (e) {
      toastErr(e);
    }
  }

  // ── backup & restore ──
  async function downloadBackup() {
    try {
      const data = await apiGet<unknown>("/api/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "dravix-backup.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toastErr(e);
    }
  }

  async function restoreBackup(file: File) {
    let data: unknown;
    try {
      data = JSON.parse(await file.text());
    } catch {
      toast(tr("הקובץ אינו JSON תקין", "The file isn't valid JSON"), "err");
      return;
    }
    try {
      // /api/import expects {store: {...}}; our own backup file is the bare store dict.
      const body = data && typeof data === "object" && "store" in (data as object) ? data : { store: data };
      await apiSend("/api/import", "POST", body);
      toast(tr("שוחזר! מרענן…", "Restored! Refreshing…"));
      props.onConfigChanged();
      // every card on this page holds mount-time state (personas/memories/schedule/…) —
      // a reload is the honest way to show the restored values instead of the old ones
      setTimeout(() => window.location.reload(), 900);
    } catch (e) {
      toastErr(e);
    }
  }

  async function setProvider(p: string) {
    try {
      const r = await apiSend<{ ai_provider: string; ai_available: boolean; error: string | null }>(
        "/api/config/ai_provider",
        "PUT",
        { provider: p },
      );
      if (r.error) toast(r.error, "err");
      setApp((cur) => (cur ? { ...cur, ai_provider: r.ai_provider, ai_available: r.ai_available } : cur));
    } catch (e) {
      toastErr(e);
    }
  }

  async function setIdle(enabled: boolean) {
    try {
      await apiSend("/api/robot/idle-motion", "PUT", { enabled });
      setApp((cur) => (cur ? { ...cur, store: { ...cur.store, idle_motion: enabled } } : cur));
    } catch (e) {
      toastErr(e);
    }
  }

  async function setSpeak(enabled: boolean) {
    try {
      await apiSend("/api/robot/spontaneous-speech", "PUT", { enabled });
      setApp((cur) => (cur ? { ...cur, store: { ...cur.store, spontaneous_speech: enabled } } : cur));
    } catch (e) {
      toastErr(e);
    }
  }

  async function setLocalOnly(enabled: boolean) {
    try {
      const r = await apiSend<{ local_only: boolean; ai_available: boolean; error: string | null }>(
        "/api/config/local_only",
        "PUT",
        { enabled },
      );
      if (r.error) toast(r.error, "err");
      setApp((cur) => (cur ? { ...cur, local_only: r.local_only, ai_available: r.ai_available } : cur));
    } catch (e) {
      toastErr(e);
    }
  }

  async function saveRobotName() {
    try {
      await apiSend("/api/config/robot_name", "PUT", { name: (robotName ?? "").trim() });
      toast(tr("השם נשמר — הרובוט יענה לשם הזה", "Name saved — the robot answers to it"));
      props.onConfigChanged(); // the header picks the new name up from /api/robot/config
    } catch (e) {
      toastErr(e);
    }
  }

  async function saveDashUrl() {
    const url = (dashUrl ?? "").trim();
    try {
      const r = await apiSend<{ url: string; pushed?: boolean; error?: string }>(
        "/api/config/dashboard_url",
        "PUT",
        { url },
      );
      setDashSaved(r.url ?? "");
      setDashUrl(r.url ?? "");
      if (r.error) {
        toast(tr("נשמר, אך הדחיפה לרובוט נכשלה", "Saved, but the push to the robot failed"), "err");
      } else if (!url) {
        toast(tr("הדף הוסר — גללו והוא כבר לא יופיע", "Removed — the 🌐 page left the swipe cycle"));
      } else {
        toast(tr("נשמר — גללו לדף ה-🌐 כדי לראות את הדשבורד", "Saved — swipe to the 🌐 page to see it"));
      }
    } catch (e) {
      toastErr(e);
    }
  }

  if (!cfg) return <div className="card animate-rise text-mute">{tr("טוען הגדרות…", "Loading settings…")}</div>;

  return (
    <div className="space-y-4">
      {/* ── status ── */}
      <Section title={tr("חיבור לרובוט", "Robot connection")}>
        <div className="mb-3 flex items-center gap-2">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${cfg.online ? "bg-green" : "bg-red"}`} />
          <span>{cfg.online ? tr("מחובר", "Connected") : tr("לא מחובר", "Offline")}</span>
          <span dir="ltr" className="ms-auto font-mono text-xs text-mute">
            v{props.version}
          </span>
        </div>
        {(cfg as { degraded?: boolean }).degraded && (
          <p className="mb-3 rounded-xl border border-amber/40 bg-amber/10 p-2 text-xs text-amber">
            {tr(
              "הדרייבר המבוקש נכשל — רץ על דרייבר דמה (הפקודות לא מגיעות לרובוט האמיתי).",
              "The requested driver failed to build — running on the mock fallback (commands don't reach the real robot).",
            )}
          </p>
        )}
        {cfg.last_error && (!cfg.online || (cfg as { degraded?: boolean }).degraded) && (
          <p dir="ltr" className="mb-3 rounded-xl border border-red/30 bg-red/10 p-2 text-start text-xs text-red">
            {cfg.last_error}
          </p>
        )}
        <div className="flex gap-2">
          {cfg.drivers.map((d) => (
            <button
              key={d}
              className={`chip ${cfg.driver === d ? "chip-on" : ""}`}
              onClick={() => void setDriver(d)}
            >
              {d === "ha" ? "Home Assistant" : d === "mock" ? tr("דמה (בדיקות)", "Mock (testing)") : "MCP"}
            </button>
          ))}
        </div>
      </Section>

      {/* ── robot name ── */}
      <Section title={tr("שם הרובוט", "Robot name")} delay={40}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "תנו לו שם — הוא יופיע למעלה, וה-AI יידע שכך קוראים לו ויענה לשם.",
            "Give it a name — shown in the header, and the AI knows it's called that.",
          )}
        </p>
        <div className="flex gap-2">
          <input
            className="inp flex-1"
            maxLength={40}
            placeholder={tr("למשל: צ'יפי", "e.g. Chippy")}
            value={robotName ?? cfg.robot_name ?? ""}
            onChange={(e) => setRobotName(e.target.value)}
          />
          <button className="btn btn-primary" disabled={robotName === null} onClick={() => void saveRobotName()}>
            {tr("שמור", "Save")}
          </button>
        </div>
      </Section>

      {/* ── 🌐 dashboard page — a HA dashboard screenshot on its own swipe page ── */}
      <Section title={tr("🌐 דף דשבורד", "🌐 Dashboard page")} delay={41}>
        <p className="mb-2 text-sm text-mute">
          {tr(
            "כתובת של תמונה שתוצג כדף נפרד בגלילה של הרובוט — נשארת שם עד שגוללים ממנה, ומתרעננת כל 15 שניות. השאירו ריק כדי להסיר את הדף.",
            "An image URL shown as its own page in the robot's swipe cycle — it stays until you swipe away and refreshes every 15s. Leave empty to remove the page.",
          )}
        </p>
        <p className="mb-3 text-xs text-mute">
          {tr(
            "להצגת דשבורד של Home Assistant התקינו את התוסף הקהילתי „Puppet” והפנו לכתובת שלו, למשל:",
            "To show a Home Assistant dashboard, install the community “Puppet” add-on and point at its URL, e.g.:",
          )}{" "}
          <code dir="ltr" className="rounded bg-card2 px-1 py-0.5 font-mono text-[11px]">
            http://homeassistant.local:10000/lovelace/0?viewport=320x240
          </code>
        </p>
        <div className="flex gap-2">
          <input
            dir="ltr"
            className="inp flex-1 font-mono text-xs"
            maxLength={255}
            placeholder="http://homeassistant.local:10000/lovelace/0?viewport=320x240"
            value={dashUrl ?? ""}
            onChange={(e) => setDashUrl(e.target.value)}
          />
          <button
            className="btn btn-primary"
            disabled={dashUrl === null || (dashUrl ?? "").trim() === dashSaved}
            onClick={() => void saveDashUrl()}
          >
            {tr("שמור", "Save")}
          </button>
        </div>
      </Section>

      {/* ── memories — long-term facts fed into every conversation ── */}
      <Section title={tr("🧠 זיכרונות", "🧠 Memories")} delay={42}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "עובדות שהרובוט זוכר על העולם שלך — נכנסות להקשר של כל שיחה.",
            "Facts the robot remembers about your world — fed into every conversation.",
          )}
        </p>
        {memories.length > 0 && (
          <div className="mb-3 space-y-1.5">
            {memories.map((m) => (
              <div key={m.id} className="flex items-center gap-2 rounded-2xl border border-line bg-card2 px-3 py-2 text-sm">
                <span className="flex-1">{m.text}</span>
                <button className="chip" onClick={() => void deleteMemory(m.id)} aria-label={tr("מחק", "Delete")}>
                  🗑
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            className="inp flex-1"
            placeholder={tr("למשל: לחתול שלנו קוראים מוקה", "e.g. Our cat is called Mocha")}
            value={memText}
            onChange={(e) => setMemText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && memText.trim()) void addMemory();
            }}
          />
          <button className="btn btn-primary" disabled={!memText.trim()} onClick={() => void addMemory()}>
            {tr("הוסף", "Add")}
          </button>
        </div>
      </Section>

      {/* ── updates — add-on + robot firmware versions, with rollback hints ── */}
      {updates && (
        <Section title={tr("עדכונים", "Updates")} delay={45}>
          <div className="space-y-1.5 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span>{tr("תוסף dravix-os", "dravix-os add-on")}</span>
              <span dir="ltr" className="font-mono text-xs">
                v{updates.addon_version}
                {updates.addon_update && updates.addon_latest ? ` → v${updates.addon_latest}` : ""}
              </span>
            </div>
            {updates.addon_update && (
              <p className="text-xs text-amber">
                {tr(
                  "גרסה חדשה זמינה — עדכן ב-Home Assistant: הגדרות ← תוספים ← dravix-os.",
                  "A new version is available — update in Home Assistant: Settings → Add-ons → dravix-os.",
                )}
              </p>
            )}
            <div className="flex items-center justify-between gap-2">
              <span>{tr("קושחת הרובוט", "Robot firmware")}</span>
              <span dir="ltr" className="font-mono text-xs">
                {updates.fw_robot ?? "?"}
                {updates.fw_update && updates.fw_bundled ? ` → ${updates.fw_bundled}` : ""}
              </span>
            </div>
            {updates.fw_update && (
              <p className="text-xs text-amber">
                {tr(
                  "קושחה חדשה זמינה — פתח את ESPHome ולחץ Install (עם קובץ ה-git זה הכול).",
                  "New firmware available — open ESPHome and press Install (with the git stub that's all).",
                )}
              </p>
            )}
            {!updates.fw_robot && (
              <p className="text-xs text-mute">
                {tr(
                  "הרובוט לא מדווח גרסת קושחה (כבוי, או קושחה מלפני מנגנון הגרסאות).",
                  "The robot isn't reporting a firmware version (off, or pre-versioning firmware).",
                )}
              </p>
            )}
            <p className="text-xs text-mute">
              {tr(
                "חזרה לגרסה קודמת: בקובץ ה-ESPHome קבע ref: v<גרסה> מעמוד ה-Releases ולחץ Install.",
                "Rollback: in the ESPHome stub set ref: v<version> from the Releases page and press Install.",
              )}
            </p>
          </div>
        </Section>
      )}

      {/* ── isLocal — the master local-only flag ── */}
      <Section title={tr("🏠 מקומי בלבד (isLocal)", "🏠 Local only (isLocal)")} delay={50}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "הבחירה שלך בלבד — נשאר בדיוק כמו שקבעת, שום דבר לא מחליף אותו אוטומטית. דלוק: הכל נשאר ברשת הביתית — כלום לא יוצא החוצה וכלום לא נכנס מבחוץ (בינה בענן חסומה, החיבור לענן מנותק, תמונות רק מהרשת, בלי בדיקות עדכונים). כבוי: הכל רגיל. אפשר להחליף גם מהרובוט עצמו — כפתור LOCAL בסרגל שנפתח בהחלקה למטה.",
            "Your choice alone — it stays exactly as you set it, nothing flips it automatically. ON: everything stays inside your home network — nothing goes out and nothing comes in (cloud AI blocked, cloud bridge disconnected, LAN-only images, no update checks). OFF: everything works normally. You can also flip it on the robot itself — the LOCAL button on its swipe-down status bar.",
          )}
        </p>
        <Toggle
          label={tr("מצב מקומי בלבד", "Local-only mode")}
          on={Boolean(app?.local_only)}
          onChange={(v) => void setLocalOnly(v)}
        />
      </Section>

      {/* ── entity wiring — auto-discovered, read-only ── */}
      <Section title={tr("חיבור ישויות — אוטומטי", "Entity wiring — automatic")} delay={60}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "דרביקס מזהה לבד את כל ישויות הרובוט ב-Home Assistant — אין מה למלא. זה מה שנמצא:",
            "dravix auto-detects all the robot's Home Assistant entities — nothing to fill in. Found:",
          )}
        </p>
        <div className="space-y-1.5">
          {cfg.roles.map((role) => {
            const found = cfg.entities[role.key];
            return (
              <div key={role.key} className="flex items-center justify-between gap-2 text-sm">
                <span className={found ? "" : "text-mute"}>{pick(ROLES[role.key], role.label)}</span>
                {found ? (
                  <span dir="ltr" className="truncate font-mono text-xs text-teal">{found}</span>
                ) : (
                  <span className="text-xs text-mute">{tr("לא נמצא", "not found")}</span>
                )}
              </div>
            );
          })}
        </div>
      </Section>

      {/* ── behaviour toggles (the robot's on-device switches) ── */}
      {behaviors.length > 0 && (
        <Section title={tr("התנהגות הרובוט", "Robot behaviour")} delay={90}>
          <div className="space-y-2">
            {behaviors.map((b) => (
              <Toggle
                key={b.entity_id}
                label={tr(b.he, b.en)}
                on={b.state === "on"}
                onChange={(v) => void flipBehavior(b.entity_id, v)}
              />
            ))}
          </div>
        </Section>
      )}

      {/* ── plugin modes — the full manager: enable/disable, run, edit config ── */}
      {modes.length > 0 && (
        <Section title={tr("🧩 מצבים והתנהגויות (תוספים)", "🧩 Modes & behaviours (plugins)")} delay={100}>
          <p className="mb-3 text-sm text-mute">
            {tr(
              "כל מצבי התוכנה של הרובוט — הפעלה, כיבוי ועריכת ההגדרות של כל אחד, מכאן.",
              "Every software mode the robot has — run, disable, and edit each one's settings, right here.",
            )}
          </p>
          <div className="space-y-2">
            {modes.map((m) => {
              const edits = modeEdits[m.name] ?? {};
              const cfg2 = { ...m.config, ...edits };
              const open = openMode === m.name;
              return (
                <div key={m.name} className="rounded-2xl border border-line bg-card2 p-3">
                  <div className="flex items-center gap-2">
                    <span className={`inline-block h-2 w-2 rounded-full ${m.active ? "bg-green" : m.disabled ? "bg-red" : "bg-mute"}`} />
                    <span className="font-mono text-sm" dir="ltr">{m.name}</span>
                    <span className="text-xs text-mute">{m.kind === "ambient" ? tr("רקע", "ambient") : tr("קדמי", "foreground")}</span>
                    <div className="ms-auto flex items-center gap-2">
                      {!m.disabled && m.kind === "foreground" && (
                        <button className="chip" onClick={() => void toggleModeActive(m)}>
                          {m.active ? tr("⏹ עצור", "⏹ Stop") : tr("▶ הפעל", "▶ Run")}
                        </button>
                      )}
                      <button className="chip" onClick={() => void setModeDisabled(m.name, !m.disabled)}>
                        {m.disabled ? tr("אפשר", "Enable") : tr("השבת", "Disable")}
                      </button>
                      {Object.keys(m.config).length > 0 && (
                        <button className="chip" onClick={() => setOpenMode(open ? null : m.name)}>
                          {open ? tr("סגור", "Close") : tr("⚙ הגדרות", "⚙ Config")}
                        </button>
                      )}
                    </div>
                  </div>
                  {m.description && <p className="mt-1 text-xs text-mute">{m.description}</p>}
                  {open && (
                    <div className="mt-3 space-y-2 border-t border-line pt-3">
                      {Object.entries(cfg2).map(([k, v]) =>
                        typeof v === "boolean" ? (
                          <Toggle
                            key={k}
                            label={k}
                            on={v}
                            onChange={(nv) =>
                              setModeEdits((cur) => ({ ...cur, [m.name]: { ...cur[m.name], [k]: nv } }))
                            }
                          />
                        ) : (
                          <div key={k} className="flex items-center gap-2">
                            <label className="lbl mb-0 flex-1 font-mono text-xs" dir="ltr">{k}</label>
                            <input
                              className="inp w-40 text-sm"
                              dir="ltr"
                              type={typeof v === "number" ? "number" : "text"}
                              value={String(v ?? "")}
                              onChange={(e) =>
                                setModeEdits((cur) => ({
                                  ...cur,
                                  [m.name]: {
                                    ...cur[m.name],
                                    [k]: typeof v === "number" ? Number(e.target.value) : e.target.value,
                                  },
                                }))
                              }
                            />
                          </div>
                        ),
                      )}
                      <button className="btn btn-primary mt-2 w-full" onClick={() => void saveModeConfig(m.name)}>
                        {tr("💾 שמור והחל", "💾 Save & apply")}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* ── birthday — it celebrates you 🎂 ── */}
      <Section title={tr("🎂 יום הולדת", "🎂 Birthday")} delay={110}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "פעם בשנה, בבוקר התאריך הזה, הרובוט יחגוג אותך — עיני-אהבה, אורות וברכה בקול.",
            "Once a year, on this date's morning, the robot celebrates you — love-eyes, lights and a spoken greeting.",
          )}
        </p>
        <div className="flex gap-2">
          <input
            className="inp flex-1"
            dir="ltr"
            placeholder="MM-DD"
            maxLength={5}
            value={birthday ?? String(app?.store.birthday ?? "")}
            onChange={(e) => setBirthdayState(e.target.value)}
          />
          <button className="btn btn-primary" disabled={birthday === null} onClick={() => void saveBirthday()}>
            {tr("שמור", "Save")}
          </button>
        </div>
      </Section>

      {/* ── people — face recognition → personal greetings ── */}
      {peopleLoaded && (
        <Section title={tr("🙂 אנשים — זיהוי פנים", "🙂 People — face recognition")} delay={112}>
          <p className="mb-3 text-sm text-mute">
            {tr(
              "כשהרובוט מזהה פרצוף מוכר הוא מברך אותו אישית — בשם ובמשפט משלו. הזיהוי עצמו נעשה על ידי זיהוי הפנים של Frigate (צריך לאמן שם את הפרצופים), והשם כאן חייב להתאים לשם שב-Frigate. אפשר לכתוב {name} בתוך המשפט. ⭐ = המועדף — מקבל ברכה חמה במיוחד.",
              "When the robot recognizes a familiar face it greets that person personally — by name, with their own line. Recognition itself is done by Frigate face recognition (train the faces there), and the name here must match the one in Frigate. You can use {name} inside the line. ⭐ = the favourite — gets the extra-warm greeting.",
            )}
          </p>
          <div className="space-y-2">
            {people.map((p, i) => (
              <div key={i} className="space-y-2 rounded-2xl border border-line bg-card2 p-3">
                <div className="flex items-center gap-2">
                  <input
                    className="inp flex-1"
                    dir="ltr"
                    placeholder={tr("שם (כמו ב-Frigate)", "Name (as in Frigate)")}
                    value={p.name}
                    onChange={(e) => editPerson(i, { name: e.target.value })}
                  />
                  <button
                    className="chip"
                    title={tr("המועדף — ברכה חמה במיוחד", "Favourite — extra-warm greeting")}
                    onClick={() => setPrimary(i)}
                  >
                    {p.primary ? "⭐" : "☆"}
                  </button>
                  <button className="chip" onClick={() => setPeople((cur) => cur.filter((_, j) => j !== i))}>
                    🗑
                  </button>
                </div>
                <input
                  className="inp w-full text-sm"
                  placeholder={tr("ברכה בעברית (ריק = ברירת מחדל)", "Hebrew greeting (empty = default)")}
                  value={p.line_he}
                  onChange={(e) => editPerson(i, { line_he: e.target.value })}
                />
                <input
                  className="inp w-full text-sm"
                  dir="ltr"
                  placeholder={tr("ברכה באנגלית (ריק = ברירת מחדל)", "English greeting (empty = default)")}
                  value={p.line}
                  onChange={(e) => editPerson(i, { line: e.target.value })}
                />
              </div>
            ))}
            {people.length === 0 && (
              <p className="text-sm text-mute">{tr("עוד אין אנשים — הוסיפו את הראשון.", "No people yet — add the first one.")}</p>
            )}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              className="chip"
              onClick={() => setPeople((cur) => [...cur, { name: "", line: "", line_he: "", primary: false }])}
            >
              {tr("+ הוסף אדם", "+ Add person")}
            </button>
            <button className="btn btn-primary ms-auto" onClick={() => void savePeople()}>
              {tr("💾 שמור", "💾 Save")}
            </button>
          </div>
        </Section>
      )}

      {/* ── day schedule — preset hours → robot modes ── */}
      {schedLoaded && (
        <Section title={tr("🕐 סדר יום", "🕐 Day schedule")} delay={115}>
          <p className="mb-3 text-sm text-mute">
            {tr(
              "שעות קבועות שבהן הרובוט נכנס למצב לבד — למשל 07:30 בוקר, 23:00 שינה. אפשר גם משפט שייאמר.",
              "Preset hours when the robot enters a mode on its own — e.g. 07:30 morning, 23:00 sleep. An optional line to speak, too.",
            )}
          </p>
          <div className="space-y-2">
            {sched.map((row, i) => (
              <div key={i} className="rounded-2xl border border-line bg-card2 p-3">
                <div className="flex items-center gap-2">
                  <input
                    className="inp w-24 text-center"
                    dir="ltr"
                    placeholder="07:30"
                    maxLength={5}
                    value={row.at}
                    onChange={(e) =>
                      setSched((cur) => cur.map((r, j) => (j === i ? { ...r, at: e.target.value } : r)))
                    }
                  />
                  <select
                    className="inp flex-1"
                    value={row.mode}
                    onChange={(e) =>
                      setSched((cur) => cur.map((r, j) => (j === i ? { ...r, mode: e.target.value } : r)))
                    }
                  >
                    <option value="">{tr("— בלי שינוי מצב —", "— no mode change —")}</option>
                    <option value="awake">{tr("☀️ ער", "☀️ Awake")}</option>
                    <option value="morning">{tr("🌅 בוקר", "🌅 Morning")}</option>
                    <option value="focus">{tr("🎯 מרוכז", "🎯 Focus")}</option>
                    <option value="quiet">{tr("🤫 שקט", "🤫 Quiet")}</option>
                    <option value="night">{tr("🌙 לילה", "🌙 Night")}</option>
                    <option value="sleep">{tr("😴 שינה", "😴 Sleep")}</option>
                  </select>
                  <button
                    className="chip"
                    onClick={() => setSched((cur) => cur.filter((_, j) => j !== i))}
                    aria-label={tr("מחק", "Delete")}
                  >
                    🗑
                  </button>
                </div>
                <input
                  className="inp mt-2 w-full"
                  placeholder={tr("משפט לומר (לא חובה) — למשל: בוקר טוב!", "Line to speak (optional) — e.g. Good morning!")}
                  value={row.say}
                  onChange={(e) =>
                    setSched((cur) => cur.map((r, j) => (j === i ? { ...r, say: e.target.value } : r)))
                  }
                />
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              className="btn flex-1"
              onClick={() => setSched((cur) => [...cur, { at: "", mode: "", say: "" }])}
            >
              {tr("+ הוסף שעה", "+ Add time")}
            </button>
            <button className="btn btn-primary flex-1" onClick={() => void saveSchedule()}>
              {tr("💾 שמור סדר יום", "💾 Save schedule")}
            </button>
          </div>
        </Section>
      )}

      {/* ── head calibration ── */}
      <Section title={tr("כיול ראש", "Head calibration")} delay={120}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "אם הראש זז הפוך — הפעל היפוך לציר המתאים. ״קבע כ׳ישר׳״ נמצא בדף הבית, ליד הג׳ויסטיק.",
            "If the head moves the wrong way, flip the matching axis. 'Set as straight' is on the Home tab, next to the joystick.",
          )}
        </p>
        <div className="space-y-2">
          <Toggle
            label={tr("היפוך ימינה/שמאלה", "Invert left/right")}
            on={Boolean(cfg.calibration.yaw?.invert)}
            onChange={(v) => void setInvert("yaw", v)}
          />
          <Toggle
            label={tr("היפוך למעלה/למטה", "Invert up/down")}
            on={Boolean(cfg.calibration.pitch?.invert)}
            onChange={(v) => void setInvert("pitch", v)}
          />
          <button className="btn btn-danger w-full" onClick={() => void resetCalibration()}>
            {tr("↺ איפוס כיול", "↺ Reset calibration")}
          </button>
        </div>
      </Section>

      {/* ── screen: brightness + screensaver/sleep timers ── */}
      <Section title={tr("מסך, שומר מסך ושינה", "Screen, screensaver & sleep")} delay={180}>
        {bright != null && (
          <div className="mb-3">
            <label className="lbl">{tr("בהירות המסך", "Screen brightness")}</label>
            <div className="flex items-center gap-3">
              <span className="text-sm text-mute">🔆</span>
              <input
                type="range"
                min={10}
                max={100}
                value={bright}
                onChange={(e) => onBrightness(Number(e.target.value))}
                className="h-2 flex-1 accent-teal"
                aria-label={tr("בהירות המסך", "Screen brightness")}
              />
              <span dir="ltr" className="w-10 text-end font-mono text-xs text-mute">{bright}%</span>
            </div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="lbl">{tr("שומר מסך אחרי (דק׳)", "Screensaver after (min)")}</label>
            <input
              type="number"
              inputMode="numeric"
              className="inp text-center"
              value={timers.saver}
              onChange={(e) => setTimers((t) => ({ ...t, saver: e.target.value }))}
            />
          </div>
          <div>
            <label className="lbl">{tr("שינה אחרי (דק׳)", "Sleep after (min)")}</label>
            <input
              type="number"
              inputMode="numeric"
              className="inp text-center"
              value={timers.sleep}
              onChange={(e) => setTimers((t) => ({ ...t, sleep: e.target.value }))}
            />
          </div>
        </div>
        <button className="btn mt-3 w-full" onClick={() => void saveTimers()}>
          {tr("💾 עדכן טיימרים", "💾 Update timers")}
        </button>
      </Section>

      {/* ── AI + behaviour ── */}
      <Section title={tr("בינה והתנהגות", "AI & behaviour")} delay={240}>
        <label className="lbl">{tr("ספק הבינה המלאכותית", "AI provider")}</label>
        <div className="mb-3 flex flex-wrap gap-2">
          {(app?.providers ?? []).map((p) => (
            <button
              key={p}
              className={`chip ${app?.ai_provider === p ? "chip-on" : ""}`}
              onClick={() => void setProvider(p)}
            >
              {pick(PROVIDERS[p], p)}
            </button>
          ))}
        </div>
        {app && !app.ai_available && (
          <p className="mb-3 text-xs text-amber">
            {tr("ספק הבינה לא זמין כרגע — בדוק את ההגדרות שלו.", "The AI provider is unavailable — check its settings.")}
          </p>
        )}

        {/* personas — who the robot IS when it answers */}
        <label className="lbl">{tr("אישיות", "Persona")}</label>
        <div className="mb-3 flex flex-wrap gap-2">
          <button
            className={`chip ${activePersona == null ? "chip-on" : ""}`}
            onClick={() => void activatePersona(null)}
          >
            {tr("🤖 ברירת מחדל", "🤖 Default")}
          </button>
          {personas.map((p) => (
            <span key={p.name} className={`chip ${activePersona === p.name ? "chip-on" : ""}`}>
              <button onClick={() => void activatePersona(p.name)}>{p.name}</button>
              <button
                className="text-xs opacity-70"
                onClick={() => void deletePersona(p.name)}
                aria-label={tr("מחק אישיות", "Delete persona")}
              >
                🗑
              </button>
            </span>
          ))}
          <button className="chip" onClick={() => setPersonaOpen((v) => !v)}>
            {personaOpen ? tr("סגור", "Close") : tr("＋ הוסף אישיות", "＋ Add persona")}
          </button>
        </div>
        {personaOpen && (
          <div className="mb-3 space-y-2 rounded-2xl border border-line bg-card2 p-3">
            <input
              className="inp w-full"
              maxLength={40}
              placeholder={tr("שם — למשל: פיראט", "Name — e.g. Pirate")}
              value={pName}
              onChange={(e) => setPName(e.target.value)}
            />
            <textarea
              className="inp min-h-20 w-full resize-none"
              placeholder={tr(
                "הנחיית מערכת — מי הרובוט ואיך הוא מדבר…",
                "System prompt — who the robot is and how it talks…",
              )}
              value={pPrompt}
              onChange={(e) => setPPrompt(e.target.value)}
            />
            <button
              className="btn btn-primary w-full"
              disabled={!pName.trim() || !pPrompt.trim()}
              onClick={() => void addPersona()}
            >
              {tr("💾 שמור אישיות", "💾 Save persona")}
            </button>
          </div>
        )}

        {/* voice — TTS voice-id override */}
        {voiceLoaded && (
          <div className="mb-3">
            <label className="lbl">
              {tr("קול (מזהה קול של מנוע ה-TTS; ריק = ברירת מחדל)", "Voice (TTS voice id; empty = default)")}
            </label>
            <div className="flex gap-2">
              <input
                className="inp flex-1"
                dir="ltr"
                placeholder="he_IL-..."
                list="voice-options"
                value={voiceText}
                onChange={(e) => setVoiceText(e.target.value)}
              />
              <datalist id="voice-options">
                {voices.map((v) => (
                  <option key={v} value={v} />
                ))}
              </datalist>
              <button className="btn btn-primary" onClick={() => void saveVoice()}>
                {tr("שמור", "Save")}
              </button>
            </div>
          </div>
        )}

        <Toggle
          label={tr("תנועת ראש עצמאית (כשהוא משועמם)", "Autonomous head motion (when bored)")}
          on={Boolean(app?.store.idle_motion ?? false)}
          onChange={(v) => void setIdle(v)}
        />
        <Toggle
          label={tr("מדבר מיוזמתו", "Speaks on its own")}
          on={Boolean(app?.store.spontaneous_speech ?? false)}
          onChange={(v) => void setSpeak(v)}
        />
        <p className="-mt-1 px-1 text-xs text-mute">
          {tr(
            "כשכבוי — הרובוט מדבר רק בשיחת AI ובכפתורים שאתה לוחץ. כשדולק — גם משפטי שעמום, הפתעות, ברכות והכרזות.",
            "Off — the robot speaks only in AI conversations and when you press a button. On — also idle quips, surprises, greetings and announcements.",
          )}
        </p>
      </Section>

      {/* ── backup & restore — the whole add-on config as one JSON file ── */}
      <Section title={tr("גיבוי ושחזור", "Backup & restore")} delay={300}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "כל ההגדרות, האישיויות והזיכרונות — קובץ JSON אחד להורדה ולשחזור.",
            "All settings, personas and memories — one JSON file to download and restore.",
          )}
        </p>
        <div className="grid grid-cols-2 gap-2">
          <button className="btn" onClick={() => void downloadBackup()}>
            {tr("⬇ הורד גיבוי", "⬇ Download backup")}
          </button>
          <button className="btn" onClick={() => restoreInput.current?.click()}>
            {tr("⬆ שחזר מגיבוי", "⬆ Restore from backup")}
          </button>
        </div>
        <input
          ref={restoreInput}
          type="file"
          accept=".json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void restoreBackup(f);
            e.target.value = ""; // allow re-picking the same file
          }}
        />
      </Section>
    </div>
  );
}
