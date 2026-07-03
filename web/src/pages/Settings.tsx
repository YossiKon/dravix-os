// Settings — robot connection, behaviour, head calibration, timers, AI. Entity wiring is
// AUTO-DISCOVERED by the core (discovery.py) — shown here read-only, nothing to fill in.
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { AppConfig, HAEntity, RobotConfig, ScreenTimers, Updates } from "../api";
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
  privacy_switch: { he: "מצב פרטיות (Privacy)", en: "Privacy mode" },
};

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
  const [updates, setUpdates] = useState<Updates | null>(null);

  useEffect(() => {
    apiGet<{ entities: HAEntity[] }>("/api/ha/entities?domains=switch")
      .then((r) => setSwitches(r.entities))
      .catch(() => undefined);
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
      .then((t) =>
        setTimers({
          saver: t.screensaver_min != null ? String(t.screensaver_min) : "",
          sleep: t.sleep_min != null ? String(t.sleep_min) : "",
        }),
      )
      .catch(() => undefined);
    apiGet<AppConfig>("/api/config").then(setApp).catch(toastErr);
    apiGet<Updates>("/api/updates").then(setUpdates).catch(() => undefined);
  }, []);

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
        {cfg.last_error && !cfg.online && (
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
            "כשהמתג דלוק — רק דברים מקומיים מאושרים: בינה בענן חסומה, החיבור לענן מתנתק, ותמונות רק מכתובות ברשת הביתית. כשהוא כבוי — הכל רגיל.",
            "When ON, only local things are allowed: cloud AI is blocked, the cloud bridge disconnects, and images load only from LAN addresses. When OFF, everything works normally.",
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

      {/* ── timers ── */}
      <Section title={tr("שומר מסך ושינה", "Screensaver & sleep")} delay={180}>
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
        <Toggle
          label={tr("תנועת ראש עצמאית (כשהוא משועמם)", "Autonomous head motion (when bored)")}
          on={Boolean(app?.store.idle_motion ?? true)}
          onChange={(v) => void setIdle(v)}
        />
      </Section>
    </div>
  );
}
