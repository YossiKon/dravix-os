// Climate — pick a climate entity and control it: target temp + hvac mode.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { ClimateState, HAEntity } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { Section, Spinner, toastErr } from "../ui";
import { useI18n } from "../i18n";

const MODES: Record<string, { he: string; en: string }> = {
  off: { he: "כבוי", en: "Off" },
  cool: { he: "קירור", en: "Cool" },
  heat: { he: "חימום", en: "Heat" },
  heat_cool: { he: "אוטומטי", en: "Auto" },
  auto: { he: "אוטומטי", en: "Auto" },
  dry: { he: "ייבוש", en: "Dry" },
  fan_only: { he: "מאוורר", en: "Fan" },
};

export function ClimatePage(props: { entities: HAEntity[] }) {
  const { tr, lang } = useI18n();
  const modeLabel = (m: string) => {
    const o = MODES[m];
    return o ? (lang === "en" ? o.en : o.he) : m;
  };

  const [entity, setEntity] = useState("");
  const [st, setSt] = useState<ClimateState | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedCfg, setLoadedCfg] = useState(false);

  useEffect(() => {
    apiGet<{ entity: string }>("/api/config/climate")
      .then((r) => {
        setEntity(r.entity);
        setLoadedCfg(true);
      })
      .catch(() => setLoadedCfg(true));
  }, []);

  const [failed, setFailed] = useState(false);
  // Request sequence — a slow poll that resolves after a newer request (or an
  // optimistic set) must not overwrite the fresher state.
  const seqRef = useRef(0);

  const refresh = useCallback(async (ent: string, background: boolean) => {
    if (!ent) {
      seqRef.current += 1;
      setSt(null);
      return;
    }
    const seq = ++seqRef.current;
    try {
      const next = await apiGet<ClimateState>(`/api/climate/state?entity_id=${encodeURIComponent(ent)}`);
      if (seq !== seqRef.current) return; // a newer request already answered
      setSt(next);
      setFailed(false);
    } catch (e) {
      if (seq !== seqRef.current) return;
      // Background polls stay quiet and keep the last known state; only a
      // user-initiated load (choosing an entity) surfaces the error.
      if (!background) {
        setSt(null);
        setFailed(true);
        toastErr(e);
      }
    }
  }, []);

  useEffect(() => {
    if (loadedCfg) void refresh(entity, false);
  }, [entity, loadedCfg, refresh]);

  // poll while visible so the current temperature stays fresh
  useEffect(() => {
    if (!entity) return;
    const t = setInterval(() => {
      if (document.visibilityState === "visible") void refresh(entity, true);
    }, 10000);
    return () => clearInterval(t);
  }, [entity, refresh]);

  async function choose(ent: string) {
    setEntity(ent);
    try {
      await apiSend("/api/config/climate", "PUT", { entity: ent });
    } catch (e) {
      toastErr(e);
    }
  }

  async function setTemp(next: number) {
    if (!entity) return;
    setBusy(true);
    try {
      await apiSend("/api/climate/set", "POST", { entity_id: entity, temperature: next });
      seqRef.current += 1; // invalidate any in-flight poll — it predates this set
      setSt((cur) => (cur ? { ...cur, temperature: next } : cur));
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(false);
    }
  }

  async function setMode(mode: string) {
    if (!entity) return;
    setBusy(true);
    try {
      await apiSend("/api/climate/set", "POST", { entity_id: entity, hvac_mode: mode });
      seqRef.current += 1; // invalidate any in-flight poll — it predates this set
      setSt((cur) => (cur ? { ...cur, state: mode } : cur));
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(false);
    }
  }

  const step = st?.target_temp_step ?? 0.5;
  const target = st?.temperature ?? null;

  return (
    <div className="space-y-4">
      <Section title={tr("איזה מזגן?", "Which AC?")}>
        <EntityPicker
          entities={props.entities}
          domains={["climate"]}
          value={entity}
          onChange={(id) => void choose(id)}
          placeholder={tr("בחר מזגן…", "Pick an AC…")}
        />
      </Section>

      {entity && st && (
        <Section title={tr("שליטה", "Control")} delay={70}>
          {/* current + target */}
          <div className="mb-4 flex items-center justify-around">
            <div className="text-center">
              <div className="text-sm text-mute">{tr("בבית עכשיו", "Current")}</div>
              <div className="font-display text-4xl">
                {st.current_temperature != null ? `${st.current_temperature}°` : "—"}
              </div>
            </div>
            <div className="text-center">
              <div className="text-sm text-mute">{tr("יעד", "Target")}</div>
              <div className="font-display text-4xl text-teal">{target != null ? `${target}°` : "—"}</div>
            </div>
          </div>
          {/* target +/- */}
          <div className="mb-4 grid grid-cols-2 gap-2">
            <button
              className="btn text-2xl"
              disabled={busy || target == null}
              onClick={() => target != null && void setTemp(st.min_temp != null ? Math.max(st.min_temp, target - step) : target - step)}
            >
              −
            </button>
            <button
              className="btn text-2xl"
              disabled={busy || target == null}
              onClick={() => target != null && void setTemp(st.max_temp != null ? Math.min(st.max_temp, target + step) : target + step)}
            >
              ＋
            </button>
          </div>
          {/* hvac modes */}
          <div className="flex flex-wrap gap-2">
            {(st.hvac_modes ?? []).map((m) => (
              <button
                key={m}
                className={`chip ${st.state === m ? "chip-on" : ""}`}
                disabled={busy}
                onClick={() => void setMode(m)}
              >
                {modeLabel(m)}
              </button>
            ))}
            {busy && <Spinner />}
          </div>
        </Section>
      )}

      {entity && !st && failed && (
        <div className="card animate-rise">
          <p className="mb-3 text-red">{tr("לא הצלחתי לקרוא את מצב המזגן.", "Couldn't read the AC state.")}</p>
          <button className="btn w-full" onClick={() => void refresh(entity, false)}>
            {tr("↻ נסה שוב", "↻ Retry")}
          </button>
        </div>
      )}
      {entity && !st && !failed && (
        <div className="card animate-rise text-mute">{tr("טוען את מצב המזגן…", "Loading AC state…")}</div>
      )}
      {!entity && loadedCfg && (
        <div className="card animate-rise text-mute">
          {tr(
            "בחר מזגן מהרשימה כדי לשלוט בו מכאן ומכרטיסי הרובוט.",
            "Pick an AC from the list to control it here and from the robot's cards.",
          )}
        </div>
      )}
    </div>
  );
}
