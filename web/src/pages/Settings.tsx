// הגדרות — חיבור לרובוט, מיפוי ישויות, התנהגות, כיול ראש, טיימרים, בינה.
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { AppConfig, HAEntity, RobotConfig, ScreenTimers } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { Section, Toggle, toast, toastErr } from "../ui";

// Hebrew labels for the robot's behaviour switches (matched by entity object_id suffix).
const BEHAVIOR_HE: [string, string][] = [
  ["greet_on_approach", "ברכה כשמישהו מתקרב"],
  ["sleep_when_dark", "שינה כשחשוך בחדר"],
  ["touch_reaction", "תגובה לליטוף"],
  ["speaking_leds", "לדים צהובים בשיחה"],
  ["random_blink", "מצמוץ טבעי"],
  ["idle_head_drift", "מבט/תנועה עצמאית"],
  ["tap_face_to_talk", "הקשה על הפרצוף = דיבור"],
  ["body_language", "שפת גוף (תנועות ראש)"],
  ["mood_leds", "לדים לפי רגש"],
];

// Hebrew labels for the entity roles (falls back to the server's English label).
const ROLE_HE: Record<string, string> = {
  face_select: "פרצוף (Face select)",
  head_yaw: "ראש — ימינה / שמאלה",
  head_pitch: "ראש — למעלה / למטה",
  media_player: "רמקול (להקראה)",
  tts_engine: "קול — מנוע דיבור",
  led_light: "פס הלדים",
  camera: "מצלמה",
  screensaver_number: "טיימר שומר מסך (דקות)",
  sleep_number: "טיימר שינה (דקות)",
  mode_select: "מצב (ער / שינה)",
  state_sensor: "מצב חי (State)",
  heard_sensor: "מה שמע (Last heard)",
  reply_sensor: "מה ענה (Last reply)",
  image_url_text: "הצגת תמונה (Show image URL)",
  privacy_switch: "מצב פרטיות (Privacy)",
};

const PROVIDER_HE: Record<string, string> = {
  ha_assist: "העוזר של Home Assistant",
  claude: "Claude",
  openai: "OpenAI",
  ollama: "Ollama (מקומי)",
};

export function SettingsPage(props: {
  config: RobotConfig | null;
  entities: HAEntity[];
  version: string;
  onConfigChanged: () => void;
}) {
  const cfg = props.config;
  const [entities, setEntities] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [timers, setTimers] = useState<{ saver: string; sleep: string }>({ saver: "", sleep: "" });
  const [app, setApp] = useState<AppConfig | null>(null);
  const [switches, setSwitches] = useState<HAEntity[]>([]);

  // the robot's entity prefix, derived from any mapped entity (e.g. select.dravix_mode → "dravix")
  const robotPrefix = useMemo(() => {
    for (const id of Object.values(cfg?.entities ?? {})) {
      const obj = id.split(".")[1];
      const p = obj?.split("_")[0];
      if (p) return p;
    }
    return "";
  }, [cfg]);

  useEffect(() => {
    apiGet<{ entities: HAEntity[] }>("/api/ha/entities?domains=switch")
      .then((r) => setSwitches(r.entities))
      .catch(() => undefined);
  }, []);

  const behaviors = useMemo(() => {
    if (!robotPrefix) return [];
    return BEHAVIOR_HE.flatMap(([suffix, he]) => {
      const ent = switches.find((s) => s.entity_id === `switch.${robotPrefix}_${suffix}`);
      return ent ? [{ ...ent, he }] : [];
    });
  }, [switches, robotPrefix]);

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
    if (cfg) setEntities(cfg.entities);
  }, [cfg]);

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
  }, []);

  async function saveEntities() {
    setSaving(true);
    try {
      const res = await apiSend<RobotConfig>("/api/robot/config", "PUT", { entities });
      if (res.error) toast(res.error, "err");
      else toast("החיבורים נשמרו והרובוט חובר מחדש");
      props.onConfigChanged();
    } catch (e) {
      toastErr(e);
    } finally {
      setSaving(false);
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
      toast("הכיול אופס");
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
      toast("הטיימרים עודכנו על הרובוט");
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

  if (!cfg) return <div className="card animate-rise text-mute">טוען הגדרות…</div>;

  return (
    <div className="space-y-4">
      {/* ── status ── */}
      <Section title="חיבור לרובוט">
        <div className="mb-3 flex items-center gap-2">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${cfg.online ? "bg-green" : "bg-red"}`} />
          <span>{cfg.online ? "מחובר" : "לא מחובר"}</span>
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
              {d === "ha" ? "Home Assistant" : d === "mock" ? "דמה (בדיקות)" : "MCP"}
            </button>
          ))}
        </div>
      </Section>

      {/* ── entity mapping ── */}
      <Section title="חיבור ישויות" delay={60}>
        <p className="mb-3 text-sm text-mute">איזה ישות Home Assistant ממלאת כל תפקיד אצל הרובוט. אפשר להשאיר ריק מה שאין.</p>
        <div className="space-y-3">
          {cfg.roles.map((role) => (
            <div key={role.key}>
              <label className="lbl">{ROLE_HE[role.key] ?? role.label}</label>
              <EntityPicker
                entities={props.entities}
                domains={role.domains}
                value={entities[role.key] ?? ""}
                onChange={(id) =>
                  setEntities((cur) => {
                    const next = { ...cur };
                    if (id) next[role.key] = id;
                    else delete next[role.key];
                    return next;
                  })
                }
              />
            </div>
          ))}
        </div>
        <button className="btn btn-primary mt-4 w-full" disabled={saving} onClick={() => void saveEntities()}>
          {saving ? "שומר…" : "💾 שמור חיבורים"}
        </button>
      </Section>

      {/* ── behaviour toggles (the robot's on-device switches) ── */}
      {behaviors.length > 0 && (
        <Section title="התנהגות הרובוט" delay={90}>
          <div className="space-y-2">
            {behaviors.map((b) => (
              <Toggle
                key={b.entity_id}
                label={b.he}
                on={b.state === "on"}
                onChange={(v) => void flipBehavior(b.entity_id, v)}
              />
            ))}
          </div>
        </Section>
      )}

      {/* ── head calibration ── */}
      <Section title="כיול ראש" delay={120}>
        <p className="mb-3 text-sm text-mute">
          אם הראש זז הפוך — הפעל היפוך לציר המתאים. ״קבע כ׳ישר׳״ נמצא בדף הבית, ליד הג׳ויסטיק.
        </p>
        <div className="space-y-2">
          <Toggle
            label="היפוך ימינה/שמאלה"
            on={Boolean(cfg.calibration.yaw?.invert)}
            onChange={(v) => void setInvert("yaw", v)}
          />
          <Toggle
            label="היפוך למעלה/למטה"
            on={Boolean(cfg.calibration.pitch?.invert)}
            onChange={(v) => void setInvert("pitch", v)}
          />
          <button className="btn btn-danger w-full" onClick={() => void resetCalibration()}>
            ↺ איפוס כיול
          </button>
        </div>
      </Section>

      {/* ── timers ── */}
      <Section title="שומר מסך ושינה" delay={180}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="lbl">שומר מסך אחרי (דק׳)</label>
            <input
              type="number"
              inputMode="numeric"
              className="inp text-center"
              value={timers.saver}
              onChange={(e) => setTimers((t) => ({ ...t, saver: e.target.value }))}
            />
          </div>
          <div>
            <label className="lbl">שינה אחרי (דק׳)</label>
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
          💾 עדכן טיימרים
        </button>
      </Section>

      {/* ── AI + behaviour ── */}
      <Section title="בינה והתנהגות" delay={240}>
        <label className="lbl">ספק הבינה המלאכותית</label>
        <div className="mb-3 flex flex-wrap gap-2">
          {(app?.providers ?? []).map((p) => (
            <button
              key={p}
              className={`chip ${app?.ai_provider === p ? "chip-on" : ""}`}
              onClick={() => void setProvider(p)}
            >
              {PROVIDER_HE[p] ?? p}
            </button>
          ))}
        </div>
        {app && !app.ai_available && (
          <p className="mb-3 text-xs text-amber">ספק הבינה לא זמין כרגע — בדוק את ההגדרות שלו.</p>
        )}
        <Toggle
          label="תנועת ראש עצמאית (כשהוא משועמם)"
          on={Boolean(app?.store.idle_motion ?? true)}
          onChange={(v) => void setIdle(v)}
        />
      </Section>
    </div>
  );
}
